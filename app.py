"""Tela da conferência de pagamentos. Rodar com:  streamlit run app.py

Cada página fica em telas/; aqui só a moldura (marca, estilo, navegação) e o que roda uma vez ao abrir.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

import conferencia
from conferencia import config, historico, log

RAIZ = Path(__file__).parent

try:
    CFG = config.atual()
except config.ErroConfig as e:
    st.set_page_config(page_title="Conferência de Pagamentos", layout="wide")
    st.error(f"Configuração inválida: {e}", icon=":material/error:")
    st.stop()

st.set_page_config(page_title=CFG.marca.nome, page_icon=str(RAIZ / CFG.marca.icone), layout="wide")

from telas import codigos, conferir, estilo, historico as tela_historico, reprocessar, sobre, ucm  # noqa: E402


@st.cache_resource
def _ao_abrir() -> int:
    """Uma vez por processo: registra a abertura e apaga o histórico mais velho que a retenção (LGPD)."""
    log.obter().info("programa aberto, versão %s, operador %s", conferencia.__version__, historico.operador())
    try:
        apagados = historico.expurgar(datetime.now() - timedelta(days=CFG.retencao_dias))
    except Exception:
        log.obter().exception("falha ao expurgar histórico antigo")
        return 0
    if apagados:
        log.obter().info("expurgo LGPD: %d item(ns) com mais de %d dias", apagados, CFG.retencao_dias)
    return apagados


_ao_abrir()
estilo.aplicar()
st.logo(str(RAIZ / CFG.marca.logo), icon_image=str(RAIZ / CFG.marca.icone))
if CFG.e_exemplo:
    st.warning("Usando a configuração de exemplo: crie config/cliente.yaml com as pastas do cliente.",
               icon=":material/warning:")

pagina = st.navigation([
    st.Page(conferir.pagina, title="Conferir", icon=":material/fact_check:", default=True, url_path="conferir"),
    st.Page(reprocessar.pagina, title="Reprocessar", icon=":material/replay:", url_path="reprocessar"),
    st.Page(tela_historico.pagina, title="Histórico", icon=":material/history:", url_path="historico"),
    st.Page(codigos.pagina, title="Códigos de ocorrência", icon=":material/menu_book:", url_path="codigos"),
    st.Page(ucm.pagina, title="Arquivos UCM", icon=":material/cloud_download:", url_path="ucm"),
    st.Page(sobre.pagina, title="Sobre", icon=":material/info:", url_path="sobre"),
])
st.title(CFG.marca.nome)
st.sidebar.caption(f"Versão {conferencia.__version__}")

pagina.run()
