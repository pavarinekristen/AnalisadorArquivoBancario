from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from . import config

# Endereços do OIC/IDCS de cada cliente vêm de config/cliente.yaml (bloco ucm).
URL_TOKEN = config.atual().ucm.url_token
ESCOPO = config.atual().ucm.escopo
URL_OIC = config.atual().ucm.url_oic
URL_BUSCA = f"{URL_OIC}/MTS___SEAR_UCM_SOAP_TO_REST/1.0/searchUCM"
URL_ARQUIVO = f"{URL_OIC}/MTS___GET_UCM_FILE_CONT/1.0/getUCMFile"

# O flow searchUCM devolve no máximo 20 linhas (ResultCount padrão do UCM) e não expõe paginação.
# Ele concatena folder_path dentro do QueryText (dDocAccount <matches> `folder_path`), então
# filtros extras de dID são injetados ali e a faixa é dividida na mediana até cada consulta vir
# incompleta (menos de 20 linhas = faixa inteira já veio).
LIMITE_PAGINA = 20
FORMATO_DATA = "%m/%d/%y %I:%M %p"
TENTATIVAS = 3
REPESCAGENS = 2
PREFIXO_CONTENT_ID = "UCMFA"
RE_IDENTIFICADOR = re.compile(r"[A-Z0-9_.\-]+")

Buscador = Callable[[str], list[dict[str, str]]]


class ErroUCM(RuntimeError):
    """recuperavel=False: tentar de novo não adianta (credencial errada, consulta inválida)."""

    def __init__(self, mensagem: str, recuperavel: bool = True) -> None:
        super().__init__(mensagem)
        self.recuperavel = recuperavel


class ErroUCMParcial(ErroUCM):
    """Parte das consultas falhou mesmo após repescagem; `docs` tem o que foi encontrado."""

    def __init__(self, docs: list[DocumentoUCM], faixas_perdidas: int) -> None:
        super().__init__(f"{faixas_perdidas} consulta(s) ao UCM falharam (rede/OIC lento). "
                         f"Mostrando {len(docs)} arquivo(s) encontrados; pode faltar algum.")
        self.docs = docs


@dataclass(slots=True, frozen=True)
class DocumentoUCM:
    id: int
    titulo: str
    nome: str
    conta: str
    formato: str
    tamanho: int
    criado_em: datetime | None

    @classmethod
    def de_linha(cls, linha: dict[str, str]) -> DocumentoUCM:
        return cls(
            id=int(linha["document_id"]),
            titulo=linha.get("document_title", ""),
            nome=linha.get("document_name", ""),
            conta=linha.get("document_account", ""),
            formato=linha.get("document_format", ""),
            tamanho=int(linha.get("vault_file_size") or 0),
            criado_em=_data(linha.get("document_created_date", "")),
        )


def _data(texto: str) -> datetime | None:
    try:
        return datetime.strptime(texto.strip(), FORMATO_DATA)
    except ValueError:
        return None


def _sem_crase(*textos: str) -> None:
    if any("`" in t for t in textos):
        raise ValueError("Pasta e termo de busca não podem conter crase.")


def _alvo(pasta: str, subpastas: bool = False) -> str:
    # A tela do UCM mostra a conta e as subcontas juntas (retorno$ + retorno$/processed$ +
    # retorno$/error$), mas o flow compara com <matches>, que é o nome exato. Para incluir as
    # subcontas, o <matches> recebe uma conta que não existe ("-") e o filtro real vai num
    # <OR> dDocAccount <starts>. Como o lado do <matches> é vazio, tanto faz se o UCM resolve
    # <AND> ou <OR> primeiro: as cláusulas seguintes sempre filtram o <starts>.
    pasta = pasta.strip()
    _sem_crase(pasta)
    if not pasta:
        raise ValueError("Informe a pasta (conta UCM).")
    return f"-` <OR> dDocAccount <starts> `{pasta}" if subpastas else pasta


def _consulta(alvo: str, *clausulas: str) -> str:
    # O flow monta `dDocAccount <matches> `{folder_path}``: a crase final de cada cláusula
    # extra é omitida porque o próprio flow a acrescenta.
    if not clausulas:
        return alvo
    return f"{alvo}` <AND> {' <AND> '.join(clausulas)}"[:-1]


def _faixa(inicio: int, fim: int | None) -> tuple[str, ...]:
    return (f"dID >= `{inicio}`",) if fim is None else (f"dID >= `{inicio}`", f"dID < `{fim}`")


def _dividir(inicio: int, fim: int | None, ids: list[int], pedacos: int) -> list[tuple[int, int | None]]:
    # Página cheia traz os mais recentes da faixa. Acima do menor dID visto reconsulta sem ele
    # (esperado vir incompleta); abaixo, fatias que dobram de largura rumo ao passado.
    menor, maior = min(ids), max(ids)
    faixas: list[tuple[int, int | None]] = [(menor + 1, fim)]
    largura = max(1, (maior - menor) // 2)
    topo = menor
    for _ in range(pedacos - 1):
        base = topo - largura
        if base <= inicio:
            break
        faixas.append((base, topo))
        topo, largura = base, largura * 2
    if topo > inicio:
        faixas.append((inicio, topo))
    return faixas


def _ordenar(docs: Iterable[DocumentoUCM]) -> list[DocumentoUCM]:
    return sorted(docs, key=lambda d: (d.criado_em or datetime.min, d.id), reverse=True)


def listar_paginado(pasta: str, buscar: Buscador, *filtros: str, paralelo: int = 6,
                    subpastas: bool = False) -> list[DocumentoUCM]:
    # Pastas grandes (ex.: retornos do Tribanco) geram dezenas de consultas e o OIC às vezes trava
    # uma delas. A faixa que falhar volta para a fila REPESCAGENS vezes; se ainda falhar, devolve o
    # que achou em ErroUCMParcial em vez de perder a busca inteira.
    alvo = _alvo(pasta, subpastas)
    achados: dict[int, DocumentoUCM] = {}
    faixas: list[tuple[int, int | None]] = [(0, None)]
    falhas: Counter[tuple[int, int | None]] = Counter()
    perdidas = 0

    def consultar(faixa: tuple[int, int | None]) -> list[DocumentoUCM] | None:
        try:
            return [DocumentoUCM.de_linha(l) for l in buscar(_consulta(alvo, *filtros, *_faixa(*faixa)))]
        except ErroUCM as e:
            if not e.recuperavel:
                raise
            return None

    with ThreadPoolExecutor(max_workers=paralelo) as pool:
        while faixas:
            proximas: list[tuple[int, int | None]] = []
            for (inicio, fim), docs in zip(faixas, pool.map(consultar, faixas)):
                if docs is None:
                    falhas[(inicio, fim)] += 1
                    if falhas[(inicio, fim)] <= REPESCAGENS:
                        proximas.append((inicio, fim))
                    else:
                        perdidas += 1
                    continue
                achados.update({d.id: d for d in docs})
                if len(docs) < LIMITE_PAGINA:
                    continue
                proximas += _dividir(inicio, fim, [d.id for d in docs], paralelo)
            faixas = proximas
    if perdidas:
        raise ErroUCMParcial(_ordenar(achados.values()), perdidas)
    return _ordenar(achados.values())


class ClienteUCM:
    def __init__(self, client_id: str, client_secret: str, timeout: float = 30) -> None:
        self._credencial = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self._timeout = timeout
        self._token = ""
        self._expira = 0.0
        self._trava = threading.Lock()

    @classmethod
    def do_ambiente(cls) -> ClienteUCM:
        try:
            return cls(os.environ["UCM_CLIENT_ID"], os.environ["UCM_CLIENT_SECRET"])
        except KeyError as e:
            raise ErroUCM(f"Variável de ambiente {e.args[0]} não definida.") from None

    def _requisitar(self, req: urllib.request.Request) -> bytes:
        # Timeout curto + poucas tentativas: com o OIC travado, a tela avisa em ~1,5 min em vez de
        # ficar presa. A mensagem cita só o serviço (sem consulta nem corpo da resposta).
        servico = urllib.parse.urlsplit(req.full_url).path.rsplit("/", 1)[-1]
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    raise ErroUCM(f"HTTP {e.code} no serviço {servico} (credencial ou consulta recusada).",
                                  recuperavel=False) from e
                if tentativa == TENTATIVAS:
                    raise ErroUCM(f"HTTP {e.code} no serviço {servico}.") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if tentativa == TENTATIVAS:
                    raise ErroUCM(f"Sem resposta do serviço {servico} (rede/OIC lento): {e}") from e
            time.sleep(2 ** tentativa)
        raise AssertionError("inalcançável")

    @staticmethod
    def _json(bruto: bytes) -> object:
        try:
            return json.loads(bruto) if bruto.strip() else {}
        except ValueError as e:
            raise ErroUCM("Resposta inválida do OIC (não é JSON).") from e

    def _bearer(self) -> str:
        with self._trava:
            if time.monotonic() >= self._expira:
                self._renovar_token()
            return self._token

    def _renovar_token(self) -> None:
        if not (URL_TOKEN and ESCOPO):
            raise ErroUCM("UCM não configurado (bloco ucm em config/cliente.yaml).", recuperavel=False)
        corpo = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": ESCOPO}).encode()
        req = urllib.request.Request(URL_TOKEN, data=corpo, headers={
            "Authorization": f"Basic {self._credencial}",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        dados = self._json(self._requisitar(req))
        if not isinstance(dados, dict) or "access_token" not in dados:
            raise ErroUCM("O OIC não devolveu o token de acesso. Confira client_id e client_secret.",
                          recuperavel=False)
        self._token = dados["access_token"]
        self._expira = time.monotonic() + int(dados.get("expires_in", 3600)) - 60

    def _get_json(self, url: str, **params: str) -> object:
        req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                     headers={"Authorization": f"Bearer {self._bearer()}"})
        return self._json(self._requisitar(req))

    def buscar(self, folder_path: str) -> list[dict[str, str]]:
        dados = self._get_json(URL_BUSCA, folder_path=folder_path)
        return dados.get("rows", []) if isinstance(dados, dict) else []

    def listar(self, pasta: str, subpastas: bool = False) -> list[DocumentoUCM]:
        return listar_paginado(pasta, self.buscar, subpastas=subpastas)

    def buscar_por_id(self, pasta: str, identificador: int | str, subpastas: bool = False) -> DocumentoUCM | None:
        # Aceita o Content ID mostrado na tela do UCM (UCMFA80505382, ou só os dígitos) e o
        # document_id (dID) da API. São números diferentes; o Content ID tem prioridade.
        alvo = _alvo(pasta, subpastas)
        texto = str(identificador).strip().upper()
        if not RE_IDENTIFICADOR.fullmatch(texto):
            raise ValueError(f"ID inválido: {identificador!r}")
        clausulas = [f"dDocName <matches> `{texto}`"]
        if texto.isdigit():
            clausulas = [f"dDocName <matches> `{PREFIXO_CONTENT_ID}{texto}`", f"dID = `{texto}`"]
        for clausula in clausulas:
            linhas = self.buscar(_consulta(alvo, clausula))
            if linhas:
                return DocumentoUCM.de_linha(linhas[0])
        return None

    def localizar(self, pasta: str, texto: str, subpastas: bool = False) -> DocumentoUCM | None:
        # Campo único da tela: aceita Content ID, document_id ou nome do arquivo. Tenta o ID primeiro
        # e, se não achar, procura o texto no título (uma consulta só; vem o mais recente).
        texto = texto.strip()
        doc = self.buscar_por_id(pasta, texto, subpastas) if RE_IDENTIFICADOR.fullmatch(texto.upper()) else None
        if doc or texto.isdigit():
            return doc
        _sem_crase(texto)
        linhas = self.buscar(_consulta(_alvo(pasta, subpastas), f"dDocTitle <substring> `{texto}`"))
        return _ordenar(DocumentoUCM.de_linha(l) for l in linhas)[0] if linhas else None

    def na_posicao(self, pasta: str, posicao: int, subpastas: bool = False) -> DocumentoUCM | None:
        # Mesma ordem da tela do UCM (mais recente primeiro): avança página a página pelo menor dID.
        alvo = _alvo(pasta, subpastas)
        if posicao < 1:
            raise ValueError("Posição começa em 1.")
        filtros: tuple[str, ...] = ()
        while True:
            # Ordena aqui: a posição só bate com a tela do UCM se a página estiver do mais novo pro mais velho.
            docs = sorted((DocumentoUCM.de_linha(l) for l in self.buscar(_consulta(alvo, *filtros))),
                          key=lambda d: d.id, reverse=True)
            if posicao <= len(docs):
                return docs[posicao - 1]
            if len(docs) < LIMITE_PAGINA:
                return None
            posicao -= len(docs)
            filtros = (f"dID < `{min(d.id for d in docs)}`",)

    def buscar_por_nome(self, pasta: str, trecho: str, subpastas: bool = False) -> list[DocumentoUCM]:
        trecho = trecho.strip()
        _sem_crase(trecho)
        return listar_paginado(pasta, self.buscar, f"dDocTitle <substring> `{trecho}`", subpastas=subpastas)

    def baixar(self, document_id: int | str) -> bytes:
        dados = self._get_json(URL_ARQUIVO, document_id=str(document_id))
        if not isinstance(dados, dict) or "file_content" not in dados:
            raise ErroUCM(f"Resposta sem file_content para document_id={document_id}.")
        return base64.b64decode(dados["file_content"])
