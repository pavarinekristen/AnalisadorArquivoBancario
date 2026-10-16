"""Página Sobre / Diagnóstico: versão, configuração carregada e pacote para o suporte."""
from __future__ import annotations

import io
import platform
import sys
import zipfile
from datetime import datetime

import streamlit as st

import conferencia
from conferencia import config, log


def _pacote_diagnostico() -> bytes:
    """Zip com o log (CPF/CNPJ já mascarado) e a configuração (que não guarda senha)."""
    buf = io.BytesIO()
    cfg = config.atual()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("versao.txt", f"Conferência de Pagamentos {conferencia.__version__}\n"
                                 f"Python {sys.version}\nStreamlit {st.__version__}\n{platform.platform()}\n")
        if cfg.origem and cfg.origem.exists():
            z.writestr(f"config/{cfg.origem.name}", cfg.origem.read_text(encoding="utf-8"))
        for arq in sorted(log.PASTA.glob("app.log*")):
            z.writestr(f"logs/{arq.name}", log.mascarar_documento(arq.read_text(encoding="utf-8", errors="replace")))
    return buf.getvalue()


def pagina() -> None:
    cfg = config.atual()
    st.subheader("Sobre")
    st.markdown(f"**{cfg.marca.nome}** versão `{conferencia.__version__}`  \n"
                f"Python `{platform.python_version()}` · Streamlit `{st.__version__}`")
    st.markdown(f"Configuração: `{cfg.origem}`  \nLog: `{log.ARQUIVO}`  \n"
                f"Bancos ativos: {', '.join(cfg.bancos_ativos)} · Retenção do histórico: {cfg.retencao_dias} dias")
    if cfg.e_exemplo:
        st.warning("Usando a configuração de EXEMPLO. Copie config/cliente.exemplo.yaml para config/cliente.yaml "
                   "e preencha as pastas do cliente.", icon=":material/warning:")
    st.download_button("Exportar diagnóstico (para o suporte)", _pacote_diagnostico(),
                       file_name=f"diagnostico_{datetime.now():%Y%m%d_%H%M}.zip", mime="application/zip",
                       icon=":material/support:")
    st.caption("O pacote leva o log (com CPF/CNPJ mascarado) e a configuração. Nenhuma senha vai junto.")
