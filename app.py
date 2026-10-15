"""Tela da conferência de pagamentos. Rodar com:  streamlit run app.py"""
from __future__ import annotations

import io
import time
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath

import pandas as pd
import streamlit as st

from conferencia import (area_transferencia, cnab240, historico, mensagem, motor, ntedi, relatorio,
                         reprocessar, ucm)
from conferencia.modelos import (ACEITO_NAO_PAGO, BANCOS, DEVOLUCAO, NAO_ENVIADO, OUTRO_PAGAMENTO, PAGO,
                                 REJEITADO, ROTULOS, Banco)

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Conferência de Pagamentos", page_icon=str(ASSETS / "techone_icon.jpg"),
                   layout="wide")

CORES_HEX = {PAGO: "#16A34A", DEVOLUCAO: "#D97706", REJEITADO: "#DC2626", NAO_ENVIADO: "#DC2626",
             ACEITO_NAO_PAGO: "#0059A9", OUTRO_PAGAMENTO: "#6B7280"}

CODIGO_BANCO: dict[Banco, str] = {"santander": "033", "tribanco": cnab240.CODIGO_TRIBANCO}
ARQUIVOS_BANCO: dict[Banco, str] = {
    "santander": "MOV, CRI e Retorno (ex: FORN_EZN1_06_071026P_MOV.TXT)",
    "tribanco": "retorno .dat, com crítica e pagamento no mesmo arquivo (ex: A35708191410260001.dat)",
}
ROTULOS_TIPO = {"RET": "retorno Tribanco"}

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
st.markdown(_ESTILO, unsafe_allow_html=True)


def _passo(numero: int, titulo: str) -> None:
    st.markdown(f'<div class="passo"><span class="passo-numero">{numero}</span>'
                f'<span class="passo-titulo">{titulo}</span></div>', unsafe_allow_html=True)


def _fmt_valor(v) -> str:
    return "" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_data(d: str) -> str:
    return f"{d[0:2]}/{d[2:4]}/{d[4:8]}" if len(d) == 8 and d.isdigit() else d


def _sem_ext(nome: str) -> str:
    return nome[:-4] if nome.upper().endswith((".TXT", ".DAT")) else nome


def _codigos_arquivos(r, tipo: str, filtro=lambda x: True) -> str:
    """Ex: 'BD em FORN_EZN1_02_071026P_CRI'. Só do pagamento conferido (não de outros pagamentos)."""
    if r.status == OUTRO_PAGAMENTO:
        return ""
    return " | ".join(f"{x.ocorrencia_bruta or '-'} em {_sem_ext(x.arquivo.nome)}"
                      for x in r.registros if x.arquivo.tipo == tipo and filtro(x))


def _e_pago(x) -> bool:
    return x.ocorrencias[:1] in (["00"], ["03"])


def _e_devolvido(x) -> bool:
    return bool(x.ocorrencias[:1]) and (x.ocorrencias[0].startswith("Z") or "XD" in x.ocorrencias)


def _devolucao(r, tipo: str) -> str:
    dev = _codigos_arquivos(r, tipo, _e_devolvido)
    return f"Sim: {dev}" if dev else "Não"


def _colunas_banco(r, banco: Banco) -> dict[str, str]:
    if banco == "tribanco":   # crítica e pagamento vêm no mesmo retorno .dat
        return {
            "Retorno Tribanco (código e arquivo)": _codigos_arquivos(r, "RET") or "Não está em retorno",
            "Pago (00)": _codigos_arquivos(r, "RET", _e_pago) or "Não",
            "Devolução (Z...)": _devolucao(r, "RET"),
        }
    return {
        "CRI (código e arquivo)": _codigos_arquivos(r, "CRI") or "Não está em CRI",
        "MOV pago (00)": _codigos_arquivos(r, "MOV", _e_pago) or "Não",
        "Devolução no MOV (Z...)": _devolucao(r, "MOV"),
    }


def tabela(resultados, banco: Banco = "santander") -> pd.DataFrame:
    return pd.DataFrame([{
        "Favorecido": r.pagamento.favorecido,
        "CPF/CNPJ": r.pagamento.cpf_cnpj,
        "Documento": r.pagamento.documento,
        "Valor": _fmt_valor(r.pagamento.valor),
        "Status": r.rotulo,
        **_colunas_banco(r, banco),
        "Código": " ".join(r.codigos),
        "Significado": motor.descrever_varios([c for cod in r.codigos for c in cnab240._ocorrencias(cod)]),
        "Arquivo": r.arquivo_status,
        "Nome no banco": r.registros[-1].nome if r.registros else "",
        "Empresa pagadora": r.registros[-1].arquivo.pagador if r.registros else "",
        "Sistema diz pago?": "Sim — confirmar com o banco" if r.alerta_sistema else "",
        "Obs.": " | ".join(r.observacoes),
    } for r in resultados])


# Guardados para não refazer a cada clique: o Streamlit roda a página inteira em toda interação.
@st.cache_data(show_spinner=False, max_entries=5)
def excel_resultado(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Conferência")
    return buf.getvalue()


@st.cache_data(show_spinner=False, max_entries=10)
def _ler_excel(conteudo: bytes) -> dict[str, list]:
    return relatorio.ler_excel(conteudo)


def escolher_lista(nome_arquivo: str, conteudo: bytes):
    """Lê o Excel e deixa escolher qual lista conferir. Devolve (pagamentos, nome do relatório)."""
    try:
        listas = _ler_excel(conteudo)
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
def _limpar_resultado() -> None:
    for chave in ("resultados", "resultados_banco", "anteriores", "msg"):
        st.session_state.pop(chave, None)


def _escolher_banco() -> Banco:
    banco: Banco = st.radio("Qual banco vai conferir?", list(BANCOS), format_func=BANCOS.__getitem__,
                            horizontal=True, key="banco", on_change=_limpar_resultado)
    st.markdown(f'<div class="banco-ativo banco-{banco}">'
                f'<div class="banco-nome">Conferindo: {BANCOS[banco]} (banco {CODIGO_BANCO[banco]})</div>'
                f'<div class="banco-detalhe">Arquivos lidos: {ARQUIVOS_BANCO[banco]}. '
                f'Arquivos de outro banco são ignorados.</div></div>', unsafe_allow_html=True)
    return banco


_VALIDADE_LEITURA = 300   # segundos


def _ler_rede(banco: Banco, tipo: ntedi.Tipo, subpasta: str, de: date, ate: date) -> ntedi.ResultadoNtedi:
    # O Streamlit roda a página de novo a cada clique e a pasta de rede é lenta, então guarda a
    # última leitura por 5 minutos (o botão "Atualizar pasta" força ler de novo; mesmo relendo, o
    # cache por arquivo de cnab240 só baixa o que é novo ou mudou). Só guarda leitura que achou arquivos e não teve aviso: leitura
    # vazia ou com erro (VPN desligada, login não feito, subpasta pela metade) é sempre refeita.
    chave = (banco, tipo, subpasta.strip(), de, ate)
    guardado = st.session_state.get("leitura_rede")
    if guardado and guardado[0] == chave and time.monotonic() - guardado[1] < _VALIDADE_LEITURA:
        return guardado[2]
    if banco == "tribanco":
        resultado = ntedi.ler_tribanco(subpasta, de, ate)
    else:
        resultado = ntedi.ler_subpasta(tipo, subpasta, de, ate)
    if resultado.arquivos and not resultado.avisos:
        st.session_state["leitura_rede"] = (chave, time.monotonic(), resultado)
    else:
        st.session_state.pop("leitura_rede", None)
    return resultado


def _pasta_rede(banco: Banco) -> tuple[list, list]:
    if banco == "tribanco":
        st.caption(f"Pasta do Tribanco: `{ntedi.BASE_TRIBANCO}`")
        tipo_pasta: ntedi.Tipo = "retorno"
        subpasta = st.text_input("Subpasta (opcional, vazio = pasta do Tribanco)")
    else:
        tipo_pasta = st.radio("Retorno ou remessa?", ["retorno", "remessa"], horizontal=True,
                              format_func=lambda t: f"{ntedi.ROTULOS[t]} ({'INBOXENV' if t == 'retorno' else 'SENTBOX'})")
        subpasta = st.text_input("Nome da subpasta (ex.: GE202255)")
    col_de, col_ate = st.columns(2)
    de = col_de.date_input("De", value=date.today() - timedelta(days=7))
    ate = col_ate.date_input("Até", value=date.today())
    if not subpasta.strip() and banco != "tribanco":
        return [], []
    if st.button("Atualizar pasta", icon=":material/refresh:",
                 help="Lê a pasta de novo para pegar arquivos que chegaram agora."):
        st.session_state.pop("leitura_rede", None)
    with st.spinner("Lendo arquivos da rede..."):
        resultado = _ler_rede(banco, tipo_pasta, subpasta, de, ate)
    for aviso in resultado.avisos:
        st.warning(aviso, icon=":material/warning:")
    if not resultado.arquivos and not resultado.avisos:
        st.warning(f"Nenhum arquivo do {BANCOS[banco]} em {resultado.pasta} entre {de:%d/%m/%Y} e {ate:%d/%m/%Y}. "
                   f"Fora do período: {resultado.total_ignorados_data}; "
                   f"fora do padrão do banco: {resultado.total_fora_do_padrao}. "
                   "Confira a subpasta, o período (De/Até) e o tipo (retorno/remessa).",
                   icon=":material/search_off:")
    elif resultado.total_ignorados_data:
        st.caption(f"{resultado.total_ignorados_data} arquivo(s) fora do intervalo de data foram ignorados.")
    return resultado.arquivos, resultado.registros


def _ler_arquivos(nomes_e_conteudos) -> tuple[list, list]:
    arquivos, registros = [], []
    for nome, conteudo in nomes_e_conteudos:
        arq, regs = cnab240.ler_bytes(nome, conteudo)
        if arq.tipo != "OUTRO":
            arquivos.append(arq)
            registros.extend(regs)
    return arquivos, registros


def _avisos_arquivos(banco: Banco, tipos: dict[str, int]) -> None:
    if banco == "tribanco":
        if "RET" not in tipos:
            st.warning("Nenhum retorno do Tribanco (.dat). Sem ele não dá para saber se foi pago.",
                       icon=":material/warning:")
        else:
            st.caption("No Tribanco o mesmo retorno traz a crítica (BD = aceito, ou código de erro) "
                       "e depois o pagamento (00) ou a devolução (Z...).")
        return
    if "MOV" not in tipos:
        st.warning("Nenhum arquivo MOV. Sem MOV não dá para saber se foi pago ou devolvido.",
                   icon=":material/warning:")
    if "CRI" not in tipos:
        st.info("Nenhum arquivo CRI. Não dá para ver rejeições na crítica do banco.",
                icon=":material/info:")


def pagina_conferir() -> None:
    banco = _escolher_banco()
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
                "Um por linha: nome (inteiro ou parte) ou CPF/CNPJ do favorecido ou da empresa pagadora, "
                "ou nº do documento. "
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
        _passo(2, f"Arquivos do {BANCOS[banco]}")
        arquivos, registros = [], []
        if banco_colados:
            arquivos, registros = _ler_arquivos((c.name, c.read_bytes()) for c in banco_colados)
            st.success(f"{len(banco_colados)} arquivos colados.", icon=":material/check_circle:")
        else:
            modo_arq = st.radio(
                "Como vai informar os arquivos?",
                ["Pasta padrão (rede)", "Arrastar arquivos", "Caminho manual (avançado)"], horizontal=True)
            if modo_arq == "Pasta padrão (rede)":
                arquivos, registros = _pasta_rede(banco)
            elif modo_arq == "Arrastar arquivos":
                rotulo = ("Arraste os arquivos de retorno do Tribanco (.dat)" if banco == "tribanco"
                          else "Arraste TODOS os arquivos da pasta (MOV, CRI, Retorno...)")
                ups = st.file_uploader(rotulo, accept_multiple_files=True)
                arquivos, registros = _ler_arquivos((u.name, u.getvalue()) for u in ups or [])
            else:
                pasta = st.text_input("Caminho da pasta", placeholder=r"C:\Users\krist\Downloads\arquivos\FINAL24")
                if pasta:
                    with st.spinner("Lendo arquivos..."):
                        lidos = ntedi.ler_pasta(Path(pasta.strip().strip('"')), "Pasta")
                    for aviso in lidos.avisos:
                        st.warning(aviso, icon=":material/warning:")
                    arquivos, registros = lidos.arquivos, lidos.registros
        outro_banco = [a for a in arquivos if a.banco != banco]
        if outro_banco:
            st.warning(f"{len(outro_banco)} arquivo(s) de outro banco ignorado(s): você está conferindo o "
                       f"{BANCOS[banco]}. Troque o banco lá em cima se quiser conferir esses.",
                       icon=":material/warning:")
            arquivos = [a for a in arquivos if a.banco == banco]
            registros = [r for r in registros if r.arquivo.banco == banco]
        if arquivos:
            tipos = pd.Series([a.tipo for a in arquivos]).value_counts().to_dict()
            st.caption(f"{len(arquivos)} arquivos "
                       f"({', '.join(f'{v} {ROTULOS_TIPO.get(k, k)}' for k, v in tipos.items())}), "
                       f"{len(registros)} pagamentos lidos.")
            _avisos_arquivos(banco, tipos)
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

    # O botão fica sempre habilitado: o Streamlit só envia o texto digitado quando o campo perde o
    # foco, então um botão desabilitado ficava travado até a pessoa clicar fora. O clique já
    # entrega o texto pendente; o que faltar é avisado aqui.
    pendentes = [o for o, ok in (("os favorecidos", pagamentos), ("os arquivos do banco", arquivos)) if not ok]
    clicou = st.button("CONFERIR", type="primary", width="stretch", icon=":material/fact_check:")
    if clicou and pendentes:
        st.warning(f"Falta informar {' e '.join(pendentes)}.", icon=":material/warning:")
    elif clicou:
        if modo_rel == "Digitar nomes":
            resultados = motor.pesquisar(pagamentos, registros)   # um resultado por pagamento achado
        else:
            resultados = motor.conferir(pagamentos, registros)
        anteriores = historico.devolucoes_anteriores(resultados)
        historico.salvar(resultados, nome_relatorio, [a.nome for a in arquivos], banco)
        st.session_state["resultados"] = resultados
        st.session_state["resultados_banco"] = banco
        st.session_state["anteriores"] = anteriores
        st.session_state["msg"] = (mensagem.montar_pesquisa(resultados) if modo_rel == "Digitar nomes"
                                   else mensagem.montar(resultados))
        st.toast(f"Conferência {BANCOS[banco]} concluída: {len(resultados)} favorecido(s).",
                 icon=":material/task_alt:")
    elif pendentes:
        st.caption(f"Informe {' e '.join(pendentes)} e clique em CONFERIR.")

    # ------------------------------------------------------------------ resultado
    resultados = st.session_state.get("resultados")
    if resultados:
        banco_res: Banco = st.session_state.get("resultados_banco", banco)
        st.divider()
        st.subheader(f"Resultado {BANCOS[banco_res]}: {len(resultados)} favorecidos")
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

        df = tabela(resultados, banco_res)
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


# ------------------------------------------------------------------ página: Reprocessar
def _limpar_reprocesso() -> None:
    st.session_state.pop("reprocesso_simulado", None)


def _mostrar_resultado_mover(r: reprocessar.ResultadoMover, verbo: str) -> None:
    if r.movidos:
        st.success(f"{len(r.movidos)} arquivo(s) {verbo}: {', '.join(r.movidos)}", icon=":material/check_circle:")
    for nome, motivo in r.pulados:
        st.warning(f"{nome}: {motivo}", icon=":material/warning:")


def pagina_reprocessar() -> None:
    st.subheader("Reprocessar arquivos")
    st.caption("Move arquivos do INBOXENV de volta para o INBOX (mesma subpasta), onde são processados de novo. "
               "Nunca sobrescreve: se já existir no INBOX, o arquivo não é movido.")
    _avisar_reprocesso_feito()
    banco: Banco = st.radio("Banco", list(BANCOS), format_func=BANCOS.__getitem__, horizontal=True,
                            key="reprocesso_banco", on_change=_limpar_reprocesso)
    subpasta = st.text_input("Subpasta" + (" (opcional)" if banco == "tribanco" else " (ex.: GE202255)"),
                             key="reprocesso_subpasta", on_change=_limpar_reprocesso)
    if banco != "tribanco" and not subpasta.strip():
        st.info("Informe a subpasta.", icon=":material/folder_open:")
        return
    origem, destino = reprocessar.caminhos(banco, subpasta)
    st.markdown(f"De `{origem}`  \nPara `{destino or 'NÃO CONFIGURADO'}`")
    if destino is None:
        st.error("Destino do Tribanco ainda não configurado (BASE_TRIBANCO_INBOX em conferencia/reprocessar.py).",
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
        key=f"reprocesso_tabela_{origem}_{de}_{ate}_{trecho}", on_change=_limpar_reprocesso)
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
        historico.registrar_movimentacao(banco, origem, destino, resultado)
        st.session_state.pop("leitura_rede", None)
        _limpar_reprocesso()
        st.session_state["reprocesso_feito"] = resultado
        st.rerun()


def _avisar_reprocesso_feito() -> None:
    if feito := st.session_state.pop("reprocesso_feito", None):
        _mostrar_resultado_mover(feito, "movidos para o INBOX")


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
    st.subheader("Arquivos movidos para reprocessar")
    mov = historico.movimentacoes()
    if mov.empty:
        st.caption("Nenhum por enquanto.")
    else:
        st.dataframe(mov, width="stretch", hide_index=True)


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


# ------------------------------------------------------------------ página: Arquivos UCM
# Só atalhos para preencher o campo: qualquer conta digitada vale.
ATALHOS_UCM: dict[str, str] = {
    "tranap$/santander$/inbox$": "Santander · retornos",
    "tranap$/tribanco$/retorno$": "Tribanco · retornos",
    "fin$/trangl$/mastersf$/pendentes$": "Financeiro · mastersf pendentes",
    "fin$/trangl$/cognos$/processados$": "Financeiro · cognos processados",
}
_CHAVES_RESULTADO_UCM = ("ucm_id", "ucm_pos")


def _md(texto: object) -> str:
    # "$...$" vira fórmula no markdown do Streamlit, e as contas UCM são cheias de "$".
    return str(texto).replace("$", r"\$")


def _limpar_ucm() -> None:
    for chave in _CHAVES_RESULTADO_UCM:
        st.session_state.pop(chave, None)


def _usar_atalho_ucm() -> None:
    if atalho := st.session_state.get("ucm_atalho"):
        st.session_state["ucm_pasta"] = atalho
        st.session_state["ucm_atalho"] = None
        _limpar_ucm()


@st.cache_resource
def _cliente_ucm(versao_classe: int) -> ucm.ClienteUCM:
    # versao_classe = id(ucm.ClienteUCM): quando o Streamlit recarrega o ucm.py, a classe nova tem
    # outro id e o cache cria um cliente novo, em vez de manter um objeto da classe antiga.
    try:
        cred = st.secrets["ucm"]
        return ucm.ClienteUCM(cred["client_id"], cred["client_secret"])
    except (KeyError, FileNotFoundError):
        return ucm.ClienteUCM.do_ambiente()


def _texto(conteudo: bytes) -> str:
    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return conteudo.decode("latin-1")


def _mostrar_documento(cliente: ucm.ClienteUCM, doc: ucm.DocumentoUCM, origem: str) -> None:
    with st.container(border=True):
        criado = f"{doc.criado_em:%d/%m/%Y %H:%M}" if doc.criado_em else "?"
        st.markdown(f"**{_md(doc.titulo)}** · Content ID `{doc.nome}` · document_id `{doc.id}` · {criado} · {doc.tamanho / 1024:,.1f} KB")
        st.caption(_md(f"{origem} · pasta {doc.conta}"))
        chave = f"ucm_conteudo_{doc.id}"
        if st.button("Baixar conteúdo", key=f"baixar_{origem}_{doc.id}", icon=":material/download:"):
            with st.spinner("Baixando do UCM..."):
                st.session_state[chave] = cliente.baixar(doc.id)
        conteudo = st.session_state.get(chave)
        if conteudo is not None:
            linhas = _texto(conteudo).splitlines()
            st.caption(f"{len(conteudo):,} bytes · {len(linhas):,} linhas (mostrando as 50 primeiras)")
            st.code("\n".join(linhas[:50]), language=None)
            st.download_button("Salvar arquivo", conteudo, file_name=PurePosixPath(doc.titulo).name or f"{doc.id}.bin",
                               key=f"salvar_{origem}_{doc.id}", icon=":material/save:")


def _busca_ucm(cliente: ucm.ClienteUCM, pasta: str, subpastas: bool) -> None:
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
            st.warning(_md(f"{buscado} não está em {pasta}.{dica}"), icon=":material/search_off:")


def _busca_por_posicao(cliente: ucm.ClienteUCM, pasta: str, subpastas: bool) -> None:
    with st.form("form_ucm_pos"):
        c1, c2 = st.columns(2)
        pagina_n = c1.number_input("Página", min_value=1, value=4, step=1)
        item_n = c2.number_input("Item na página", min_value=1, max_value=ucm.LIMITE_PAGINA, value=18, step=1)
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


def pagina_ucm() -> None:
    st.subheader("Arquivos UCM")
    st.caption("Busque pelo Content ID, document_id ou nome do arquivo. A busca filtra no próprio UCM, "
               "então encontra o arquivo em qualquer página (a API devolve só 20 por consulta).")
    try:
        cliente = _cliente_ucm(id(ucm.ClienteUCM))
    except ucm.ErroUCM as e:
        st.error(f"{e} Configure [ucm] client_id e client_secret em .streamlit/secrets.toml "
                 "ou as variáveis UCM_CLIENT_ID e UCM_CLIENT_SECRET.", icon=":material/key_off:")
        return
    st.session_state.setdefault("ucm_pasta", "tranap$/tribanco$/retorno$")
    pasta = st.text_input("Pasta (conta UCM)", key="ucm_pasta", on_change=_limpar_ucm,
                          placeholder="ex.: tranap$/tribanco$/retorno$").strip()
    st.pills("Atalhos", list(ATALHOS_UCM), format_func=ATALHOS_UCM.__getitem__, key="ucm_atalho",
             on_change=_usar_atalho_ucm, label_visibility="collapsed")
    subpastas = st.toggle("Incluir subpastas (processed$, error$...), igual à tela do UCM", value=True,
                          key="ucm_subpastas", on_change=_limpar_ucm)
    if not pasta:
        st.info("Digite a pasta (conta UCM) ou escolha um atalho.", icon=":material/folder_open:")
        return
    try:
        _busca_ucm(cliente, pasta, subpastas)
        with st.expander("Pegar pela posição na tela do UCM (página e item)"):
            _busca_por_posicao(cliente, pasta, subpastas)
    except ValueError as e:
        st.error(_md(e), icon=":material/error:")
    except ucm.ErroUCM as e:
        st.error(_md(f"Erro no UCM/OIC: {e}"), icon=":material/cloud_off:")


# ------------------------------------------------------------------ entrada
st.logo(str(ASSETS / "techone_banner.jpg"), icon_image=str(ASSETS / "techone_icon.jpg"))

pagina = st.navigation([
    st.Page(pagina_conferir, title="Conferir", icon=":material/fact_check:", default=True),
    st.Page(pagina_reprocessar, title="Reprocessar", icon=":material/replay:"),
    st.Page(pagina_historico, title="Histórico", icon=":material/history:"),
    st.Page(pagina_codigos, title="Códigos de ocorrência", icon=":material/menu_book:"),
    st.Page(pagina_ucm, title="Arquivos UCM", icon=":material/cloud_download:"),
])
st.title("Conferência de Pagamentos")

pagina.run()
