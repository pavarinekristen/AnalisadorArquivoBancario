"""Página Códigos de ocorrência (regras/ocorrencias.yaml)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from conferencia import motor, relatorio


def pagina() -> None:
    st.subheader("Tabela de ocorrências")
    st.caption("Fonte: regras/ocorrencias.yaml (dá para editar e acrescentar códigos; vale na hora). "
               "Primeiro código começando com Z é sempre devolução, com qualquer complemento.")
    motor.recarregar_ocorrencias()
    busca = st.text_input("Buscar código ou texto").strip().upper()
    df = pd.DataFrame([{"Código": k, "Categoria": v["categoria"], "Descrição": v["descricao"]}
                       for k, v in motor.OCORRENCIAS.items()])
    if busca:
        df = df[df.apply(lambda r: busca in r["Código"] or busca in relatorio.sem_acento(r["Descrição"]), axis=1)]
    st.dataframe(df, width="stretch", hide_index=True)
