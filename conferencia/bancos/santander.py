from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .. import motor
from ..modelos import ArquivoBanco, Resultado, TipoArquivo
from . import NivelAviso, codigos_arquivos

_NOME_FORN = re.compile(r"FORN_(?P<emp>[A-Z0-9]+)_(?P<lote>\d+)_(?P<data>\d{6})P_(?P<tipo>[A-Z]+)", re.I)
TIPOS_COM_LOTE: frozenset[str] = frozenset({"MOV", "CRI", "REL"})


class Santander:
    """Santander (033): crítica (CRI) e movimento (MOV) em arquivos separados, reconhecidos pelo nome."""
    chave = "santander"
    nome = "Santander"
    codigo = "033"
    descricao_arquivos = "MOV, CRI e Retorno (ex: FORN_EZN1_06_071026P_MOV.TXT)"
    rotulo_upload = "Arraste TODOS os arquivos da pasta (MOV, CRI, Retorno...)"
    rotulos_tipo: dict[str, str] = {}

    def identificar(self, nome: str) -> ArquivoBanco | None:
        base = Path(nome).name
        m = _NOME_FORN.search(base)
        if m:
            d = m.group("data")
            try:
                dt: date | None = date(2000 + int(d[4:6]), int(d[2:4]), int(d[0:2]))
            except ValueError:
                dt = None
            tipo = m.group("tipo").upper()
            tipo_final: TipoArquivo = tipo if tipo in TIPOS_COM_LOTE else "OUTRO"
            return ArquivoBanco(base, tipo_final, dt, int(m.group("lote")), m.group("emp").upper())
        if base.lower().startswith("retorno_"):
            return ArquivoBanco(base, "RETORNO", None, None, None)
        return None

    def reconhece_header(self, header: str) -> bool:
        return False   # só pelo nome

    def preparar(self, arq: ArquivoBanco, header: str, mtime_ns: int | None) -> None:
        pass

    def colunas_tela(self, r: Resultado) -> dict[str, str]:
        dev = codigos_arquivos(r, "MOV", motor.e_devolucao)
        return {
            "CRI (código e arquivo)": codigos_arquivos(r, "CRI") or "Não está em CRI",
            "MOV pago (00)": codigos_arquivos(r, "MOV", motor.e_pago) or "Não",
            "Devolução no MOV (Z...)": f"Sim: {dev}" if dev else "Não",
        }

    def avisos_arquivos(self, tipos: dict[str, int]) -> list[tuple[NivelAviso, str]]:
        avisos: list[tuple[NivelAviso, str]] = []
        if "MOV" not in tipos:
            avisos.append(("warning", "Nenhum arquivo MOV. Sem MOV não dá para saber se foi pago ou devolvido."))
        if "CRI" not in tipos:
            avisos.append(("info", "Nenhum arquivo CRI. Não dá para ver rejeições na crítica do banco."))
        return avisos
