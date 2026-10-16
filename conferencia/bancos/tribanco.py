from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .. import motor
from ..modelos import ArquivoBanco, Resultado
from . import NivelAviso, codigos_arquivos

# Retorno do Tribanco: A + convênio (7 dígitos) + data/sequencial em formatos variados, sempre .dat
# (A35708191410260001.dat, A3570819_17062026001.dat, A3570801001.dat). A data certa vem do header.
_NOME_TRIBANCO = re.compile(r"^A(?P<conv>\d{7})[\d_]*(?: \(\d+\))?\.dat$", re.I)
CODIGO = "634"


def _campo(linha: str, a: int, b: int) -> str:
    return linha[a - 1:b]


class Tribanco:
    """Tribanco (634): crítica e pagamento no mesmo retorno .dat; o header decide se o arquivo é dele."""
    chave = "tribanco"
    nome = "Tribanco"
    codigo = CODIGO
    descricao_arquivos = "retorno .dat, com crítica e pagamento no mesmo arquivo (ex: A35708191410260001.dat)"
    rotulo_upload = "Arraste os arquivos de retorno do Tribanco (.dat)"
    rotulos_tipo = {"RET": "retorno Tribanco"}

    def identificar(self, nome: str) -> ArquivoBanco | None:
        base = Path(nome).name
        m = _NOME_TRIBANCO.match(base)
        return ArquivoBanco(base, "RET", None, None, m.group("conv"), banco="tribanco") if m else None

    def reconhece_header(self, header: str) -> bool:
        return header[:3] == CODIGO and header[7:8] == "0"

    def preparar(self, arq: ArquivoBanco, header: str, mtime_ns: int | None) -> None:
        """Header de arquivo CNAB 240: 144-151 data de geração (DDMMAAAA), 152-157 hora (HHMMSS)."""
        hora = _campo(header, 152, 157)
        arq.hora = hora if hora.isdigit() else ""
        try:
            arq.data = datetime.strptime(_campo(header, 144, 151), "%d%m%Y").date()
            return
        except ValueError:
            pass
        # Sem data no header o arquivo ficaria por último na ordem e uma devolução nele perderia para um 00 antigo.
        if mtime_ns is not None:
            arq.data, arq.hora = datetime.fromtimestamp(mtime_ns / 1e9).date(), ""
            arq.avisos.append(f"{arq.nome}: data inválida no header; usei a data do arquivo ({arq.data:%d/%m/%Y}).")
        else:
            arq.avisos.append(f"{arq.nome}: data inválida no header; a ordem entre retornos pode ficar errada.")

    def colunas_tela(self, r: Resultado) -> dict[str, str]:
        dev = codigos_arquivos(r, "RET", motor.e_devolucao)
        return {
            "Retorno Tribanco (código e arquivo)": codigos_arquivos(r, "RET") or "Não está em retorno",
            "Pago (00)": codigos_arquivos(r, "RET", motor.e_pago) or "Não",
            "Devolução (Z...)": f"Sim: {dev}" if dev else "Não",
        }

    def avisos_arquivos(self, tipos: dict[str, int]) -> list[tuple[NivelAviso, str]]:
        if "RET" not in tipos:
            return [("warning", "Nenhum retorno do Tribanco (.dat). Sem ele não dá para saber se foi pago.")]
        return [("caption", "No Tribanco o mesmo retorno traz a crítica (BD = aceito, ou código de erro) "
                            "e depois o pagamento (00) ou a devolução (Z...).")]
