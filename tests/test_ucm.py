import re

import pytest

from conferencia import ucm

PASTA = "fin$/trangl$/mastersf$/pendentes$"


def _linha(i: int) -> dict[str, str]:
    return {"document_id": str(i), "document_title": f"arq{i}.csv",
            "document_created_date": "10/14/26 12:00 AM", "vault_file_size": "10"}


def _falso_ucm(ids: list[int], chamadas: list[str]) -> ucm.Buscador:
    def buscar(folder_path: str) -> list[dict[str, str]]:
        chamadas.append(folder_path)
        assert folder_path.startswith(PASTA)
        inicio = int(re.search(r"dID >= `(\d+)", folder_path).group(1))
        fim = re.search(r"dID < `(\d+)", folder_path)
        sel = [i for i in ids if i >= inicio and (fim is None or i < int(fim.group(1)))]
        return [_linha(i) for i in sorted(sel, reverse=True)[:ucm.LIMITE_PAGINA]]
    return buscar


@pytest.mark.parametrize("ids", [
    [],
    list(range(1, 10)),
    list(range(1, 21)),
    list(range(1000, 1500)),
    [5, 7, 80_000_000, 80_000_001] + list(range(79_000_000, 79_000_300, 3)),
])
def test_listar_paginado_traz_todos(ids):
    chamadas: list[str] = []
    docs = ucm.listar_paginado(PASTA, _falso_ucm(ids, chamadas))
    assert sorted(d.id for d in docs) == sorted(ids)


def test_listar_paginado_rejeita_crase():
    with pytest.raises(ValueError):
        ucm.listar_paginado("x` <OR> dID > `0", lambda _: [])


def test_documento_de_linha_converte_data():
    d = ucm.DocumentoUCM.de_linha(_linha(42) | {"document_created_date": "8/28/26 12:02 AM"})
    assert d.id == 42 and d.criado_em.year == 2026 and d.criado_em.minute == 2


def test_consulta_fecha_crases_como_o_flow():
    q = ucm._consulta(PASTA, "dID >= `10`", "dID < `20`")
    assert f"dDocAccount <matches> `{q}`" == (
        f"dDocAccount <matches> `{PASTA}` <AND> dID >= `10` <AND> dID < `20`")
    assert ucm._consulta(PASTA) == PASTA


def test_listar_paginado_repassa_filtro_extra():
    chamadas: list[str] = []
    ids = list(range(100, 160))
    docs = ucm.listar_paginado(PASTA, _falso_ucm(ids, chamadas), "dDocTitle <substring> `X`")
    assert sorted(d.id for d in docs) == ids
    assert all("<AND> dDocTitle <substring> `X` <AND> dID >= `" in c for c in chamadas)


class _ClienteFalso(ucm.ClienteUCM):
    def __init__(self, linhas):
        super().__init__("id", "segredo")
        self.linhas, self.consultas = linhas, []

    def buscar(self, folder_path):
        self.consultas.append(folder_path)
        return self.linhas


def test_buscar_por_id_tenta_content_id_e_depois_did():
    c = _ClienteFalso([])
    assert c.buscar_por_id(PASTA, " 80505382 ") is None
    assert c.consultas == [f"{PASTA}` <AND> dDocName <matches> `UCMFA80505382",
                           f"{PASTA}` <AND> dID = `80505382"]


def test_buscar_por_id_aceita_content_id_completo():
    c = _ClienteFalso([_linha(80503291)])
    assert c.buscar_por_id(PASTA, "ucmfa80505382").id == 80503291
    assert c.consultas == [f"{PASTA}` <AND> dDocName <matches> `UCMFA80505382"]


@pytest.mark.parametrize("ruim", ["1` <OR> dID > `0", "", "80 1"])
def test_buscar_por_id_rejeita_injecao(ruim):
    with pytest.raises(ValueError):
        _ClienteFalso([]).buscar_por_id(PASTA, ruim)


class _UcmMemoria(ucm.ClienteUCM):
    def __init__(self, ids):
        super().__init__("id", "segredo")
        self.ids = ids

    def buscar(self, folder_path):
        chamadas: list[str] = []
        teto = re.search(r"dID < `(\d+)", folder_path)
        if teto and "dID >=" not in folder_path:
            sel = [i for i in self.ids if i < int(teto.group(1))]
            return [_linha(i) for i in sorted(sel, reverse=True)[:ucm.LIMITE_PAGINA]]
        if "dID" not in folder_path:
            return [_linha(i) for i in sorted(self.ids, reverse=True)[:ucm.LIMITE_PAGINA]]
        return _falso_ucm(self.ids, chamadas)(folder_path)


def test_na_posicao_atravessa_paginas():
    ids = list(range(1000, 1100))
    c = _UcmMemoria(ids)
    assert c.na_posicao(PASTA, 1).id == 1099
    assert c.na_posicao(PASTA, 78).id == 1099 - 77
    assert c.na_posicao(PASTA, 100).id == 1000
    assert c.na_posicao(PASTA, 101) is None


def test_listar_paginado_repesca_faixa_que_falhou():
    chamadas: list[str] = []
    real = _falso_ucm(list(range(1000, 1100)), chamadas)
    falhou: set[str] = set()

    def instavel(folder_path: str) -> list[dict[str, str]]:
        if folder_path not in falhou:   # cada consulta falha na primeira vez
            falhou.add(folder_path)
            raise ucm.ErroUCM("timeout")
        return real(folder_path)

    docs = ucm.listar_paginado(PASTA, instavel)
    assert sorted(d.id for d in docs) == list(range(1000, 1100))


def test_listar_paginado_devolve_parcial_quando_faixa_sempre_falha():
    chamadas: list[str] = []
    real = _falso_ucm(list(range(1000, 1100)), chamadas)

    def quebrada(folder_path: str) -> list[dict[str, str]]:
        if "dID < `" in folder_path and "dID >= `0`" in folder_path:
            raise ucm.ErroUCM("timeout")
        return real(folder_path)

    with pytest.raises(ucm.ErroUCMParcial) as erro:
        ucm.listar_paginado(PASTA, quebrada)
    ids = [d.id for d in erro.value.docs]
    assert ids and ids == sorted(ids, reverse=True) and set(ids) <= set(range(1000, 1100))


def test_subpastas_usa_starts_com_matches_vazio():
    alvo = ucm._alvo("tranap$/tribanco$/retorno$", subpastas=True)
    q = ucm._consulta(alvo, "dID >= `10`")
    assert f"dDocAccount <matches> `{q}`" == ("dDocAccount <matches> `-` <OR> dDocAccount <starts> "
                                              "`tranap$/tribanco$/retorno$` <AND> dID >= `10`")
    assert ucm._alvo(" tranap$/tribanco$/retorno$ ") == "tranap$/tribanco$/retorno$"


@pytest.mark.parametrize("ruim", ["", "   ", "a` <OR> b"])
def test_alvo_rejeita_pasta_vazia_ou_com_crase(ruim):
    with pytest.raises(ValueError):
        ucm._alvo(ruim, subpastas=True)


def test_buscar_por_id_com_subpastas():
    c = _ClienteFalso([])
    c.buscar_por_id(PASTA, "UCMFA1", subpastas=True)
    assert c.consultas == [f"-` <OR> dDocAccount <starts> `{PASTA}` <AND> dDocName <matches> `UCMFA1"]


def test_localizar_cai_no_titulo_quando_nao_e_id():
    c = _ClienteFalso([])
    assert c.localizar(PASTA, "A35708190210260002.dat", subpastas=True) is None
    assert c.consultas[-1] == (f"-` <OR> dDocAccount <starts> `{PASTA}` <AND> "
                               "dDocTitle <substring> `A35708190210260002.dat")


def test_localizar_so_digitos_nao_busca_titulo():
    c = _ClienteFalso([])
    assert c.localizar(PASTA, "80505382") is None
    assert all("dDocTitle" not in q for q in c.consultas)


def test_listar_paginado_nao_repesca_erro_de_credencial():
    chamadas: list[str] = []

    def recusa(folder_path: str) -> list[dict[str, str]]:
        chamadas.append(folder_path)
        raise ucm.ErroUCM("HTTP 401", recuperavel=False)

    with pytest.raises(ucm.ErroUCM) as erro:
        ucm.listar_paginado(PASTA, recusa)
    assert not isinstance(erro.value, ucm.ErroUCMParcial) and len(chamadas) == 1


class _Resposta:
    def __init__(self, corpo: bytes) -> None:
        self.corpo = corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self) -> bytes:
        return self.corpo


def _http_erro(codigo: int):
    import urllib.error
    return urllib.error.HTTPError("https://x/servico", codigo, "erro", {}, None)


def test_requisitar_repete_5xx_e_nao_repete_4xx(monkeypatch):
    import urllib.request
    monkeypatch.setattr(ucm.time, "sleep", lambda _s: None)
    respostas = [_http_erro(503), _Resposta(b"ok")]
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: (
        (_ for _ in ()).throw(r) if isinstance(r := respostas.pop(0), Exception) else r))
    c = ucm.ClienteUCM("id", "segredo")
    assert c._requisitar(urllib.request.Request("https://x/servico")) == b"ok"

    tentativas: list[int] = []

    def sempre_401(req, timeout):
        tentativas.append(1)
        raise _http_erro(401)

    monkeypatch.setattr(urllib.request, "urlopen", sempre_401)
    with pytest.raises(ucm.ErroUCM) as erro:
        c._requisitar(urllib.request.Request("https://x/servico"))
    assert len(tentativas) == 1 and not erro.value.recuperavel


def test_token_renovado_quando_expira(monkeypatch):
    import json
    import urllib.request
    pedidos: list[str] = []

    def urlopen(req, timeout):
        pedidos.append(req.full_url)
        return _Resposta(json.dumps({"access_token": f"t{len(pedidos)}", "expires_in": 3600}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(ucm, "URL_TOKEN", "https://idcs.exemplo/oauth2/v1/token")
    monkeypatch.setattr(ucm, "ESCOPO", "escopo")
    c = ucm.ClienteUCM("id", "segredo")
    assert c._bearer() == "t1" and c._bearer() == "t1" and len(pedidos) == 1
    c._expira = 0
    assert c._bearer() == "t2" and len(pedidos) == 2


def test_sem_configuracao_nao_tenta_conectar(monkeypatch):
    monkeypatch.setattr(ucm, "URL_TOKEN", "")
    with pytest.raises(ucm.ErroUCM) as erro:
        ucm.ClienteUCM("id", "segredo")._bearer()
    assert not erro.value.recuperavel
