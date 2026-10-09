"""Lê os arquivos copiados no Explorer do Windows (Ctrl+C). O programa roda na mesma máquina."""
from __future__ import annotations

import subprocess
from pathlib import Path


def arquivos_copiados() -> list[Path]:
    """Caminhos copiados na área de transferência. Pastas são expandidas (só o primeiro nível)."""
    try:
        saida = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
             "Get-Clipboard -Format FileDropList | ForEach-Object { $_.FullName }"],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    caminhos: list[Path] = []
    for linha in saida.splitlines():
        p = Path(linha.strip())
        if p.is_dir():
            caminhos.extend(sorted(x for x in p.iterdir() if x.is_file()))
        elif p.is_file():
            caminhos.append(p)
    return list(dict.fromkeys(caminhos))


def e_excel(p: Path) -> bool:
    return p.suffix.lower() in (".xlsx", ".xlsm") and not p.name.startswith("~$")
