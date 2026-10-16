"""Credencial do UCM/OIC no cofre do Windows (Gerenciador de Credenciais), nunca em arquivo de texto."""
from __future__ import annotations

try:
    import keyring
    from keyring.errors import KeyringError
except ImportError:   # instalação antiga sem keyring: cai para secrets.toml / variáveis de ambiente
    keyring = None

    class KeyringError(Exception):   # type: ignore[no-redef]
        pass

SERVICO = "conferencia-pagamentos-ucm"


def disponivel() -> bool:
    return keyring is not None


def ler() -> tuple[str, str] | None:
    if keyring is None:
        return None
    try:
        cid, segredo = keyring.get_password(SERVICO, "client_id"), keyring.get_password(SERVICO, "client_secret")
    except KeyringError:
        return None
    return (cid, segredo) if cid and segredo else None


def gravar(client_id: str, client_secret: str) -> None:
    if keyring is None:
        raise RuntimeError("Cofre de credenciais indisponível (pacote keyring não instalado).")
    keyring.set_password(SERVICO, "client_id", client_id.strip())
    keyring.set_password(SERVICO, "client_secret", client_secret.strip())


def apagar() -> None:
    if keyring is None:
        return
    for nome in ("client_id", "client_secret"):
        try:
            keyring.delete_password(SERVICO, nome)
        except KeyringError:
            pass
