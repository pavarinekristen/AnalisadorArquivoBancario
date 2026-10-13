from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from . import cnab240
from .modelos import ArquivoBanco, RegistroBanco

Tipo = Literal["retorno", "remessa"]

BASE_RETORNO = Path(r"\\Ntedi020\grpaftdata$\INBOXENV")
BASE_REMESSA = Path(r"\\Ntedi020\grpaftdata$\SENTBOX")

ROTULOS: dict[Tipo, str] = {"retorno": "Retorno", "remessa": "Remessa"}


@dataclass
class ResultadoNtedi:
    arquivos: list[ArquivoBanco] = field(default_factory=list)
    registros: list[RegistroBanco] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    total_ignorados_data: int = 0


def caminho(tipo: Tipo, subpasta: str) -> Path:
    base = BASE_RETORNO if tipo == "retorno" else BASE_REMESSA
    nome = subpasta.strip().strip("\\/")
    return base / nome


def _listar_com_filtro(pasta: Path, de: date | None, ate: date | None) -> tuple[list[Path], int]:
    achados: list[Path] = []
    descartados = 0
    for p in sorted(pasta.iterdir()):
        if not p.is_file():
            continue
        if de or ate:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).date()
            if (de and mtime < de) or (ate and mtime > ate):
                descartados += 1
                continue
        achados.append(p)
    return achados, descartados


def ler_subpasta(tipo: Tipo, subpasta: str, de: date | None = None, ate: date | None = None) -> ResultadoNtedi:
    rotulo = ROTULOS[tipo]
    pasta = caminho(tipo, subpasta)
    r = ResultadoNtedi()
    try:
        if not pasta.is_dir():
            r.avisos.append(f"{rotulo}: pasta não encontrada ({pasta}).")
            return r
        arqs_path, r.total_ignorados_data = _listar_com_filtro(pasta, de, ate)
    except OSError as e:
        r.avisos.append(f"{rotulo}: não foi possível acessar {pasta} (rede/VPN?). Detalhe: {e}")
        return r
    for p in arqs_path:
        try:
            arq, regs = cnab240.ler_bytes(p.name, p.read_bytes())
        except OSError as e:
            r.avisos.append(f"{rotulo}: falha ao ler {p.name}: {e}")
            continue
        if arq.tipo == "OUTRO":
            continue
        r.arquivos.append(arq)
        r.registros.extend(regs)
    return r
