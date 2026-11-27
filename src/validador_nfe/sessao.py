"""Estado de uma sessão de validação, sem dependência de interface.

A interface gráfica (gui.py) só desenha o que esta classe guarda. Isso mantém a lógica testável
e permite trocar a interface (Flet, web, Kotlin) sem mexer na validação.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from validador_nfe.regras import BaseRegras, Perfil
from validador_nfe.regras.base import PASTA_PADRAO
from validador_nfe.relatorio import gerar_excel, gerar_json, resumo
from validador_nfe.validador import Resultado, validar_arquivo

REGIMES = {
    "": "Não informado (não confere)",
    "nao_cumulativo": "Não cumulativo (Lucro Real)",
    "cumulativo": "Cumulativo (Lucro Presumido)",
}


def listar_xml(caminhos: Iterable[Path]) -> list[Path]:
    saida: list[Path] = []
    for c in caminhos:
        if c.is_dir():
            saida += sorted(p for p in c.rglob("*") if p.suffix.lower() == ".xml")
        elif c.suffix.lower() == ".xml":
            saida.append(c)
    return saida


class Sessao:
    def __init__(self, pasta_regras: Path = PASTA_PADRAO):
        self.pasta_regras = pasta_regras
        self.tipi: Path | None = None
        self.regime: str = ""
        self.arquivos: list[Path] = []
        self.resultados: list[Resultado] = []
        self.base = BaseRegras.da_pasta(pasta_regras)

    @property
    def perfil(self) -> Perfil:
        return Perfil(regime_pis_cofins=self.regime or None)

    def carregar(self, caminhos: Iterable[Path]) -> int:
        """Adiciona XMLs (arquivos ou pastas) e valida os novos. Retorna quantos entraram."""
        novos = [a for a in listar_xml(caminhos) if a not in self.arquivos]
        self.arquivos += novos
        self.resultados += [validar_arquivo(a, base=self.base, perfil=self.perfil) for a in novos]
        return len(novos)

    def revalidar(self) -> None:
        self.resultados = [validar_arquivo(a, base=self.base, perfil=self.perfil) for a in self.arquivos]

    def definir_regime(self, regime: str) -> None:
        if regime not in REGIMES:
            raise ValueError(f"regime desconhecido: {regime}")
        self.regime = regime
        self.revalidar()

    def definir_tipi(self, caminho: Path | None) -> None:
        self.tipi = caminho
        self.base = BaseRegras.da_pasta(self.pasta_regras, tipi=caminho)
        self.revalidar()

    def limpar(self) -> None:
        self.arquivos, self.resultados = [], []

    def resumo(self) -> dict:
        return resumo(self.resultados)

    def exportar_excel(self, destino: Path) -> None:
        gerar_excel(self.resultados, destino)

    def exportar_json(self, destino: Path) -> None:
        gerar_json(self.resultados, destino)
