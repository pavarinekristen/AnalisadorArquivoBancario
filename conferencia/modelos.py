from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Literal

TipoArquivo = Literal["MOV", "CRI", "REL", "RETORNO", "OUTRO"]
Segmento = Literal["A", "J"]


class Status(StrEnum):
    PAGO = "pago"
    DEVOLUCAO = "devolucao"
    REJEITADO = "rejeitado"
    ACEITO_NAO_PAGO = "aceito_nao_pago"
    OUTRO_PAGAMENTO = "outro_pagamento"
    NAO_ENVIADO = "nao_enviado"


PAGO = Status.PAGO
DEVOLUCAO = Status.DEVOLUCAO
REJEITADO = Status.REJEITADO
ACEITO_NAO_PAGO = Status.ACEITO_NAO_PAGO
OUTRO_PAGAMENTO = Status.OUTRO_PAGAMENTO
NAO_ENVIADO = Status.NAO_ENVIADO

ROTULOS: dict[Status, str] = {
    PAGO: "Pago",
    DEVOLUCAO: "Devolução",
    REJEITADO: "Rejeitado pelo banco",
    ACEITO_NAO_PAGO: "Aceito, ainda não pago",
    OUTRO_PAGAMENTO: "Outro pagamento",
    NAO_ENVIADO: "Não enviado",
}


@dataclass(slots=True)
class ArquivoBanco:
    nome: str
    tipo: TipoArquivo
    data: date | None
    lote: int | None
    empresa: str | None

    @property
    def ordem(self) -> tuple[date, int, str]:
        return (self.data or date.min, self.lote or 0, self.nome)


@dataclass(slots=True)
class RegistroBanco:
    arquivo: ArquivoBanco
    segmento: Segmento
    nome: str
    cpf_cnpj: str
    documento: str
    data: str
    valor: float
    ocorrencias: list[str] = field(default_factory=list)

    @property
    def ocorrencia_bruta(self) -> str:
        return "".join(self.ocorrencias)


@dataclass(slots=True)
class Pagamento:
    favorecido: str
    cpf_cnpj: str = ""
    documento: str = ""
    valor: float | None = None
    data: str = ""
    metodo: str = ""
    referencia: str = ""
    op: str = ""
    situacao_sistema: str = ""
    retorno_sistema: str = ""
    situacao_banco: str = ""


@dataclass(slots=True)
class Resultado:
    pagamento: Pagamento
    status: Status
    registros: list[RegistroBanco] = field(default_factory=list)
    codigos: list[str] = field(default_factory=list)
    arquivo_status: str = ""
    match_fraco: bool = False
    observacoes: list[str] = field(default_factory=list)
    alerta_sistema: bool = False

    @property
    def rotulo(self) -> str:
        return ROTULOS[self.status]
