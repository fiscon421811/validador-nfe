"""Relatório de divergências em JSON e Excel."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from validador_nfe.validador import Resultado

_COLUNAS = ["Arquivo", "Chave", "Número", "Item", "Código", "Severidade", "Mensagem", "Campo",
            "Esperado", "Encontrado", "Diferença (R$)", "Fundamento"]
_CORES = {"erro": "F8D7DA", "alerta": "FFF3CD", "info": "D1ECF1"}


def _linhas(resultados: list[Resultado]):
    for r in resultados:
        for d in r.divergencias:
            yield [
                r.arquivo, r.nota.chave if r.nota else None, r.nota.numero if r.nota else None,
                d.item, d.codigo, d.severidade.value, d.mensagem, d.campo, d.esperado, d.encontrado,
                float(d.diferenca) if d.diferenca is not None else None, d.fundamento,
            ]


def resumo(resultados: list[Resultado]) -> dict:
    sev = Counter(d.severidade.value for r in resultados for d in r.divergencias)
    return {
        "notas": len(resultados),
        "notas_ok": sum(r.situacao == "ok" for r in resultados),
        "notas_com_alertas": sum(r.situacao == "com alertas" for r in resultados),
        "notas_com_erros": sum(r.situacao == "com erros" for r in resultados),
        "erros": sev.get("erro", 0),
        "alertas": sev.get("alerta", 0),
    }


def gerar_json(resultados: list[Resultado], destino: Path) -> None:
    dados = {
        "resumo": resumo(resultados),
        "notas": [
            {
                "arquivo": r.arquivo,
                "chave": r.nota.chave if r.nota else None,
                "numero": r.nota.numero if r.nota else None,
                "situacao": r.situacao,
                "divergencias": [d.como_dict() for d in r.divergencias],
            }
            for r in resultados
        ],
    }
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def gerar_excel(resultados: list[Resultado], destino: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Divergências"
    ws.append(_COLUNAS)
    for cel in ws[1]:
        cel.font = Font(bold=True)
    for linha in _linhas(resultados):
        ws.append(linha)
        cor = _CORES.get(linha[5])
        if cor:
            ws.cell(row=ws.max_row, column=6).fill = PatternFill("solid", fgColor=cor)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col, largura in zip("ABCDEFGHIJKL", (28, 46, 10, 6, 8, 11, 70, 22, 14, 14, 14, 40)):
        ws.column_dimensions[col].width = largura

    notas = wb.create_sheet("Notas")
    notas.append(["Arquivo", "Chave", "Número", "Situação", "Erros", "Alertas"])
    for cel in notas[1]:
        cel.font = Font(bold=True)
    for r in resultados:
        notas.append([
            r.arquivo, r.nota.chave if r.nota else None, r.nota.numero if r.nota else None, r.situacao,
            sum(d.severidade.value == "erro" for d in r.divergencias),
            sum(d.severidade.value == "alerta" for d in r.divergencias),
        ])
    wb.save(destino)
