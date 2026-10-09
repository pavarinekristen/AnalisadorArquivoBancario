from datetime import date

from conferencia import cnab240

from .conftest import FINAL24, HEADER, precisa_dados_reais, seg_a, seg_b, seg_j, seg_j52


def test_identificar_nome():
    a = cnab240.identificar("FORN_EZN1_06_071026P_MOV.TXT")
    assert (a.tipo, a.lote, a.data, a.empresa) == ("MOV", 6, date(2026, 10, 7), "EZN1")
    assert cnab240.identificar("FORN_EZN1_04_300926P_CRI_5029168.TXT").tipo == "CRI"
    assert cnab240.identificar("Retorno_150920275_OK").tipo == "RETORNO"
    assert cnab240.identificar("planilha.xlsx").tipo == "OUTRO"


def test_segmento_a_com_b():
    txt = "\n".join([HEADER, seg_a("F T DA SILVA", "100009000000001", "07102026", 5400, "ZAZ7"),
                     seg_b("11222333000181")])
    _, regs = cnab240.ler_bytes("FORN_X_06_071026P_MOV.TXT", txt.encode("latin-1"))
    assert len(regs) == 1
    r = regs[0]
    assert (r.nome, r.documento, r.data, r.valor, r.cpf_cnpj) == (
        "F T DA SILVA", "100009000000001", "07102026", 54.0, "11222333000181")
    assert r.ocorrencias == ["ZA", "Z7"]


def test_segmento_j_com_j52():
    txt = "\n".join([seg_j("EMPRESA EXEMPLO", "100009000000002", "05102026", 1076758, "BD"),
                     seg_j52("04252011000110")])
    _, regs = cnab240.ler_bytes("FORN_X_02_051026P_CRI.TXT", txt.encode("latin-1"))
    assert len(regs) == 1
    assert (regs[0].segmento, regs[0].documento, regs[0].valor, regs[0].cpf_cnpj) == (
        "J", "100009000000002", 10767.58, "4252011000110")


def test_lotes_faltando():
    arqs = [cnab240.identificar(n) for n in
            ["FORN_E_01_071026P_MOV.TXT", "FORN_E_03_071026P_CRI.TXT", "FORN_E_01_081026P_MOV.TXT"]]
    assert cnab240.lotes_faltando(arqs) == {"E 07/10/2026": [2]}


@precisa_dados_reais
def test_final24_le_tudo():
    arqs, regs = cnab240.ler_pasta(FINAL24)
    assert sum(r.segmento == "A" for r in regs) == 4787
    assert cnab240.lotes_faltando(arqs) == {}
