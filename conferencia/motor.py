from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from collections.abc import Sequence
from pathlib import Path

import yaml

from .modelos import (ACEITO_NAO_PAGO, DEVOLUCAO, NAO_ENVIADO, OUTRO_PAGAMENTO, PAGO, REJEITADO,
                      Pagamento, RegistroBanco, Resultado)
from .relatorio import sem_acento

_REGRAS = Path(__file__).resolve().parent.parent / "regras" / "ocorrencias.yaml"
_PALAVRAS_IGNORADAS: frozenset[str] = frozenset(
    {"DE", "DA", "DO", "DAS", "DOS", "E", "LTDA", "ME", "EPP", "SA", "S", "A", "EIRELI"})


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
    curto, longo = sorted((a, b), key=len)
    return len(curto) >= 12 and longo.startswith(curto)


def _e_devolucao(r: RegistroBanco) -> bool:
    return bool(r.ocorrencias) and (r.ocorrencias[0].startswith("Z") or "XD" in r.ocorrencias)


def _e_pago(r: RegistroBanco) -> bool:
    return bool(r.ocorrencias) and r.ocorrencias[0] in ("00", "03")


def _tem_erro(r: RegistroBanco) -> bool:
    return any(OCORRENCIAS.get(c, {}).get("categoria", "erro") == "erro" for c in r.ocorrencias)


# Santander separa crítica (CRI) e movimento (MOV) em arquivos diferentes. O Tribanco manda tudo no
# mesmo retorno (RET): o que já é pagamento/devolução conta como MOV, o resto (BD, erros) como CRI.
def _e_efetivacao(r: RegistroBanco) -> bool:
    return r.arquivo.tipo == "MOV" or (r.arquivo.tipo == "RET" and (_e_pago(r) or _e_devolucao(r)))


def _e_critica(r: RegistroBanco) -> bool:
    return r.arquivo.tipo == "CRI" or (r.arquivo.tipo == "RET" and not _e_efetivacao(r))


def _valor_igual(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) < 0.005


class Indice:
    def __init__(self, registros: list[RegistroBanco]) -> None:
        self.registros = registros
        self.por_doc: defaultdict[str, list[RegistroBanco]] = defaultdict(list)
        self.por_cpf: defaultdict[str, list[RegistroBanco]] = defaultdict(list)
        self.por_nome: defaultdict[str, list[RegistroBanco]] = defaultdict(list)
        for r in registros:
            if r.documento:
                self.por_doc[r.documento].append(r)
            if r.cpf_cnpj:
                self.por_cpf[r.cpf_cnpj].append(r)
            self.por_nome[nome_normalizado(r.nome)].append(r)

    def buscar(self, p: Pagamento) -> tuple[list[RegistroBanco], bool, list[RegistroBanco], list[str]]:
        doc = p.documento.lstrip("0")
        cpf = p.cpf_cnpj.lstrip("0")
        nome = nome_normalizado(p.favorecido)

        # A varredura por nome é a parte cara: só roda quando o CPF não resolve.
        def por_nome() -> list[RegistroBanco]:
            return [r for chave, rs in self.por_nome.items() if _nomes_compativeis(chave, nome) for r in rs]

        do_cpf = list(self.por_cpf.get(cpf, [])) if cpf else []
        do_favorecido = do_cpf or por_nome()

        def resposta(achados: list[RegistroBanco], fraco: bool,
                    avisos: Sequence[str] = ()) -> tuple[list[RegistroBanco], bool, list[RegistroBanco], list[str]]:
            ja = {id(r) for r in achados}
            return achados, fraco, [r for r in do_favorecido if id(r) not in ja], list(avisos)

        if doc:
            return resposta(self.por_doc.get(doc, []), False)

        if cpf and cpf in self.por_cpf:
            candidatos = [r for r in self.por_cpf[cpf] if p.valor is None or _valor_igual(r.valor, p.valor)]
            if candidatos:
                achados, avisos = _um_pagamento(candidatos, p)
                return resposta(achados, False, avisos)

        candidatos = [r for r in (do_favorecido if not do_cpf else por_nome()) if _valor_igual(r.valor, p.valor)]
        if candidatos:
            achados, avisos = _um_pagamento(candidatos, p)
            return resposta(achados, True, avisos)
        return [], False, do_favorecido, []


def _chave_pagamento(r: RegistroBanco) -> str:
    return r.documento or f"{r.data}|{r.valor:.2f}"


def _um_pagamento(candidatos: list[RegistroBanco], p: Pagamento) -> tuple[list[RegistroBanco], list[str]]:
    grupos: defaultdict[str, list[RegistroBanco]] = defaultdict(list)
    for r in candidatos:
        grupos[_chave_pagamento(r)].append(r)
    if len(grupos) == 1:
        return candidatos, []
    if p.data:
        mesma_data = {k: v for k, v in grupos.items() if any(r.data == p.data for r in v)}
        if len(mesma_data) == 1:
            return next(iter(mesma_data.values())), []
        if mesma_data:
            grupos = mesma_data
    escolhido = max(grupos.values(), key=lambda rs: max(r.arquivo.ordem for r in rs))
    docs = ", ".join(k.split("|")[0] for k in grupos)
    return escolhido, [f"Favorecido tem {len(grupos)} pagamentos com o mesmo valor nos arquivos ({docs}). "
                       f"Usei o mais recente ({_chave_pagamento(escolhido[0]).split('|')[0]}). Confira."]


def _classificar_mov(res: Resultado, movs: list[RegistroBanco]) -> None:
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


def _classificar_cri(res: Resultado, cris: list[RegistroBanco]) -> None:
    com_erro = [r for r in cris if _tem_erro(r)]
    if com_erro:
        e = com_erro[-1]
        res.status, res.codigos, res.arquivo_status = REJEITADO, [e.ocorrencia_bruta], e.arquivo.nome
    else:
        c = cris[-1]
        res.status, res.codigos, res.arquivo_status = ACEITO_NAO_PAGO, [c.ocorrencia_bruta], c.arquivo.nome


def _classificar_outro_pagamento(res: Resultado, outros: list[RegistroBanco]) -> None:
    res.status = OUTRO_PAGAMENTO
    res.registros = sorted(outros, key=lambda r: r.arquivo.ordem)
    res.observacoes.extend(
        f"{r.arquivo.nome}: {r.nome} valor {r.valor:,.2f} data {r.data} doc {r.documento} "
        f"ocorr {r.ocorrencia_bruta or '-'}"
        for r in res.registros
    )


def _adicionar_divergencias(res: Resultado, p: Pagamento, achados: list[RegistroBanco], fraco: bool) -> None:
    if achados and p.valor is not None and not any(_valor_igual(r.valor, p.valor) for r in achados):
        res.observacoes.append(f"Valor diferente: relatório {p.valor:,.2f} x banco "
                               f"{', '.join(f'{r.valor:,.2f}' for r in achados)}.")
    if achados and p.data and not any(r.data == p.data for r in achados):
        res.observacoes.append(
            f"Data diferente: relatório {p.data} x banco {', '.join(sorted({r.data for r in achados}))}.")
    if fraco:
        res.observacoes.append("Encontrado só por nome + valor (documento/CPF não bateram). Confira.")


def classificar(p: Pagamento, achados: list[RegistroBanco], fraco: bool,
                outros: list[RegistroBanco], avisos: Sequence[str] = ()) -> Resultado:
    res = Resultado(pagamento=p, status=NAO_ENVIADO, registros=sorted(achados, key=lambda r: r.arquivo.ordem),
                    match_fraco=fraco, observacoes=list(avisos))
    movs = [r for r in res.registros if _e_efetivacao(r)]
    cris = [r for r in res.registros if _e_critica(r)]

    if movs:
        _classificar_mov(res, movs)
    elif cris:
        _classificar_cri(res, cris)
    elif outros:
        _classificar_outro_pagamento(res, outros)

    _adicionar_divergencias(res, p, achados, fraco)

    desconhecidos = sorted({c for r in res.registros for c in r.ocorrencias if c not in OCORRENCIAS})
    if desconhecidos:
        res.observacoes.append(f"Código não cadastrado: {', '.join(desconhecidos)}.")

    sistema_pago = sem_acento(p.situacao_sistema).startswith("SUCESSO") or sem_acento(p.situacao_banco) == "PAGO"
    res.alerta_sistema = sistema_pago and res.status != PAGO
    return res


def conferir(pagamentos: list[Pagamento], registros: list[RegistroBanco]) -> list[Resultado]:
    idx = Indice(registros)
    return [classificar(p, *idx.buscar(p)) for p in pagamentos]


def _palavras(nome: str, manter_iniciais: bool = False) -> list[str]:
    return [w for w in nome_normalizado(nome).split()
            if w not in _PALAVRAS_IGNORADAS or (manter_iniciais and len(w) == 1)]


@lru_cache(maxsize=200_000)
def _palavras_do_banco(nome_banco: str) -> tuple[tuple[str, ...], bool]:
    # Os mesmos nomes se repetem em milhares de registros: normaliza cada um uma vez só.
    return tuple(_palavras(nome_banco, manter_iniciais=True)), len(nome_banco.strip()) >= 28


def nome_bate(digitado: str, nome_banco: str) -> bool:
    return _bate(tuple(_palavras(digitado)), nome_banco)


def _bate(procuradas: tuple[str, ...], nome_banco: str) -> bool:
    banco, truncado = _palavras_do_banco(nome_banco)
    if not procuradas or not banco:
        return False
    inteiras, ultimo, faltando = 0, -1, 0
    for w in procuradas:
        achou = None
        for i in range(ultimo + 1, len(banco)):
            b = banco[i]
            if b == w:
                achou, inteiras = i, inteiras + 1
                break
            if len(b) >= 3 and w.startswith(b) and i == len(banco) - 1:
                achou = i
                break
            if len(b) == 1 and w[0] == b:
                achou = i
                break
        if achou is None:
            if not truncado:
                return False
            faltando += 1
            continue
        if faltando:
            return False
        ultimo = achou
    return inteiras >= (2 if faltando else 1)


def _pelo_nome(digitado: str, registros: list[RegistroBanco]) -> list[RegistroBanco]:
    # Compara cada nome distinto uma vez e depois filtra os registros (mantendo a ordem).
    procuradas = tuple(_palavras(digitado))
    batem = {n for n in {r.nome for r in registros} if _bate(procuradas, n)}
    return [r for r in registros if r.nome in batem]


def _achados_por_pesquisa(p: Pagamento, idx: Indice, registros: list[RegistroBanco]) -> list[RegistroBanco]:
    if p.documento:
        achados = idx.por_doc.get(p.documento.lstrip("0"), [])
    elif p.cpf_cnpj:
        achados = idx.por_cpf.get(p.cpf_cnpj.lstrip("0"), [])
        if not achados and p.favorecido != p.cpf_cnpj:
            achados = _pelo_nome(p.favorecido, registros)
    else:
        achados = _pelo_nome(p.favorecido, registros)
    if p.valor is not None:
        achados = [r for r in achados if _valor_igual(r.valor, p.valor)]
    if p.data:
        achados = [r for r in achados if r.data == p.data]
    return achados


def _achados_por_pagador(p: Pagamento, registros: list[RegistroBanco]) -> list[RegistroBanco]:
    # O nome digitado pode ser da empresa que paga (header do arquivo), não de quem recebe:
    # aí vale todo pagamento dos arquivos dessa empresa.
    if p.documento:
        return []
    cpf = p.cpf_cnpj.lstrip("0")
    procuradas = tuple(_palavras(p.favorecido))
    bate: dict[int, bool] = {}
    for r in registros:
        a = r.arquivo
        if id(a) not in bate:
            bate[id(a)] = (a.pagador_cnpj == cpf) if cpf else bool(a.pagador) and _bate(procuradas, a.pagador)
    achados = [r for r in registros if bate[id(r.arquivo)]]
    if p.valor is not None:
        achados = [r for r in achados if _valor_igual(r.valor, p.valor)]
    if p.data:
        achados = [r for r in achados if r.data == p.data]
    return achados


def _por_pagamento(achados: list[RegistroBanco]) -> list[list[RegistroBanco]]:
    grupos: defaultdict[str, list[RegistroBanco]] = defaultdict(list)
    for r in achados:
        grupos[_chave_pagamento(r)].append(r)
    return sorted(grupos.values(), key=lambda rs: max(r.arquivo.ordem for r in rs), reverse=True)


def pesquisar(pesquisas: list[Pagamento], registros: list[RegistroBanco]) -> list[Resultado]:
    idx = Indice(registros)
    resultados: list[Resultado] = []
    for p in pesquisas:
        achados = _achados_por_pesquisa(p, idx, registros)
        ja = {id(r) for r in achados}
        do_pagador = [r for r in _achados_por_pagador(p, registros) if id(r) not in ja]
        if not achados and not do_pagador:
            resultados.append(classificar(p, [], False, []))
            continue
        grupos = _por_pagamento(achados)
        for regs in grupos:
            um = Pagamento(favorecido=p.favorecido, cpf_cnpj=regs[0].cpf_cnpj or p.cpf_cnpj,
                           documento=regs[0].documento, valor=regs[0].valor, data=regs[0].data)
            res = classificar(um, regs, False, [])
            if len(grupos) > 1:
                res.observacoes.insert(0, f"Favorecido tem {len(grupos)} pagamentos nos arquivos.")
            resultados.append(res)
        for regs in _por_pagamento(do_pagador):
            um = Pagamento(favorecido=regs[0].nome, cpf_cnpj=regs[0].cpf_cnpj, documento=regs[0].documento,
                           valor=regs[0].valor, data=regs[0].data)
            res = classificar(um, regs, False, [])
            res.observacoes.insert(0, f"Pago por {regs[0].arquivo.pagador} (achado pela empresa pagadora).")
            resultados.append(res)
    return resultados
