"""Parâmetros legais usados pelas checagens da Fase 0.

ATENÇÃO: valores escritos a partir da legislação conhecida em 2026-11. Cada um traz o
fundamento para conferência. Na Fase 1 eles migram para a base de regras com vigência.
"""

from datetime import date
from decimal import Decimal

TOLERANCIA = Decimal("0.01")  # arredondamento aceito por valor, em reais

# CRT: 1 Simples Nacional, 2 Simples com excesso de sublimite, 3 regime normal, 4 MEI
CRT_USA_CSOSN = {"1", "4"}

# Alíquotas interestaduais de ICMS: 4% (importados, Res. Senado 13/2012), 7% e 12% (Res. Senado 22/1989)
ALIQUOTAS_INTERESTADUAIS = {Decimal("4"), Decimal("7"), Decimal("12")}

# CST de ICMS com retenção de ST na própria operação
CST_COM_ST = {"10", "30", "70"}
CSOSN_COM_ST = {"201", "202", "203"}
# ICMS cobrado anteriormente por ST: não deve haver novo destaque de ST
CST_ST_ANTERIOR = {"60"}
CSOSN_ST_ANTERIOR = {"500"}
# Sem ICMS destacado
CST_SEM_ICMS = {"40", "41", "50"}
CST_TRIBUTADO_INTEGRAL = {"00"}
CST_COM_REDUCAO = {"20", "70"}

# Reforma Tributária (LC 214/2025): ano de teste com alíquotas simbólicas
INICIO_IBSCBS = date(2026, 1, 1)
ALIQUOTAS_TESTE_2026 = {
    "CBS": Decimal("0.90"),
    "IBS_UF": Decimal("0.10"),
    "IBS_MUN": Decimal("0.00"),
}
FUNDAMENTO_TESTE_2026 = "LC 214/2025, arts. 343 a 346 (conferir)"
