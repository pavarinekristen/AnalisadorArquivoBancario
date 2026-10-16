"""Configuração por cliente: tudo que muda de uma empresa para outra fica em config/cliente.yaml.

Sem config/cliente.yaml, vale config/cliente.exemplo.yaml (e a tela avisa). Para instalar num cliente novo,
copie o exemplo para cliente.yaml e preencha.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PASTA = Path(__file__).resolve().parent.parent / "config"
ARQUIVO_CLIENTE = PASTA / "cliente.yaml"
ARQUIVO_EXEMPLO = PASTA / "cliente.exemplo.yaml"


class ErroConfig(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Marca:
    nome: str = "Conferência de Pagamentos"
    logo: str = "assets/techone_banner.jpg"
    icone: str = "assets/techone_icon.jpg"


@dataclass(frozen=True, slots=True)
class Pastas:
    retorno: Path
    remessa: Path
    tribanco: Path
    inbox: Path
    tribanco_inbox: Path | None = None


@dataclass(frozen=True, slots=True)
class Documento:
    prefixo: str = "10000"
    tamanho: int = 15


@dataclass(frozen=True, slots=True)
class MarcadoresExcel:
    banco: str = "TOTAL P/ REFER"
    resumo: tuple[str, ...] = ("NOME RCA", "CPF/CNPJ")
    sistema: tuple[str, ...] = ("SITUACAO", "NUMERO OP")


@dataclass(frozen=True, slots=True)
class ConfigUCM:
    url_token: str = ""
    escopo: str = ""
    url_oic: str = ""
    contas: dict[str, str] = field(default_factory=dict)   # conta -> rótulo do atalho; só elas são aceitas

    @property
    def configurado(self) -> bool:
        return bool(self.url_token and self.escopo and self.url_oic)


@dataclass(frozen=True, slots=True)
class Config:
    pastas: Pastas
    marca: Marca = Marca()
    bancos_ativos: tuple[str, ...] = ("santander", "tribanco")
    pastas_permitidas: tuple[Path, ...] = ()
    subpastas: tuple[str, ...] = ()   # opções da lista de subpastas (GE202255...) na tela
    documento: Documento = Documento()
    excel: MarcadoresExcel = MarcadoresExcel()
    ucm: ConfigUCM = ConfigUCM()
    retencao_dias: int = 365
    api: dict[str, Any] = field(default_factory=dict)   # reservado para a integração futura por API/JSON
    origem: Path | None = None

    @property
    def e_exemplo(self) -> bool:
        return self.origem == ARQUIVO_EXEMPLO


def _caminho(v: Any, campo: str) -> Path:
    if not v or not isinstance(v, str):
        raise ErroConfig(f"Campo obrigatório ausente ou inválido em config: {campo}")
    return Path(v).expanduser()


def _ler(dados: dict[str, Any], origem: Path) -> Config:
    p = dados.get("pastas") or {}
    pastas = Pastas(
        retorno=_caminho(p.get("retorno"), "pastas.retorno"),
        remessa=_caminho(p.get("remessa"), "pastas.remessa"),
        tribanco=_caminho(p.get("tribanco"), "pastas.tribanco"),
        inbox=_caminho(p.get("inbox"), "pastas.inbox"),
        tribanco_inbox=_caminho(p["tribanco_inbox"], "pastas.tribanco_inbox") if p.get("tribanco_inbox") else None,
    )
    bancos = tuple(dados.get("bancos_ativos") or ("santander", "tribanco"))
    desconhecidos = set(bancos) - {"santander", "tribanco"}
    if desconhecidos:
        raise ErroConfig(f"Banco não suportado em bancos_ativos: {', '.join(sorted(desconhecidos))}")
    doc = dados.get("documento") or {}
    ex = dados.get("excel") or {}
    u = dados.get("ucm") or {}
    retencao = int(dados.get("retencao_dias", 365))
    if retencao < 1:
        raise ErroConfig("retencao_dias precisa ser 1 ou mais.")
    return Config(
        pastas=pastas,
        marca=Marca(**(dados.get("marca") or {})),
        bancos_ativos=bancos,
        pastas_permitidas=tuple(_caminho(x, "pastas_permitidas") for x in dados.get("pastas_permitidas") or ()),
        subpastas=tuple(str(x).strip() for x in dados.get("subpastas") or () if str(x).strip()),
        documento=Documento(prefixo=str(doc.get("prefixo", "10000")), tamanho=int(doc.get("tamanho", 15))),
        excel=MarcadoresExcel(banco=ex.get("banco", "TOTAL P/ REFER"),
                              resumo=tuple(ex.get("resumo", ("NOME RCA", "CPF/CNPJ"))),
                              sistema=tuple(ex.get("sistema", ("SITUACAO", "NUMERO OP")))),
        ucm=ConfigUCM(url_token=u.get("url_token", ""), escopo=u.get("escopo", ""), url_oic=u.get("url_oic", ""),
                      contas=dict(u.get("contas") or {})),
        retencao_dias=retencao,
        api=dict(dados.get("api") or {}),
        origem=origem,
    )


def carregar(caminho: Path | None = None) -> Config:
    caminho = caminho or (ARQUIVO_CLIENTE if ARQUIVO_CLIENTE.exists() else ARQUIVO_EXEMPLO)
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = yaml.safe_load(f) or {}
    except FileNotFoundError as e:
        raise ErroConfig(f"Arquivo de configuração não encontrado: {caminho}") from e
    except yaml.YAMLError as e:
        raise ErroConfig(f"Erro de sintaxe em {caminho.name}: {e}") from e
    if not isinstance(dados, dict):
        raise ErroConfig(f"{caminho.name} precisa ser um mapa (chave: valor).")
    return _ler(dados, caminho)


@lru_cache(maxsize=1)
def atual() -> Config:
    return carregar()


def caminho_permitido(caminho: Path, cfg: Config | None = None) -> bool:
    """Caminho manual só dentro das pastas liberadas na config (nada de UNC para servidor qualquer)."""
    cfg = cfg or atual()
    try:
        alvo = caminho.expanduser().resolve(strict=False)
    except OSError:
        return False
    for raiz in (*cfg.pastas_permitidas, cfg.pastas.retorno, cfg.pastas.remessa, cfg.pastas.tribanco):
        try:
            if alvo.is_relative_to(raiz.expanduser().resolve(strict=False)):
                return True
        except OSError:
            continue
    return False


def conta_ucm_permitida(conta: str, cfg: Config | None = None) -> bool:
    cfg = cfg or atual()
    conta = conta.strip().rstrip("/")
    return any(conta == c.rstrip("/") or conta.startswith(c.rstrip("/") + "/") for c in cfg.ucm.contas)
