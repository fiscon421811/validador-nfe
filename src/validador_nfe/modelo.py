"""Modelo canônico da NF-e: um registro por nota e por item, independente do layout do XML."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class Tributo:
    """Valores de um tributo em um item. Campos ausentes no XML ficam como None."""

    nome: str  # ICMS, ICMS_ST, IPI, PIS, COFINS, IBS_UF, IBS_MUN, CBS
    cst: str | None = None
    base: Decimal | None = None
    aliquota: Decimal | None = None
    valor: Decimal | None = None
    reducao_base: Decimal | None = None
    mva: Decimal | None = None


@dataclass
class Item:
    numero: int
    codigo: str
    descricao: str
    ncm: str
    cest: str | None
    cfop: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_produto: Decimal
    valor_desconto: Decimal = Decimal("0")
    valor_frete: Decimal = Decimal("0")
    valor_seguro: Decimal = Decimal("0")
    valor_outros: Decimal = Decimal("0")
    compoe_total: bool = True
    origem: str | None = None
    # Situação tributária do ICMS: CST (regime normal) ou CSOSN (Simples Nacional)
    cst_icms: str | None = None
    csosn: str | None = None
    tributos: dict[str, Tributo] = field(default_factory=dict)
    # Grupo da Reforma Tributária (NT 2025.002)
    tem_grupo_ibscbs: bool = False
    cst_ibscbs: str | None = None
    cclasstrib: str | None = None
    # Grupo de partilha do DIFAL para não contribuinte (ICMSUFDest)
    tem_difal: bool = False

    def tributo(self, nome: str) -> Tributo | None:
        return self.tributos.get(nome)


@dataclass
class Participante:
    cnpj_cpf: str | None
    nome: str | None
    uf: str | None
    ie: str | None = None
    crt: str | None = None  # só emitente
    ind_ie_dest: str | None = None  # só destinatário: 1 contribuinte, 2 isento, 9 não contribuinte


@dataclass
class Nota:
    chave: str | None
    numero: str | None
    serie: str | None
    modelo: str | None
    data_emissao: datetime | None
    tipo: str | None  # tpNF: 0 entrada, 1 saída
    destino: str | None  # idDest: 1 interna, 2 interestadual, 3 exterior
    consumidor_final: bool
    finalidade: str | None  # finNFe
    emitente: Participante
    destinatario: Participante
    itens: list[Item]
    totais: dict[str, Decimal]
    arquivo: str | None = None
