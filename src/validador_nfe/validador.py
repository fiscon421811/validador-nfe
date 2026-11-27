"""Orquestra a leitura e as checagens de uma nota."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from validador_nfe.checagens import checar_coerencia, checar_estrutura
from validador_nfe.divergencia import Divergencia, Severidade
from validador_nfe.leitor import ErroLeitura, ler_nfe, validar_xsd
from validador_nfe.modelo import Nota
from validador_nfe.regras import BaseRegras, Perfil, determinar


@dataclass
class Resultado:
    arquivo: str | None
    nota: Nota | None
    divergencias: list[Divergencia] = field(default_factory=list)

    @property
    def situacao(self) -> str:
        if any(d.severidade is Severidade.ERRO for d in self.divergencias):
            return "com erros"
        if any(d.severidade is Severidade.ALERTA for d in self.divergencias):
            return "com alertas"
        return "ok"


def validar(nota: Nota, base: BaseRegras | None = None, perfil: Perfil | None = None) -> list[Divergencia]:
    """Checagens estruturais e de coerência; com `base`, também a determinação pelas regras."""
    saida = checar_estrutura(nota) + checar_coerencia(nota)
    if base is not None:
        saida += determinar(nota, base, perfil)
    return saida


def validar_arquivo(caminho: Path, caminho_xsd: Path | None = None, base: BaseRegras | None = None,
                    perfil: Perfil | None = None) -> Resultado:
    divergencias: list[Divergencia] = []
    if caminho_xsd is not None:
        for erro in validar_xsd(caminho, caminho_xsd):
            divergencias.append(Divergencia("X001", Severidade.ERRO, f"Schema XSD: {erro}"))
    try:
        nota = ler_nfe(caminho)
    except ErroLeitura as exc:
        divergencias.append(Divergencia("X000", Severidade.ERRO, f"Não foi possível ler a nota: {exc}"))
        return Resultado(str(caminho), None, divergencias)
    divergencias += validar(nota, base, perfil)
    return Resultado(str(caminho), nota, divergencias)
