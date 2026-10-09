"""Tela da conferência de pagamentos. Rodar com:  streamlit run app.py"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from conferencia import area_transferencia, cnab240, historico, mensagem, motor, ntedi, relatorio
from conferencia.modelos import (ACEITO_NAO_PAGO, DEVOLUCAO, NAO_ENVIADO, OUTRO_PAGAMENTO, PAGO,
                                 REJEITADO, ROTULOS)

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Conferência de Pagamentos", page_icon=str(ASSETS / "techone_icon.jpg"),
                   layout="wide")

CORES_HEX = {PAGO: "#16A34A", DEVOLUCAO: "#D97706", REJEITADO: "#DC2626", NAO_ENVIADO: "#DC2626",
             ACEITO_NAO_PAGO: "#0059A9", OUTRO_PAGAMENTO: "#6B7280"}

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
    grid-template-columns: repeat(6, 1fr);
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
</style>
"""
st.markdown(_ESTILO, unsafe_allow_html=True)


def _passo(numero: int, titulo: str) -> None:
    st.markdown(f'<div class="passo"><span class="passo-numero">{numero}</span>'
                f'<span class="passo-titulo">{titulo}</span></div>', unsafe_allow_html=True)


def _fmt_valor(v) -> str:
    return "" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_data(d: str) -> str:
    return f"{d[0:2]}/{d[2:4]}/{d[4:8]}" if len(d) == 8 and d.isdigit() else d


def _sem_ext(nome: str) -> str:
    return nome[:-4] if nome.upper().endswith(".TXT") else nome


def _codigos_arquivos(r, tipo: str, filtro=lambda x: True) -> str:
    """Ex: 'BD em FORN_EZN1_02_071026P_CRI'. Só do pagamento conferido (não de outros pagamentos)."""
    if r.status == OUTRO_PAGAMENTO:
        return ""
    return " | ".join(f"{x.ocorrencia_bruta or '-'} em {_sem_ext(x.arquivo.nome)}"
                      for x in r.registros if x.arquivo.tipo == tipo and filtro(x))


def _devolucao_mov(r) -> str:
    dev = _codigos_arquivos(r, "MOV", lambda x: x.ocorrencias[:1] and (x.ocorrencias[0].startswith("Z")
                                                                       or "XD" in x.ocorrencias))
    return f"Sim: {dev}" if dev else "Não"


def tabela(resultados) -> pd.DataFrame:
    return pd.DataFrame([{
        "Favorecido": r.pagamento.favorecido,
        "CPF/CNPJ": r.pagamento.cpf_cnpj,
        "Documento": r.pagamento.documento,
        "Valor": _fmt_valor(r.pagamento.valor),
        "Status": r.rotulo,
        "CRI (código e arquivo)": _codigos_arquivos(r, "CRI") or "Não está em CRI",
        "MOV pago (00)": _codigos_arquivos(r, "MOV", lambda x: x.ocorrencias[:1] in (["00"], ["03"])) or "Não",
        "Devolução no MOV (Z...)": _devolucao_mov(r),
        "Código": " ".join(r.codigos),
        "Significado": motor.descrever_varios([c for cod in r.codigos for c in cnab240._ocorrencias(cod)]),
        "Arquivo": r.arquivo_status,
        "Nome no banco": r.registros[-1].nome if r.registros else "",
        "Sistema diz pago?": "Sim — confirmar com o banco" if r.alerta_sistema else "",
        "Obs.": " | ".join(r.observacoes),
    } for r in resultados])


def excel_resultado(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Conferência")
    return buf.getvalue()


def escolher_lista(nome_arquivo: str, conteudo: bytes):
    """Lê o Excel e deixa escolher qual lista conferir. Devolve (pagamentos, nome do relatório)."""
    try:
        listas = relatorio.ler_excel(conteudo)
    except Exception as e:  # arquivo corrompido, protegido etc.
        st.error(f"Não consegui ler o Excel: {e}", icon=":material/error:")
        return [], ""
    if not listas:
        st.warning("Não reconheci nenhuma aba (BANCO, RESUMO ou SISTEMA) nesse Excel.", icon=":material/warning:")
        return [], ""
    nomes = list(listas)
    padrao = next((i for i, n in enumerate(nomes) if "banco" in n), 0)
    escolha = st.selectbox("Qual lista conferir?", nomes, index=padrao,
                           format_func=lambda n: f"{n} — {len(listas[n])} favorecidos")
    return listas[escolha], f"{nome_arquivo} / {escolha}"


# ------------------------------------------------------------------ página: Conferir
def pagina_conferir() -> None:
    with st.container(border=True):
        st.markdown("**Jeito mais rápido:** selecione no Explorer o Excel e todos os arquivos do banco "
                    "(ou a pasta inteira), aperte **Ctrl+C** e clique em Colar.")
        b1, b2, _ = st.columns([1, 1, 3])
        if b1.button("Colar arquivos copiados", type="primary", icon=":material/content_paste:"):
            copiados = area_transferencia.arquivos_copiados()
            if copiados:
                st.session_state["colados"] = copiados
                st.session_state.pop("resultados", None)
            else:
                st.warning("Nada copiado. Selecione os arquivos no Explorer e aperte Ctrl+C antes.",
                          icon=":material/warning:")
        if st.session_state.get("colados") and b2.button("Limpar colados"):
            st.session_state.pop("colados")
            st.session_state.pop("resultados", None)
            st.rerun()

    colados = st.session_state.get("colados", [])
    excel_colado = next((c for c in colados if area_transferencia.e_excel(c)), None)
    banco_colados = [c for c in colados if not area_transferencia.e_excel(c)]

    col1, col2 = st.columns(2)

    with col1:
        _passo(1, "Quem conferir")
        pagamentos, nome_relatorio = [], ""
        opcoes = ["Digitar nomes", "Excel", "Colar lista do sistema"]
        modo_rel = st.radio("Como vai informar os favorecidos?", opcoes, horizontal=True,
                            index=1 if excel_colado else 0)
        if modo_rel == "Digitar nomes":
            texto = st.text_area(
                "Um favorecido por linha. Pode ser o nome (inteiro ou parte), CPF/CNPJ ou nº do documento. "
                "Se quiser, acrescente o valor (ex: 1.234,56) ou a data (ex: 07/10/2026) para filtrar.",
                height=220, placeholder="FULANO DE TAL DA SILVA\nCICLANO 11.222.333/0001-81\n"
                                        "BELTRANO SOUZA 1.234,56\n100009000000001")
            if texto.strip():
                pagamentos, nome_relatorio = relatorio.ler_nomes_digitados(texto), "nomes digitados"
        elif modo_rel == "Excel":
            if excel_colado:
                st.success(f"Excel colado: {excel_colado.name}", icon=":material/check_circle:")
                pagamentos, nome_relatorio = escolher_lista(excel_colado.name, excel_colado.read_bytes())
            else:
                xl = st.file_uploader("Arraste o Excel do relatório", type=["xlsx", "xlsm"])
                if xl:
                    pagamentos, nome_relatorio = escolher_lista(xl.name, xl.getvalue())
        else:
            texto = st.text_area("Cole aqui a lista do sistema (Situação: Com Erro)", height=220)
            if texto.strip():
                pagamentos, nome_relatorio = relatorio.ler_texto_colado(texto), "lista colada"
                if not pagamentos:
                    st.warning("Não reconheci nenhum pagamento no texto colado.", icon=":material/warning:")
        if pagamentos:
            st.caption(f"{len(pagamentos)} favorecido(s) para conferir.")

    with col2:
        _passo(2, "Arquivos do banco")
        arquivos, registros = [], []
        if banco_colados:
            for c in banco_colados:
                arq, regs = cnab240.ler_bytes(c.name, c.read_bytes())
                if arq.tipo != "OUTRO":
                    arquivos.append(arq)
                    registros.extend(regs)
            st.success(f"{len(banco_colados)} arquivos colados.", icon=":material/check_circle:")
        else:
            modo_arq = st.radio(
                "Como vai informar os arquivos?",
                ["Pasta padrão (rede)", "Arrastar arquivos", "Caminho manual (avançado)"], horizontal=True)
            if modo_arq == "Pasta padrão (rede)":
                tipo_pasta = st.radio("Retorno ou remessa?", ["retorno", "remessa"], horizontal=True,
                                      format_func=lambda t: f"{ntedi.ROTULOS[t]} ({'INBOXENV' if t == 'retorno' else 'SENTBOX'})")
                subpasta = st.text_input("Nome da subpasta (ex.: GE202255)")
                col_de, col_ate = st.columns(2)
                de = col_de.date_input("De", value=date.today() - timedelta(days=7))
                ate = col_ate.date_input("Até", value=date.today())
                if subpasta:
                    with st.spinner("Lendo arquivos da rede..."):
                        resultado = ntedi.ler_subpasta(tipo_pasta, subpasta, de, ate)
                    arquivos, registros = resultado.arquivos, resultado.registros
                    for aviso in resultado.avisos:
                        st.warning(aviso, icon=":material/warning:")
                    if resultado.total_ignorados_data:
                        st.caption(f"{resultado.total_ignorados_data} arquivo(s) fora do intervalo "
                                   "de data foram ignorados.")
            elif modo_arq == "Arrastar arquivos":
                ups = st.file_uploader("Arraste TODOS os arquivos da pasta (MOV, CRI, Retorno...)",
                                       accept_multiple_files=True)
                for u in ups or []:
                    arq, regs = cnab240.ler_bytes(u.name, u.getvalue())
                    if arq.tipo != "OUTRO":
                        arquivos.append(arq)
                        registros.extend(regs)
            else:
                pasta = st.text_input("Caminho da pasta", placeholder=r"C:\Users\krist\Downloads\arquivos\FINAL24")
                if pasta:
                    p = Path(pasta.strip().strip('"'))
                    if p.is_dir():
                        arquivos, registros = cnab240.ler_pasta(p)
                    else:
                        st.error("Pasta não encontrada.", icon=":material/error:")
        if arquivos:
            tipos = pd.Series([a.tipo for a in arquivos]).value_counts().to_dict()
            st.caption(f"{len(arquivos)} arquivos ({', '.join(f'{v} {k}' for k, v in tipos.items())}), "
                       f"{len(registros)} pagamentos lidos.")
            if "MOV" not in tipos:
                st.warning("Nenhum arquivo MOV. Sem MOV não dá para saber se foi pago ou devolvido.",
                          icon=":material/warning:")
            if "CRI" not in tipos:
                st.info("Nenhum arquivo CRI. Não dá para ver rejeições na crítica do banco.",
                       icon=":material/info:")
            # Só um lembrete, não impede a conferência: às vezes o banco realmente não gera o lote.
            # Se o relatório tem datas, só interessam arquivos da data do pagamento em diante
            # (a devolução chega depois).
            datas = [datetime.strptime(p.data, "%d%m%Y").date() for p in pagamentos
                     if len(p.data) == 8 and p.data.isdigit()]
            relevantes = [a for a in arquivos if not datas or (a.data and a.data >= min(datas))]
            faltando = cnab240.lotes_faltando(relevantes)
            if faltando:
                st.caption("Obs.: lote(s) fora da sequência, confira se não faltou baixar algum: " + "; ".join(
                    f"{grupo} → {', '.join(f'{l:02d}' for l in lotes)}" for grupo, lotes in faltando.items()))

    pronto = bool(pagamentos and arquivos)
    if st.button("CONFERIR", type="primary", disabled=not pronto, width="stretch",
                icon=":material/fact_check:"):
        if modo_rel == "Digitar nomes":
            resultados = motor.pesquisar(pagamentos, registros)   # um resultado por pagamento achado
        else:
            resultados = motor.conferir(pagamentos, registros)
        anteriores = historico.devolucoes_anteriores(resultados)
        historico.salvar(resultados, nome_relatorio, [a.nome for a in arquivos])
        st.session_state["resultados"] = resultados
        st.session_state["anteriores"] = anteriores
        st.session_state["msg"] = (mensagem.montar_pesquisa(resultados) if modo_rel == "Digitar nomes"
                                   else mensagem.montar(resultados))
        st.toast(f"Conferência concluída: {len(resultados)} favorecido(s).", icon=":material/task_alt:")
    elif not pronto:
        st.caption("Informe os favorecidos e os arquivos para liberar o botão.")

    # ------------------------------------------------------------------ resultado
    resultados = st.session_state.get("resultados")
    if resultados:
        st.divider()
        st.subheader(f"Resultado: {len(resultados)} favorecidos")
        cont = pd.Series([r.status for r in resultados]).value_counts()
        ordem = [DEVOLUCAO, PAGO, REJEITADO, NAO_ENVIADO, ACEITO_NAO_PAGO, OUTRO_PAGAMENTO]
        cards = "".join(
            f'<div class="kpi-card" style="border-left-color:{CORES_HEX[status]}">'
            f'<div class="kpi-valor">{int(cont.get(status, 0))}</div>'
            f'<div class="kpi-rotulo"><span class="kpi-dot" style="background:{CORES_HEX[status]}"></span>'
            f'{ROTULOS[status]}</div></div>'
            for status in ordem)
        st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)

        alertas = sum(r.alerta_sistema for r in resultados)
        if alertas:
            st.error(f"{alertas} favorecido(s) aparecem como pagos no sistema, mas o banco não pagou.",
                    icon=":material/error:")
        for nome, n in st.session_state.get("anteriores", {}).items():
            st.warning(f"Reincidência: {nome} já teve {n} devolução(ões) em conferências anteriores.",
                      icon=":material/warning:")

        df = tabela(resultados)
        filtro = st.multiselect("Filtrar status", sorted(df["Status"].unique()), placeholder="Todos os status")
        st.dataframe(df[df["Status"].isin(filtro)] if filtro else df, width="stretch", hide_index=True)

        escolhido = st.selectbox(
            "Ver detalhes de:", list(range(len(resultados))), index=None,
            placeholder="Escolha um favorecido para ver em quais arquivos ele aparece",
            format_func=lambda i: f"{resultados[i].pagamento.favorecido} — {_fmt_valor(resultados[i].pagamento.valor)} — "
            f"{resultados[i].rotulo}")
        if escolhido is not None:
            r = resultados[escolhido]
            p = r.pagamento
            st.markdown(f"**{p.favorecido}** — {r.rotulo}  \n"
                        f"Relatório: doc `{p.documento or '-'}` · CPF/CNPJ `{p.cpf_cnpj or '-'}` · "
                        f"valor {_fmt_valor(p.valor)} · data {_fmt_data(p.data) or '-'} · OP {p.op or '-'}  \n"
                        f"Retorno no relatório: {p.retorno_sistema or '-'}")
            if r.registros:
                st.dataframe(pd.DataFrame([{
                    "Arquivo": x.arquivo.nome, "Tipo": x.arquivo.tipo, "Seg.": x.segmento,
                    "Nome no banco": x.nome, "CPF/CNPJ": x.cpf_cnpj, "Documento": x.documento,
                    "Data": _fmt_data(x.data), "Valor": _fmt_valor(x.valor),
                    "Ocorrência": x.ocorrencia_bruta,
                    "Significado": motor.descrever_varios(x.ocorrencias),
                } for x in r.registros]), width="stretch", hide_index=True)
            else:
                st.info("Não aparece em nenhum arquivo.", icon=":material/info:")
            for o in r.observacoes:
                st.caption(f"• {o}")

        st.subheader("Mensagem pro chefe")
        st.caption("Clique no ícone de copiar no canto da caixa.")
        st.code(st.session_state["msg"], language=None, wrap_lines=True)

        st.download_button("Exportar resultado (Excel)", excel_resultado(df),
                           file_name="conferencia.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ------------------------------------------------------------------ página: Histórico
def pagina_historico() -> None:
    st.subheader("Histórico de conferências")
    busca = st.text_input("Buscar por nome, CPF/CNPJ ou documento")
    st.dataframe(historico.buscar(busca), width="stretch", hide_index=True)
    st.subheader("Favorecidos com mais de uma devolução")
    rein = historico.reincidentes()
    if rein.empty:
        st.caption("Nenhum por enquanto.")
    else:
        st.dataframe(rein, width="stretch", hide_index=True)


# ------------------------------------------------------------------ página: Códigos de ocorrência
def pagina_codigos() -> None:
    st.subheader("Tabela de ocorrências")
    st.caption("Fonte: regras/ocorrencias.yaml (dá para editar e acrescentar códigos).")
    busca_cod = st.text_input("Buscar código ou texto").strip().upper()
    df_cod = pd.DataFrame([{"Código": k, "Categoria": v["categoria"], "Descrição": v["descricao"]}
                           for k, v in motor.OCORRENCIAS.items()])
    if busca_cod:
        df_cod = df_cod[df_cod.apply(lambda r: busca_cod in r["Código"] or
                                     busca_cod in relatorio.sem_acento(r["Descrição"]), axis=1)]
    st.dataframe(df_cod, width="stretch", hide_index=True)


# ------------------------------------------------------------------ entrada
st.logo(str(ASSETS / "techone_banner.jpg"), icon_image=str(ASSETS / "techone_icon.jpg"))

pagina = st.navigation([
    st.Page(pagina_conferir, title="Conferir", icon=":material/fact_check:", default=True),
    st.Page(pagina_historico, title="Histórico", icon=":material/history:"),
    st.Page(pagina_codigos, title="Códigos de ocorrência", icon=":material/menu_book:"),
])
st.title("Conferência de Pagamentos")

pagina.run()
