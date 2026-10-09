import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FINAL24 = Path(r"C:\Users\krist\Downloads\arquivos\FINAL24")
EXCEL_0510 = Path(r"C:\Users\krist\Downloads\RELATÓRIO COMPLETO 05-10.xlsx")

precisa_dados_reais = pytest.mark.skipif(
    not (FINAL24.is_dir() and EXCEL_0510.is_file()),
    reason="dados reais (FINAL24 / Excel 05-10) não estão nesta máquina")


def _campo(linha: list, ini: int, fim: int, valor: str):
    """Escreve valor nas posições 1-based ini..fim."""
    tam = fim - ini + 1
    linha[ini - 1:fim] = list(valor[:tam].ljust(tam))


def _base(seg: str, seq: int) -> list:
    l = list(" " * 240)
    _campo(l, 1, 8, "03300013")
    _campo(l, 9, 13, f"{seq:05d}")
    _campo(l, 14, 14, seg)
    return l


def seg_a(nome, doc, data, valor_centavos, ocorr, seq=1):
    l = _base("A", seq)
    _campo(l, 44, 73, nome)
    _campo(l, 74, 93, doc)
    _campo(l, 94, 101, data)
    _campo(l, 120, 134, f"{valor_centavos:015d}")
    _campo(l, 231, 240, ocorr)
    return "".join(l)


def seg_b(cpf, seq=2):
    l = _base("B", seq)
    _campo(l, 18, 18, "2")
    _campo(l, 19, 32, f"{int(cpf):014d}")
    return "".join(l)


def seg_j(nome, doc, data, valor_centavos, ocorr, seq=1):
    l = _base("J", seq)
    _campo(l, 18, 61, "0339" + "1" * 40)
    _campo(l, 62, 91, nome)
    _campo(l, 100, 114, f"{valor_centavos:015d}")
    _campo(l, 145, 152, data)
    _campo(l, 153, 167, f"{valor_centavos:015d}")
    _campo(l, 183, 202, f"{int(doc):020d}")
    _campo(l, 231, 240, ocorr)
    return "".join(l)


def seg_j52(cnpj, seq=2):
    l = _base("J", seq)
    _campo(l, 18, 19, "52")
    _campo(l, 76, 76, "2")
    _campo(l, 77, 91, f"{int(cnpj):015d}")
    return "".join(l)


HEADER = "0330000" + "0" * 233
