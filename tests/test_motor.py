from collections import Counter
from datetime import datetime

from conferencia import cnab240, mensagem, motor, relatorio
from conferencia.modelos import (ACEITO_NAO_PAGO, DEVOLUCAO, NAO_ENVIADO, OUTRO_PAGAMENTO, PAGO,
                                 REJEITADO, Pagamento)

from .conftest import EXCEL_0510, FINAL24, precisa_dados_reais, seg_a, seg_b

DOC, CPF = "100009000000001", "11222333000181"


def _regs(nome_arquivo, *linhas):
    return cnab240.ler_bytes(nome_arquivo, "\n".join(linhas).encode("latin-1"))[1]


def _pag(**kw):
    base = dict(favorecido="FULANO DE TAL DA SILVA", cpf_cnpj=CPF, documento=DOC, valor=54.0,
                data="07102026", situacao_banco="Pago")
    base.update(kw)
    return Pagamento(**base)


def _um(pag, regs):
    return motor.conferir([pag], regs)[0]


def test_pago_depois_devolvido_vira_devolucao():
    regs = (_regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "00"), seg_b(CPF))
            + _regs("FORN_E_06_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "ZAZ7"), seg_b(CPF)))
    r = _um(_pag(), regs)
    assert r.status == DEVOLUCAO
    assert r.codigos == ["ZAZ7"]
    assert r.arquivo_status == "FORN_E_06_071026P_MOV.TXT"
    assert r.alerta_sistema


def test_pago():
    regs = (_regs("FORN_E_02_071026P_CRI.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "BD"), seg_b(CPF))
            + _regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "00"), seg_b(CPF)))
    r = _um(_pag(), regs)
    assert r.status == PAGO and not r.alerta_sistema


def test_rejeitado_no_cri():
    regs = _regs("FORN_E_02_071026P_CRI.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "AG"), seg_b(CPF))
    r = _um(_pag(), regs)
    assert r.status == REJEITADO and r.codigos == ["AG"]


def test_aceito_nao_pago():
    regs = _regs("FORN_E_02_071026P_CRI.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "BD"), seg_b(CPF))
    assert _um(_pag(), regs).status == ACEITO_NAO_PAGO


def test_outro_pagamento():
    regs = _regs("FORN_E_03_071026P_MOV.TXT",
                 seg_a("F T DA SILVA", "100009999999999", "01102026", 99900, "00"), seg_b(CPF))
    assert _um(_pag(), regs).status == OUTRO_PAGAMENTO


def test_nao_enviado():
    assert _um(_pag(), []).status == NAO_ENVIADO


def test_nome_truncado_e_comercial():
    regs = _regs("FORN_E_03_071026P_MOV.TXT",
                 seg_a("ALFA   BETA  CONSULTORIA EMPRE", "", "01102026", 799868, "00"))
    r = _um(Pagamento(favorecido="ALFA & BETA CONSULTORIA EMPRESARIAL LTDA", valor=7998.68), regs)
    assert r.status == PAGO and r.match_fraco


def test_codigo_desconhecido_avisado():
    regs = _regs("FORN_E_02_071026P_CRI.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "Q9"), seg_b(CPF))
    assert any("não cadastrado" in o for o in _um(_pag(), regs).observacoes)


def test_codigos_cadastrados():
    for c in ["00", "01", "02", "03", "BD", "BE", "BF", "ZA", "ZK", "Z7", "Z8", "Z9", "AG", "AE", "HF",
              "TA", "YA", "BH", "BS", "HM", "HZ", "H1", "H9", "IA", "IQ", "PA", "PN", "XD"]:
        assert c in motor.OCORRENCIAS, c


def test_mensagem_todos_devolucao():
    regs = _regs("FORN_EZN1_06_071026P_MOV.TXT",
                 seg_a("F T DA SILVA", DOC, "07102026", 5400, "ZAZ7"), seg_b(CPF))
    msg = mensagem.montar(motor.conferir([_pag()], regs), agora=datetime(2026, 10, 8, 9))
    assert msg == ("Bom dia. Fiz a análise dos nomes dos favorecidos do relatório e encontrei todos no arquivo "
                   "FORN_EZN1_06_071026P_MOV com código de devolução (ZAZ7).")


def test_mensagem_misto():
    regs = _regs("FORN_E_06_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "ZAZ7"), seg_b(CPF))
    res = motor.conferir([_pag(), _pag(favorecido="FULANO", cpf_cnpj="1", documento="100001111111111")], regs)
    msg = mensagem.montar(res, agora=datetime(2026, 10, 8, 15))
    assert msg.startswith("Boa tarde. Fiz a análise dos 2 favorecidos do relatório.")
    assert "1 não está em nenhum arquivo, não foi enviado ao banco: FULANO." in msg


@precisa_dados_reais
def test_caso_real_final24():
    _, regs = cnab240.ler_pasta(FINAL24)
    listas = relatorio.ler_excel(EXCEL_0510.read_bytes())

    banco = next(v for k, v in listas.items() if "banco" in k)
    res = motor.conferir(banco, regs)
    assert all(r.status == DEVOLUCAO for r in res)
    assert {r.arquivo_status for r in res} == {"FORN_EZN1_06_071026P_MOV.TXT"}
    assert Counter(r.codigos[0] for r in res) == {"ZAZ7": 10, "ZAAE": 7, "ZA": 1}
    assert all("FORN_EZN1_03_071026P_MOV.TXT" in r.observacoes[0] for r in res)
    assert mensagem.montar(res, agora=datetime(2026, 10, 8, 9)) == (
        "Bom dia. Fiz a análise dos nomes dos favorecidos do relatório e encontrei todos no arquivo "
        "FORN_EZN1_06_071026P_MOV com código de devolução (ZA, ZAAE e ZAZ7).")

    sistema = next(v for k, v in listas.items() if "sistema" in k)
    assert Counter(r.status for r in motor.conferir(sistema, regs)) == {NAO_ENVIADO: 10, PAGO: 2}


# ---- mesmo favorecido com vários pagamentos diferentes ----

def _dois_pagamentos_mesmo_valor():
    antigo = _regs("FORN_E_03_011026P_MOV.TXT",
                   seg_a("F T DA SILVA", "100001111111111", "01102026", 5400, "00"), seg_b(CPF))
    novo = _regs("FORN_E_06_071026P_MOV.TXT",
                 seg_a("F T DA SILVA", DOC, "07102026", 5400, "ZAZ7"), seg_b(CPF))
    return antigo + novo


def test_mesmo_favorecido_com_documento_pega_o_certo():
    regs = _dois_pagamentos_mesmo_valor()
    assert _um(_pag(), regs).status == DEVOLUCAO
    assert _um(_pag(documento="100001111111111", data="01102026"), regs).status == PAGO


def test_mesmo_favorecido_sem_documento_usa_data():
    regs = _dois_pagamentos_mesmo_valor()
    r = _um(_pag(documento="", data="01102026"), regs)
    assert r.status == PAGO and len(r.registros) == 1
    assert not any("pagamentos com o mesmo valor" in o for o in r.observacoes)


def test_mesmo_favorecido_sem_documento_nem_data_avisa():
    regs = _dois_pagamentos_mesmo_valor()
    r = _um(_pag(documento="", data=""), regs)
    assert r.status == DEVOLUCAO and len(r.registros) == 1
    assert any("2 pagamentos com o mesmo valor" in o for o in r.observacoes)


def test_documento_do_relatorio_nao_esta_mas_favorecido_tem_outro():
    regs = _regs("FORN_E_03_011026P_MOV.TXT",
                 seg_a("F T DA SILVA", "100001111111111", "01102026", 5400, "00"), seg_b(CPF))
    assert _um(_pag(), regs).status == OUTRO_PAGAMENTO


def test_dois_pagamentos_do_mesmo_favorecido_no_relatorio():
    regs = _dois_pagamentos_mesmo_valor()
    res = motor.conferir([_pag(), _pag(documento="100001111111111", data="01102026")], regs)
    assert [r.status for r in res] == [DEVOLUCAO, PAGO]


# ---- pesquisa por nomes digitados ----

def test_nome_bate_abreviado_truncado_e_comercial():
    casos = [("BELTRANO PEREIRA DE SOUZA", "B PEREIRA DE SOUZA LTDA", True),
             ("FULANO DE TAL DA SILVA", "F T DA SILVA", True),
             ("CICLANO DE ALBUQUERQUE PEREIRA FONSECA", "CICLANO DE ALBUQUERQUE PEREIRA", True),
             ("alfa & beta", "ALFA   BETA  CONSULTORIA EMPRE", True),
             ("SILVA", "JOSE DA SILVA", True),
             ("MARIA SILVA", "JOSE DA SILVA", False),
             ("ANA PAULA", "A P COMERCIO", False)]
    for digitado, banco, esperado in casos:
        assert motor.nome_bate(digitado, banco) == esperado, (digitado, banco)


def test_ler_nomes_digitados():
    pags = relatorio.ler_nomes_digitados(
        "FULANO DE TAL\nCICLANO 11.222.333/0001-81\nBELTRANO 6.503,00 07/10/2026\n100009000000001\n\n")
    assert [(p.favorecido, p.cpf_cnpj, p.documento, p.valor, p.data) for p in pags] == [
        ("FULANO DE TAL", "", "", None, ""),
        ("CICLANO", "11222333000181", "", None, ""),
        ("BELTRANO", "", "", 6503.0, "07102026"),
        ("100009000000001", "", "100009000000001", None, "")]


def test_pesquisar_um_resultado_por_pagamento():
    regs = _dois_pagamentos_mesmo_valor()
    res = motor.pesquisar(relatorio.ler_nomes_digitados("FULANO DE TAL DA SILVA\nBELTRANO"), regs)
    assert [(r.pagamento.favorecido, r.status) for r in res] == [
        ("FULANO DE TAL DA SILVA", DEVOLUCAO),      # mais recente primeiro
        ("FULANO DE TAL DA SILVA", PAGO),
        ("BELTRANO", NAO_ENVIADO)]


def test_pesquisar_com_valor_filtra():
    regs = _dois_pagamentos_mesmo_valor() + _regs(
        "FORN_E_04_071026P_MOV.TXT", seg_a("F T DA SILVA", "100009000000077", "07102026", 99900, "00"), seg_b(CPF))
    res = motor.pesquisar(relatorio.ler_nomes_digitados("FULANO DA SILVA 999,00"), regs)
    assert [(r.status, r.pagamento.valor) for r in res] == [(PAGO, 999.0)]
