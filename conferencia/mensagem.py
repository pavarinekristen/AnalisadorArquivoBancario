"""Resumo da conferência: texto técnico e direto, para bater o olho e saber a situação de cada favorecido.

Problemas primeiro (devolução, rejeição, verificar, não enviado), pago por último. Cada linha traz o favorecido,
o valor, o código com o significado e o arquivo onde foi encontrado.
"""
from __future__ import annotations

from datetime import datetime

from . import cnab240, motor
from .modelos import (ACEITO_NAO_PAGO, BANCOS, DEVOLUCAO, NAO_ENVIADO, OUTRO_PAGAMENTO, PAGO, REJEITADO, ROTULOS,
                      VERIFICAR, Banco, Resultado, Status)

ORDEM: list[Status] = [DEVOLUCAO, REJEITADO, VERIFICAR, NAO_ENVIADO, ACEITO_NAO_PAGO, OUTRO_PAGAMENTO, PAGO]
_PROBLEMAS = frozenset(ORDEM) - {PAGO}


def _valor_br(v: float | None) -> str:
    return "valor não informado" if v is None else (
        "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))


def arquivo_curto(nome: str) -> str:
    return nome.rsplit(".", 1)[0] if nome.upper().endswith((".TXT", ".DAT")) else nome


def _codigo(r: Resultado) -> str:
    codigos = [c for c in r.codigos if c]
    if not codigos:
        return ""
    significado = motor.descrever_varios([c for cod in codigos for c in cnab240.ocorrencias(cod)])
    return f"{' '.join(codigos)}: {significado}"


def _linha(r: Resultado) -> str:
    partes = [r.pagamento.favorecido, _valor_br(r.pagamento.valor)]
    if r.status == NAO_ENVIADO:
        partes.append("não está em nenhum arquivo do banco")
    elif r.status == OUTRO_PAGAMENTO:
        partes.append("aparece nos arquivos com outro valor, data ou documento")
    else:
        if codigo := _codigo(r):
            partes.append(codigo)
        if r.arquivo_status:
            partes.append(arquivo_curto(r.arquivo_status))
    linha = "- " + " | ".join(partes)
    if r.match_fraco:
        linha += " (confirmar: achado sem documento/CPF)"
    return linha


def _juntar(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _arquivos(resultados: list[Resultado]) -> list[str]:
    """Seção só dos arquivos: em qual arquivo cada favorecido foi encontrado."""
    por_arquivo: dict[str, list[str]] = {}
    for r in resultados:
        if r.arquivo_status:
            por_arquivo.setdefault(arquivo_curto(r.arquivo_status), []).append(r.pagamento.favorecido)
    if not por_arquivo:
        return ["ARQUIVOS", "Nenhum favorecido foi encontrado nos arquivos do banco."]
    nomes = sorted(por_arquivo)
    frase = (f"Favorecidos encontrados no arquivo {nomes[0]}." if len(nomes) == 1
             else f"Favorecidos encontrados nos arquivos {_juntar(nomes)}.")
    linhas = ["ARQUIVOS", frase]
    if len(nomes) > 1:
        linhas += [f"- {a}: {', '.join(dict.fromkeys(por_arquivo[a]))}" for a in nomes]
    return linhas


def _totais(grupos: dict[Status, list[Resultado]]) -> str:
    return ", ".join(f"{len(grupos[s])} {ROTULOS[s].lower()}" for s in ORDEM if s in grupos)


def resumo(resultados: list[Resultado], banco: Banco | None = None, agora: datetime | None = None,
           anteriores: dict[int, int] | None = None) -> str:
    if not resultados:
        return ""
    agora = agora or datetime.now()
    grupos: dict[Status, list[Resultado]] = {}
    for r in resultados:
        grupos.setdefault(r.status, []).append(r)

    titulo = "Resumo da conferência" + (f" {BANCOS[banco]}" if banco else "") + f" ({agora:%d/%m/%Y %H:%M})"
    linhas = [titulo, f"{len(resultados)} favorecido(s): {_totais(grupos)}."]
    if not _PROBLEMAS & grupos.keys():
        linhas.append("Tudo certo: todos pagos.")
    linhas += ["", *_arquivos(resultados)]

    for status in ORDEM:
        if status in grupos:
            linhas += ["", f"{ROTULOS[status].upper()} ({len(grupos[status])})", *map(_linha, grupos[status])]

    atencao = []
    if alertas := [r.pagamento.favorecido for r in resultados if r.alerta_sistema]:
        atencao.append(f"- Sistema diz pago, mas o banco não pagou: {', '.join(dict.fromkeys(alertas))}.")
    for i, n in (anteriores or {}).items():
        atencao.append(f"- {resultados[i].pagamento.favorecido} já teve {n} devolução(ões) em conferências anteriores.")
    if atencao:
        linhas += ["", "ATENÇÃO", *atencao]
    return "\n".join(linhas)
