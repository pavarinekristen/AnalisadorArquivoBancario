from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import ntedi
from .modelos import Banco

# Arquivo com erro sai do INBOXENV e volta para o INBOX (mesma subpasta): lá ele é processado de novo.
BASE_INBOX = Path(r"\\Ntedi020\grpaftdata$\INBOX")
# Destino do Tribanco ainda não informado: enquanto for None, a tela não deixa mover.
BASE_TRIBANCO_INBOX: Path | None = None

_ERRO_VOLUME_DIFERENTE = 17   # ERROR_NOT_SAME_DEVICE: rename entre shares/discos diferentes


@dataclass(slots=True, frozen=True)
class ItemArquivo:
    nome: str
    tamanho: int
    modificado: datetime


@dataclass
class ResultadoMover:
    movidos: list[str] = field(default_factory=list)
    pulados: list[tuple[str, str]] = field(default_factory=list)


def _subpasta(subpasta: str) -> str:
    return subpasta.strip().strip("\\/")


def caminhos(banco: Banco, subpasta: str) -> tuple[Path, Path | None]:
    nome = _subpasta(subpasta)
    if banco == "tribanco":
        destino = None
        if BASE_TRIBANCO_INBOX is not None:
            destino = BASE_TRIBANCO_INBOX / nome if nome else BASE_TRIBANCO_INBOX
        return ntedi.caminho_tribanco(subpasta), destino
    return ntedi.caminho("retorno", subpasta), BASE_INBOX / nome


def listar(origem: Path, de: date | None = None, ate: date | None = None, trecho: str = "") -> list[ItemArquivo]:
    entradas, _ = ntedi.listar_com_filtro(origem, de, ate)
    trecho = trecho.strip().upper()
    itens: list[ItemArquivo] = []
    for e in entradas:
        if trecho and trecho not in e.name.upper():
            continue
        info = e.stat()
        itens.append(ItemArquivo(e.name, info.st_size, datetime.fromtimestamp(info.st_mtime)))
    return itens


def _nome_valido(nome: str) -> bool:
    return bool(nome) and nome not in (".", "..") and Path(nome).name == nome and not any(c in nome for c in "\\/:")


def _copiar_e_apagar(de: Path, para: Path) -> None:
    # Fallback para volumes diferentes: copia com nome temporário, confere e só então troca e apaga.
    tmp = para.with_name(para.name + ".tmp")
    if tmp.exists():
        raise FileExistsError(f"já existe {tmp.name} no destino")
    shutil.copy2(de, tmp)
    try:
        if tmp.stat().st_size != de.stat().st_size:
            raise OSError("cópia ficou com tamanho diferente")
        os.rename(tmp, para)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    de.unlink()


def _mover_um(de: Path, para: Path) -> None:
    # os.rename no Windows falha se o destino existir: nunca sobrescreve, nem em corrida.
    try:
        os.rename(de, para)
    except OSError as e:
        if getattr(e, "winerror", None) != _ERRO_VOLUME_DIFERENTE:
            raise
        _copiar_e_apagar(de, para)


def mover(origem: Path, destino: Path | None, nomes: list[str], simular: bool = False) -> ResultadoMover:
    r = ResultadoMover()
    motivo_geral = ""
    if destino is None:
        motivo_geral = "pasta de destino não configurada"
    elif not destino.is_dir():
        motivo_geral = f"pasta de destino não existe ({destino})"
    elif not origem.is_dir():
        motivo_geral = f"pasta de origem não existe ({origem})"
    elif os.path.normcase(os.path.abspath(origem)) == os.path.normcase(os.path.abspath(destino)):
        motivo_geral = "origem e destino são a mesma pasta"
    if motivo_geral:
        r.pulados = [(n, motivo_geral) for n in nomes]
        return r
    assert destino is not None

    for nome in dict.fromkeys(nomes):
        if not _nome_valido(nome):
            r.pulados.append((nome, "nome de arquivo inválido"))
            continue
        de, para = origem / nome, destino / nome
        try:
            if not de.is_file():
                r.pulados.append((nome, "não está na pasta de origem"))
                continue
            if para.exists():
                r.pulados.append((nome, "já existe no destino (não sobrescrevo)"))
                continue
            if not simular:
                _mover_um(de, para)
        except OSError as e:
            r.pulados.append((nome, f"falha ao mover: {e}"))
            continue
        r.movidos.append(nome)
    return r
