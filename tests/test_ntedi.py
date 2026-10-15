import os
import time
from datetime import date, timedelta
from pathlib import Path

from conferencia import cnab240, ntedi

from .conftest import do_tribanco, header_tribanco, seg_a


def _preparar_bases(monkeypatch, tmp_path):
    monkeypatch.setattr(ntedi, "BASE_RETORNO", tmp_path / "INBOXENV")
    monkeypatch.setattr(ntedi, "BASE_REMESSA", tmp_path / "SENTBOX")


def test_caminho_monta_cada_tipo(monkeypatch, tmp_path):
    _preparar_bases(monkeypatch, tmp_path)
    assert ntedi.caminho("retorno", "GE202255") == tmp_path / "INBOXENV" / "GE202255"
    assert ntedi.caminho("remessa", "GE202255") == tmp_path / "SENTBOX" / "GE202255"


def test_caminho_ignora_barras_nas_pontas():
    assert ntedi.caminho("retorno", "/GE1/").name == "GE1"


def test_ler_subpasta_so_le_o_tipo_escolhido(monkeypatch, tmp_path):
    _preparar_bases(monkeypatch, tmp_path)
    inbox = tmp_path / "INBOXENV" / "GE1"
    sent = tmp_path / "SENTBOX" / "GE1"
    inbox.mkdir(parents=True)
    sent.mkdir(parents=True)
    (inbox / "FORN_E_01_071026P_MOV.TXT").write_bytes(b"")
    (sent / "FORN_E_01_071026P_CRI.TXT").write_bytes(b"")

    r = ntedi.ler_subpasta("retorno", "GE1")
    assert {a.nome for a in r.arquivos} == {"FORN_E_01_071026P_MOV.TXT"}
    assert not r.avisos


def test_ler_subpasta_avisa_quando_pasta_nao_existe(monkeypatch, tmp_path):
    _preparar_bases(monkeypatch, tmp_path)
    r = ntedi.ler_subpasta("remessa", "GE1")
    assert any("Remessa" in a and "não encontrada" in a for a in r.avisos)
    assert r.arquivos == []


def test_filtro_por_data_de_modificacao(monkeypatch, tmp_path):
    _preparar_bases(monkeypatch, tmp_path)
    inbox = tmp_path / "INBOXENV" / "GE1"
    inbox.mkdir(parents=True)
    recente = inbox / "FORN_E_01_071026P_MOV.TXT"
    antigo = inbox / "FORN_E_02_071026P_MOV.TXT"
    recente.write_bytes(b"")
    antigo.write_bytes(b"")
    ts_antigo = time.mktime((date.today() - timedelta(days=30)).timetuple())
    os.utime(antigo, (ts_antigo, ts_antigo))

    r = ntedi.ler_subpasta("retorno", "GE1", de=date.today() - timedelta(days=1), ate=date.today())
    assert r.total_ignorados_data == 1
    assert {a.nome for a in r.arquivos} == {"FORN_E_01_071026P_MOV.TXT"}


def test_erro_de_rede_vira_aviso_e_nao_propaga(monkeypatch, tmp_path):
    _preparar_bases(monkeypatch, tmp_path)
    inbox = tmp_path / "INBOXENV" / "GE1"
    inbox.mkdir(parents=True)

    def _scandir_com_erro(_caminho):
        raise OSError("rede indisponível")

    monkeypatch.setattr(ntedi.os, "scandir", _scandir_com_erro)
    r = ntedi.ler_subpasta("retorno", "GE1")
    assert any("rede indisponível" in a for a in r.avisos)


def _contar_aberturas(monkeypatch):
    abertos: list[str] = []
    abrir, ler = open, Path.read_bytes

    def open_contando(caminho, *a, **k):
        abertos.append(Path(caminho).name)
        return abrir(caminho, *a, **k)

    def read_bytes_contando(self):
        abertos.append(self.name)
        return ler(self)

    monkeypatch.setattr(cnab240, "open", open_contando, raising=False)
    monkeypatch.setattr(Path, "read_bytes", read_bytes_contando)
    return abertos


def _retorno_tribanco() -> bytes:
    return "\n".join([header_tribanco(), do_tribanco(seg_a("X", "100004079087464", "18062026", 100, "BD"))]
                     ).encode("latin-1")


def test_so_abre_o_que_precisa(monkeypatch, tmp_path):
    pasta = tmp_path / "GE1"
    pasta.mkdir()
    (pasta / "FORN_E_01_071026P_MOV.TXT").write_bytes(b"")
    (pasta / "FORN_E_01_071026P_REL.TXT").write_bytes(b"x")
    (pasta / "Retorno_150920275_OK").write_bytes(b"x")
    (pasta / "relatorio.pdf").write_bytes(b"%PDF")
    (pasta / "baixado_sem_nome.txt").write_bytes(_retorno_tribanco())
    (pasta / "outro_banco.txt").write_bytes(b"0330000" + b"0" * 300)
    abertos = _contar_aberturas(monkeypatch)

    r = ntedi.ler_pasta(pasta, "Teste")
    assert sorted(abertos) == ["FORN_E_01_071026P_MOV.TXT", "baixado_sem_nome.txt", "outro_banco.txt"]
    assert {a.nome: a.tipo for a in r.arquivos} == {
        "FORN_E_01_071026P_MOV.TXT": "MOV", "FORN_E_01_071026P_REL.TXT": "REL",
        "Retorno_150920275_OK": "RETORNO", "baixado_sem_nome.txt": "RET"}
    assert r.total_fora_do_padrao == 2 and len(r.registros) == 1


def test_segunda_leitura_usa_cache_e_rele_arquivo_alterado(monkeypatch, tmp_path):
    pasta = tmp_path / "GE1"
    pasta.mkdir()
    arq = pasta / "A35708191410260001.dat"
    arq.write_bytes(_retorno_tribanco())
    (pasta / "FORN_E_01_071026P_MOV.TXT").write_bytes(b"")
    abertos = _contar_aberturas(monkeypatch)

    ntedi.ler_pasta(pasta, "Teste")
    assert len(abertos) == 2
    abertos.clear()
    r = ntedi.ler_pasta(pasta, "Teste")
    assert abertos == [] and len(r.arquivos) == 2

    arq.write_bytes(_retorno_tribanco() + b"\n")
    os.utime(arq, (time.time() + 60, time.time() + 60))
    ntedi.ler_pasta(pasta, "Teste")
    assert abertos == ["A35708191410260001.dat"]


def test_falha_em_um_arquivo_nao_derruba_os_outros(monkeypatch, tmp_path):
    pasta = tmp_path / "GE1"
    pasta.mkdir()
    (pasta / "FORN_E_01_071026P_MOV.TXT").write_bytes(b"")
    (pasta / "FORN_E_02_071026P_MOV.TXT").write_bytes(b"")
    ler = Path.read_bytes

    def read_bytes_quebrado(self):
        if self.name.startswith("FORN_E_01"):
            raise OSError("conexão caiu")
        return ler(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes_quebrado)
    r = ntedi.ler_pasta(pasta, "Teste")
    assert [a.nome for a in r.arquivos] == ["FORN_E_02_071026P_MOV.TXT"]
    assert any("FORN_E_01_071026P_MOV.TXT" in a and "conexão caiu" in a for a in r.avisos)
