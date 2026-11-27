"""Resumo de classificação fiscal por item: como cada tributo se enquadra para o NCM da nota.

Para cada linha o resumo diz de onde veio a informação:
- "base": determinado pela base de regras (TIPI, regras de SP, PIS/COFINS, IBS/CBS);
- "nota": só o que a nota declara, porque a base ainda não tem regra para conferir.
Assim o usuário sabe o que foi conferido e o que é apenas leitura do XML.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from validador_nfe.modelo import Item, Nota
from validador_nfe.regras.base import BaseRegras
from validador_nfe.regras.determinacao import Perfil, contexto
from validador_nfe.regras.modelo import Regra

CST_PIS_COFINS = {
    "01": "Alíquota básica",
    "02": "Alíquota diferenciada",
    "03": "Alíquota por unidade de medida",
    "04": "Monofásico (revenda a alíquota zero)",
    "05": "Substituição tributária",
    "06": "Alíquota zero",
    "07": "Isenta",
    "08": "Sem incidência",
    "09": "Suspensão",
    "49": "Outras operações de saída",
}
CST_ICMS = {
    "00": "Tributada integralmente",
    "10": "Tributada, com cobrança de ICMS-ST",
    "20": "Com redução de base de cálculo",
    "30": "Isenta ou não tributada, com cobrança de ICMS-ST",
    "40": "Isenta",
    "41": "Não tributada",
    "50": "Suspensão",
    "51": "Diferimento",
    "60": "ICMS-ST cobrado anteriormente",
    "70": "Redução de base, com cobrança de ICMS-ST",
    "90": "Outras",
}
CSOSN = {
    "101": "Simples, com permissão de crédito",
    "102": "Simples, sem permissão de crédito",
    "103": "Simples, isenção por faixa de receita",
    "201": "Simples, com crédito e cobrança de ICMS-ST",
    "202": "Simples, sem crédito e com cobrança de ICMS-ST",
    "203": "Simples, isenção e cobrança de ICMS-ST",
    "300": "Imune",
    "400": "Não tributada pelo Simples",
    "500": "ICMS-ST cobrado anteriormente",
    "900": "Outros",
}
_COM_ST = {"10", "30", "60", "70", "201", "202", "203", "500"}
_ST_ANTERIOR = {"60", "500"}


@dataclass
class Linha:
    tributo: str  # rótulo, como no relatório
    situacao: str  # palavra-chave curta: Enquadrado, Aplicável, Monofásico...
    detalhe: str
    origem: str  # "base" ou "nota"
    fundamento: str = ""
    divergente: bool = False


@dataclass
class EnquadramentoItem:
    item: int
    descricao: str
    ncm: str
    cest: str | None
    linhas: list[Linha] = field(default_factory=list)

    @property
    def base_legal(self) -> list[str]:
        return list(dict.fromkeys(linha.fundamento for linha in self.linhas if linha.fundamento))

    def como_dict(self) -> dict:
        d = asdict(self)
        d["base_legal"] = self.base_legal
        return d


def _fmt(valor) -> str:
    return "" if valor is None else f"{valor.normalize():f}%".replace(".", ",")


def _regra(base: BaseRegras, nota: Nota, item: Item, tributo: str, perfil: Perfil) -> Regra | None:
    if nota.data_emissao is None:
        return None
    return base.buscar(contexto(nota, item, tributo, perfil))


def _ncm(item: Item, base: BaseRegras, nota: Nota, perfil: Perfil) -> Linha:
    regra = _regra(base, nota, item, "IPI", perfil)
    if not base.tem_tipi:
        return Linha("NCM", "Informado", f"{_ncm_formatado(item.ncm)} (TIPI não disponível para conferir)", "nota")
    if regra is None:
        return Linha("NCM", "Não encontrado", f"{_ncm_formatado(item.ncm)} não consta na TIPI vigente", "base",
                     f"TIPI, {base.tipi_descricao}", divergente=True)
    return Linha("NCM", "Válido", f"{_ncm_formatado(item.ncm)} consta na TIPI vigente", "base", regra.fundamento)


def _ncm_formatado(ncm: str) -> str:
    return f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}" if len(ncm) == 8 else ncm


def _ipi(item: Item, base: BaseRegras, nota: Nota, perfil: Perfil) -> Linha:
    trib = item.tributo("IPI")
    regra = _regra(base, nota, item, "IPI", perfil)
    informado = _fmt(trib.aliquota) if trib and trib.aliquota is not None else "não destacado"
    if regra is None:
        cst = f"CST {trib.cst}" if trib and trib.cst else "sem grupo IPI"
        return Linha("IPI", "Conforme a nota", f"{cst}, alíquota {informado}", "nota")
    if regra.observacao == "NT":
        destacou = bool(trib and trib.valor)
        return Linha("IPI", "Não tributado (NT)", "NCM sem incidência de IPI na TIPI", "base", regra.fundamento,
                     divergente=destacou)
    esperado = _fmt(regra.aliquota)
    diverge = bool(trib and trib.aliquota is not None and trib.aliquota != regra.aliquota)
    return Linha("IPI", "Tributado", f"TIPI {esperado}; nota {informado}", "base", regra.fundamento, diverge)


def _ibscbs(item: Item, base: BaseRegras, nota: Nota, perfil: Perfil) -> Linha:
    if not item.tem_grupo_ibscbs:
        return Linha("CBS / IBS", "Sem grupo IBSCBS", "A nota não traz o grupo da Reforma Tributária", "nota")
    partes = [f"CST {item.cst_ibscbs}", f"cClassTrib {item.cclasstrib}"]
    fundamentos, diverge = [], False
    for nome, rotulo in (("CBS", "CBS"), ("IBS_UF", "IBS UF"), ("IBS_MUN", "IBS Mun")):
        trib = item.tributo(nome)
        regra = _regra(base, nota, item, nome, perfil)
        if trib and trib.aliquota is not None:
            partes.append(f"{rotulo} {_fmt(trib.aliquota)}")
        if regra is not None and regra.aliquota is not None and (not regra.cst or item.cst_ibscbs in regra.cst):
            fundamentos.append(regra.fundamento)
            if trib and trib.aliquota is not None and trib.aliquota != regra.aliquota:
                diverge = True
    if fundamentos:
        situacao = "Divergente" if diverge else "Enquadrado"
        return Linha("CBS / IBS", situacao, ", ".join(partes), "base", fundamentos[0], diverge)
    return Linha("CBS / IBS", "Conforme a nota", ", ".join(partes), "nota")


def _icms(item: Item, base: BaseRegras, nota: Nota, perfil: Perfil) -> Linha:
    situacao = item.cst_icms or item.csosn or ""
    nome = CST_ICMS.get(item.cst_icms or "") or CSOSN.get(item.csosn or "") or "situação não informada"
    rotulo = f"CST {item.cst_icms}" if item.cst_icms else f"CSOSN {item.csosn}" if item.csosn else ""
    st = "com ICMS-ST" if situacao in _COM_ST else "sem ICMS-ST"
    icms = item.tributo("ICMS")
    regra = _regra(base, nota, item, "ICMS", perfil)
    detalhe = f"{rotulo} – {nome}; {st}"
    if situacao in _ST_ANTERIOR:
        return Linha("ICMS / ICMS-ST", "ST já recolhida", detalhe + "; sem ICMS próprio a destacar", "nota")
    if regra is not None and regra.aliquota is not None:
        informado = _fmt(icms.aliquota) if icms and icms.aliquota is not None else "sem destaque"
        detalhe += f"; alíquota prevista {_fmt(regra.aliquota)}, nota {informado}"
        diverge = bool(icms and icms.aliquota and icms.aliquota != regra.aliquota)
        palavra = "Aplicável" if situacao not in {"40", "41", "50", "300", "400"} else "Não incide"
        return Linha("ICMS / ICMS-ST", palavra, detalhe + ". ICMS-ST conforme a nota (regras de ST ainda não cadastradas)",
                     "base", regra.fundamento, diverge)
    return Linha("ICMS / ICMS-ST", "Conforme a nota", detalhe, "nota")


def _pis_cofins(item: Item, base: BaseRegras, nota: Nota, perfil: Perfil) -> Linha:
    pis, cofins = item.tributo("PIS"), item.tributo("COFINS")
    cst = (pis.cst if pis else None) or (cofins.cst if cofins else None) or ""
    nome = CST_PIS_COFINS.get(cst, "CST não informado")
    palavra = "Monofásico" if cst == "04" else nome.split(" (")[0]
    partes = [f"CST {cst} – {nome}"] if cst else [nome]
    if pis and pis.aliquota is not None:
        partes.append(f"PIS {_fmt(pis.aliquota)}, COFINS {_fmt(cofins.aliquota) if cofins else '?'}")
    if perfil.regime_pis_cofins is None:
        return Linha("PIS / COFINS", palavra, "; ".join(partes) + " (regime da empresa não informado)", "nota")
    fundamentos, diverge = [], False
    for t in (pis, cofins):
        if t is None:
            continue
        regra = _regra(base, nota, item, t.nome, perfil)
        if regra is not None and (not regra.cst or t.cst in regra.cst):
            fundamentos.append(regra.fundamento)
            if t.aliquota is not None and regra.aliquota is not None and t.aliquota != regra.aliquota:
                diverge = True
    if fundamentos:
        return Linha("PIS / COFINS", palavra, "; ".join(partes), "base", " e ".join(dict.fromkeys(fundamentos)), diverge)
    return Linha("PIS / COFINS", palavra, "; ".join(partes) + " (sem regra para este CST; monofásicos ainda não cadastrados)",
                 "nota")


def _cest(item: Item) -> Linha:
    if not item.cest:
        return Linha("CEST", "Não informado", "Item sem CEST", "nota")
    c = item.cest.replace(".", "")
    fmt = f"{c[:2]}.{c[2:5]}.{c[5:]}" if len(c) == 7 else item.cest
    return Linha("CEST", fmt, "Informado na nota (tabela CEST × NCM ainda não carregada)", "nota")


def enquadrar_item(nota: Nota, item: Item, base: BaseRegras, perfil: Perfil | None = None) -> EnquadramentoItem:
    perfil = perfil or Perfil()
    e = EnquadramentoItem(item.numero, item.descricao, item.ncm, item.cest)
    e.linhas = [
        _ncm(item, base, nota, perfil),
        _ibscbs(item, base, nota, perfil),
        _icms(item, base, nota, perfil),
        _pis_cofins(item, base, nota, perfil),
        _ipi(item, base, nota, perfil),
        _cest(item),
    ]
    return e


def enquadrar(nota: Nota, base: BaseRegras, perfil: Perfil | None = None) -> list[EnquadramentoItem]:
    return [enquadrar_item(nota, item, base, perfil) for item in nota.itens]
