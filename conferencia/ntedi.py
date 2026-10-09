"""Leitura das pastas de rede fixas do NTEDI (INBOXENV = retorno, SENTBOX = remessa)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import cnab240
from .modelos import ArquivoBanco, RegistroBanco

BASE_RETORNO = Path(r"\\Ntedi020\grpaftdata$\INBOXENV")
BASE_REMESSA = Path(r"\\Ntedi020\grpaftdata$\SENTBOX")

ROTULOS = {"retorno": "Retorno", "remessa": "Remessa"}


@dataclass
class ResultadoNtedi:
    arquivos: list[ArquivoBanco] = field(default_factory=list)
    registros: list[RegistroBanco] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    total_ignorados_data: int = 0


def caminho(tipo: str, subpasta: str) -> Path:
    """Monta o caminho completo (base fixa do `tipo` + subpasta digitada pela pessoa)."""
    base = BASE_RETORNO if tipo == "retorno" else BASE_REMESSA
    nome = subpasta.strip().strip("\\/")
    return base / nome


def _listar_com_filtro(pasta: Path, de: date | None, ate: date | None) -> tuple[list[Path], int]:
    """Arquivos de `pasta` cujo mtime cai em [de, ate]. Devolve (achados, nº descartados por data)."""
    achados, descartados = [], 0
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


def ler_subpasta(tipo: str, subpasta: str, de: date | None = None, ate: date | None = None) -> ResultadoNtedi:
    """Lê a subpasta dentro da pasta padrão do `tipo` escolhido ('retorno' ou 'remessa')."""
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
