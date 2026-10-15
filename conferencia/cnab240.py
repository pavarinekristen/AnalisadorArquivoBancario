from __future__ import annotations

import os
import re
import threading
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

from .modelos import ArquivoBanco, RegistroBanco, TipoArquivo

_NOME_FORN = re.compile(r"FORN_(?P<emp>[A-Z0-9]+)_(?P<lote>\d+)_(?P<data>\d{6})P_(?P<tipo>[A-Z]+)", re.I)
# Retorno do Tribanco: A + convênio (7 dígitos) + data/sequencial em formatos variados, sempre .dat
# (A35708191410260001.dat, A3570819_17062026001.dat, A3570801001.dat). A data certa vem do header.
_NOME_TRIBANCO = re.compile(r"^A(?P<conv>\d{7})[\d_]*(?: \(\d+\))?\.dat$", re.I)
CODIGO_TRIBANCO = "634"
_TIPOS_COM_LOTE: frozenset[str] = frozenset({"MOV", "CRI", "REL"})
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
    base = Path(nome).name
    m = _NOME_FORN.search(base)
    if m:
        d = m.group("data")
        try:
            dt = date(2000 + int(d[4:6]), int(d[2:4]), int(d[0:2]))
        except ValueError:
            dt = None
        tipo = m.group("tipo").upper()
        tipo_final: TipoArquivo = tipo if tipo in _TIPOS_COM_LOTE else "OUTRO"
        return ArquivoBanco(base, tipo_final, dt, int(m.group("lote")), m.group("emp").upper())
    m = _NOME_TRIBANCO.match(base)
    if m:
        return ArquivoBanco(base, "RET", None, None, m.group("conv"), banco="tribanco")
    if base.lower().startswith("retorno_"):
        return ArquivoBanco(base, "RETORNO", None, None, None)
    return ArquivoBanco(base, "OUTRO", None, None, None)


def _e_header_tribanco(linha: str) -> bool:
    return linha[:3] == CODIGO_TRIBANCO and linha[7:8] == "0"


def _aplicar_header_tribanco(arq: ArquivoBanco, header: str) -> None:
    """Header de arquivo CNAB 240: 144-151 data de geração (DDMMAAAA), 152-157 hora (HHMMSS)."""
    try:
        arq.data = datetime.strptime(_campo(header, 144, 151), "%d%m%Y").date()
    except ValueError:
        pass
    hora = _campo(header, 152, 157)
    arq.hora = hora if hora.isdigit() else ""


def _sem_zeros(s: str) -> str:
    return s.strip().lstrip("0")


def _valor(s: str) -> float:
    s = s.strip()
    return int(s) / 100 if s.isdigit() else 0.0


def _ocorrencias(s: str) -> list[str]:
    s = s.strip()
    return [par for i in range(0, len(s), 2) if (par := s[i:i + 2]).strip()]


def _campo(linha: str, a: int, b: int) -> str:
    return linha[a - 1:b]


def ler_texto(texto: str, arquivo: ArquivoBanco) -> list[RegistroBanco]:
    regs: list[RegistroBanco] = []
    atual: RegistroBanco | None = None
    for linha_bruta in texto.splitlines():
        linha = linha_bruta.ljust(240) if len(linha_bruta) < 240 else linha_bruta
        if linha[7] == "0":
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
                valor=_valor(c(120, 134)), ocorrencias=_ocorrencias(c(231, 240)),
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
                ocorrencias=_ocorrencias(c(231, 240)),
            )
            regs.append(atual)
        else:
            atual = atual if seg in ("B", "C", "Z") else None
    return regs


def _ler_tribanco(arq: ArquivoBanco, conteudo: bytes) -> tuple[ArquivoBanco, list[RegistroBanco]]:
    # O header (banco 634) é quem decide: aceita retorno com nome fora do padrão e descarta
    # .dat de nome parecido que não seja do Tribanco.
    header = conteudo[:240].decode("latin-1")
    if not _e_header_tribanco(header):
        return ArquivoBanco(arq.nome, "OUTRO", None, None, None), []
    arq.tipo, arq.banco = "RET", "tribanco"
    _aplicar_header_tribanco(arq, header)
    return arq, ler_texto(conteudo.decode("latin-1"), arq)


def ler_bytes(nome: str, conteudo: bytes) -> tuple[ArquivoBanco, list[RegistroBanco]]:
    arq = identificar(nome)
    if arq.tipo == "OUTRO" or arq.banco == "tribanco":
        return _ler_tribanco(arq, conteudo)
    if arq.tipo not in _TIPOS_COM_CONTEUDO:
        return arq, []
    return arq, ler_texto(conteudo.decode("latin-1"), arq)


def _ler_do_disco(caminho: Path) -> Lido:
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
            if not _e_header_tribanco(header.decode("latin-1")):
                return arq, []
            return ler_bytes(caminho.name, header + f.read())
    return ler_bytes(caminho.name, caminho.read_bytes())


def ler_arquivo(caminho: Path, tamanho: int, mtime_ns: int) -> Lido:
    chave = (str(caminho), tamanho, mtime_ns)
    with _TRAVA_CACHE:
        if chave in _CACHE:
            _CACHE.move_to_end(chave)
            return _CACHE[chave]
    lido = _ler_do_disco(caminho)
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
