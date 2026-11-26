"""Checagens aritméticas: valores do item, cálculo de cada tributo e totais da nota."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from validador_nfe.divergencia import Divergencia, Severidade
from validador_nfe.modelo import Item, Nota
from validador_nfe.parametros import TOLERANCIA

CENTAVO = Decimal("0.01")


def _r(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _checar_valor_produto(item: Item) -> list[Divergencia]:
    esperado = _r(item.quantidade * item.valor_unitario)
    diferenca = item.valor_produto - esperado
    if abs(diferenca) <= TOLERANCIA:
        return []
    return [
        Divergencia(
            codigo="E001",
            severidade=Severidade.ERRO,
            mensagem="Valor do produto difere de quantidade × valor unitário",
            item=item.numero,
            campo="vProd",
            esperado=str(esperado),
            encontrado=str(item.valor_produto),
            diferenca=diferenca,
        )
    ]


def _checar_calculo_tributos(item: Item) -> list[Divergencia]:
    saida = []
    for trib in item.tributos.values():
        if trib.base is None or trib.aliquota is None or trib.valor is None:
            continue
        esperado = _r(trib.base * trib.aliquota / 100)
        diferenca = trib.valor - esperado
        if abs(diferenca) > TOLERANCIA:
            saida.append(
                Divergencia(
                    codigo="E002",
                    severidade=Severidade.ERRO,
                    mensagem=f"{trib.nome}: valor difere de base × alíquota",
                    item=item.numero,
                    campo=f"v{trib.nome}",
                    esperado=str(esperado),
                    encontrado=str(trib.valor),
                    diferenca=diferenca,
                )
            )
    return saida


def _soma(nota: Nota, tributo: str, atributo: str = "valor") -> Decimal:
    total = Decimal("0")
    for item in nota.itens:
        trib = item.tributo(tributo)
        if trib is not None and getattr(trib, atributo) is not None:
            total += getattr(trib, atributo)
    return total


# campo do ICMSTot -> função que soma o valor esperado a partir dos itens
_TOTAIS = {
    "vProd": lambda n: sum((i.valor_produto for i in n.itens if i.compoe_total), Decimal("0")),
    "vDesc": lambda n: sum((i.valor_desconto for i in n.itens), Decimal("0")),
    "vFrete": lambda n: sum((i.valor_frete for i in n.itens), Decimal("0")),
    "vSeg": lambda n: sum((i.valor_seguro for i in n.itens), Decimal("0")),
    "vOutro": lambda n: sum((i.valor_outros for i in n.itens), Decimal("0")),
    "vBC": lambda n: _soma(n, "ICMS", "base"),
    "vICMS": lambda n: _soma(n, "ICMS"),
    "vBCST": lambda n: _soma(n, "ICMS_ST", "base"),
    "vST": lambda n: _soma(n, "ICMS_ST"),
    "vFCP": lambda n: _soma(n, "FCP"),
    "vIPI": lambda n: _soma(n, "IPI"),
    "vPIS": lambda n: _soma(n, "PIS"),
    "vCOFINS": lambda n: _soma(n, "COFINS"),
}


def _checar_totais(nota: Nota) -> list[Divergencia]:
    saida = []
    for campo, calcular in _TOTAIS.items():
        if campo not in nota.totais:
            continue
        esperado = _r(calcular(nota))
        encontrado = nota.totais[campo]
        diferenca = encontrado - esperado
        if abs(diferenca) > TOLERANCIA:
            saida.append(
                Divergencia(
                    codigo="E003",
                    severidade=Severidade.ERRO,
                    mensagem=f"Total {campo} não fecha com a soma dos itens",
                    campo=f"ICMSTot/{campo}",
                    esperado=str(esperado),
                    encontrado=str(encontrado),
                    diferenca=diferenca,
                )
            )
    return saida


def _checar_valor_nota(nota: Nota) -> list[Divergencia]:
    t = nota.totais
    if "vNF" not in t:
        return []
    g = lambda c: t.get(c, Decimal("0"))  # noqa: E731
    esperado = _r(
        g("vProd") - g("vDesc") - g("vICMSDeson") + g("vST") + g("vFCPST")
        + g("vFrete") + g("vSeg") + g("vOutro") + g("vII") + g("vIPI") + g("vIPIDevol")
        + g("vServ")
    )
    diferenca = t["vNF"] - esperado
    if abs(diferenca) <= TOLERANCIA:
        return []
    return [
        Divergencia(
            codigo="E004",
            severidade=Severidade.ERRO,
            mensagem="Valor total da nota não fecha com a composição dos totais",
            campo="ICMSTot/vNF",
            esperado=str(esperado),
            encontrado=str(t["vNF"]),
            diferenca=diferenca,
            fundamento="MOC da NF-e, regra de validação W16-10 (rejeição 610)",
        )
    ]


def checar_estrutura(nota: Nota) -> list[Divergencia]:
    saida: list[Divergencia] = []
    for item in nota.itens:
        saida += _checar_valor_produto(item)
        saida += _checar_calculo_tributos(item)
    saida += _checar_totais(nota)
    saida += _checar_valor_nota(nota)
    return saida
