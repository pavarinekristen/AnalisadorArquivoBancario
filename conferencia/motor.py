"""Cruza a lista do relatório com os registros dos arquivos do banco e classifica cada favorecido."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .modelos import (ACEITO_NAO_PAGO, DEVOLUCAO, NAO_ENVIADO, OUTRO_PAGAMENTO, PAGO, REJEITADO,
                      Pagamento, RegistroBanco, Resultado)
from .relatorio import sem_acento

_REGRAS = Path(__file__).resolve().parent.parent / "regras" / "ocorrencias.yaml"


def carregar_ocorrencias(caminho: Path = _REGRAS) -> dict[str, dict]:
    with open(caminho, encoding="utf-8") as f:
        return {str(k): v for k, v in yaml.safe_load(f).items()}


OCORRENCIAS = carregar_ocorrencias()


def descrever(codigo: str) -> str:
    o = OCORRENCIAS.get(codigo)
    return o["descricao"] if o else "Código não cadastrado (consultar tabela FEBRABAN/banco)"


def descrever_varios(codigos: list[str]) -> str:
    return " + ".join(f"{c} ({descrever(c)})" for c in codigos)


def nome_normalizado(s: str) -> str:
    s = sem_acento(s).replace("&", " ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return " ".join(s.split())


def _nomes_compativeis(a: str, b: str) -> bool:
    """Nome no banco vem truncado em 30 caracteres: aceita quando um é começo do outro."""
    curto, longo = sorted((a, b), key=len)
    return len(curto) >= 12 and longo.startswith(curto)


def _e_devolucao(r: RegistroBanco) -> bool:
    return bool(r.ocorrencias) and (r.ocorrencias[0].startswith("Z") or "XD" in r.ocorrencias)


def _e_pago(r: RegistroBanco) -> bool:
    return bool(r.ocorrencias) and r.ocorrencias[0] in ("00", "03")


def _tem_erro(r: RegistroBanco) -> bool:
    return any(OCORRENCIAS.get(c, {}).get("categoria", "erro") == "erro" for c in r.ocorrencias)


def _valor_igual(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) < 0.005


class Indice:
    def __init__(self, registros: list[RegistroBanco]):
        self.registros = registros
        self.por_doc: dict[str, list[RegistroBanco]] = {}
        self.por_cpf: dict[str, list[RegistroBanco]] = {}
        self.por_nome: dict[str, list[RegistroBanco]] = {}
        for r in registros:
            if r.documento:
                self.por_doc.setdefault(r.documento, []).append(r)
            if r.cpf_cnpj:
                self.por_cpf.setdefault(r.cpf_cnpj, []).append(r)
            self.por_nome.setdefault(nome_normalizado(r.nome), []).append(r)

    def buscar(self, p: Pagamento) -> tuple[list[RegistroBanco], bool, list[RegistroBanco], list[str]]:
        """Devolve (registros do pagamento, match_fraco, outros pagamentos do favorecido, avisos)."""
        doc = p.documento.lstrip("0")
        cpf = p.cpf_cnpj.lstrip("0")
        nome = nome_normalizado(p.favorecido)

        por_nome = [r for chave, rs in self.por_nome.items() if _nomes_compativeis(chave, nome) for r in rs]
        do_favorecido = list(self.por_cpf.get(cpf, [])) if cpf else []
        if not do_favorecido:
            do_favorecido = por_nome

        def resposta(achados, fraco, avisos=()):
            return achados, fraco, [r for r in do_favorecido if r not in achados], list(avisos)

        if doc:
            # Documento é a chave: se o relatório tem documento, só ele vale.
            # Outro pagamento do mesmo favorecido (outro documento) não conta como encontrado.
            return resposta(self.por_doc.get(doc, []), False)

        # Sem documento: o mesmo favorecido pode ter vários pagamentos nos arquivos.
        if cpf and cpf in self.por_cpf:
            candidatos = [r for r in self.por_cpf[cpf] if p.valor is None or _valor_igual(r.valor, p.valor)]
            if candidatos:
                achados, avisos = _um_pagamento(candidatos, p)
                return resposta(achados, False, avisos)

        candidatos = [r for r in por_nome if _valor_igual(r.valor, p.valor)]
        if candidatos:
            achados, avisos = _um_pagamento(candidatos, p)
            return resposta(achados, True, avisos)
        return [], False, do_favorecido, []


def _chave_pagamento(r: RegistroBanco) -> str:
    """Identifica um pagamento: o documento, ou data + valor quando não há documento."""
    return r.documento or f"{r.data}|{r.valor:.2f}"


def _um_pagamento(candidatos: list[RegistroBanco], p: Pagamento) -> tuple[list[RegistroBanco], list[str]]:
    """Quando a busca foi sem documento, separa os pagamentos encontrados e fica com um só."""
    grupos: dict[str, list[RegistroBanco]] = {}
    for r in candidatos:
        grupos.setdefault(_chave_pagamento(r), []).append(r)
    if len(grupos) == 1:
        return candidatos, []
    if p.data:
        mesma_data = {k: v for k, v in grupos.items() if any(r.data == p.data for r in v)}
        if len(mesma_data) == 1:
            return next(iter(mesma_data.values())), []
        if mesma_data:
            grupos = mesma_data
    escolhido = max(grupos.values(), key=lambda rs: max(r.arquivo.ordem for r in rs))
    docs = ", ".join(f"{k.split('|')[0]}" for k in grupos)
    return escolhido, [f"Favorecido tem {len(grupos)} pagamentos com o mesmo valor nos arquivos ({docs}). "
                       f"Usei o mais recente ({_chave_pagamento(escolhido[0]).split('|')[0]}). Confira."]


def classificar(p: Pagamento, achados: list[RegistroBanco], fraco: bool,
                outros: list[RegistroBanco], avisos: list[str] = ()) -> Resultado:
    res = Resultado(pagamento=p, status=NAO_ENVIADO, registros=sorted(achados, key=lambda r: r.arquivo.ordem),
                    match_fraco=fraco, observacoes=list(avisos))
    movs = [r for r in res.registros if r.arquivo.tipo == "MOV"]
    cris = [r for r in res.registros if r.arquivo.tipo == "CRI"]

    if movs:
        ultimo = movs[-1]
        devolvidos = [r for r in movs if _e_devolucao(r)]
        if _e_devolucao(ultimo) or (devolvidos and not _e_pago(ultimo)):
            d = devolvidos[-1]
            res.status, res.codigos, res.arquivo_status = DEVOLUCAO, [d.ocorrencia_bruta], d.arquivo.nome
            pagos_antes = [r.arquivo.nome for r in movs if _e_pago(r)]
            if pagos_antes:
                res.observacoes.append(f"Apareceu pago (00) antes em {', '.join(pagos_antes)} e depois foi devolvido.")
        elif _e_pago(ultimo):
            res.status, res.codigos, res.arquivo_status = PAGO, [ultimo.ocorrencia_bruta], ultimo.arquivo.nome
            if devolvidos:
                res.observacoes.append(f"Teve devolução antes em {devolvidos[-1].arquivo.nome} "
                                       f"({devolvidos[-1].ocorrencia_bruta}) e depois foi pago.")
        else:
            res.status, res.codigos, res.arquivo_status = REJEITADO, [ultimo.ocorrencia_bruta], ultimo.arquivo.nome
    elif cris:
        com_erro = [r for r in cris if _tem_erro(r)]
        if com_erro:
            e = com_erro[-1]
            res.status, res.codigos, res.arquivo_status = REJEITADO, [e.ocorrencia_bruta], e.arquivo.nome
        else:
            c = cris[-1]
            res.status, res.codigos, res.arquivo_status = ACEITO_NAO_PAGO, [c.ocorrencia_bruta], c.arquivo.nome
    elif outros:
        res.status = OUTRO_PAGAMENTO
        res.registros = sorted(outros, key=lambda r: r.arquivo.ordem)
        for r in res.registros:
            res.observacoes.append(f"{r.arquivo.nome}: {r.nome} valor {r.valor:,.2f} data {r.data} "
                                   f"doc {r.documento} ocorr {r.ocorrencia_bruta or '-'}")

    # divergências parciais
    if achados and p.valor is not None and not any(_valor_igual(r.valor, p.valor) for r in achados):
        res.observacoes.append(f"Valor diferente: relatório {p.valor:,.2f} x banco "
                               f"{', '.join(f'{r.valor:,.2f}' for r in achados)}.")
    if achados and p.data and not any(r.data == p.data for r in achados):
        res.observacoes.append(f"Data diferente: relatório {p.data} x banco {', '.join(sorted({r.data for r in achados}))}.")
    if fraco:
        res.observacoes.append("Encontrado só por nome + valor (documento/CPF não bateram). Confira.")

    desconhecidos = sorted({c for r in res.registros for c in r.ocorrencias if c not in OCORRENCIAS})
    if desconhecidos:
        res.observacoes.append(f"Código não cadastrado: {', '.join(desconhecidos)}.")

    sistema_pago = sem_acento(p.situacao_sistema).startswith("SUCESSO") or sem_acento(p.situacao_banco) == "PAGO"
    res.alerta_sistema = sistema_pago and res.status != PAGO
    return res


def conferir(pagamentos: list[Pagamento], registros: list[RegistroBanco]) -> list[Resultado]:
    idx = Indice(registros)
    return [classificar(p, *idx.buscar(p)) for p in pagamentos]


# ---------------------------------------------------------------- pesquisa por nome digitado

_PALAVRAS_IGNORADAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "LTDA", "ME", "EPP", "SA", "S", "A", "EIRELI"}


def _palavras(nome: str, manter_iniciais: bool = False) -> list[str]:
    """Palavras significativas. No nome do banco as letras soltas ficam: podem ser iniciais (F SOUZA = FULANO SOUZA)."""
    return [w for w in nome_normalizado(nome).split()
            if w not in _PALAVRAS_IGNORADAS or (manter_iniciais and len(w) == 1)]


def nome_bate(digitado: str, nome_banco: str) -> bool:
    """Cada palavra digitada precisa aparecer no nome do banco: igual, abreviada pelo banco
    (inicial, ex: FULANO -> F) ou cortada no fim (o banco trunca em 30 caracteres).
    Pelo menos uma palavra tem que bater inteira, para não achar só por iniciais."""
    procuradas, banco = _palavras(digitado), _palavras(nome_banco, manter_iniciais=True)
    if not procuradas or not banco:
        return False
    # Nome com 30 caracteres foi cortado pelo banco: as ÚLTIMAS palavras digitadas podem não estar lá.
    truncado = len(nome_banco.strip()) >= 28
    inteiras, ultimo, faltando = 0, -1, 0
    for w in procuradas:
        achou = None
        # as palavras precisam aparecer na mesma ordem do nome
        for i in range(ultimo + 1, len(banco)):
            b = banco[i]
            if b == w:
                achou, inteiras = i, inteiras + 1
                break
            if len(b) >= 3 and w.startswith(b) and i == len(banco) - 1:   # truncado no fim
                achou = i
                break
            if len(b) == 1 and w[0] == b:                                   # abreviado (inicial)
                achou = i
                break
        if achou is None:
            if not truncado:
                return False
            faltando += 1
            continue
        if faltando:          # palavra achada depois de uma que faltou: não é corte no fim
            return False
        ultimo = achou
    return inteiras >= (2 if faltando else 1)


def pesquisar(pesquisas: list[Pagamento], registros: list[RegistroBanco]) -> list[Resultado]:
    """Para cada nome/CPF/documento digitado, devolve um resultado por pagamento encontrado nos arquivos."""
    idx = Indice(registros)
    resultados: list[Resultado] = []
    for p in pesquisas:
        if p.documento:
            achados = idx.por_doc.get(p.documento.lstrip("0"), [])
        elif p.cpf_cnpj:
            achados = idx.por_cpf.get(p.cpf_cnpj.lstrip("0"), [])
            if not achados and p.favorecido != p.cpf_cnpj:
                achados = [r for r in registros if nome_bate(p.favorecido, r.nome)]
        else:
            achados = [r for r in registros if nome_bate(p.favorecido, r.nome)]
        if p.valor is not None:
            achados = [r for r in achados if _valor_igual(r.valor, p.valor)]
        if p.data:
            achados = [r for r in achados if r.data == p.data]

        if not achados:
            resultados.append(classificar(p, [], False, []))
            continue
        grupos: dict[str, list[RegistroBanco]] = {}
        for r in achados:
            grupos.setdefault(_chave_pagamento(r), []).append(r)
        for regs in sorted(grupos.values(), key=lambda rs: max(r.arquivo.ordem for r in rs), reverse=True):
            um = Pagamento(favorecido=p.favorecido, cpf_cnpj=regs[0].cpf_cnpj or p.cpf_cnpj,
                           documento=regs[0].documento, valor=regs[0].valor, data=regs[0].data)
            res = classificar(um, regs, False, [])
            if len(grupos) > 1:
                res.observacoes.insert(0, f"Favorecido tem {len(grupos)} pagamentos nos arquivos.")
            resultados.append(res)
    return resultados
