"""Formatação para a tela e para o Excel exportado."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from conferencia import bancos, cnab240, motor
from conferencia.log import mascarar_documento, mascarar_valor
from conferencia.modelos import Banco, Resultado


def fmt_valor(v: float | None) -> str:
    return "" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_data(d: str) -> str:
    return f"{d[0:2]}/{d[2:4]}/{d[4:8]}" if len(d) == 8 and d.isdigit() else d


def md(texto: object) -> str:
    # "$...$" vira fórmula no markdown do Streamlit (contas UCM e nomes podem ter "$"); [..](..) vira link.
    return str(texto).replace("$", r"\$").replace("[", r"\[").replace("]", r"\]")


def documento(cpf_cnpj: str, completo: bool) -> str:
    return cpf_cnpj if completo else mascarar_valor(cpf_cnpj)


def texto(t: str, documentos_completos: bool) -> str:
    return t if documentos_completos else mascarar_documento(t)


def tabela(resultados: list[Resultado], banco: Banco = "santander", documentos_completos: bool = False) -> pd.DataFrame:
    perfil = bancos.perfil(banco)
    return pd.DataFrame([{
        "Favorecido": r.pagamento.favorecido,
        "CPF/CNPJ": documento(r.pagamento.cpf_cnpj, documentos_completos),
        "Documento": r.pagamento.documento,
        "Valor": fmt_valor(r.pagamento.valor),
        "Status": r.rotulo,
        **perfil.colunas_tela(r),
        "Código": " ".join(r.codigos),
        "Significado": motor.descrever_varios([c for cod in r.codigos for c in cnab240.ocorrencias(cod)]),
        "Arquivo": r.arquivo_status,
        "Nome no banco": r.registros[-1].nome if r.registros else "",
        "Empresa pagadora": r.registros[-1].arquivo.pagador if r.registros else "",
        "Sistema diz pago?": "Sim — confirmar com o banco" if r.alerta_sistema else "",
        "Obs.": texto(" | ".join(r.observacoes), documentos_completos),
    } for r in resultados])


# Guardado para não refazer a cada clique: o Streamlit roda a página inteira em toda interação.
@st.cache_data(show_spinner=False, max_entries=5)
def excel(df: pd.DataFrame, aba: str = "Conferência") -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name=aba)
    return buf.getvalue()
