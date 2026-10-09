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
            esta="está" if len(rs) == 1 else "estão", foi="foi" if len(rs) == 1 else "foram",
            s="" if len(rs) == 1 else "s", m="" if len(rs) == 1 else "m",
        )

    if len(grupos) == 1:
        status, rs = next(iter(grupos.items()))
        return modelos["todos"][status].format(**campos(rs))

    linhas = [modelos["abertura"].format(**campos(resultados))]
    for status in _ORDEM:
        if status in grupos:
            linhas.append(modelos["grupos"][status].format(**campos(grupos[status])))
    return "\n\n".join(linhas)


def _valor_br(v) -> str:
    return "-" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def montar_pesquisa(resultados: list[Resultado], agora: datetime | None = None,
                    caminho_modelos: Path = _MODELOS) -> str:
    """Mensagem da pesquisa por nomes: se todos deram devolução, uma frase só; senão, uma linha por pagamento."""
    if not resultados:
        return ""
    nomes = list(dict.fromkeys(r.pagamento.favorecido for r in resultados))
    um_por_nome = len(nomes) == len(resultados)
    if um_por_nome and len({r.status for r in resultados}) == 1:
        return montar(resultados, agora, caminho_modelos)

    with open(caminho_modelos, encoding="utf-8") as f:
        modelos = yaml.safe_load(f)["pesquisa"]
    linhas = [modelos["abertura"].format(saudacao=saudacao(agora))]
    for r in resultados:
        linhas.append(modelos[r.status].format(
            nome=r.pagamento.favorecido, codigos=" ".join(r.codigos),
            arquivo=_arquivo_curto(r.arquivo_status), valor=_valor_br(r.pagamento.valor)))
    return "\n".join(linhas)
