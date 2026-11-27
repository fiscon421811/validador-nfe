"""Estado de uma sessão de validação, sem dependência de interface.

A interface gráfica (gui.py) só desenha o que esta classe guarda. Isso mantém a lógica testável
e permite trocar a interface (Flet, web, Kotlin) sem mexer na validação.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from validador_nfe import tipi
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
        """Usa um CSV avulso ncm;aliquota no lugar das versões guardadas da TIPI."""
        self.tipi = caminho
        self.recarregar_base()

    def recarregar_base(self) -> None:
        self.base = BaseRegras.da_pasta(self.pasta_regras, tipi=self.tipi)
        self.revalidar()

    @property
    def descricao_tipi(self) -> str:
        return self.base.tipi_descricao

    def atualizar_tipi(self, forcar: bool = False) -> tipi.ResultadoAtualizacao:
        """Verifica a TIPI na Receita (1x por dia, salvo forcar) e recarrega as regras se mudou."""
        r = tipi.atualizar(pastas_existentes=[self.pasta_regras / "tipi"], forcar=forcar)
        if r.atualizou:
            self.recarregar_base()
        return r

    def importar_tipi(self, planilha: Path) -> tipi.ResultadoAtualizacao:
        """Importa uma planilha .xlsx da TIPI baixada manualmente."""
        r = tipi.importar(planilha.read_bytes(), tipi.pasta_dados(), str(planilha),
                          pastas_existentes=[self.pasta_regras / "tipi"])
        if r.atualizou:
            self.tipi = None
            self.recarregar_base()
        return r

    def limpar(self) -> None:
        self.arquivos, self.resultados = [], []

    def resumo(self) -> dict:
        return resumo(self.resultados)

    def exportar_excel(self, destino: Path) -> None:
        gerar_excel(self.resultados, destino)

    def exportar_json(self, destino: Path) -> None:
        gerar_json(self.resultados, destino)
