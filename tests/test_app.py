"""Tela de ponta a ponta com o AppTest do Streamlit (sem navegador)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import logging

from conferencia import historico, log

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(historico, "BANCO", tmp_path / "historico.db")
    monkeypatch.setattr(log, "PASTA", tmp_path / "logs")
    monkeypatch.setattr(log, "ARQUIVO", tmp_path / "logs" / "app.log")
    logging.getLogger("conferencia").handlers.clear()
    for nome in ("salvar", "devolucoes_anteriores", "buscar", "reincidentes", "movimentacoes", "expurgar"):
        func = getattr(historico, nome)
        monkeypatch.setattr(historico, nome, lambda *a, _f=func, **k: _f(*a, **{"caminho": tmp_path / "historico.db", **k}))
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def test_abre_sem_erro(app):
    assert not app.exception
    assert app.title[0].value == "Conferência de Pagamentos"


def test_conferir_sem_informar_avisa(app):
    botao = next(b for b in app.button if b.label == "CONFERIR")
    botao.click().run()
    assert not app.exception
    assert any("Falta informar" in w.value for w in app.warning)


def test_data_invalida_digitada_nao_quebra(app):
    app.text_area[0].input("FULANO DA SILVA 31/02/2026").run()
    assert not app.exception


@pytest.mark.parametrize("pagina", ["reprocessar", "historico", "codigos", "ucm", "sobre"])
def test_cada_pagina_abre(app, pagina):
    at = AppTest.from_string(f"from telas import {pagina}\n{pagina}.pagina()", default_timeout=30)
    at.run()
    assert not at.exception, at.exception
