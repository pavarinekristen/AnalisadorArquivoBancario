"""Página Reprocessar: devolve arquivos do INBOXENV para o INBOX (mesma subpasta)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from conferencia import config, historico, log, ntedi, reprocessar
from conferencia.modelos import BANCOS, Banco
from telas.componentes import escolher_subpasta


def _limpar() -> None:
    st.session_state.pop("reprocesso_simulado", None)


def _mostrar_resultado_mover(r: reprocessar.ResultadoMover, verbo: str) -> None:
    if r.movidos:
        st.success(f"{len(r.movidos)} arquivo(s) {verbo}: {', '.join(r.movidos)}", icon=":material/check_circle:")
    for nome in r.copiados_sem_apagar:
        st.error(f"{nome}: copiado para o INBOX, mas não consegui apagar da origem. Ele VAI ser processado; "
                 "apague a cópia da origem à mão para não mover de novo.", icon=":material/error:")
    for nome, motivo in r.pulados:
        st.warning(f"{nome}: {motivo}", icon=":material/warning:")


def _avisar_feito() -> None:
    if feito := st.session_state.pop("reprocesso_feito", None):
        _mostrar_resultado_mover(feito, "movidos para o INBOX")


def pagina() -> None:
    st.subheader("Reprocessar arquivos")
    st.caption("Move arquivos do INBOXENV de volta para o INBOX (mesma subpasta), onde são processados de novo. "
               "Nunca sobrescreve: se já existir no INBOX, o arquivo não é movido.")
    _avisar_feito()
    ativos: list[Banco] = [b for b in BANCOS if b in config.atual().bancos_ativos]
    banco: Banco = st.radio("Banco", ativos, format_func=BANCOS.__getitem__, horizontal=True,
                            key="reprocesso_banco", on_change=_limpar)
    base = ntedi.BASE_TRIBANCO if banco == "tribanco" else ntedi.BASE_RETORNO
    subpasta = escolher_subpasta("Subpasta", (base,), key=f"reprocesso_subpasta_{banco}",
                                 opcional=banco == "tribanco", on_change=_limpar)
    if banco != "tribanco" and not subpasta.strip():
        st.info("Informe a subpasta.", icon=":material/folder_open:")
        return
    origem, destino = reprocessar.caminhos(banco, subpasta)
    st.markdown(f"De `{origem}`  \nPara `{destino or 'NÃO CONFIGURADO'}`")
    if destino is None:
        st.error("Destino do Tribanco ainda não configurado (pastas.tribanco_inbox em config/cliente.yaml).",
                 icon=":material/block:")
        return

    c1, c2, c3 = st.columns(3)
    de = c1.date_input("De", value=date.today() - timedelta(days=7), key="reprocesso_de")
    ate = c2.date_input("Até", value=date.today(), key="reprocesso_ate")
    trecho = c3.text_input("Nome contém", key="reprocesso_trecho")
    try:
        with st.spinner("Lendo pasta..."):
            itens = reprocessar.listar(origem, de, ate, trecho)
    except OSError as e:
        st.error(f"Não foi possível acessar {origem}. Confira VPN e login na pasta pelo Explorer. Detalhe: {e}",
                 icon=":material/error:")
        return
    if not itens:
        st.info("Nenhum arquivo nesse período/filtro.", icon=":material/search_off:")
        return

    tabela_arq = st.data_editor(
        pd.DataFrame([{"Mover?": False, "Arquivo": i.nome, "Tamanho (KB)": round(i.tamanho / 1024, 1),
                       "Modificado": i.modificado} for i in itens]),
        disabled=["Arquivo", "Tamanho (KB)", "Modificado"], hide_index=True, width="stretch",
        key=f"reprocesso_tabela_{origem}_{de}_{ate}_{trecho}", on_change=_limpar)
    nomes = list(tabela_arq.loc[tabela_arq["Mover?"], "Arquivo"])
    if not nomes:
        st.caption("Marque os arquivos que quer mover.")
        return

    if st.button(f"Simular ({len(nomes)})", icon=":material/preview:"):
        st.session_state["reprocesso_simulado"] = (origem, destino, nomes,
                                                   reprocessar.mover(origem, destino, nomes, simular=True))
    simulado = st.session_state.get("reprocesso_simulado")
    if not simulado or simulado[:3] != (origem, destino, nomes):
        st.caption("Clique em Simular para ver o que vai acontecer antes de mover.")
        return
    _mostrar_resultado_mover(simulado[3], "seriam movidos")
    if not simulado[3].movidos:
        return

    confirmou = st.checkbox(f"Confirmo que quero mover {len(simulado[3].movidos)} arquivo(s) para o INBOX")
    if st.button("Mover agora", type="primary", icon=":material/drive_file_move:", disabled=not confirmou):
        resultado = reprocessar.mover(origem, destino, nomes)
        log.obter().info("reprocessar %s: %s -> %s, movidos %s, copiados sem apagar %s, pulados %s", banco, origem,
                         destino, resultado.movidos, resultado.copiados_sem_apagar, resultado.pulados)
        try:
            historico.registrar_movimentacao(banco, origem, destino, resultado)
        except Exception as e:
            log.obter().exception("falha ao registrar movimentação")
            st.warning(f"Arquivos movidos, mas não consegui registrar no histórico: {e}", icon=":material/warning:")
        st.session_state.pop("leitura_rede", None)
        _limpar()
        st.session_state["reprocesso_feito"] = resultado
        st.rerun()
