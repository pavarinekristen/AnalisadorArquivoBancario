"""Página Histórico: conferências, reincidentes e arquivos movidos."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import streamlit as st

from conferencia import config, historico, log
from conferencia.log import mascarar_valor


def _apagar_antigos() -> None:
    with st.expander("Apagar histórico antigo (LGPD)"):
        st.caption(f"Ao abrir o programa, conferências com mais de {config.atual().retencao_dias} dias já são "
                   "apagadas sozinhas (retencao_dias em config/cliente.yaml).")
        limite = st.date_input("Apagar tudo anterior a", value=date.today() - timedelta(days=90), key="hist_limite")
        confirmou = st.checkbox(f"Confirmo apagar o histórico anterior a {limite:%d/%m/%Y} (não dá para desfazer)",
                                key="hist_confirma")
        if st.button("Apagar", disabled=not confirmou, icon=":material/delete:"):
            n = historico.expurgar(datetime.combine(limite, datetime.min.time()))
            log.obter().info("operador apagou o histórico anterior a %s (%d itens)", limite, n)
            st.success(f"{n} item(ns) apagado(s).", icon=":material/check_circle:")


def pagina() -> None:
    st.subheader("Histórico de conferências")
    busca = st.text_input("Buscar por nome, CPF/CNPJ ou documento")
    completos = st.toggle("Mostrar CPF/CNPJ completos", key="hist_completos")
    achados = historico.buscar(busca)
    if len(achados) >= historico.LIMITE_BUSCA:
        st.caption(f"Mostrando os {historico.LIMITE_BUSCA} mais recentes. Refine a busca para ver outros.")
    if not completos and not achados.empty:
        achados["cpf_cnpj"] = achados["cpf_cnpj"].fillna("").map(mascarar_valor)
    st.dataframe(achados, width="stretch", hide_index=True)
    st.subheader("Favorecidos com mais de uma devolução")
    rein = historico.reincidentes()
    if rein.empty:
        st.caption("Nenhum por enquanto.")
    else:
        if not completos:
            rein["chave"] = rein["chave"].fillna("").map(lambda c: mascarar_valor(c) if c.isdigit() else c)
        st.dataframe(rein, width="stretch", hide_index=True)
    st.subheader("Arquivos movidos para reprocessar")
    mov = historico.movimentacoes()
    if mov.empty:
        st.caption("Nenhum por enquanto.")
    else:
        st.dataframe(mov, width="stretch", hide_index=True)
    _apagar_antigos()
