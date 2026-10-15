import os
import time
from datetime import date, timedelta

import pytest

from conferencia import ntedi, reprocessar


@pytest.fixture
def pastas(monkeypatch, tmp_path):
    monkeypatch.setattr(ntedi, "BASE_RETORNO", tmp_path / "INBOXENV")
    monkeypatch.setattr(ntedi, "BASE_TRIBANCO", tmp_path / "tribanco")
    monkeypatch.setattr(reprocessar, "BASE_INBOX", tmp_path / "INBOX")
    monkeypatch.setattr(reprocessar, "BASE_TRIBANCO_INBOX", None)
    origem, destino = reprocessar.caminhos("santander", "GE1")
    origem.mkdir(parents=True)
    destino.mkdir(parents=True)
    return origem, destino


def test_caminhos(pastas, tmp_path, monkeypatch):
    assert reprocessar.caminhos("santander", " /GE1/ ") == (tmp_path / "INBOXENV" / "GE1", tmp_path / "INBOX" / "GE1")
    assert reprocessar.caminhos("tribanco", "") == (tmp_path / "tribanco", None)
    monkeypatch.setattr(reprocessar, "BASE_TRIBANCO_INBOX", tmp_path / "tri_inbox")
    assert reprocessar.caminhos("tribanco", "X")[1] == tmp_path / "tri_inbox" / "X"


def test_move_arquivo(pastas):
    origem, destino = pastas
    (origem / "A.TXT").write_bytes(b"conteudo")
    r = reprocessar.mover(origem, destino, ["A.TXT"])
    assert r.movidos == ["A.TXT"] and r.pulados == []
    assert not (origem / "A.TXT").exists()
    assert (destino / "A.TXT").read_bytes() == b"conteudo"


def test_conflito_nao_sobrescreve(pastas):
    origem, destino = pastas
    (origem / "A.TXT").write_bytes(b"novo")
    (destino / "A.TXT").write_bytes(b"antigo")
    r = reprocessar.mover(origem, destino, ["A.TXT"])
    assert r.movidos == [] and "já existe" in r.pulados[0][1]
    assert (origem / "A.TXT").read_bytes() == b"novo"
    assert (destino / "A.TXT").read_bytes() == b"antigo"


@pytest.mark.parametrize("ruim", ["..", "../A.TXT", "sub\\A.TXT", "C:A.TXT", ""])
def test_nome_invalido(pastas, ruim):
    origem, destino = pastas
    r = reprocessar.mover(origem, destino, [ruim])
    assert r.movidos == [] and r.pulados == [(ruim, "nome de arquivo inválido")]


def test_arquivo_inexistente(pastas):
    origem, destino = pastas
    r = reprocessar.mover(origem, destino, ["NAO.TXT"])
    assert r.pulados == [("NAO.TXT", "não está na pasta de origem")]


def test_destino_inexistente_nao_cria(pastas, tmp_path):
    origem, _ = pastas
    (origem / "A.TXT").write_bytes(b"x")
    destino = tmp_path / "INBOX" / "OUTRA"
    r = reprocessar.mover(origem, destino, ["A.TXT"])
    assert r.movidos == [] and "não existe" in r.pulados[0][1]
    assert not destino.exists() and (origem / "A.TXT").exists()


def test_destino_nao_configurado(pastas):
    origem, _ = pastas
    (origem / "A.TXT").write_bytes(b"x")
    r = reprocessar.mover(origem, None, ["A.TXT"])
    assert r.pulados == [("A.TXT", "pasta de destino não configurada")]


def test_mesma_pasta(pastas):
    origem, _ = pastas
    (origem / "A.TXT").write_bytes(b"x")
    r = reprocessar.mover(origem, origem, ["A.TXT"])
    assert "mesma pasta" in r.pulados[0][1] and (origem / "A.TXT").exists()


def test_simular_nao_mexe(pastas):
    origem, destino = pastas
    (origem / "A.TXT").write_bytes(b"x")
    (origem / "B.TXT").write_bytes(b"y")
    (destino / "B.TXT").write_bytes(b"z")
    r = reprocessar.mover(origem, destino, ["A.TXT", "B.TXT"], simular=True)
    assert r.movidos == ["A.TXT"] and [n for n, _ in r.pulados] == ["B.TXT"]
    assert sorted(p.name for p in origem.iterdir()) == ["A.TXT", "B.TXT"]
    assert [p.name for p in destino.iterdir()] == ["B.TXT"]


def test_falha_em_um_nao_derruba_os_outros(pastas, monkeypatch):
    origem, destino = pastas
    (origem / "A.TXT").write_bytes(b"x")
    (origem / "B.TXT").write_bytes(b"y")
    renomear = os.rename

    def rename_quebrado(de, para):
        if str(de).endswith("A.TXT"):
            raise PermissionError("acesso negado")
        return renomear(de, para)

    monkeypatch.setattr(reprocessar.os, "rename", rename_quebrado)
    r = reprocessar.mover(origem, destino, ["A.TXT", "B.TXT"])
    assert r.movidos == ["B.TXT"]
    assert r.pulados[0][0] == "A.TXT" and "acesso negado" in r.pulados[0][1]
    assert (origem / "A.TXT").exists() and (destino / "B.TXT").exists()


def test_volume_diferente_copia_e_apaga(pastas, monkeypatch):
    origem, destino = pastas
    (origem / "A.TXT").write_bytes(b"conteudo")
    renomear = os.rename

    def rename_outro_volume(de, para):
        if not str(de).endswith(".tmp"):
            erro = OSError("volume diferente")
            erro.winerror = 17
            raise erro
        return renomear(de, para)

    monkeypatch.setattr(reprocessar.os, "rename", rename_outro_volume)
    r = reprocessar.mover(origem, destino, ["A.TXT"])
    assert r.movidos == ["A.TXT"]
    assert not (origem / "A.TXT").exists()
    assert [p.name for p in destino.iterdir()] == ["A.TXT"]
    assert (destino / "A.TXT").read_bytes() == b"conteudo"


def test_listar_filtra_data_e_nome(pastas):
    origem, _ = pastas
    (origem / "FORN_A_MOV.TXT").write_bytes(b"x")
    (origem / "FORN_B_CRI.TXT").write_bytes(b"x")
    antigo = origem / "FORN_C_MOV.TXT"
    antigo.write_bytes(b"x")
    ts = time.mktime((date.today() - timedelta(days=30)).timetuple())
    os.utime(antigo, (ts, ts))
    hoje = date.today()
    assert [i.nome for i in reprocessar.listar(origem, hoje - timedelta(days=1), hoje)] == [
        "FORN_A_MOV.TXT", "FORN_B_CRI.TXT"]
    assert [i.nome for i in reprocessar.listar(origem, trecho="mov")] == ["FORN_A_MOV.TXT", "FORN_C_MOV.TXT"]


def test_registrar_movimentacao(pastas, tmp_path):
    from conferencia import historico
    origem, destino = pastas
    (origem / "A.TXT").write_bytes(b"x")
    r = reprocessar.mover(origem, destino, ["A.TXT", "NAO.TXT"])
    db = tmp_path / "historico.db"
    historico.registrar_movimentacao("santander", origem, destino, r, caminho=db)
    df = historico.movimentacoes(caminho=db)
    assert list(zip(df["arquivo"], df["resultado"])) == [
        ("A.TXT", "movido"), ("NAO.TXT", "não movido: não está na pasta de origem")]
