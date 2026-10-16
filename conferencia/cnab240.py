from __future__ import annotations

import os
import threading
from collections import OrderedDict
from datetime import date
from pathlib import Path

from . import bancos
from .bancos.santander import TIPOS_COM_LOTE as _TIPOS_COM_LOTE
from .bancos.tribanco import CODIGO as CODIGO_TRIBANCO
from .modelos import ArquivoBanco, RegistroBanco

_TIPOS_COM_CONTEUDO: frozenset[str] = frozenset({"MOV", "CRI", "RET"})
# Extensões que nunca são arquivo do banco: nem abre para olhar o header.
_EXTENSOES_FORA: frozenset[str] = frozenset(
    {".pdf", ".xls", ".xlsx", ".xlsm", ".csv", ".doc", ".docx", ".zip", ".png", ".jpg", ".jpeg", ".msg", ".eml"})
_TAMANHO_HEADER = 240

Lido = tuple[ArquivoBanco, list[RegistroBanco]]
# Arquivos já lidos, por (caminho, tamanho, mtime): a pasta de rede é lenta e o mesmo arquivo
# não muda depois de gerado. Mudou tamanho ou data, a chave muda e ele é lido de novo.
_CACHE: OrderedDict[tuple[str, int, int], Lido] = OrderedDict()
_LIMITE_CACHE = 5000
_TRAVA_CACHE = threading.Lock()


def identificar(nome: str) -> ArquivoBanco:
    """Cada perfil de banco (conferencia/bancos) tenta reconhecer o arquivo pelo nome."""
    for perfil in bancos.REGISTRO.values():
        arq = perfil.identificar(nome)
        if arq is not None:
            return arq
    return ArquivoBanco(Path(nome).name, "OUTRO", None, None, None)


def _perfil_do_header(header: str) -> bancos.PerfilBanco | None:
    return next((p for p in bancos.REGISTRO.values() if p.reconhece_header(header)), None)


def _sem_zeros(s: str) -> str:
    return s.strip().lstrip("0")


def _valor(s: str) -> float:
    s = s.strip()
    return int(s) / 100 if s.isdigit() else 0.0


def ocorrencias(s: str) -> list[str]:
    s = s.strip()
    return [par for i in range(0, len(s), 2) if (par := s[i:i + 2]).strip()]


def _campo(linha: str, a: int, b: int) -> str:
    return linha[a - 1:b]


def decodificar(conteudo: bytes) -> str:
    # As posições do CNAB contam caracteres: arquivo em UTF-8 lido como latin-1 desloca as colunas depois
    # de um acento (valor 54,00 virava 5,40). UTF-8 inválido cai para latin-1, o padrão dos bancos.
    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return conteudo.decode("latin-1")


def _linhas(texto: str) -> list[str]:
    linhas = texto.splitlines()
    # Alguns envios chegam sem quebra de linha: os registros de 240 vêm grudados num bloco só.
    if len(linhas) == 1 and len(linhas[0]) > 240 and len(linhas[0]) % 240 == 0:
        return [linhas[0][i:i + 240] for i in range(0, len(linhas[0]), 240)]
    return linhas


def ler_texto(texto: str, arquivo: ArquivoBanco) -> list[RegistroBanco]:
    regs: list[RegistroBanco] = []
    atual: RegistroBanco | None = None
    tem_header, fora_do_tamanho = False, 0
    for linha_bruta in _linhas(texto):
        if linha_bruta and len(linha_bruta) != 240:
            fora_do_tamanho += 1
        linha = linha_bruta.ljust(240) if len(linha_bruta) < 240 else linha_bruta
        if linha[7] == "0":
            tem_header = True
            arquivo.pagador = linha[72:102].strip()
            arquivo.pagador_cnpj = _sem_zeros(linha[18:32])
        if linha[7] != "3":
            atual = None
            continue
        seg = linha[13]
        c = lambda a, b, _linha=linha: _campo(_linha, a, b)
        if seg == "A":
            atual = RegistroBanco(
                arquivo=arquivo, segmento="A",
                nome=c(44, 73).strip(), cpf_cnpj="",
                documento=_sem_zeros(c(74, 93)), data=c(94, 101),
                valor=_valor(c(120, 134)), ocorrencias=ocorrencias(c(231, 240)),
            )
            regs.append(atual)
        elif seg == "B" and atual is not None and atual.segmento == "A":
            atual.cpf_cnpj = _sem_zeros(c(19, 32))
        elif seg == "J" and c(18, 19) == "52":
            if atual is not None and atual.segmento == "J":
                atual.cpf_cnpj = _sem_zeros(c(77, 91))
        elif seg == "J":
            atual = RegistroBanco(
                arquivo=arquivo, segmento="J",
                nome=c(62, 91).strip(), cpf_cnpj="",
                documento=_sem_zeros(c(183, 202)), data=c(145, 152),
                valor=_valor(c(153, 167)) or _valor(c(100, 114)),
                ocorrencias=ocorrencias(c(231, 240)),
            )
            regs.append(atual)
        else:
            atual = atual if seg in ("B", "C", "Z") else None
    if fora_do_tamanho:
        arquivo.avisos.append(f"{arquivo.nome}: {fora_do_tamanho} linha(s) fora do tamanho 240 do CNAB; "
                              "valores podem ter sido lidos errado.")
    if tem_header and not regs and arquivo.tipo in _TIPOS_COM_CONTEUDO:
        arquivo.avisos.append(f"{arquivo.nome}: arquivo do banco sem nenhum pagamento lido.")
    return regs


def _ler_pelo_header(arq: ArquivoBanco, conteudo: bytes, mtime_ns: int | None) -> tuple[ArquivoBanco, list[RegistroBanco]]:
    # O header é quem decide (ex.: banco 634 = Tribanco): aceita retorno com nome fora do padrão e
    # descarta .dat de nome parecido que não seja do banco.
    perfil = _perfil_do_header(conteudo[:240].decode("latin-1"))
    if perfil is None:
        return ArquivoBanco(arq.nome, "OUTRO", None, None, None), []
    arq.tipo, arq.banco = "RET", perfil.chave
    texto = decodificar(conteudo)
    perfil.preparar(arq, _linhas(texto)[0], mtime_ns)
    return arq, ler_texto(texto, arq)


def ler_bytes(nome: str, conteudo: bytes, mtime_ns: int | None = None) -> tuple[ArquivoBanco, list[RegistroBanco]]:
    arq = identificar(nome)
    if arq.tipo == "OUTRO" or arq.tipo == "RET":
        return _ler_pelo_header(arq, conteudo, mtime_ns)
    if arq.tipo not in _TIPOS_COM_CONTEUDO:
        return arq, []
    return arq, ler_texto(decodificar(conteudo), arq)


def _ler_do_disco(caminho: Path, mtime_ns: int) -> Lido:
    """Baixa só o necessário: REL/Retorno_ são reconhecidos pelo nome e não são abertos; nome
    desconhecido só tem o header lido, e o resto só se for retorno do Tribanco."""
    arq = identificar(caminho.name)
    if arq.tipo in ("REL", "RETORNO"):
        return arq, []
    if arq.tipo == "OUTRO":
        if caminho.suffix.lower() in _EXTENSOES_FORA:
            return arq, []
        with open(caminho, "rb") as f:
            header = f.read(_TAMANHO_HEADER)
            if _perfil_do_header(header.decode("latin-1")) is None:
                return arq, []
            return ler_bytes(caminho.name, header + f.read(), mtime_ns)
    return ler_bytes(caminho.name, caminho.read_bytes(), mtime_ns)


def ler_arquivo(caminho: Path, tamanho: int, mtime_ns: int) -> Lido:
    chave = (str(caminho), tamanho, mtime_ns)
    with _TRAVA_CACHE:
        if chave in _CACHE:
            _CACHE.move_to_end(chave)
            return _CACHE[chave]
    lido = _ler_do_disco(caminho, mtime_ns)
    with _TRAVA_CACHE:
        _CACHE[chave] = lido
        while len(_CACHE) > _LIMITE_CACHE:
            _CACHE.popitem(last=False)
    return lido


def ler_pasta(pasta: str | Path) -> tuple[list[ArquivoBanco], list[RegistroBanco]]:
    arquivos: list[ArquivoBanco] = []
    regs: list[RegistroBanco] = []
    with os.scandir(pasta) as it:
        entradas = sorted((e for e in it if e.is_file()), key=lambda e: e.name)
    for e in entradas:
        info = e.stat()
        arq, r = ler_arquivo(Path(e.path), info.st_size, info.st_mtime_ns)
        if arq.tipo == "OUTRO":
            continue
        arquivos.append(arq)
        regs.extend(r)
    return arquivos, regs


def lotes_faltando(arquivos: list[ArquivoBanco]) -> dict[str, list[int]]:
    grupos: dict[tuple[str | None, date], set[int]] = {}
    for a in arquivos:
        if a.lote is not None and a.data is not None and a.tipo in _TIPOS_COM_LOTE:
            grupos.setdefault((a.empresa, a.data), set()).add(a.lote)
    faltando: dict[str, list[int]] = {}
    for (emp, dt), lotes in sorted(grupos.items()):
        falta = sorted(set(range(1, max(lotes) + 1)) - lotes)
        if falta:
            faltando[f"{emp} {dt:%d/%m/%Y}"] = falta
    return faltando
