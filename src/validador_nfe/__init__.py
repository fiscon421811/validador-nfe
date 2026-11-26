"""Validador da tributação de NF-e."""

from validador_nfe.leitor import ler_nfe
from validador_nfe.validador import validar

__all__ = ["ler_nfe", "validar"]
__version__ = "0.1.0"
