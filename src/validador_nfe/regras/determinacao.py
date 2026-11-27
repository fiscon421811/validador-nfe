"""Determinação: busca a regra vigente de cada tributo do item e compara com o que veio na nota."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from validador_nfe.divergencia import Divergencia, Severidade
from validador_nfe.modelo import Item, Nota
from validador_nfe.regras.base import BaseRegras
from validador_nfe.regras.modelo import Contexto, Regra

_TIPO_DEST = {"1": "contribuinte", "2": "isento", "9": "nao_contribuinte"}
# CST de ICMS em que a alíquota destacada deve ser a da operação
_CST_ICMS_TRIBUTADO = {"00", "10", "20", "70"}
_CSOSN_COM_DESTAQUE = {"900"}


@dataclass(frozen=True)
class Perfil:
    """Dados da empresa que não estão na nota."""

    regime_pis_cofins: str | None = None  # nao_cumulativo, cumulativo


def contexto(nota: Nota, item: Item, tributo: str, perfil: Perfil) -> Contexto:
    regime = perfil.regime_pis_cofins if tributo in ("PIS", "COFINS") else nota.emitente.crt
    return Contexto(
        tributo=tributo,
        data=nota.data_emissao.date(),
        uf_origem=nota.emitente.uf,
        uf_destino=nota.destinatario.uf,
        origem_mercadoria=item.origem,
        tipo_destinatario=_TIPO_DEST.get(nota.destinatario.ind_ie_dest or ""),
        regime=regime,
        cfop=item.cfop,
        ncm=item.ncm,
        cest=item.cest,
    )


def _cst_do_item(item: Item, tributo: str) -> str | None:
    if tributo == "ICMS":
        return item.cst_icms or item.csosn
    if tributo in ("CBS", "IBS_UF", "IBS_MUN"):
        return item.cst_ibscbs
    trib = item.tributo(tributo)
    return trib.cst if trib else None


def _deve_comparar_aliquota(item: Item, tributo: str, regra: Regra) -> bool:
    cst = _cst_do_item(item, tributo)
    if regra.cst and cst not in regra.cst:
        return False
    if tributo == "ICMS":
        return cst in _CST_ICMS_TRIBUTADO or cst in _CSOSN_COM_DESTAQUE
    return True


def _severidade(regra: Regra) -> Severidade:
    especifica = "ncm" in regra.chaves or "cest" in regra.chaves
    return Severidade.ERRO if especifica else Severidade.ALERTA


def _comparar(nota: Nota, item: Item, tributo: str, regra: Regra) -> list[Divergencia]:
    trib = item.tributo(tributo)
    fundamento = f"{regra.fundamento} [regra {regra.id}]"

    # IPI não tributado na TIPI, mas destacado na nota
    if tributo == "IPI" and regra.aliquota is None and regra.observacao == "NT":
        if trib and trib.valor and trib.valor > 0:
            return [Divergencia("D002", Severidade.ERRO, "IPI destacado para NCM não tributado (NT) na TIPI",
                                item.numero, campo="vIPI", esperado="0", encontrado=str(trib.valor),
                                diferenca=trib.valor, fundamento=fundamento)]
        return []

    if regra.aliquota is None or trib is None or trib.aliquota is None:
        return []
    if not _deve_comparar_aliquota(item, tributo, regra):
        return []
    if trib.aliquota == regra.aliquota:
        return []

    diferenca = None
    if trib.base is not None and trib.valor is not None:
        esperado_valor = (trib.base * regra.aliquota / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        diferenca = trib.valor - esperado_valor
    mensagem = f"{tributo}: alíquota diferente da prevista para a operação"
    if regra.observacao:
        mensagem += f" ({regra.observacao})"
    return [Divergencia("D001", _severidade(regra), mensagem, item.numero, campo=f"p{tributo}",
                        esperado=str(regra.aliquota), encontrado=str(trib.aliquota),
                        diferenca=diferenca, fundamento=fundamento)]


TRIBUTOS = ("ICMS", "IPI", "PIS", "COFINS", "CBS", "IBS_UF", "IBS_MUN")


def determinar(nota: Nota, base: BaseRegras, perfil: Perfil | None = None) -> list[Divergencia]:
    perfil = perfil or Perfil()
    if nota.data_emissao is None:
        return [Divergencia("D000", Severidade.ALERTA, "Nota sem data de emissão: determinação não realizada")]
    saida: list[Divergencia] = []
    for item in nota.itens:
        for tributo in TRIBUTOS:
            if tributo in ("PIS", "COFINS") and perfil.regime_pis_cofins is None:
                continue
            regra = base.buscar(contexto(nota, item, tributo, perfil))
            if regra is not None:
                saida += _comparar(nota, item, tributo, regra)
    return saida
