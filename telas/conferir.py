"""Página Conferir: relatório x arquivos do banco."""
from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from conferencia import (area_transferencia, bancos, cnab240, config, historico, log, mensagem, motor, ntedi,
                         relatorio)
from conferencia.modelos import (ACEITO_NAO_PAGO, BANCOS, DEVOLUCAO, NAO_ENVIADO, OUTRO_PAGAMENTO, PAGO, REJEITADO,
                                 ROTULOS, VERIFICAR, ArquivoBanco, Banco, Pagamento, RegistroBanco)
from telas import estilo
from telas.componentes import escolher_subpasta
from telas.formatos import documento, excel, fmt_data, fmt_valor, md, tabela, texto

CORES_HEX = {PAGO: "#16A34A", DEVOLUCAO: "#D97706", REJEITADO: "#DC2626", NAO_ENVIADO: "#DC2626",
             ACEITO_NAO_PAGO: "#0059A9", OUTRO_PAGAMENTO: "#6B7280", VERIFICAR: "#7C3AED"}
ORDEM_CARDS = [DEVOLUCAO, PAGO, REJEITADO, VERIFICAR, NAO_ENVIADO, ACEITO_NAO_PAGO, OUTRO_PAGAMENTO]
_VALIDADE_LEITURA = 300   # segundos

Lidos = tuple[list[ArquivoBanco], list[RegistroBanco]]


@st.cache_data(show_spinner=False, max_entries=10)
def _ler_excel(conteudo: bytes) -> dict[str, list[Pagamento]]:
    return relatorio.ler_excel(conteudo)


def escolher_lista(nome_arquivo: str, conteudo: bytes) -> tuple[list[Pagamento], str]:
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


def _limpar_resultado() -> None:
    for chave in ("resultados", "resultados_banco", "anteriores", "msg", "colados"):
        st.session_state.pop(chave, None)


def datas_validas(pagamentos: Iterable[Pagamento]) -> list[date]:
    """Datas do relatório que existem de fato (31/02 digitado não derruba a tela)."""
    datas = []
    for p in pagamentos:
        try:
            datas.append(datetime.strptime(p.data, "%d%m%Y").date())
        except ValueError:
            continue
    return datas


def _escolher_banco() -> Banco:
    ativos: list[Banco] = [b for b in BANCOS if b in config.atual().bancos_ativos]
    banco: Banco = st.radio("Qual banco vai conferir?", ativos, format_func=BANCOS.__getitem__,
                            horizontal=True, key="banco", on_change=_limpar_resultado)
    perfil = bancos.perfil(banco)
    st.markdown(f'<div class="banco-ativo banco-{banco}">'
                f'<div class="banco-nome">Conferindo: {perfil.nome} (banco {perfil.codigo})</div>'
                f'<div class="banco-detalhe">Arquivos lidos: {perfil.descricao_arquivos}. '
                f'Arquivos de outro banco são ignorados.</div></div>', unsafe_allow_html=True)
    return banco


def _ler_rede(banco: Banco, tipo: ntedi.Tipo, subpasta: str, de: date, ate: date) -> ntedi.ResultadoNtedi:
    # O Streamlit roda a página de novo a cada clique e a pasta de rede é lenta, então guarda a
    # última leitura por 5 minutos (o botão "Atualizar pasta" força ler de novo; mesmo relendo, o
    # cache por arquivo de cnab240 só baixa o que é novo ou mudou). Só guarda leitura que achou arquivos e
    # não teve aviso: leitura vazia ou com erro (VPN desligada, login não feito) é sempre refeita.
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


def _pasta_rede(banco: Banco, datas_relatorio: list[date]) -> Lidos:
    if banco == "tribanco":
        st.caption(f"Pasta do Tribanco: `{ntedi.BASE_TRIBANCO}`")
        tipo_pasta: ntedi.Tipo = "retorno"
        subpasta = escolher_subpasta("Subpasta", (ntedi.BASE_TRIBANCO,), key="subpasta_tribanco", opcional=True)
    else:
        tipo_pasta = st.radio("Retorno ou remessa?", ["retorno", "remessa"], horizontal=True,
                              format_func=lambda t: f"{ntedi.ROTULOS[t]} ({'INBOXENV' if t == 'retorno' else 'SENTBOX'})")
        base = ntedi.BASE_RETORNO if tipo_pasta == "retorno" else ntedi.BASE_REMESSA
        subpasta = escolher_subpasta("Subpasta", (base,), key="subpasta_santander")
    col_de, col_ate = st.columns(2)
    # Com datas no relatório, a janela começa um pouco antes do pagamento mais antigo (a devolução vem depois).
    de_padrao = min(datas_relatorio) - timedelta(days=2) if datas_relatorio else date.today() - timedelta(days=7)
    de = col_de.date_input("De", value=de_padrao)
    ate = col_ate.date_input("Até", value=max(date.today(), de_padrao))
    if datas_relatorio and min(datas_relatorio) < de:
        st.warning(f"O relatório tem pagamento de {min(datas_relatorio):%d/%m/%Y}, antes do \"De\". Arquivos "
                   "anteriores não serão lidos e esse pagamento pode aparecer como não enviado.",
                   icon=":material/warning:")
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


def _caminho_manual() -> Lidos:
    pasta = st.text_input("Caminho da pasta", placeholder=r"ex.: Downloads\arquivos\FINAL24")
    if not pasta:
        return [], []
    caminho = Path(pasta.strip().strip('"')).expanduser()
    if not config.caminho_permitido(caminho):
        st.error("Essa pasta não está liberada. Use uma pasta dentro de: "
                 + ", ".join(str(p) for p in config.atual().pastas_permitidas)
                 + " (lista em config/cliente.yaml, pastas_permitidas).", icon=":material/block:")
        return [], []
    with st.spinner("Lendo arquivos..."):
        lidos = ntedi.ler_pasta(caminho, "Pasta")
    for aviso in lidos.avisos:
        st.warning(aviso, icon=":material/warning:")
    return lidos.arquivos, lidos.registros


def _ler_arquivos(nomes_e_conteudos: Iterable[tuple[str, bytes]]) -> Lidos:
    arquivos, registros = [], []
    for nome, conteudo in nomes_e_conteudos:
        arq, regs = cnab240.ler_bytes(nome, conteudo)
        if arq.tipo != "OUTRO":
            arquivos.append(arq)
            registros.extend(regs)
    return arquivos, registros


def _colar() -> None:
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


def _quem_conferir(excel_colado: Path | None) -> tuple[list[Pagamento], str, str]:
    estilo.passo(1, "Quem conferir")
    pagamentos: list[Pagamento] = []
    nome_relatorio = ""
    opcoes = ["Digitar nomes", "Excel", "Colar lista do sistema"]
    modo = st.radio("Como vai informar os favorecidos?", opcoes, horizontal=True, index=1 if excel_colado else 0)
    if modo == "Digitar nomes":
        digitado = st.text_area(
            "Um por linha: nome (inteiro ou parte) ou CPF/CNPJ do favorecido ou da empresa pagadora, "
            "ou nº do documento. "
            "Se quiser, acrescente o valor (ex: 1.234,56) ou a data (ex: 07/10/2026) para filtrar.",
            height=220, placeholder="FULANO DE TAL DA SILVA\nCICLANO 11.222.333/0001-81\n"
                                    "BELTRANO SOUZA 1.234,56\n100009000000001")
        if digitado.strip():
            pagamentos, nome_relatorio = relatorio.ler_nomes_digitados(digitado), "nomes digitados"
    elif modo == "Excel":
        if excel_colado:
            st.success(f"Excel colado: {excel_colado.name}", icon=":material/check_circle:")
            pagamentos, nome_relatorio = escolher_lista(excel_colado.name, excel_colado.read_bytes())
        else:
            xl = st.file_uploader("Arraste o Excel do relatório", type=["xlsx", "xlsm"])
            if xl:
                pagamentos, nome_relatorio = escolher_lista(xl.name, xl.getvalue())
    else:
        colado = st.text_area("Cole aqui a lista do sistema (Situação: Com Erro)", height=220)
        if colado.strip():
            pagamentos, nome_relatorio = relatorio.ler_texto_colado(colado), "lista colada"
            if not pagamentos:
                st.warning("Não reconheci nenhum pagamento no texto colado.", icon=":material/warning:")
    if pagamentos:
        st.caption(f"{len(pagamentos)} favorecido(s) para conferir.")
    return pagamentos, nome_relatorio, modo


def _arquivos_do_banco(banco: Banco, colados: list[Path], pagamentos: list[Pagamento]) -> Lidos:
    perfil = bancos.perfil(banco)
    estilo.passo(2, f"Arquivos do {perfil.nome}")
    arquivos: list[ArquivoBanco] = []
    registros: list[RegistroBanco] = []
    if colados:
        arquivos, registros = _ler_arquivos((c.name, c.read_bytes()) for c in colados)
        st.success(f"{len(colados)} arquivos colados.", icon=":material/check_circle:")
    else:
        modo = st.radio("Como vai informar os arquivos?",
                        ["Pasta padrão (rede)", "Arrastar arquivos", "Caminho manual (avançado)"], horizontal=True)
        if modo == "Pasta padrão (rede)":
            arquivos, registros = _pasta_rede(banco, datas_validas(pagamentos))
        elif modo == "Arrastar arquivos":
            ups = st.file_uploader(perfil.rotulo_upload, accept_multiple_files=True)
            arquivos, registros = _ler_arquivos((u.name, u.getvalue()) for u in ups or [])
        else:
            arquivos, registros = _caminho_manual()
    outro_banco = [a for a in arquivos if a.banco != banco]
    if outro_banco:
        st.warning(f"{len(outro_banco)} arquivo(s) de outro banco ignorado(s): você está conferindo o "
                   f"{perfil.nome}. Troque o banco lá em cima se quiser conferir esses.", icon=":material/warning:")
        arquivos = [a for a in arquivos if a.banco == banco]
        registros = [r for r in registros if r.arquivo.banco == banco]
    for aviso in (a for arq in arquivos for a in arq.avisos):
        st.warning(aviso, icon=":material/warning:")
    if arquivos:
        tipos = pd.Series([a.tipo for a in arquivos]).value_counts().to_dict()
        st.caption(f"{len(arquivos)} arquivos "
                   f"({', '.join(f'{v} {perfil.rotulos_tipo.get(k, k)}' for k, v in tipos.items())}), "
                   f"{len(registros)} pagamentos lidos.")
        for nivel, aviso in perfil.avisos_arquivos(tipos):
            if nivel == "warning":
                st.warning(aviso, icon=":material/warning:")
            elif nivel == "info":
                st.info(aviso, icon=":material/info:")
            else:
                st.caption(aviso)
        # Só um lembrete, não impede a conferência: às vezes o banco realmente não gera o lote.
        # Se o relatório tem datas, só interessam arquivos da data do pagamento em diante (a devolução chega depois).
        datas = datas_validas(pagamentos)
        relevantes = [a for a in arquivos if not datas or (a.data and a.data >= min(datas))]
        faltando = cnab240.lotes_faltando(relevantes)
        if faltando:
            st.caption("Obs.: lote(s) fora da sequência, confira se não faltou baixar algum: " + "; ".join(
                f"{grupo} → {', '.join(f'{l:02d}' for l in lotes)}" for grupo, lotes in faltando.items()))
    return arquivos, registros


def _executar(banco: Banco, modo: str, pagamentos: list[Pagamento], nome_relatorio: str,
              arquivos: list[ArquivoBanco], registros: list[RegistroBanco]) -> None:
    pesquisa = modo == "Digitar nomes"
    resultados = motor.pesquisar(pagamentos, registros) if pesquisa else motor.conferir(pagamentos, registros)
    anteriores: dict[int, int] = {}
    try:
        anteriores = historico.devolucoes_anteriores(resultados)
        historico.salvar(resultados, nome_relatorio, [a.nome for a in arquivos], banco)
    except Exception as e:  # base travada/corrompida: mostra o resultado mesmo assim
        log.obter().exception("falha ao gravar histórico")
        st.warning(f"Conferência feita, mas não consegui gravar no histórico: {e}", icon=":material/warning:")
    totais = pd.Series([r.status.value for r in resultados]).value_counts().to_dict()
    log.obter().info("conferência %s: %d favorecido(s), %d arquivo(s), relatório %r, totais %s",
                     banco, len(resultados), len(arquivos), nome_relatorio, totais)
    st.session_state["resultados"] = resultados
    st.session_state["resultados_banco"] = banco
    st.session_state["anteriores"] = anteriores
    st.session_state["msg"] = mensagem.resumo(resultados, banco, anteriores=anteriores)
    st.toast(f"Conferência {BANCOS[banco]} concluída: {len(resultados)} favorecido(s).", icon=":material/task_alt:")


def _mostrar_resultado(banco: Banco) -> None:
    resultados = st.session_state.get("resultados")
    if not resultados:
        return
    banco_res: Banco = st.session_state.get("resultados_banco", banco)
    st.divider()
    st.subheader(f"Resultado {BANCOS[banco_res]}: {len(resultados)} favorecidos")
    cont = pd.Series([r.status for r in resultados]).value_counts()
    cards = "".join(
        f'<div class="kpi-card" style="border-left-color:{CORES_HEX[status]}">'
        f'<div class="kpi-valor">{int(cont.get(status, 0))}</div>'
        f'<div class="kpi-rotulo"><span class="kpi-dot" style="background:{CORES_HEX[status]}"></span>'
        f'{ROTULOS[status]}</div></div>'
        for status in ORDEM_CARDS)
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)

    alertas = sum(r.alerta_sistema for r in resultados)
    if alertas:
        st.error(f"{alertas} favorecido(s) aparecem como pagos no sistema, mas o banco não pagou.",
                 icon=":material/error:")
    for i, n in st.session_state.get("anteriores", {}).items():
        st.warning(f"Reincidência: {md(resultados[i].pagamento.favorecido)} já teve {n} devolução(ões) "
                   "em conferências anteriores.", icon=":material/warning:")

    # LGPD: CPF/CNPJ mascarado por padrão, na tela e no Excel exportado.
    completos = st.toggle("Mostrar CPF/CNPJ completos", key="documentos_completos",
                          on_change=lambda: log.obter().info("operador alternou CPF/CNPJ completos na tela"))
    df = tabela(resultados, banco_res, completos)
    filtro = st.multiselect("Filtrar status", sorted(df["Status"].unique()), placeholder="Todos os status")
    st.dataframe(df[df["Status"].isin(filtro)] if filtro else df, width="stretch", hide_index=True)

    escolhido = st.selectbox(
        "Ver detalhes de:", list(range(len(resultados))), index=None,
        placeholder="Escolha um favorecido para ver em quais arquivos ele aparece",
        format_func=lambda i: f"{resultados[i].pagamento.favorecido} — {fmt_valor(resultados[i].pagamento.valor)} — "
                              f"{resultados[i].rotulo}")
    if escolhido is not None:
        r = resultados[escolhido]
        p = r.pagamento
        st.markdown(f"**{md(p.favorecido)}** — {r.rotulo}  \n"
                    f"Relatório: doc `{p.documento or '-'}` · CPF/CNPJ `{documento(p.cpf_cnpj, completos) or '-'}` · "
                    f"valor {fmt_valor(p.valor)} · data {fmt_data(p.data) or '-'} · OP {md(p.op or '-')}  \n"
                    f"Retorno no relatório: {md(p.retorno_sistema or '-')}")
        if r.registros:
            st.dataframe(pd.DataFrame([{
                "Arquivo": x.arquivo.nome, "Tipo": x.arquivo.tipo, "Seg.": x.segmento,
                "Nome no banco": x.nome, "CPF/CNPJ": documento(x.cpf_cnpj, completos), "Documento": x.documento,
                "Data": fmt_data(x.data), "Valor": fmt_valor(x.valor),
                "Ocorrência": x.ocorrencia_bruta,
                "Significado": motor.descrever_varios(x.ocorrencias),
            } for x in r.registros]), width="stretch", hide_index=True)
        else:
            st.info("Não aparece em nenhum arquivo.", icon=":material/info:")
        for o in r.observacoes:
            st.caption(f"• {md(texto(o, completos))}")

    st.subheader("Resumo da conferência")
    st.caption("Clique no ícone de copiar no canto da caixa.")
    st.code(st.session_state["msg"], language=None, wrap_lines=True)

    st.download_button("Exportar resultado (Excel)", excel(df), file_name="conferencia.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def pagina() -> None:
    banco = _escolher_banco()
    _colar()
    colados: list[Path] = st.session_state.get("colados", [])
    excel_colado = next((c for c in colados if area_transferencia.e_excel(c)), None)
    banco_colados = [c for c in colados if not area_transferencia.e_excel(c)]

    col1, col2 = st.columns(2)
    with col1:
        pagamentos, nome_relatorio, modo = _quem_conferir(excel_colado)
    with col2:
        arquivos, registros = _arquivos_do_banco(banco, banco_colados, pagamentos)

    # O botão fica sempre habilitado: o Streamlit só envia o texto digitado quando o campo perde o
    # foco, então um botão desabilitado ficava travado até a pessoa clicar fora. O clique já
    # entrega o texto pendente; o que faltar é avisado aqui.
    pendentes = [o for o, ok in (("os favorecidos", pagamentos), ("os arquivos do banco", arquivos)) if not ok]
    clicou = st.button("CONFERIR", type="primary", width="stretch", icon=":material/fact_check:")
    if clicou and pendentes:
        st.warning(f"Falta informar {' e '.join(pendentes)}.", icon=":material/warning:")
    elif clicou:
        _executar(banco, modo, pagamentos, nome_relatorio, arquivos, registros)
    elif pendentes:
        st.caption(f"Informe {' e '.join(pendentes)} e clique em CONFERIR.")

    _mostrar_resultado(banco)
