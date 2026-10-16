from conferencia import historico
from conferencia.modelos import DEVOLUCAO, PAGO, Pagamento, Resultado


def _res(nome, cpf, doc, status=DEVOLUCAO):
    return Resultado(pagamento=Pagamento(favorecido=nome, cpf_cnpj=cpf, documento=doc, valor=10.0, data="07102026"),
                     status=status)


def test_conexao_e_fechada(tmp_path):
    db = tmp_path / "historico.db"
    historico.salvar([_res("FULANO", "111", "100001")], "teste", [], caminho=db)
    historico.buscar("FULANO", caminho=db)
    db.unlink()   # no Windows falha se alguma conexão ficou aberta
    assert not db.exists()


def test_devolucoes_anteriores_por_cpf_e_nao_por_homonimo(tmp_path):
    db = tmp_path / "historico.db"
    historico.salvar([_res("JOSE DA SILVA", "111", "100001"), _res("MARIA", "333", "100003", PAGO)],
                     "antes", [], caminho=db)
    atuais = [_res("JOSE DA SILVA", "222", "100009"),   # homônimo com outro CPF: não conta
              _res("JOSE DA SILVA", "111", "100009"),   # mesmo CPF: conta
              _res("Jose  da Silva", "", "100009"),     # sem CPF: compara pelo nome normalizado
              _res("JOSE DA SILVA", "111", "100001"),   # o mesmo pagamento já gravado não conta
              _res("MARIA", "333", "100004")]           # só teve pago
    assert historico.devolucoes_anteriores(atuais, caminho=db) == {1: 1, 2: 1}


def test_registro_antigo_sem_cpf_compara_pelo_nome(tmp_path):
    db = tmp_path / "historico.db"
    historico.salvar([_res("JOSÉ DA SILVA", "", "100002")], "antes", [], caminho=db)
    assert historico.devolucoes_anteriores([_res("JOSE DA SILVA", "111", "100009")], caminho=db) == {0: 1}


def test_migra_base_antiga_e_grava_operador(tmp_path):
    import sqlite3
    db = tmp_path / "historico.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE conferencias (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT NOT NULL, "
                "relatorio TEXT, arquivos TEXT, total INTEGER, banco TEXT NOT NULL DEFAULT 'santander')")
    con.commit()
    con.close()
    historico.salvar([_res("FULANO", "111", "100001")], "teste", [], caminho=db)
    df = historico.buscar("", caminho=db)
    assert list(df["operador"]) == [historico.operador()]


def test_expurgar_apaga_antigos(tmp_path):
    from datetime import datetime, timedelta
    db = tmp_path / "historico.db"
    historico.salvar([_res("FULANO", "111", "100001")], "teste", [], caminho=db)
    assert historico.expurgar(datetime.now() - timedelta(days=1), caminho=db) == 0
    assert historico.expurgar(datetime.now() + timedelta(days=1), caminho=db) == 1
    assert historico.buscar("", caminho=db).empty
