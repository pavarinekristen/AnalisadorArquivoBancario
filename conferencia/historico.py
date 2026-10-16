from __future__ import annotations

import contextlib
import getpass
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pandas as pd

from .modelos import DEVOLUCAO, Banco, Pagamento, Resultado
from .motor import nome_normalizado
from .reprocessar import ResultadoMover

BANCO = Path(__file__).resolve().parent.parent / "dados" / "historico.db"
LIMITE_BUSCA = 1000

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS conferencias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_hora TEXT NOT NULL,
        relatorio TEXT,
        arquivos TEXT,
        total INTEGER
    );
    CREATE TABLE IF NOT EXISTS itens (
        conferencia_id INTEGER REFERENCES conferencias(id),
        favorecido TEXT, cpf_cnpj TEXT, documento TEXT, valor REAL, data_pagto TEXT,
        status TEXT, codigos TEXT, arquivo TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_itens_status ON itens(status);
    CREATE INDEX IF NOT EXISTS idx_itens_cpf_cnpj ON itens(cpf_cnpj);
    CREATE INDEX IF NOT EXISTS idx_itens_favorecido ON itens(favorecido);
    CREATE INDEX IF NOT EXISTS idx_conferencias_data_hora ON conferencias(data_hora);
    CREATE TABLE IF NOT EXISTS movimentacoes (
        data_hora TEXT NOT NULL, banco TEXT, origem TEXT, destino TEXT, arquivo TEXT, resultado TEXT
    );
"""
# Cada mudança de estrutura entra no fim da lista; PRAGMA user_version guarda até onde a base já foi.
_MIGRACOES: list[str] = [
    # Bases criadas antes do Tribanco: tudo que já está lá é Santander.
    "ALTER TABLE conferencias ADD COLUMN banco TEXT NOT NULL DEFAULT 'santander'",
    "ALTER TABLE conferencias ADD COLUMN operador TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE movimentacoes ADD COLUMN operador TEXT NOT NULL DEFAULT ''",
]
_PREPARADAS: set[Path] = set()


def _colunas(con: sqlite3.Connection, tabela: str) -> set[str]:
    return {c[1] for c in con.execute(f"PRAGMA table_info({tabela})")}


def _preparar(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    versao = con.execute("PRAGMA user_version").fetchone()[0]
    if versao == 0 and "banco" in _colunas(con, "conferencias"):
        versao = 1   # base de antes do controle de versão que já tinha a coluna banco
    for numero, sql in enumerate(_MIGRACOES[versao:], start=versao + 1):
        con.execute(sql)
        con.execute(f"PRAGMA user_version = {numero}")
    con.commit()


@contextlib.contextmanager
def _conectar(caminho: Path = BANCO) -> Iterator[sqlite3.Connection]:
    # Abre, confirma e FECHA: conexão esquecida aberta trava o .db no Windows.
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not caminho.exists():
        _PREPARADAS.discard(caminho)
    con = sqlite3.connect(caminho)
    try:
        con.create_function("nome_norm", 1, lambda s: nome_normalizado(s or ""), deterministic=True)
        if caminho not in _PREPARADAS:
            _preparar(con)
            _PREPARADAS.add(caminho)
        yield con
        con.commit()
    finally:
        con.close()


def operador() -> str:
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        return ""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def salvar(resultados: list[Resultado], relatorio: str, arquivos: list[str],
           banco: Banco = "santander", caminho: Path = BANCO) -> int:
    with _conectar(caminho) as con:
        cur = con.execute(
            "INSERT INTO conferencias (data_hora, relatorio, arquivos, total, banco, operador) VALUES (?,?,?,?,?,?)",
            (_agora(), relatorio, ", ".join(arquivos), len(resultados), banco, operador()))
        cid = cur.lastrowid
        con.executemany(
            "INSERT INTO itens (conferencia_id, favorecido, cpf_cnpj, documento, valor, data_pagto, status, codigos, "
            "arquivo) VALUES (?,?,?,?,?,?,?,?,?)",
            [(cid, r.pagamento.favorecido, r.pagamento.cpf_cnpj, r.pagamento.documento, r.pagamento.valor,
              r.pagamento.data, r.status, " ".join(r.codigos), r.arquivo_status) for r in resultados])
    assert cid is not None
    return cid


def registrar_movimentacao(banco: Banco, origem: Path, destino: Path, resultado: ResultadoMover,
                           caminho: Path = BANCO) -> None:
    agora, quem = _agora(), operador()
    linhas = ([(n, "movido") for n in resultado.movidos]
              + [(n, "copiado para o destino, mas a origem não foi apagada") for n in resultado.copiados_sem_apagar]
              + [(n, f"não movido: {motivo}") for n, motivo in resultado.pulados])
    with _conectar(caminho) as con:
        con.executemany(
            "INSERT INTO movimentacoes (data_hora, banco, origem, destino, arquivo, resultado, operador) "
            "VALUES (?,?,?,?,?,?,?)",
            [(agora, banco, str(origem), str(destino), n, res, quem) for n, res in linhas])


def movimentacoes(caminho: Path = BANCO) -> pd.DataFrame:
    with _conectar(caminho) as con:
        return pd.read_sql_query("SELECT * FROM movimentacoes ORDER BY data_hora DESC", con)


def buscar(texto: str = "", caminho: Path = BANCO, limite: int = LIMITE_BUSCA) -> pd.DataFrame:
    with _conectar(caminho) as con:
        like = f"%{texto.strip()}%"
        return pd.read_sql_query("""
            SELECT c.data_hora AS conferido_em, c.banco, c.operador, i.favorecido, i.cpf_cnpj, i.documento, i.valor,
                   i.data_pagto, i.status, i.codigos, i.arquivo
            FROM itens i JOIN conferencias c ON c.id = i.conferencia_id
            WHERE i.favorecido LIKE ? OR i.cpf_cnpj LIKE ? OR i.documento LIKE ?
            ORDER BY c.data_hora DESC LIMIT ?""", con, params=(like, like, like, limite))


def reincidentes(caminho: Path = BANCO) -> pd.DataFrame:
    with _conectar(caminho) as con:
        return pd.read_sql_query("""
            SELECT COALESCE(NULLIF(cpf_cnpj, ''), favorecido) AS chave,
                   MAX(favorecido) AS favorecido,
                   COUNT(DISTINCT COALESCE(NULLIF(documento, ''), data_pagto || valor)) AS devolucoes,
                   GROUP_CONCAT(DISTINCT data_pagto) AS datas
            FROM itens WHERE status = ?
            GROUP BY chave HAVING devolucoes > 1
            ORDER BY devolucoes DESC""", con, params=(DEVOLUCAO,))


def devolucoes_anteriores(resultados: list[Resultado], caminho: Path = BANCO) -> dict[int, int]:
    """Índice do resultado -> quantas devoluções ele já teve em conferências anteriores (outro pagamento).
    Compara por CPF/CNPJ quando os dois lados têm; pelo nome (normalizado) só quando falta CPF."""
    if not caminho.exists() or not resultados:
        return {}
    pagamentos: list[Pagamento] = [r.pagamento for r in resultados]
    with _conectar(caminho) as con:
        con.execute("CREATE TEMP TABLE _consulta (idx INTEGER PRIMARY KEY, cpf_cnpj TEXT, "
                    "nome TEXT, documento TEXT, data_pagto TEXT, valor REAL)")
        con.executemany(
            "INSERT INTO _consulta VALUES (?,?,?,?,?,?)",
            [(i, p.cpf_cnpj, nome_normalizado(p.favorecido), p.documento, p.data, p.valor)
             for i, p in enumerate(pagamentos)])
        linhas = con.execute("""
            SELECT q.idx, COUNT(DISTINCT COALESCE(NULLIF(i.documento, ''), i.data_pagto || i.valor))
            FROM _consulta q JOIN itens i
              ON i.status = ?
             AND CASE WHEN q.cpf_cnpj <> '' AND COALESCE(i.cpf_cnpj, '') <> '' THEN i.cpf_cnpj = q.cpf_cnpj
                      ELSE nome_norm(i.favorecido) = q.nome END
             AND COALESCE(NULLIF(i.documento, ''), i.data_pagto || i.valor)
                 <> COALESCE(NULLIF(q.documento, ''), q.data_pagto || q.valor)
            GROUP BY q.idx""", (DEVOLUCAO,)).fetchall()
    return {idx: n for idx, n in linhas if n}


def expurgar(antes_de: datetime, caminho: Path = BANCO) -> int:
    """LGPD: apaga conferências (e itens) e movimentações anteriores à data. Devolve quantos itens saíram."""
    if not caminho.exists():
        return 0
    limite = antes_de.isoformat(timespec="seconds")
    with _conectar(caminho) as con:
        n = con.execute("DELETE FROM itens WHERE conferencia_id IN "
                        "(SELECT id FROM conferencias WHERE data_hora < ?)", (limite,)).rowcount
        con.execute("DELETE FROM conferencias WHERE data_hora < ?", (limite,))
        con.execute("DELETE FROM movimentacoes WHERE data_hora < ?", (limite,))
    return n
