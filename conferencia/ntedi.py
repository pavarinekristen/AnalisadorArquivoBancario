from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from . import cnab240
from .modelos import ArquivoBanco, RegistroBanco

Tipo = Literal["retorno", "remessa"]

BASE_RETORNO = Path(r"\\Ntedi020\grpaftdata$\INBOXENV")
BASE_REMESSA = Path(r"\\Ntedi020\grpaftdata$\SENTBOX")
BASE_TRIBANCO = Path(r"\\ntedi020\AFTData\tranap\tribanco")

ROTULOS: dict[Tipo, str] = {"retorno": "Retorno", "remessa": "Remessa"}
LEITURAS_SIMULTANEAS = 8


@dataclass
class ResultadoNtedi:
    arquivos: list[ArquivoBanco] = field(default_factory=list)
    registros: list[RegistroBanco] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    total_ignorados_data: int = 0
    total_fora_do_padrao: int = 0
    pasta: Path | None = None


def caminho(tipo: Tipo, subpasta: str) -> Path:
    base = BASE_RETORNO if tipo == "retorno" else BASE_REMESSA
    nome = subpasta.strip().strip("\\/")
    return base / nome


def caminho_tribanco(subpasta: str = "") -> Path:
    nome = subpasta.strip().strip("\\/")
    return BASE_TRIBANCO / nome if nome else BASE_TRIBANCO


def listar_com_filtro(pasta: Path, de: date | None, ate: date | None) -> tuple[list[os.DirEntry[str]], int]:
    # os.scandir traz tipo e data de cada arquivo na própria listagem (no Windows, sem ir ao
    # servidor de novo por arquivo), o que pesa muito numa pasta de rede pela VPN.
    with os.scandir(pasta) as it:
        entradas = sorted((e for e in it if e.is_file()), key=lambda e: e.name)
    if not (de or ate):
        return entradas, 0
    achados: list[os.DirEntry[str]] = []
    for e in entradas:
        mtime = datetime.fromtimestamp(e.stat().st_mtime).date()
        if (de and mtime < de) or (ate and mtime > ate):
            continue
        achados.append(e)
    return achados, len(entradas) - len(achados)


def _ler_entrada(e: os.DirEntry[str]) -> tuple[ArquivoBanco, list[RegistroBanco]]:
    info = e.stat()
    return cnab240.ler_arquivo(Path(e.path), info.st_size, info.st_mtime_ns)


def ler_pasta(pasta: Path, rotulo: str, de: date | None = None, ate: date | None = None) -> ResultadoNtedi:
    r = ResultadoNtedi(pasta=pasta)
    try:
        if not pasta.is_dir():
            r.avisos.append(f"{rotulo}: pasta não encontrada ({pasta}).")
            return r
        entradas, r.total_ignorados_data = listar_com_filtro(pasta, de, ate)
    except OSError as e:
        r.avisos.append(f"{rotulo}: não foi possível acessar {pasta}. Confira se a VPN está ligada e se "
                        f"você já entrou com seu usuário e senha nessa pasta pelo Explorer. Detalhe: {e}")
        return r

    def ler(e: os.DirEntry[str]) -> tuple[ArquivoBanco, list[RegistroBanco]] | OSError:
        try:
            return _ler_entrada(e)
        except OSError as erro:
            return erro

    # Leitura em paralelo: o tempo é quase todo espera de rede. map mantém a ordem por nome.
    with ThreadPoolExecutor(max_workers=LEITURAS_SIMULTANEAS) as pool:
        for e, lido in zip(entradas, pool.map(ler, entradas)):
            if isinstance(lido, OSError):
                r.avisos.append(f"{rotulo}: falha ao ler {e.name}: {lido}")
                continue
            arq, regs = lido
            if arq.tipo == "OUTRO":
                r.total_fora_do_padrao += 1
                continue
            r.arquivos.append(arq)
            r.registros.extend(regs)
    return r


def ler_subpasta(tipo: Tipo, subpasta: str, de: date | None = None, ate: date | None = None) -> ResultadoNtedi:
    return ler_pasta(caminho(tipo, subpasta), ROTULOS[tipo], de, ate)


def ler_tribanco(subpasta: str = "", de: date | None = None, ate: date | None = None) -> ResultadoNtedi:
    return ler_pasta(caminho_tribanco(subpasta), "Tribanco", de, ate)
