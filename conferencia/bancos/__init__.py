"""Perfis de banco: o que muda de um banco para outro (nome dos arquivos, header, colunas da tela, avisos).

Para atender um banco novo, crie um módulo aqui com uma classe que siga `PerfilBanco` e registre em REGISTRO.
A leitura do CNAB 240 (cnab240.py) e a classificação (motor.py) são as mesmas para todos.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol

from ..modelos import ArquivoBanco, Banco, RegistroBanco, Resultado, Status

NivelAviso = Literal["warning", "info", "caption"]


class PerfilBanco(Protocol):
    chave: Banco
    nome: str
    codigo: str                 # código do banco na FEBRABAN (033, 634...)
    descricao_arquivos: str     # texto da tela: quais arquivos são lidos
    rotulo_upload: str
    rotulos_tipo: dict[str, str]

    def identificar(self, nome: str) -> ArquivoBanco | None:
        """Reconhece o arquivo pelo nome. None = não é deste banco (pelo nome)."""

    def reconhece_header(self, header: str) -> bool:
        """Arquivo de nome qualquer que é deste banco pelo header (primeiros 240 caracteres)."""

    def preparar(self, arq: ArquivoBanco, header: str, mtime_ns: int | None) -> None:
        """Aplica no arquivo o que vem do header (data/hora de geração...)."""

    def colunas_tela(self, r: Resultado) -> dict[str, str]:
        """Colunas próprias do banco na tabela de resultado."""

    def avisos_arquivos(self, tipos: dict[str, int]) -> list[tuple[NivelAviso, str]]:
        """Avisos sobre o conjunto de arquivos informado (ex: faltou MOV)."""


def codigos_arquivos(r: Resultado, tipo: str, filtro: Callable[[RegistroBanco], bool] = lambda x: True) -> str:
    """Ex: 'BD em FORN_EZN1_02_071026P_CRI'. Só do pagamento conferido (não de outros pagamentos)."""
    if r.status == Status.OUTRO_PAGAMENTO:
        return ""
    return " | ".join(f"{x.ocorrencia_bruta or '-'} em {sem_extensao(x.arquivo.nome)}"
                      for x in r.registros if x.arquivo.tipo == tipo and filtro(x))


def sem_extensao(nome: str) -> str:
    return nome[:-4] if nome.upper().endswith((".TXT", ".DAT")) else nome


def _registro() -> dict[Banco, PerfilBanco]:
    from .santander import Santander
    from .tribanco import Tribanco
    return {"santander": Santander(), "tribanco": Tribanco()}


REGISTRO: dict[Banco, PerfilBanco] = _registro()


def perfil(banco: Banco) -> PerfilBanco:
    return REGISTRO[banco]
