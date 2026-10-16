"""Log do programa em dados/logs/app.log (gira em 5 arquivos de 5 MB). CPF/CNPJ sempre mascarado."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "dados" / "logs"
ARQUIVO = PASTA / "app.log"
_NOME = "conferencia"


def mascarar_documento(texto: str) -> str:
    """Deixa só o miolo de CPF (11) e CNPJ (14 dígitos) à mostra: 11222333000181 -> ***223330001**."""
    def mascara(m: re.Match[str]) -> str:
        d = m.group(0)
        return "***" + d[3:-2] + "**"
    # 10/13 dígitos: CPF/CNPJ que perdeu o zero da frente (o programa guarda sem zeros à esquerda).
    return re.sub(r"(?<!\d)(\d{10,11}|\d{13,14})(?!\d)", mascara, texto)


def mascarar_valor(cpf_cnpj: str) -> str:
    """Um CPF/CNPJ só, para a tela e o Excel exportado."""
    v = cpf_cnpj.strip()
    return "***" + v[3:-2] + "**" if len(v) > 6 else v


class _FiltroMascara(logging.Filter):
    def filter(self, registro: logging.LogRecord) -> bool:
        registro.msg = mascarar_documento(registro.getMessage())
        registro.args = ()
        return True


def obter() -> logging.Logger:
    log = logging.getLogger(_NOME)
    if not log.handlers:   # o Streamlit reexecuta a página: configura uma vez só
        log.setLevel(logging.INFO)
        log.propagate = False
        try:
            PASTA.mkdir(parents=True, exist_ok=True)
            h: logging.Handler = RotatingFileHandler(ARQUIVO, maxBytes=5 * 1024 * 1024, backupCount=5,
                                                     encoding="utf-8")
        except OSError:
            h = logging.NullHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        h.addFilter(_FiltroMascara())
        log.addHandler(h)
    return log
