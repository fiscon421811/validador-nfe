"""Resultado de uma checagem."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum


class Severidade(str, Enum):
    ERRO = "erro"  # a nota está errada ou seria rejeitada pela SEFAZ
    ALERTA = "alerta"  # provável erro, precisa de revisão humana
    INFO = "info"  # observação, sem indício de erro


@dataclass
class Divergencia:
    codigo: str
    severidade: Severidade
    mensagem: str
    item: int | None = None  # None = nível da nota
    campo: str | None = None
    esperado: str | None = None
    encontrado: str | None = None
    diferenca: Decimal | None = None
    fundamento: str | None = None

    def como_dict(self) -> dict:
        d = asdict(self)
        d["severidade"] = self.severidade.value
        d["diferenca"] = str(self.diferenca) if self.diferenca is not None else None
        return d
