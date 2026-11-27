"""Regra tributária: chaves de busca, resultado esperado, vigência e fundamento.

Chave vazia = coringa. Uma chave pode listar alternativas separadas por "|".
`ncm` e `cfop` casam por prefixo (ex.: ncm "2202" casa com 22021000).
Entre várias regras que casam, vence a mais específica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# Peso de cada chave no cálculo da especificidade. ncm e cfop somam também o tamanho do prefixo.
PESOS = {
    "uf_origem": 1,
    "uf_destino": 2,
    "origem_mercadoria": 3,
    "tipo_destinatario": 2,
    "regime": 1,
    "cfop": 1,
    "ncm": 10,
    "cest": 20,
}
CHAVES = tuple(PESOS)
CHAVES_POR_PREFIXO = {"ncm", "cfop"}


@dataclass(frozen=True)
class Contexto:
    """O que se sabe da operação de um item, usado para buscar a regra."""

    tributo: str
    data: date
    uf_origem: str | None = None
    uf_destino: str | None = None
    origem_mercadoria: str | None = None
    tipo_destinatario: str | None = None  # contribuinte, nao_contribuinte, isento
    regime: str | None = None  # nao_cumulativo, cumulativo (PIS/COFINS); crt para ICMS
    cfop: str | None = None
    ncm: str | None = None
    cest: str | None = None


@dataclass(frozen=True)
class Regra:
    id: str
    tributo: str
    vigencia_inicio: date
    vigencia_fim: date | None
    chaves: dict[str, tuple[str, ...]] = field(default_factory=dict)
    cst: tuple[str, ...] = ()
    aliquota: Decimal | None = None
    reducao_base: Decimal | None = None
    mva: Decimal | None = None
    fundamento: str = ""
    observacao: str = ""
    fonte: str = ""

    def vigente(self, dia: date) -> bool:
        return self.vigencia_inicio <= dia and (self.vigencia_fim is None or dia <= self.vigencia_fim)

    def casa(self, ctx: Contexto) -> bool:
        if self.tributo != ctx.tributo or not self.vigente(ctx.data):
            return False
        for chave, alternativas in self.chaves.items():
            valor = getattr(ctx, chave)
            if valor is None:
                return False
            valor = valor.replace(".", "")
            if chave in CHAVES_POR_PREFIXO:
                if not any(valor.startswith(a) for a in alternativas):
                    return False
            elif valor not in alternativas:
                return False
        return True

    @property
    def especificidade(self) -> int:
        total = 0
        for chave, alternativas in self.chaves.items():
            total += PESOS[chave]
            if chave in CHAVES_POR_PREFIXO:
                total += min(len(a) for a in alternativas)
        return total
