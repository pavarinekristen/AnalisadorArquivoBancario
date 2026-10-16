"""Gera dados de teste anonimizados a partir dos arquivos reais (roda só na máquina que tem os dados reais).

    .venv\\Scripts\\python -m tests.ferramentas.anonimizar <pasta FINAL24> <Excel do relatório> <pasta de saída>

O que muda e o que fica:
- Nomes: cada palavra vira outra do mesmo tamanho, preservando prefixo (o que o banco abrevia/corta continua
  batendo: "F" de "FULANO" e "EMPRE" de "EMPRESARIAL"). Palavras ignoradas na busca (DE, DA, LTDA...) ficam.
- CPF/CNPJ, documento, agência/conta: dígitos trocados de forma consistente (mesmo número = mesmo número falso).
  Documento mantém o prefixo 10000. Zeros à esquerda ficam (o programa compara sem eles).
- Endereço (segmento B) é apagado.
- Valores, datas, códigos de ocorrência, nomes de arquivo e estrutura CNAB ficam iguais.
A chave é sorteada a cada execução e não é gravada: não dá para voltar ao dado original.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sys
import unicodedata
from pathlib import Path

import openpyxl

from conferencia.motor import _PALAVRAS_IGNORADAS

_CHAVE = secrets.token_bytes(32)
_LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _h(texto: str) -> int:
    return int.from_bytes(hmac.new(_CHAVE, texto.encode(), hashlib.sha256).digest()[:8], "big")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).upper()


# Rótulos que o programa procura no Excel/lista: ficam como estão para o leitor continuar reconhecendo.
_ROTULOS: frozenset[str] = frozenset(
    "SITUACAO TOTAL P REFER REFERENCIA NOME RCA CPF CNPJ NUMERO OP VALOR BANCO RETORNO SISTEMA DESCRICAO ERRO "
    "DATA PROGRAMADA SUCESSO PAGO COM BOLETO BANCARIO ELETRONICO MENSAGEM SOLICITACAOPAGAMENTO SUPPLIERNUM "
    "INCLUSAO EFETUADA".split())


def palavra(p: str) -> str:
    base = _sem_acento(p)
    if base in _PALAVRAS_IGNORADAS or base in _ROTULOS:
        return p
    if not base.isalpha() or len(base) != len(p):
        return base
    return "".join(_LETRAS[_h("L" + base[:i + 1]) % 26] for i in range(len(base)))


def texto(s: str) -> str:
    return re.sub(r"[^\W\d_]+", lambda m: palavra(m.group(0)), s)


def digitos(s: str) -> str:
    """Mesmo número (ignorando zeros à esquerda) = mesmo número falso; documento 10000... mantém o prefixo."""
    zeros = len(s) - len(s.lstrip("0"))
    sig = s[zeros:]
    if not sig:
        return s
    fixo = 5 if len(sig) == 15 and sig.startswith("10000") else 0
    resto = sig[fixo:]
    novo = "".join(str(_h(f"D{sig}{i}") % 10) for i in range(len(resto)))
    if not fixo:
        novo = str(1 + _h("P" + sig) % 9) + novo[1:]
    return "0" * zeros + sig[:fixo] + novo


def _campo_digitos(linha: list[str], a: int, b: int) -> None:
    trecho = "".join(linha[a - 1:b])
    linha[a - 1:b] = list(re.sub(r"\d+", lambda m: digitos(m.group(0)), trecho))


def _campo_texto(linha: list[str], a: int, b: int) -> None:
    linha[a - 1:b] = list(texto("".join(linha[a - 1:b])))


def linha_cnab(s: str) -> str:
    if len(s) < 240:
        return s
    l = list(s)
    tipo, seg = s[7], s[13]
    if tipo in "01":                       # header de arquivo / de lote: empresa pagadora
        _campo_digitos(l, 19, 72)
        _campo_texto(l, 73, 142)
        if tipo == "1":
            _campo_texto(l, 143, 222)      # endereço da empresa
            _campo_digitos(l, 143, 222)
    elif tipo == "3" and seg == "A":
        _campo_digitos(l, 24, 43)          # agência/conta do favorecido
        _campo_texto(l, 44, 73)            # nome
        _campo_digitos(l, 74, 93)          # documento (seu número)
        _campo_digitos(l, 135, 154)        # nosso número
        _campo_texto(l, 178, 217)          # informação livre
    elif tipo == "3" and seg == "B":
        _campo_digitos(l, 19, 32)          # CPF/CNPJ
        l[32:230] = list(" " * 198)        # endereço, CEP, e-mail: fora
    elif tipo == "3" and seg == "J" and s[17:19] == "52":
        _campo_digitos(l, 20, 230)
        _campo_texto(l, 20, 230)
    elif tipo == "3" and seg == "J":
        _campo_digitos(l, 20, 44)          # código de barras (menos o "52"/banco das posições 18-19)
        _campo_texto(l, 62, 91)            # nome do cedente
        _campo_digitos(l, 183, 202)        # documento
        _campo_digitos(l, 203, 222)        # nosso número
    return "".join(l)


def arquivo_cnab(origem: Path, destino: Path) -> None:
    bruto = origem.read_bytes()
    try:
        conteudo, cod = bruto.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        conteudo, cod = bruto.decode("latin-1"), "latin-1"
    fim = "\r\n" if "\r\n" in conteudo else "\n"
    linhas = [linha_cnab(l) for l in conteudo.splitlines()]
    destino.write_bytes((fim.join(linhas) + (fim if conteudo.endswith(("\n", "\r")) else "")).encode(cod))


def _celula(v: object) -> object:
    if isinstance(v, int) and not isinstance(v, bool) and len(str(v)) >= 10:   # CPF/CNPJ/documento como número
        return int(digitos(str(v)))
    if not isinstance(v, str):
        return v
    v = re.sub(r"\d{2,3}\.\d{3}\.\d{3}[/-][\d./-]+", lambda m: _formatado(m.group(0)), v)   # CPF/CNPJ formatado
    v = re.sub(r"(?<![\d.,])\d{6,}(?![\d.,])", lambda m: digitos(m.group(0)), v)              # documento, CPF/CNPJ
    return texto(v)


def _formatado(s: str) -> str:
    novos = iter(digitos(re.sub(r"\D", "", s)))
    return re.sub(r"\d", lambda _m: next(novos), s)


def excel(origem: Path, destino: Path) -> None:
    wb = openpyxl.load_workbook(origem, data_only=True)
    for ws in wb.worksheets:
        for linha in ws.iter_rows():
            for c in linha:
                if not isinstance(c, openpyxl.cell.cell.MergedCell):
                    c.value = _celula(c.value)
    wb.save(destino)


def main(pasta: str, planilha: str, saida: str) -> None:
    destino = Path(saida)
    (destino / "FINAL24").mkdir(parents=True, exist_ok=True)
    for arq in sorted(Path(pasta).iterdir()):
        if arq.is_file():
            arquivo_cnab(arq, destino / "FINAL24" / arq.name)
    excel(Path(planilha), destino / "relatorio_0510.xlsx")
    print(f"Gerado em {destino}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
