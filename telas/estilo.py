"""Visual da tela (cores TechOne) e pequenos componentes de layout."""
from __future__ import annotations

import streamlit as st

_ESTILO = """
<style>
[data-testid="stSidebar"] {
    background-color: #050D32;
}
[data-testid="stSidebar"] * {
    color: #E7ECF7 !important;
}
[data-testid="stSidebarNav"] a[aria-selected="true"] {
    background: rgba(0,89,169,.35);
    border-left: 3px solid #2AADD7;
    border-radius: 6px;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(42,173,215,.12);
    border-radius: 6px;
}
[data-testid="stLogo"] {
    padding: 0.75rem 0.5rem 1rem 0.5rem;
}
.stButton>button[kind="primary"], .stDownloadButton>button {
    background: linear-gradient(90deg, #0059A9, #0B6FA0);
    border: none;
    font-weight: 600;
}
.stButton>button[kind="primary"]:hover, .stDownloadButton>button:hover {
    filter: brightness(1.08);
}
div[role="radiogroup"] {
    gap: 0.4rem;
}
div[role="radiogroup"] label {
    background: #F2F5FA;
    border: 1px solid #E2E8F4;
    border-radius: 999px;
    padding: 0.25rem 0.9rem;
}
.passo {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin: 0.3rem 0 0.7rem 0;
}
.passo-numero {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    min-width: 28px;
    border-radius: 50%;
    background: linear-gradient(135deg, #0059A9, #0B6FA0);
    color: #fff;
    font-weight: 700;
    font-size: 0.9rem;
}
.passo-titulo {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0B1E3A;
}
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 0.75rem;
    margin-bottom: 0.5rem;
}
.kpi-card {
    background: #F2F5FA;
    border-left: 4px solid;
    border-radius: 10px;
    padding: 0.9rem 1rem;
    box-shadow: 0 1px 2px rgba(11,30,58,0.06);
}
.kpi-valor {
    font-size: 1.6rem;
    font-weight: 700;
    color: #0B1E3A;
    line-height: 1.1;
}
.kpi-rotulo {
    font-size: 0.85rem;
    color: #44546B;
    margin-top: 2px;
}
.kpi-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 6px;
}
.banco-ativo {
    border-left: 5px solid;
    border-radius: 10px;
    padding: 0.7rem 1rem;
    margin: 0.2rem 0 1rem 0;
    color: #0B1E3A;
}
.banco-santander {
    background: #FDECEC;
    border-left-color: #CC0000;
}
.banco-tribanco {
    background: #E8F1FB;
    border-left-color: #0059A9;
}
.banco-nome {
    font-size: 1.15rem;
    font-weight: 700;
}
.banco-detalhe {
    font-size: 0.85rem;
    color: #44546B;
}
</style>
"""


def aplicar() -> None:
    st.markdown(_ESTILO, unsafe_allow_html=True)


def passo(numero: int, titulo: str) -> None:
    st.markdown(f'<div class="passo"><span class="passo-numero">{numero}</span>'
                f'<span class="passo-titulo">{titulo}</span></div>', unsafe_allow_html=True)
