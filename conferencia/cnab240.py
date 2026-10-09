"""Leitor dos arquivos CNAB 240 do Santander (MOV, CRI) e identificação dos demais."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .modelos import ArquivoBanco, RegistroBanco

_NOME_FORN = re.compile(r"FORN_(?P<emp>[A-Z0-9]+)_(?P<lote>\d+)_(?P<data>\d{6})P_(?P<tipo>[A-Z]+)", re.I)


def identificar(nome: str) -> ArquivoBanco:
    """Descobre tipo, data e lote pelo nome do arquivo."""
    base = Path(nome).name
    m = _NOME_FORN.search(base)
    if m:
        d = m.group("data")
        try:
            dt = date(2000 + int(d[4:6]), int(d[2:4]), int(d[0:2]))
        except ValueError:
            dt = None
        tipo = m.group("tipo").upper()
        if tipo not in ("MOV", "CRI", "REL"):
            tipo = "OUTRO"
        return ArquivoBanco(base, tipo, dt, int(m.group("lote")), m.group("emp").upper())
    if base.lower().startswith("retorno_"):
        return ArquivoBanco(base, "RETORNO", None, None, None)
    return ArquivoBanco(base, "OUTRO", None, None, None)


def _sem_zeros(s: str) -> str:
    return s.strip().lstrip("0")


def _valor(s: str) -> float:
    s = s.strip()
    return int(s) / 100 if s.isdigit() else 0.0


def _ocorrencias(s: str) -> list[str]:
    s = s.strip()
    return [s[i:i + 2] for i in range(0, len(s), 2) if s[i:i + 2].strip()]


def ler_texto(texto: str, arquivo: ArquivoBanco) -> list[RegistroBanco]:
    """Lê o conteúdo de um MOV/CRI e devolve os pagamentos (segmentos A e J)."""
    linhas = texto.splitlines()
    regs: list[RegistroBanco] = []
    atual: RegistroBanco | None = None
    for linha in linhas:
        if len(linha) < 240:
            linha = linha.ljust(240)
        if linha[7] != "3":          # só registros de detalhe
            atual = None
            continue
        seg = linha[13]
        c = lambda a, b: linha[a - 1:b]  # posições 1-based, como no layout
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
            atual = None if seg not in ("B", "C", "Z") else atual
    return regs


def ler_bytes(nome: str, conteudo: bytes) -> tuple[ArquivoBanco, list[RegistroBanco]]:
    arq = identificar(nome)
    if arq.tipo not in ("MOV", "CRI"):
        return arq, []
    return arq, ler_texto(conteudo.decode("latin-1"), arq)


def ler_pasta(pasta: str | Path) -> tuple[list[ArquivoBanco], list[RegistroBanco]]:
    arquivos, regs = [], []
    for p in sorted(Path(pasta).iterdir()):
        if not p.is_file():
            continue
        arq, r = ler_bytes(p.name, p.read_bytes())
        if arq.tipo == "OUTRO":
            continue
        arquivos.append(arq)
        regs.extend(r)
    return arquivos, regs


def lotes_faltando(arquivos: list[ArquivoBanco]) -> dict[str, list[int]]:
    """Por empresa+data, lotes que faltam na sequência 1..maior lote."""
    grupos: dict[tuple, set[int]] = {}
    for a in arquivos:
        if a.lote is not None and a.data is not None and a.tipo in ("MOV", "CRI", "REL"):
            grupos.setdefault((a.empresa, a.data), set()).add(a.lote)
    faltando = {}
    for (emp, dt), lotes in sorted(grupos.items()):
        falta = sorted(set(range(1, max(lotes) + 1)) - lotes)
        if falta:
            faltando[f"{emp} {dt:%d/%m/%Y}"] = falta
    return faltando
