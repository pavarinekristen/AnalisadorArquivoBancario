"""Página Arquivos UCM: busca e baixa arquivos do Oracle UCM pelo OIC."""
from __future__ import annotations

from pathlib import PurePosixPath

import streamlit as st

from conferencia import config, credenciais, log, ucm
from telas.formatos import md

_CHAVES_RESULTADO = ("ucm_id", "ucm_pos")


def _limpar() -> None:
    for chave in _CHAVES_RESULTADO:
        st.session_state.pop(chave, None)


def _usar_atalho() -> None:
    if atalho := st.session_state.get("ucm_atalho"):
        st.session_state["ucm_pasta"] = atalho
        st.session_state["ucm_atalho"] = None
        _limpar()


@st.cache_resource
def _cliente(versao_classe: int, credencial: tuple[str, str] | None) -> ucm.ClienteUCM:
    # versao_classe = id(ucm.ClienteUCM): quando o Streamlit recarrega o ucm.py, a classe nova tem
    # outro id e o cache cria um cliente novo, em vez de manter um objeto da classe antiga.
    if credencial:
        return ucm.ClienteUCM(*credencial)
    try:
        cred = st.secrets["ucm"]
        return ucm.ClienteUCM(cred["client_id"], cred["client_secret"])
    except (KeyError, FileNotFoundError):
        return ucm.ClienteUCM.do_ambiente()


def _configurar_credencial(tem: bool) -> None:
    with st.expander("Configurar credencial do UCM", expanded=not tem):
        if not credenciais.disponivel():
            st.caption("Cofre do Windows indisponível (pacote keyring). Use .streamlit/secrets.toml ou as variáveis "
                       "UCM_CLIENT_ID e UCM_CLIENT_SECRET.")
            return
        st.caption("Fica guardada no Gerenciador de Credenciais do Windows deste usuário, não em arquivo.")
        with st.form("form_ucm_credencial", clear_on_submit=True):
            cid = st.text_input("client_id")
            segredo = st.text_input("client_secret", type="password")
            salvar = st.form_submit_button("Salvar no cofre", icon=":material/key:")
        if salvar and cid.strip() and segredo.strip():
            credenciais.gravar(cid, segredo)
            _cliente.clear()
            log.obter().info("credencial do UCM gravada no cofre")
            st.success("Credencial salva.", icon=":material/check_circle:")
            st.rerun()
        if tem and st.button("Apagar credencial do cofre", icon=":material/key_off:"):
            credenciais.apagar()
            _cliente.clear()
            log.obter().info("credencial do UCM apagada do cofre")
            st.rerun()


def _mostrar_documento(cliente: ucm.ClienteUCM, doc: ucm.DocumentoUCM, origem: str) -> None:
    with st.container(border=True):
        criado = f"{doc.criado_em:%d/%m/%Y %H:%M}" if doc.criado_em else "?"
        st.markdown(f"**{md(doc.titulo)}** · Content ID `{doc.nome}` · document_id `{doc.id}` · {criado} · "
                    f"{doc.tamanho / 1024:,.1f} KB")
        st.caption(md(f"{origem} · pasta {doc.conta}"))
        chave = f"ucm_conteudo_{doc.id}"
        if st.button("Baixar conteúdo", key=f"baixar_{origem}_{doc.id}", icon=":material/download:"):
            with st.spinner("Baixando do UCM..."):
                st.session_state[chave] = cliente.baixar(doc.id)
            log.obter().info("UCM: baixado document_id %s (%s)", doc.id, doc.titulo)
        conteudo = st.session_state.get(chave)
        if conteudo is not None:
            try:
                linhas = conteudo.decode("utf-8").splitlines()
            except UnicodeDecodeError:
                linhas = conteudo.decode("latin-1").splitlines()
            st.caption(f"{len(conteudo):,} bytes · {len(linhas):,} linhas (mostrando as 50 primeiras)")
            st.code("\n".join(linhas[:50]), language=None)
            st.download_button("Salvar arquivo", conteudo, file_name=PurePosixPath(doc.titulo).name or f"{doc.id}.bin",
                               key=f"salvar_{origem}_{doc.id}", icon=":material/save:")


def _busca(cliente: ucm.ClienteUCM, pasta: str, subpastas: bool) -> None:
    with st.form("form_ucm_id"):
        id_doc = st.text_input("Content ID (tela do UCM), document_id ou nome do arquivo",
                               placeholder="UCMFA80505382, 80503291 ou A35708190210260002.dat")
        ok = st.form_submit_button("Buscar", type="primary", icon=":material/search:")
    if ok and id_doc.strip():
        with st.spinner("Consultando UCM..."):
            st.session_state["ucm_id"] = (id_doc.strip(), cliente.localizar(pasta, id_doc, subpastas))
    if "ucm_id" in st.session_state:
        buscado, doc = st.session_state["ucm_id"]
        if doc:
            _mostrar_documento(cliente, doc, "Busca por ID ou nome")
        else:
            dica = "" if subpastas else " Tente ligar \"Incluir subpastas\"."
            st.warning(md(f"{buscado} não está em {pasta}.{dica}"), icon=":material/search_off:")


def _busca_por_posicao(cliente: ucm.ClienteUCM, pasta: str, subpastas: bool) -> None:
    with st.form("form_ucm_pos"):
        c1, c2 = st.columns(2)
        pagina_n = c1.number_input("Página", min_value=1, value=1, step=1)
        item_n = c2.number_input("Item na página", min_value=1, max_value=ucm.LIMITE_PAGINA, value=1, step=1)
        ok = st.form_submit_button("Pegar arquivo", type="primary", icon=":material/format_list_numbered:")
    posicao = (int(pagina_n) - 1) * ucm.LIMITE_PAGINA + int(item_n)
    st.caption(f"Posição geral {posicao} (mais recente primeiro, {ucm.LIMITE_PAGINA} por página).")
    if ok:
        with st.spinner(f"Percorrendo {pagina_n} página(s)..."):
            st.session_state["ucm_pos"] = (posicao, cliente.na_posicao(pasta, posicao, subpastas))
    if "ucm_pos" in st.session_state:
        pos, doc = st.session_state["ucm_pos"]
        if doc:
            _mostrar_documento(cliente, doc, f"Posição {pos}")
        else:
            st.warning(f"A pasta tem menos de {pos} arquivos.", icon=":material/search_off:")


def pagina() -> None:
    st.subheader("Arquivos UCM")
    st.caption("Busque pelo Content ID, document_id ou nome do arquivo. A busca filtra no próprio UCM, "
               "então encontra o arquivo em qualquer página (a API devolve só 20 por consulta).")
    cfg = config.atual().ucm
    if not cfg.configurado:
        st.info("UCM não configurado para este cliente (bloco ucm em config/cliente.yaml).", icon=":material/cloud_off:")
        return
    credencial = credenciais.ler()
    _configurar_credencial(credencial is not None)
    try:
        cliente = _cliente(id(ucm.ClienteUCM), credencial)
    except ucm.ErroUCM as e:
        st.error(f"{e} Salve a credencial acima, ou configure [ucm] em .streamlit/secrets.toml ou as variáveis "
                 "UCM_CLIENT_ID e UCM_CLIENT_SECRET.", icon=":material/key_off:")
        return
    atalhos = cfg.contas
    if not atalhos:
        st.info("Nenhuma conta UCM liberada (ucm.contas em config/cliente.yaml).", icon=":material/folder_off:")
        return
    st.session_state.setdefault("ucm_pasta", next(iter(atalhos)))
    pasta = st.text_input("Pasta (conta UCM)", key="ucm_pasta", on_change=_limpar).strip()
    st.pills("Atalhos", list(atalhos), format_func=atalhos.__getitem__, key="ucm_atalho",
             on_change=_usar_atalho, label_visibility="collapsed")
    subpastas = st.toggle("Incluir subpastas (processed$, error$...), igual à tela do UCM", value=True,
                          key="ucm_subpastas", on_change=_limpar)
    if not pasta:
        st.info("Digite a pasta (conta UCM) ou escolha um atalho.", icon=":material/folder_open:")
        return
    if not config.conta_ucm_permitida(pasta):
        st.error(md(f"A conta {pasta} não está liberada. Contas permitidas: {', '.join(atalhos)}."),
                 icon=":material/block:")
        return
    try:
        _busca(cliente, pasta, subpastas)
        with st.expander("Pegar pela posição na tela do UCM (página e item)"):
            _busca_por_posicao(cliente, pasta, subpastas)
    except ValueError as e:
        st.error(md(e), icon=":material/error:")
    except ucm.ErroUCM as e:
        log.obter().warning("erro no UCM/OIC: %s", e)
        st.error(md(f"Erro no UCM/OIC: {e}"), icon=":material/cloud_off:")
