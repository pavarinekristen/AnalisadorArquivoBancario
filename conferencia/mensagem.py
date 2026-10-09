"""Monta a mensagem pro chefe a partir dos modelos em regras/mensagens.yaml."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from .modelos import (ACEITO_NAO_PAGO, DEVOLUCAO, NAO_ENVIADO, OUTRO_PAGAMENTO, PAGO, REJEITADO,
                      Resultado)

_MODELOS = Path(__file__).resolve().parent.parent / "regras" / "mensagens.yaml"
_ORDEM = [DEVOLUCAO, REJEITADO, ACEITO_NAO_PAGO, OUTRO_PAGAMENTO, PAGO, NAO_ENVIADO]


def saudacao(agora: datetime | None = None) -> str:
    h = (agora or datetime.now()).hour
    return "Bom dia" if h < 12 else "Boa tarde" if h < 18 else "Boa noite"


def _juntar(itens: list[str]) -> str:
    itens = list(dict.fromkeys(i for i in itens if i))
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _arquivo_curto(nome: str) -> str:
    return nome.rsplit(".", 1)[0] if nome.upper().endswith(".TXT") else nome


def montar(resultados: list[Resultado], agora: datetime | None = None,
           caminho_modelos: Path = _MODELOS) -> str:
    if not resultados:
        return ""
    with open(caminho_modelos, encoding="utf-8") as f:
        modelos = yaml.safe_load(f)

    grupos: dict[str, list[Resultado]] = {}
    for r in resultados:
        grupos.setdefault(r.status, []).append(r)

    def campos(rs: list[Resultado]) -> dict:
        return dict(
            saudacao=saudacao(agora), n=len(rs), total=len(resultados),
            arquivos=_juntar(sorted({_arquivo_curto(r.arquivo_status) for r in rs})),
            codigos=_juntar(sorted({c for r in rs for c in r.codigos})),
            nomes=_juntar([r.pagamento.favorecido for r in rs]),
        )

    if len(grupos) == 1:
        status, rs = next(iter(grupos.items()))
        return modelos["todos"][status].format(**campos(rs))

    linhas = [modelos["abertura"].format(**campos(resultados))]
    for status in _ORDEM:
        if status in grupos:
            linhas.append(modelos["grupos"][status].format(**campos(grupos[status])))
    return "\n\n".join(linhas)
