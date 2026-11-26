"""Checagens que não dependem da base de regras (Fase 0)."""

from validador_nfe.checagens.coerencia import checar_coerencia
from validador_nfe.checagens.estruturais import checar_estrutura

__all__ = ["checar_coerencia", "checar_estrutura"]
