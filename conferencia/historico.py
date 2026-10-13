from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from .modelos import DEVOLUCAO, Pagamento, Resultado

BANCO = Path(__file__).resolve().parent.parent / "dados" / "historico.db"


def _conectar(caminho: Path = BANCO) -> sqlite3.Connection:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.executescript("""
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
    """)
    return con


def salvar(resultados: list[Resultado], relatorio: str, arquivos: list[str],
           caminho: Path = BANCO) -> int:
    with _conectar(caminho) as con:
        cur = con.execute(
            "INSERT INTO conferencias (data_hora, relatorio, arquivos, total) VALUES (?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), relatorio, ", ".join(arquivos), len(resultados)))
        cid = cur.lastrowid
        con.executemany(
            "INSERT INTO itens VALUES (?,?,?,?,?,?,?,?,?)",
            [(cid, r.pagamento.favorecido, r.pagamento.cpf_cnpj, r.pagamento.documento, r.pagamento.valor,
              r.pagamento.data, r.status, " ".join(r.codigos), r.arquivo_status) for r in resultados])
    return cid


def buscar(texto: str = "", caminho: Path = BANCO) -> pd.DataFrame:
    with _conectar(caminho) as con:
        like = f"%{texto.strip()}%"
        return pd.read_sql_query("""
            SELECT c.data_hora AS conferido_em, i.favorecido, i.cpf_cnpj, i.documento, i.valor,
                   i.data_pagto, i.status, i.codigos, i.arquivo
            FROM itens i JOIN conferencias c ON c.id = i.conferencia_id
            WHERE i.favorecido LIKE ? OR i.cpf_cnpj LIKE ? OR i.documento LIKE ?
            ORDER BY c.data_hora DESC""", con, params=(like, like, like))


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


def devolucoes_anteriores(resultados: list[Resultado], caminho: Path = BANCO) -> dict[str, int]:
    if not caminho.exists() or not resultados:
        return {}
    pagamentos: list[Pagamento] = [r.pagamento for r in resultados]
    with _conectar(caminho) as con:
        con.execute("CREATE TEMP TABLE _consulta (idx INTEGER PRIMARY KEY, cpf_cnpj TEXT, "
                    "favorecido TEXT, documento TEXT, data_pagto TEXT, valor REAL)")
        con.executemany(
            "INSERT INTO _consulta VALUES (?,?,?,?,?,?)",
            [(i, p.cpf_cnpj, p.favorecido, p.documento, p.data, p.valor) for i, p in enumerate(pagamentos)])
        linhas = con.execute("""
            SELECT q.idx, COUNT(DISTINCT COALESCE(NULLIF(i.documento, ''), i.data_pagto || i.valor))
            FROM _consulta q JOIN itens i
              ON i.status = ?
             AND ((q.cpf_cnpj <> '' AND i.cpf_cnpj = q.cpf_cnpj) OR i.favorecido = q.favorecido)
             AND COALESCE(NULLIF(i.documento, ''), i.data_pagto || i.valor)
                 <> COALESCE(NULLIF(q.documento, ''), q.data_pagto || q.valor)
            GROUP BY q.idx""", (DEVOLUCAO,)).fetchall()
    return {pagamentos[idx].favorecido: n for idx, n in linhas if n}
