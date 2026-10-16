from __future__ import annotations

import io
import json
import re
import unicodedata
from datetime import date, datetime

import openpyxl

from . import config
from .modelos import Pagamento

Celula = str | int | float | date | datetime | None


def sem_acento(s: Celula) -> str:
    s = "" if s is None else str(s)
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).upper().strip()


def _digitos(s: Celula) -> str:
    return re.sub(r"\D", "", "" if s is None else str(s)).lstrip("0")


def _valor_br(v: Celula) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").strip()
    if "," in s or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):   # "1.500" é milhar, não 1,5
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _data(v: Celula) -> str:
    if isinstance(v, (datetime, date)):
        return v.strftime("%d%m%Y")
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", "" if v is None else str(v))
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else ""


_CFG = config.atual()
_PREFIXO_DOC, _TAMANHO_DOC = _CFG.documento.prefixo, _CFG.documento.tamanho


def ler_excel(conteudo: bytes) -> dict[str, list[Pagamento]]:
    marcas = _CFG.excel
    wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    listas: dict[str, list[Pagamento]] = {}
    for ws in wb.worksheets:
        linhas: list[list[Celula]] = [list(r) for r in ws.iter_rows(values_only=True)]
        texto = " ".join(sem_acento(c) for r in linhas[:40] for c in r if c is not None)
        if marcas.banco in " ".join(sem_acento(c) for r in linhas for c in r if c is not None):
            listas[f"{ws.title} (relatório do banco)"] = _aba_banco(linhas)
        elif all(m in texto for m in marcas.resumo):
            listas[f"{ws.title} (resumo)"] = _aba_resumo(linhas)
        elif all(m in texto for m in marcas.sistema):
            listas[f"{ws.title} (sistema - não pagos)"] = _aba_sistema(linhas)
    return {k: v for k, v in listas.items() if v}


def _cabecalho(linhas: list[list[Celula]], *obrigatorios: str) -> tuple[int, dict[str, int]]:
    for i, r in enumerate(linhas):
        nomes = [sem_acento(c) for c in r]
        if all(any(o in n for n in nomes) for o in obrigatorios):
            return i, {n: j for j, n in enumerate(nomes) if n}
    return -1, {}


def _col(cab: dict[str, int], *partes: str) -> int | None:
    for nome, j in cab.items():
        if all(p in nome for p in partes):
            return j
    return None


def _aba_banco(linhas: list[list[Celula]]) -> list[Pagamento]:
    pags: list[Pagamento] = []
    situacao, cab = "", None
    for r in linhas:
        cel = [c for c in r if c not in (None, "")]
        if not cel:
            continue
        primeiro = sem_acento(cel[0])
        if primeiro.startswith("SITUACAO:"):
            situacao = str(cel[0]).split(":", 1)[1].strip()
            continue
        if len(cel) >= 2 and re.fullmatch(r"\d+", str(cel[0]).strip()) and "/" in str(cel[1]):
            nome, _, doc = str(cel[1]).rpartition("/")
            cab = dict(referencia=str(cel[0]).strip(), favorecido=nome.strip(), cpf_cnpj=_digitos(doc),
                       metodo=next((str(c) for c in cel[2:] if not _data(c)), ""),
                       data=next((_data(c) for c in cel[2:] if _data(c)), ""))
            continue
        for j, c in enumerate(cel):
            m = re.fullmatch(rf"(\d{{{_TAMANHO_DOC}}})-(\d*)-?(.*)", str(c).strip())
            if m and cab:
                resto = cel[j + 1:]
                valor = next((_valor_br(x) for x in resto if _valor_br(x) is not None), None)
                retorno = next((str(x).strip() for x in resto if _valor_br(x) is None), "")
                pags.append(Pagamento(**cab, documento=m.group(1).lstrip("0"), op=m.group(2),
                                      valor=valor, retorno_sistema=retorno, situacao_banco=situacao))
                break
    return pags


def _aba_resumo(linhas: list[list[Celula]]) -> list[Pagamento]:
    i, cab = _cabecalho(linhas, *_CFG.excel.resumo)
    c_nome, c_doc, c_op = _col(cab, "NOME"), _col(cab, "CPF"), _col(cab, "OP")
    c_val = _col(cab, "VALOR", "BANCO")
    if c_val is None:   # "or" perderia a coluna 0
        c_val = _col(cab, "VALOR")
    c_sit = _col(cab, "RETORNO", "SISTEMA")
    c_ret = _col(cab, "RETORNO", "BANCO")
    pags = []
    for r in linhas[i + 1:]:
        if c_nome is None or not r[c_nome]:
            continue
        pags.append(Pagamento(
            favorecido=str(r[c_nome]).strip(),
            cpf_cnpj=_digitos(r[c_doc]) if c_doc is not None else "",
            op=str(r[c_op] or "") if c_op is not None else "",
            valor=_valor_br(r[c_val]) if c_val is not None else None,
            situacao_sistema=str(r[c_sit] or "") if c_sit is not None else "",
            retorno_sistema=str(r[c_ret] or "").strip() if c_ret is not None else "",
        ))
    return pags


def _aba_sistema(linhas: list[list[Celula]]) -> list[Pagamento]:
    i, cab = _cabecalho(linhas, *_CFG.excel.sistema)
    c_op, c_nome, c_val = _col(cab, "NUMERO OP"), _col(cab, "NOME"), _col(cab, "VALOR")
    c_sit, c_desc, c_err = _col(cab, "SITUACAO"), _col(cab, "DESCRICAO"), _col(cab, "ERRO")
    c_dt = _col(cab, "DATA PROGRAMADA")
    pags = []
    if c_op is None or c_nome is None:
        return []
    for r in linhas[i + 1:]:
        if not r[c_op] or not r[c_nome]:
            continue
        sit = str(r[c_sit] or "")
        if sem_acento(sit).startswith("SUCESSO"):
            continue
        retorno, cpf = str(r[c_desc] or "").strip(), ""
        erro = r[c_err] if c_err is not None else None
        if erro:
            try:
                j = json.loads(erro)[0]
                retorno = "; ".join(j.get("Mensagem") or []) or retorno
                cpf = _digitos((j.get("SolicitacaoPagamento") or {}).get("SupplierNum"))
            except (ValueError, TypeError, IndexError, KeyError, AttributeError):
                retorno = retorno or str(erro)[:200]
        pags.append(Pagamento(
            favorecido=str(r[c_nome]).strip(), cpf_cnpj=cpf, op=str(r[c_op]),
            valor=_valor_br(r[c_val]) if c_val is not None else None,
            data=_data(r[c_dt]) if c_dt is not None else "",
            situacao_sistema=sit, retorno_sistema=retorno,
        ))
    return pags


_FAV = re.compile(r"^(.+)/(\d{11,14})$")
_DOC = re.compile(rf"^({_PREFIXO_DOC}\d{{{_TAMANHO_DOC - len(_PREFIXO_DOC)}}})-?(\S*)")


def ler_texto_colado(texto: str) -> list[Pagamento]:
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    pags: list[Pagamento] = []
    atual: dict[str, str] | None = None
    situacao = ""
    for i, l in enumerate(linhas):
        if sem_acento(l).startswith("SITUACAO:"):
            situacao = l.split(":", 1)[1].strip()
            continue
        m = _FAV.match(l)
        if m:
            ref = linhas[i - 1] if i > 0 and re.fullmatch(r"\d+", linhas[i - 1]) else ""
            atual = dict(referencia=ref, favorecido=m.group(1).strip(), cpf_cnpj=m.group(2).lstrip("0"),
                         metodo="", data="")
            continue
        if atual is None:
            continue
        if not atual["metodo"] and sem_acento(l) in ("BOLETO BANCARIO", "ELETRONICO"):
            atual["metodo"] = l
        elif not atual["data"] and _data(l) and re.fullmatch(r"\d{2}/\d{2}/\d{4}", l):
            atual["data"] = _data(l)
        else:
            d = _DOC.match(l)
            if d:
                valor = None
                for prox in linhas[i + 1:i + 3]:
                    valor = _valor_br(prox)
                    if valor is not None:
                        break
                op = d.group(2).split("-")[0] if d.group(2) else ""
                pags.append(Pagamento(**atual, documento=d.group(1), valor=valor, op=op,
                                      situacao_banco=situacao))
    return pags


_VALOR_TXT = re.compile(r"(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}|(?:R\$\s*)?\d+,\d{2}")
_DATA_TXT = re.compile(r"\d{2}/\d{2}/\d{4}")
# Valor sem centavos ("1500", "1.500", "R$ 1500"), procurado só depois de tirar documento e CPF/CNPJ.
_VALOR_INTEIRO = re.compile(r"(?:R\$\s*)?(?<![\w.,])(?:\d{1,3}(?:\.\d{3})+|\d{3,9})(?![\w.,])")


def ler_nomes_digitados(texto: str) -> list[Pagamento]:
    pags: list[Pagamento] = []
    for linha in texto.splitlines():
        resto = linha.strip()
        if not resto:
            continue
        valor = data = doc = cpf = ""
        m = _VALOR_TXT.search(resto)
        if m:
            valor = m.group(0)
            resto = resto.replace(valor, " ")
        m = _DATA_TXT.search(resto)
        if m:
            data = _data(m.group(0))
            resto = resto.replace(m.group(0), " ")
        for m in re.finditer(r"\d[\d./-]{8,}\d", resto):
            dig = re.sub(r"\D", "", m.group(0))
            if len(dig) == _TAMANHO_DOC and dig.startswith(_PREFIXO_DOC):
                doc = dig
            elif len(dig) in (10, 11, 14):   # 10 = CPF que perdeu o zero da frente no Excel
                cpf = dig.lstrip("0")
            else:
                continue
            resto = resto.replace(m.group(0), " ")
        if not valor and (m := _VALOR_INTEIRO.search(resto)):
            valor = m.group(0)
            resto = resto.replace(valor, " ")
        nome = " ".join(re.sub(r"[;|/\t,]", " ", resto).split())
        if nome or doc or cpf:
            pags.append(Pagamento(favorecido=nome or doc or cpf, cpf_cnpj=cpf, documento=doc,
                                  valor=_valor_br(valor), data=data))
    return pags
