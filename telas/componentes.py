"""Peças de tela usadas em mais de uma página."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import streamlit as st

from conferencia import ntedi

RAIZ = "(pasta principal)"


@st.cache_data(ttl=300, show_spinner="Lendo subpastas da rede...")
def _subpastas(bases: tuple[Path, ...]) -> list[str]:
    # A pasta de rede é lenta e as subpastas quase nunca mudam: lista uma vez a cada 5 minutos.
    return ntedi.subpastas(*bases)


def escolher_subpasta(rotulo: str, bases: tuple[Path, ...], key: str, opcional: bool = False,
                      on_change: Callable[[], None] | None = None) -> str:
    """Lista de subpastas (GE202255...) com busca ao digitar; aceita digitar uma que não esteja na lista.
    opcional=True põe "(pasta principal)" no topo, que devolve "" (a própria base, ex.: Tribanco)."""
    opcoes = ([RAIZ] if opcional else []) + _subpastas(bases)
    escolha = st.selectbox(rotulo, opcoes, index=0 if opcional else None, key=key, on_change=on_change,
                           placeholder="Escolha ou digite a subpasta (ex.: GE202255)", accept_new_options=True)
    if not escolha or escolha == RAIZ:
        return ""
    return escolha.strip().strip("\\/")
