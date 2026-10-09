"""Estruturas de dados usadas em toda a conferência."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class ArquivoBanco:
    nome: str
    tipo: str              # MOV, CRI, REL, RETORNO, OUTRO
    data: date | None      # data do nome do arquivo (DDMMAA)
    lote: int | None       # NN do nome do arquivo
    empresa: str | None    # COD do nome (ex: EZN1)

    @property
    def ordem(self) -> tuple:
        return (self.data or date.min, self.lote or 0, self.nome)


@dataclass
class RegistroBanco:
    arquivo: ArquivoBanco
    segmento: str          # A ou J
    nome: str
    cpf_cnpj: str          # sem zeros à esquerda, "" se não disponível
    documento: str         # seu número sem zeros à esquerda
    data: str              # DDMMAAAA
    valor: float
    ocorrencias: list[str] = field(default_factory=list)

    @property
    def ocorrencia_bruta(self) -> str:
        return "".join(self.ocorrencias)


@dataclass
class Pagamento:
    """Um item da lista a conferir (relatório do sistema)."""
    favorecido: str
    cpf_cnpj: str = ""
    documento: str = ""
    valor: float | None = None
    data: str = ""         # DDMMAAAA
    metodo: str = ""
    referencia: str = ""
    op: str = ""
    situacao_sistema: str = ""
    retorno_sistema: str = ""
    situacao_banco: str = ""   # "Pago", "Com Erro"... no relatório do banco


# Status possíveis da conferência
PAGO = "pago"
DEVOLUCAO = "devolucao"
REJEITADO = "rejeitado"
ACEITO_NAO_PAGO = "aceito_nao_pago"
OUTRO_PAGAMENTO = "outro_pagamento"
NAO_ENVIADO = "nao_enviado"

ROTULOS = {
    PAGO: "Pago",
    DEVOLUCAO: "Devolução",
    REJEITADO: "Rejeitado pelo banco",
    ACEITO_NAO_PAGO: "Aceito, ainda não pago",
    OUTRO_PAGAMENTO: "Outro pagamento",
    NAO_ENVIADO: "Não enviado",
}


@dataclass
class Resultado:
    pagamento: Pagamento
    status: str
    registros: list[RegistroBanco] = field(default_factory=list)
    codigos: list[str] = field(default_factory=list)   # ocorrência que define o status (ex: ZAZ7)
    arquivo_status: str = ""                             # arquivo que define o status
    match_fraco: bool = False                            # achado só por nome + valor
    observacoes: list[str] = field(default_factory=list)
    alerta_sistema: bool = False                         # sistema diz pago, banco não pagou

    @property
    def rotulo(self) -> str:
        return ROTULOS[self.status]
