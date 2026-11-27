"""Base de regras carregada de arquivos CSV (separador ";").

Por enquanto a base fica em memória. A interface `BaseRegras.buscar` é o ponto de troca
para uma base em PostgreSQL ou licenciada, sem mexer no resto do validador.
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from validador_nfe.regras.modelo import CHAVES, Contexto, Regra


def _pasta_padrao() -> Path:
    """Pasta regras/: variável VALIDADOR_REGRAS, ou dentro do executável, ou na raiz do projeto."""
    if os.environ.get("VALIDADOR_REGRAS"):
        return Path(os.environ["VALIDADOR_REGRAS"])
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "regras"  # executável gerado pelo PyInstaller / flet pack
    return Path(__file__).resolve().parents[3] / "regras"


PASTA_PADRAO = _pasta_padrao()


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


def regras_da_versao(versao, inicio: date, fim: date | None) -> list[Regra]:
    """Converte uma versão guardada da TIPI (ver validador_nfe.tipi) em regras de IPI."""
    from validador_nfe.tipi import ler_csv_tipi

    regras = []
    for linha in ler_csv_tipi(versao.arquivo):
        if linha.ex:
            continue  # ex-tarifários ainda não são tratados
        nt = linha.aliquota == "NT"
        regras.append(Regra(
            id=f"IPI-TIPI-{linha.ncm}-{versao.hash[:8]}",
            tributo="IPI",
            vigencia_inicio=inicio,
            vigencia_fim=fim,
            chaves={"ncm": (linha.ncm,)},
            aliquota=None if nt else Decimal(linha.aliquota),
            fundamento=f"TIPI (Decreto 11.158/2022 e alterações), versão de {versao.detectada_em:%d/%m/%Y}",
            observacao="NT" if nt else "",
            fonte=versao.arquivo.name,
        ))
    return regras


class BaseRegras:
    def __init__(self, regras: list[Regra]):
        ids = [r.id for r in regras]
        repetidos = {i for i in ids if ids.count(i) > 1}
        if repetidos:
            raise ErroBase(f"ids de regra repetidos: {sorted(repetidos)}")
        self._por_tributo: dict[str, list[Regra]] = {}
        self._ipi_por_ncm: dict[str, list[Regra]] = {}
        self.tipi_versao = None
        self.tipi_descricao = "não disponível"
        self._adicionar(regras)

    @classmethod
    def da_pasta(cls, pasta: Path = PASTA_PADRAO, tipi: Path | None = None, tipi_inicio: date | None = None,
                 pasta_tipi_usuario: Path | None = None, usar_tipi_versionada: bool = True):
        """Regras dos CSV da pasta + TIPI.

        A TIPI vem das versões embutidas (`pasta/tipi/`) e das baixadas pelo app (pasta de dados do
        usuário). `tipi` aceita ainda um CSV avulso `ncm;aliquota`, que substitui as versões.
        """
        regras: list[Regra] = []
        for arquivo in sorted(pasta.glob("*.csv")):
            regras += ler_csv(arquivo)
        base = cls(regras)
        if tipi is not None:
            base._adicionar(ler_tipi(tipi, tipi_inicio or date(2022, 4, 1)))
            base.tipi_descricao = f"arquivo {tipi.name}"
        elif usar_tipi_versionada:
            from validador_nfe import tipi as mod_tipi

            usuario = pasta_tipi_usuario if pasta_tipi_usuario is not None else mod_tipi.pasta_dados()
            versoes = mod_tipi.listar_versoes(pasta / "tipi", usuario)
            for versao, inicio, fim in mod_tipi.periodos(versoes):
                base._adicionar(regras_da_versao(versao, inicio, fim))
            if versoes:
                base.tipi_versao = versoes[-1]
                base.tipi_descricao = f"versão de {versoes[-1].nome}"
        return base

    def _adicionar(self, regras: list[Regra]) -> None:
        for r in regras:
            self._por_tributo.setdefault(r.tributo, []).append(r)
            if r.tributo == "IPI" and "ncm" in r.chaves:
                for ncm in r.chaves["ncm"]:
                    self._ipi_por_ncm.setdefault(ncm, []).append(r)

    def __len__(self) -> int:
        return sum(len(v) for v in self._por_tributo.values())

    def buscar(self, ctx: Contexto) -> Regra | None:
        """A regra vigente mais específica que casa com o contexto, ou None."""
        fonte = self._por_tributo.get(ctx.tributo, [])
        if ctx.tributo == "IPI" and ctx.ncm and self._ipi_por_ncm:
            # a TIPI tem ~10 mil linhas: busca direta pelo NCM, mais as regras de IPI sem NCM
            fonte = self._ipi_por_ncm.get(ctx.ncm, []) + [r for r in fonte if "ncm" not in r.chaves]
        candidatas = [r for r in fonte if r.casa(ctx)]
        if not candidatas:
            return None
        candidatas.sort(key=lambda r: (r.especificidade, r.vigencia_inicio), reverse=True)
        return candidatas[0]
