import os
import time
from datetime import date, timedelta
from pathlib import Path

from conferencia import ntedi


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

    def _iterdir_com_erro(self):
        raise OSError("rede indisponível")

    monkeypatch.setattr(Path, "iterdir", _iterdir_com_erro)
    r = ntedi.ler_subpasta("retorno", "GE1")
    assert any("rede indisponível" in a for a in r.avisos)
