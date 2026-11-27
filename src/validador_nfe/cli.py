"""Linha de comando: valida um XML ou uma pasta de XMLs de NF-e."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from validador_nfe.regras import BaseRegras, ErroBase, Perfil
from validador_nfe.regras.base import PASTA_PADRAO
from validador_nfe.relatorio import gerar_excel, gerar_json, resumo
from validador_nfe.validador import validar_arquivo


def _arquivos(caminhos: list[Path]) -> list[Path]:
    saida = []
    for c in caminhos:
        saida += sorted(c.rglob("*.xml")) if c.is_dir() else [c]
    return saida


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="validador-nfe", description="Valida a tributação de NF-e")
    parser.add_argument("caminhos", nargs="+", type=Path, help="arquivos XML ou pastas")
    parser.add_argument("--json", type=Path, help="grava o relatório em JSON")
    parser.add_argument("--xlsx", type=Path, help="grava o relatório em Excel")
    parser.add_argument("--xsd", type=Path, help="XSD oficial (nfe_v4.00.xsd) para validar o schema")
    parser.add_argument("--regras", type=Path, default=PASTA_PADRAO,
                        help="pasta com os CSV da base de regras (padrão: regras/ do projeto)")
    parser.add_argument("--sem-regras", action="store_true", help="só checagens estruturais e de coerência")
    parser.add_argument("--tipi", type=Path, help="CSV ncm;aliquota exportado da TIPI, para conferir o IPI")
    parser.add_argument("--regime-pis-cofins", choices=["nao_cumulativo", "cumulativo"],
                        help="regime do emitente; sem ele PIS/COFINS não são conferidos pela base")
    args = parser.parse_args(argv)

    base = None
    if not args.sem_regras:
        try:
            base = BaseRegras.da_pasta(args.regras, tipi=args.tipi)
        except ErroBase as exc:
            parser.error(f"base de regras inválida: {exc}")
        print(f"Base de regras: {len(base)} regras de {args.regras}")
    perfil = Perfil(regime_pis_cofins=args.regime_pis_cofins)

    resultados = [validar_arquivo(a, args.xsd, base, perfil) for a in _arquivos(args.caminhos)]
    for r in resultados:
        print(f"{r.situacao.upper():12} {r.arquivo}")
        for d in r.divergencias:
            onde = f"item {d.item}" if d.item else "nota"
            print(f"    [{d.severidade.value}] {d.codigo} {onde}: {d.mensagem}"
                  + (f" (esperado {d.esperado}, encontrado {d.encontrado})" if d.esperado or d.encontrado else ""))
    print(resumo(resultados))

    if args.json:
        gerar_json(resultados, args.json)
    if args.xlsx:
        gerar_excel(resultados, args.xlsx)
    return 1 if any(r.situacao == "com erros" for r in resultados) else 0


if __name__ == "__main__":
    sys.exit(main())
