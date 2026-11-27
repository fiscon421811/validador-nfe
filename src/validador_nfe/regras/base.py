"""Base de regras carregada de arquivos CSV (separador ";").

Por enquanto a base fica em memória. A interface `BaseRegras.buscar` é o ponto de troca
para uma base em PostgreSQL ou licenciada, sem mexer no resto do validador.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from validador_nfe.regras.modelo import CHAVES, Contexto, Regra

PASTA_PADRAO = Path(__file__).resolve().parents[3] / "regras"


class ErroBase(Exception):
    pass


def _dec(valor: str) -> Decimal | None:
    valor = (valor or "").strip().replace(",", ".")
    return Decimal(valor) if valor else None


def _data(valor: str) -> date | None:
    valor = (valor or "").strip()
    return date.fromisoformat(valor) if valor else None


def _alternativas(valor: str) -> tuple[str, ...]:
    return tuple(v.strip().replace(".", "") for v in (valor or "").split("|") if v.strip())


def ler_csv(caminho: Path) -> list[Regra]:
    regras = []
    with open(caminho, encoding="utf-8", newline="") as f:
        linhas = (linha for linha in f if linha.strip() and not linha.lstrip().startswith("#"))
        for n, linha in enumerate(csv.DictReader(linhas, delimiter=";"), start=2):
            try:
                inicio = _data(linha["vigencia_inicio"])
                if inicio is None:
                    raise ErroBase("vigencia_inicio é obrigatória")
                if not (linha.get("fundamento") or "").strip():
                    raise ErroBase("fundamento é obrigatório")
                chaves = {c: _alternativas(linha.get(c, "")) for c in CHAVES}
                regras.append(
                    Regra(
                        id=linha["id"].strip(),
                        tributo=linha["tributo"].strip(),
                        vigencia_inicio=inicio,
                        vigencia_fim=_data(linha.get("vigencia_fim", "")),
                        chaves={c: v for c, v in chaves.items() if v},
                        cst=_alternativas(linha.get("cst", "")),
                        aliquota=_dec(linha.get("aliquota", "")),
                        reducao_base=_dec(linha.get("reducao_base", "")),
                        mva=_dec(linha.get("mva", "")),
                        fundamento=linha["fundamento"].strip(),
                        observacao=(linha.get("observacao") or "").strip(),
                        fonte=caminho.name,
                    )
                )
            except (KeyError, ValueError, ErroBase) as exc:
                raise ErroBase(f"{caminho.name}, regra perto da linha {n}: {exc}") from exc
    return regras


def ler_tipi(caminho: Path, vigencia_inicio: date, fundamento: str = "TIPI (Decreto 11.158/2022)") -> list[Regra]:
    """Converte um CSV "ncm;aliquota" exportado da TIPI oficial em regras de IPI.

    Linhas com alíquota "NT" (não tributado) viram regras sem alíquota.
    """
    regras = []
    with open(caminho, encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            ncm = linha["ncm"].strip().replace(".", "")
            aliq = linha["aliquota"].strip().upper()
            if not ncm:
                continue
            regras.append(
                Regra(
                    id=f"IPI-TIPI-{ncm}",
                    tributo="IPI",
                    vigencia_inicio=vigencia_inicio,
                    vigencia_fim=None,
                    chaves={"ncm": (ncm,)},
                    aliquota=None if aliq == "NT" else _dec(aliq),
                    fundamento=fundamento,
                    observacao="NT" if aliq == "NT" else "",
                    fonte=caminho.name,
                )
            )
    return regras


class BaseRegras:
    def __init__(self, regras: list[Regra]):
        ids = [r.id for r in regras]
        repetidos = {i for i in ids if ids.count(i) > 1}
        if repetidos:
            raise ErroBase(f"ids de regra repetidos: {sorted(repetidos)}")
        self._por_tributo: dict[str, list[Regra]] = {}
        for r in regras:
            self._por_tributo.setdefault(r.tributo, []).append(r)

    @classmethod
    def da_pasta(cls, pasta: Path = PASTA_PADRAO, tipi: Path | None = None, tipi_inicio: date | None = None):
        regras: list[Regra] = []
        for arquivo in sorted(pasta.glob("*.csv")):
            regras += ler_csv(arquivo)
        if tipi is not None:
            regras += ler_tipi(tipi, tipi_inicio or date(2022, 4, 1))
        return cls(regras)

    def __len__(self) -> int:
        return sum(len(v) for v in self._por_tributo.values())

    def buscar(self, ctx: Contexto) -> Regra | None:
        """A regra vigente mais específica que casa com o contexto, ou None."""
        candidatas = [r for r in self._por_tributo.get(ctx.tributo, []) if r.casa(ctx)]
        if not candidatas:
            return None
        candidatas.sort(key=lambda r: (r.especificidade, r.vigencia_inicio), reverse=True)
        return candidatas[0]
