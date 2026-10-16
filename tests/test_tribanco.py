import sqlite3
from datetime import date

from conferencia import cnab240, historico, motor, ntedi, relatorio
from conferencia.modelos import ACEITO_NAO_PAGO, DEVOLUCAO, PAGO, REJEITADO, Pagamento

from .conftest import do_tribanco, header_tribanco, seg_a, seg_b, seg_j, seg_j52

DOC, CPF = "100004079087464", "63482211000128"


def _retorno(nome, ocorr, data="17062026", hora="170948"):
    txt = "\r\n".join([header_tribanco(data, hora),
                       do_tribanco(seg_a("JERUSA MARTINS EVENTOS LTDA", DOC, "18062026", 12000000, ocorr)),
                       do_tribanco(seg_b(CPF))])
    return cnab240.ler_bytes(nome, txt.encode("latin-1"))


def _pag(**kw):
    base = dict(favorecido="JERUSA MARTINS EVENTOS LTDA", cpf_cnpj=CPF, documento=DOC, valor=120000.0,
                data="18062026")
    return Pagamento(**(base | kw))


def test_identificar_nomes_do_tribanco():
    for nome in ["A35708191410260001.dat", "A3570819_17062026001.dat", "A3570801001.dat",
                 "A357082017062026001 (1).dat"]:
        a = cnab240.identificar(nome)
        assert (a.tipo, a.banco) == ("RET", "tribanco"), nome
    assert cnab240.identificar("A35708191410260001.dat").empresa == "3570819"
    assert cnab240.identificar("FORN_EZN1_06_071026P_MOV.TXT").banco == "santander"


def test_retorno_le_header_e_registros():
    arq, regs = _retorno("A35708191706260001.dat", "BD")
    assert (arq.tipo, arq.banco, arq.data, arq.hora) == ("RET", "tribanco", date(2026, 6, 17), "170948")
    assert [(r.nome, r.documento, r.cpf_cnpj, r.valor, r.ocorrencias) for r in regs] == [
        ("JERUSA MARTINS EVENTOS LTDA", DOC, CPF, 120000.0, ["BD"])]


def test_segmento_j_do_tribanco():
    txt = "\n".join([header_tribanco(), do_tribanco(seg_j("FISERV DO BRASIL", "100004079507380", "18062026",
                                                          30935846, "BD")),
                     do_tribanco(seg_j52("04962772000165"))])
    _, regs = cnab240.ler_bytes("A357082017062026001.dat", txt.encode("latin-1"))
    assert [(r.segmento, r.valor, r.cpf_cnpj) for r in regs] == [("J", 309358.46, "4962772000165")]


def test_reconhece_pelo_conteudo_e_descarta_dat_de_outro_banco():
    txt = "\n".join([header_tribanco(), do_tribanco(seg_a("X", DOC, "18062026", 100, "00"))])
    arq, regs = cnab240.ler_bytes("arquivo_baixado.txt", txt.encode("latin-1"))
    assert (arq.tipo, arq.banco, len(regs)) == ("RET", "tribanco", 1)
    arq, regs = cnab240.ler_bytes("A1234567.dat", ("0330000" + "0" * 233).encode("latin-1"))
    assert (arq.tipo, regs) == ("OUTRO", [])


def test_aceito_no_retorno_e_ainda_nao_pago():
    _, regs = _retorno("A35708191706260001.dat", "BD")
    assert motor.conferir([_pag()], regs)[0].status == ACEITO_NAO_PAGO


def test_aceito_e_depois_pago_em_outro_retorno():
    _, aceito = _retorno("A35708191706260001.dat", "BD", "17062026")
    _, pago = _retorno("A35708191806260001.dat", "00", "18062026")
    r = motor.conferir([_pag()], aceito + pago)[0]
    assert (r.status, r.codigos, r.arquivo_status) == (PAGO, ["00"], "A35708191806260001.dat")


def test_mesmo_dia_ordena_pela_hora_do_header():
    _, pago = _retorno("A35708191806260001.dat", "00", "18062026", "090000")
    _, devolvido = _retorno("A35708191806260002.dat", "ZA", "18062026", "180000")
    r = motor.conferir([_pag()], devolvido + pago)[0]
    assert (r.status, r.codigos) == (DEVOLUCAO, ["ZA"])


def test_rejeitado_no_retorno():
    _, regs = _retorno("A35708191706260001.dat", "AR")
    r = motor.conferir([_pag()], regs)[0]
    assert (r.status, r.codigos) == (REJEITADO, ["AR"])


def test_ler_pasta_do_tribanco(monkeypatch, tmp_path):
    monkeypatch.setattr(ntedi, "BASE_TRIBANCO", tmp_path / "tribanco")
    (tmp_path / "tribanco").mkdir()
    txt = "\n".join([header_tribanco(), do_tribanco(seg_a("X", DOC, "18062026", 100, "BD"))])
    (tmp_path / "tribanco" / "A35708191410260001.dat").write_bytes(txt.encode("latin-1"))
    (tmp_path / "tribanco" / "leia-me.txt").write_bytes(b"nada")
    r = ntedi.ler_tribanco()
    assert [(a.nome, a.banco) for a in r.arquivos] == [("A35708191410260001.dat", "tribanco")]
    assert len(r.registros) == 1 and not r.avisos


def test_historico_guarda_banco_e_migra_base_antiga(tmp_path):
    db = tmp_path / "historico.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE conferencias (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT NOT NULL, "
                "relatorio TEXT, arquivos TEXT, total INTEGER)")
    con.execute("INSERT INTO conferencias (data_hora, total) VALUES ('2026-10-01T10:00:00', 0)")
    con.commit()
    con.close()
    _, regs = _retorno("A35708191706260001.dat", "BD")
    historico.salvar(motor.conferir([_pag()], regs), "nomes", ["A35708191706260001.dat"], "tribanco",
                     caminho=db)
    bancos = [b for (b,) in sqlite3.connect(db).execute("SELECT banco FROM conferencias ORDER BY id")]
    assert bancos == ["santander", "tribanco"]
    assert list(historico.buscar("JERUSA", caminho=db)["banco"]) == ["tribanco"]


def _arquivo_do_pagador(nome_arquivo, pagador, cnpj, *favorecidos):
    header = list(header_tribanco())
    header[18:32] = list(f"{int(cnpj):014d}")
    header[72:102] = list(pagador.ljust(30))
    linhas = ["".join(header)]
    for i, (nome, doc, centavos) in enumerate(favorecidos):
        linhas.append(do_tribanco(seg_a(nome, doc, "16062026", centavos, "00", seq=2 * i + 1)))
    return cnab240.ler_bytes(nome_arquivo, "\n".join(linhas).encode("latin-1"))[1]


def test_pesquisa_pelo_nome_ou_cnpj_da_empresa_pagadora():
    regs = (_arquivo_do_pagador("A3570801001.dat", "INSTITUTO ALAIR MARTINS", "07618414000128",
                                ("ECCAPLAN CONSULTORIA", "100004074802536", 156000),
                                ("LEANDRO MAMEDE", "100004074802502", 120000))
            + _arquivo_do_pagador("A3570819001.dat", "TRIPAG MEIOS DE PAGAMENTO", "22799145000014",
                                  ("JERUSA MARTINS EVENTOS LTDA", DOC, 12000000)))
    assert regs[0].arquivo.pagador == "INSTITUTO ALAIR MARTINS"
    for busca in ["INSTITUTO ALAIR MARTINS", "07.618.414/0001-28"]:
        res = motor.pesquisar(relatorio.ler_nomes_digitados(busca), regs)
        assert sorted(r.pagamento.favorecido for r in res) == ["ECCAPLAN CONSULTORIA", "LEANDRO MAMEDE"], busca
        assert all(r.status == PAGO and "INSTITUTO ALAIR MARTINS" in r.observacoes[0] for r in res)
    res = motor.pesquisar(relatorio.ler_nomes_digitados("ALAIR MARTINS 1.200,00"), regs)
    assert [r.pagamento.favorecido for r in res] == ["LEANDRO MAMEDE"]
    res = motor.pesquisar(relatorio.ler_nomes_digitados("JERUSA MARTINS"), regs)
    assert [(r.pagamento.favorecido, r.observacoes) for r in res] == [("JERUSA MARTINS", [])]


def test_pesquisa_com_uma_palavra_nao_traz_todos_da_empresa_pagadora():
    regs = (_arquivo_do_pagador("A3570801001.dat", "INSTITUTO ALAIR MARTINS", "07618414000128",
                                ("ECCAPLAN CONSULTORIA", "100004074802536", 156000))
            + _arquivo_do_pagador("A3570819001.dat", "TRIPAG MEIOS DE PAGAMENTO", "22799145000014",
                                  ("JERUSA MARTINS EVENTOS LTDA", DOC, 12000000)))
    res = motor.pesquisar(relatorio.ler_nomes_digitados("MARTINS"), regs)
    assert [r.pagamento.favorecido for r in res] == ["MARTINS"]
    assert not any("empresa pagadora" in o for r in res for o in r.observacoes)
