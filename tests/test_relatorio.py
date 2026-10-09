from conferencia import relatorio

from .conftest import EXCEL_0510, precisa_dados_reais

COLADO = """
Situação: Com Erro
578553
EMPRESA EXEMPLO SEGUROS/04252011000110
Boleto Bancário
05/10/2026
100009000000002-12345-RCA
10.767,58
Inclusão Efetuada com Sucesso
100009000000003-12346-RCA
60,90
Inclusão Efetuada com Sucesso
Total p/ Referência 578553: 10.828,48
"""


def test_lista_colada_varios_documentos():
    pags = relatorio.ler_texto_colado(COLADO)
    assert [(p.documento, p.valor) for p in pags] == [("100009000000002", 10767.58),
                                                       ("100009000000003", 60.90)]
    p = pags[0]
    assert (p.favorecido, p.cpf_cnpj, p.data, p.metodo, p.referencia, p.op) == (
        "EMPRESA EXEMPLO SEGUROS", "4252011000110", "05102026", "Boleto Bancário", "578553", "12345")


@precisa_dados_reais
def test_excel_0510_abas():
    listas = relatorio.ler_excel(EXCEL_0510.read_bytes())
    tam = {k.split(" (")[1]: len(v) for k, v in listas.items()}
    assert tam == {"relatório do banco)": 18, "resumo)": 18, "sistema - não pagos)": 12}
    banco = next(v for k, v in listas.items() if "banco" in k)
    assert all(len(p.documento) == 15 and p.documento.startswith("10000") for p in banco)
