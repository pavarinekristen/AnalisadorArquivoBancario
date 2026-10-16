from collections import Counter
from datetime import datetime

from conferencia import cnab240, mensagem, motor, relatorio
from conferencia.modelos import (ACEITO_NAO_PAGO, DEVOLUCAO, NAO_ENVIADO, OUTRO_PAGAMENTO, PAGO,
                                 REJEITADO, VERIFICAR, Pagamento)

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


def test_resumo_devolucao():
    regs = _regs("FORN_EZN1_06_071026P_MOV.TXT",
                 seg_a("F T DA SILVA", DOC, "07102026", 5400, "ZAZ7"), seg_b(CPF))
    msg = mensagem.resumo(motor.conferir([_pag()], regs), "santander", agora=datetime(2026, 10, 8, 9))
    assert msg.splitlines() == [
        "Resumo da conferência Santander (08/10/2026 09:00)",
        "1 favorecido(s): 1 devolução.",
        "",
        "ARQUIVOS",
        "Favorecidos encontrados no arquivo FORN_EZN1_06_071026P_MOV.",
        "",
        "DEVOLUÇÃO (1)",
        "- FULANO DE TAL DA SILVA | R$ 54,00 | ZAZ7: ZA (Agência/Conta do Favorecido Substituída) + Z7 (Código do "
        "banco: agência ou conta destinatária do crédito inválida) | FORN_EZN1_06_071026P_MOV",
        "",
        "ATENÇÃO",
        "- Sistema diz pago, mas o banco não pagou: FULANO DE TAL DA SILVA."]


def test_resumo_misto_problemas_primeiro():
    regs = _regs("FORN_E_06_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "ZAZ7"), seg_b(CPF))
    res = motor.conferir([_pag(situacao_banco=""),
                          _pag(favorecido="FULANO", cpf_cnpj="1", documento="100001111111111", situacao_banco="")],
                         regs)
    linhas = mensagem.resumo(res, agora=datetime(2026, 10, 8, 15)).splitlines()
    assert linhas[1] == "2 favorecido(s): 1 devolução, 1 não enviado."
    assert linhas.index("DEVOLUÇÃO (1)") < linhas.index("NÃO ENVIADO (1)")
    assert "- FULANO | R$ 54,00 | não está em nenhum arquivo do banco" in linhas
    assert "ATENÇÃO" not in linhas


def test_resumo_lista_cada_arquivo():
    regs = (_regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "00"), seg_b(CPF))
            + _regs("FORN_E_06_071026P_MOV.TXT",
                    seg_a("BELTRANO", "100002222222222", "07102026", 100, "ZA"), seg_b("99888777000166")))
    res = motor.conferir([_pag(), _pag(favorecido="BELTRANO", cpf_cnpj="99888777000166",
                                       documento="100002222222222", valor=1.0),
                          _pag(favorecido="CICLANO", cpf_cnpj="5", documento="100003333333333")], regs)
    linhas = mensagem.resumo(res, agora=datetime(2026, 10, 8, 9)).splitlines()
    i = linhas.index("ARQUIVOS")
    assert linhas[i + 1:i + 4] == [
        "Favorecidos encontrados nos arquivos FORN_E_03_071026P_MOV e FORN_E_06_071026P_MOV.",
        "- FORN_E_03_071026P_MOV: FULANO DE TAL DA SILVA",
        "- FORN_E_06_071026P_MOV: BELTRANO"]


def test_resumo_sem_nada_encontrado():
    linhas = mensagem.resumo(motor.conferir([_pag()], []), agora=datetime(2026, 10, 8, 9)).splitlines()
    assert "Nenhum favorecido foi encontrado nos arquivos do banco." in linhas


def test_resumo_tudo_certo():
    regs = _regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "00"), seg_b(CPF))
    linhas = mensagem.resumo(motor.conferir([_pag()], regs), agora=datetime(2026, 10, 8, 9)).splitlines()
    assert linhas[2] == "Tudo certo: todos pagos."
    assert "Favorecidos encontrados no arquivo FORN_E_03_071026P_MOV." in linhas
    assert "- FULANO DE TAL DA SILVA | R$ 54,00 | 00: 00 (Crédito ou Débito Efetivado) | FORN_E_03_071026P_MOV" in linhas


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
    msg = mensagem.resumo(res, "santander", agora=datetime(2026, 10, 8, 9))
    assert "18 favorecido(s): 18 devolução." in msg and "DEVOLUÇÃO (18)" in msg
    assert msg.count("| FORN_EZN1_06_071026P_MOV") == 18

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


# ---- classificação: último registro decisivo, VERIFICAR, códigos Z ----

def test_pago_seguido_de_codigo_sem_efeito_continua_pago():
    regs = (_regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "00"), seg_b(CPF))
            + _regs("FORN_E_05_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "BD"), seg_b(CPF)))
    r = _um(_pag(), regs)
    assert (r.status, r.codigos) == (PAGO, ["00"])
    assert any("sem mudar o status" in o for o in r.observacoes)


def test_mov_so_com_bd_e_aceito_nao_pago():
    regs = _regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "BD"), seg_b(CPF))
    assert _um(_pag(), regs).status == ACEITO_NAO_PAGO


def test_codigo_desconhecido_vira_verificar_e_nao_rejeitado():
    regs = _regs("FORN_E_02_071026P_CRI.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "BDQ9"), seg_b(CPF))
    assert _um(_pag(), regs).status == VERIFICAR
    regs = _regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, ""), seg_b(CPF))
    assert _um(_pag(), regs).status == VERIFICAR


def test_exclusao_bf_vira_verificar():
    regs = _regs("FORN_E_02_071026P_CRI.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "BF"), seg_b(CPF))
    r = _um(_pag(), regs)
    assert r.status == VERIFICAR and any("excluído" in o for o in r.observacoes)


def test_erro_conhecido_continua_rejeitado():
    regs = _regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "HF"), seg_b(CPF))
    assert _um(_pag(), regs).status == REJEITADO


def test_qualquer_z_no_primeiro_par_e_devolucao():
    for codigo in ["ZAZ7", "ZAAE", "ZA", "ZAZ9", "ZXQ1", "ZC"]:
        regs = _regs("FORN_E_06_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, codigo), seg_b(CPF))
        assert _um(_pag(), regs).status == DEVOLUCAO, codigo


def test_reenvio_rejeitado_depois_do_pago_vira_aviso():
    regs = (_regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "00"), seg_b(CPF))
            + _regs("FORN_E_04_071026P_CRI.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "AG"), seg_b(CPF)))
    r = _um(_pag(), regs)
    assert r.status == PAGO and any("reenvio rejeitado" in o for o in r.observacoes)


def test_resumo_com_verificar_e_codigo_03():
    regs = (_regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", DOC, "07102026", 5400, "03"), seg_b(CPF))
            + _regs("FORN_E_04_071026P_CRI.TXT",
                    seg_a("BELTRANO", "100002222222222", "07102026", 100, "Q9"), seg_b("99888777000166")))
    res = motor.conferir([_pag(), _pag(favorecido="BELTRANO", cpf_cnpj="99888777000166",
                                       documento="100002222222222", valor=1.0)], regs)
    assert [r.status for r in res] == [PAGO, VERIFICAR]
    linhas = mensagem.resumo(res, agora=datetime(2026, 10, 8, 9)).splitlines()
    assert linhas.index("VERIFICAR (SITUAÇÃO NÃO CONCLUSIVA) (1)") < linhas.index("PAGO (1)")
    assert any(l.startswith("- FULANO DE TAL DA SILVA | R$ 54,00 | 03:") for l in linhas)
    assert any(l.startswith("- BELTRANO | R$ 1,00 | Q9: Q9 (Código não cadastrado") for l in linhas)


# ---- busca por nome no modo conferir ----

def test_nome_curto_igual_casa():
    regs = _regs("FORN_E_03_071026P_MOV.TXT", seg_a("ANA LIMA", "", "07102026", 5400, "00"))
    r = _um(Pagamento(favorecido="ANA LIMA", valor=54.0), regs)
    assert r.status == PAGO and r.match_fraco


def test_nome_com_palavra_sobrando_no_banco_nao_casa():
    regs = _regs("FORN_E_03_071026P_MOV.TXT", seg_a("JOSE DA SILVA SANTOS", "", "07102026", 5400, "00"))
    assert _um(Pagamento(favorecido="JOSE DA SILVA", valor=54.0), regs).status == NAO_ENVIADO


def test_nome_abreviado_casa_no_modo_conferir():
    regs = _regs("FORN_E_03_071026P_MOV.TXT", seg_a("F T DA SILVA", "", "07102026", 5400, "00"))
    r = _um(Pagamento(favorecido="FULANO DE TAL DA SILVA", valor=54.0), regs)
    assert r.status == PAGO and r.match_fraco


def test_documento_errado_acha_por_cpf_e_valor():
    regs = _regs("FORN_E_06_071026P_MOV.TXT",
                 seg_a("F T DA SILVA", "100009999999999", "07102026", 5400, "ZAZ7"), seg_b(CPF))
    r = _um(_pag(), regs)
    assert r.status == DEVOLUCAO and r.match_fraco
    assert any("Documento do relatório não está" in o for o in r.observacoes)


def test_documento_confere_mas_cpf_diferente_avisa():
    regs = _regs("FORN_E_03_071026P_MOV.TXT",
                 seg_a("F T DA SILVA", DOC, "07102026", 5400, "00"), seg_b("99888777000166"))
    r = _um(_pag(), regs)
    assert r.status == PAGO and any("CPF/CNPJ no banco" in o for o in r.observacoes)
