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


def test_arquivo_sem_quebra_de_linha_e_lido_inteiro():
    txt = "".join([HEADER, seg_a("F T DA SILVA", "100009000000001", "07102026", 5400, "00"),
                   seg_b("11222333000181")])
    arq, regs = cnab240.ler_bytes("FORN_X_06_071026P_MOV.TXT", txt.encode("latin-1"))
    assert [(r.documento, r.valor, r.cpf_cnpj) for r in regs] == [("100009000000001", 54.0, "11222333000181")]
    assert arq.avisos == []


def test_arquivo_utf8_com_acento_nao_desloca_valor():
    txt = "\n".join([HEADER, seg_a("JOSÉ DA SILVA", "100009000000001", "07102026", 5400, "00")])
    _, regs = cnab240.ler_bytes("FORN_X_06_071026P_MOV.TXT", txt.encode("utf-8"))
    assert (regs[0].nome, regs[0].valor) == ("JOSÉ DA SILVA", 54.0)


def test_avisa_linha_fora_do_tamanho_e_arquivo_sem_pagamento():
    arq, regs = cnab240.ler_bytes("FORN_X_06_071026P_MOV.TXT", (HEADER + "\n" + "0" * 100).encode("latin-1"))
    assert regs == []
    assert any("fora do tamanho" in a for a in arq.avisos)
    assert any("sem nenhum pagamento" in a for a in arq.avisos)


def test_tribanco_com_data_invalida_usa_data_do_arquivo():
    from datetime import datetime
    from .conftest import do_tribanco, header_tribanco
    txt = "\n".join([header_tribanco(data="99999999"), do_tribanco(seg_a("X", "100009000000001", "07102026", 100, "00"))])
    mtime = int(datetime(2026, 10, 9, 12).timestamp() * 1e9)
    arq, _ = cnab240.ler_bytes("A35708191410260001.dat", txt.encode("latin-1"), mtime)
    assert arq.data == date(2026, 10, 9) and any("data inválida" in a for a in arq.avisos)
