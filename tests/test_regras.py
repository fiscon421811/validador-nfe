from datetime import date
from decimal import Decimal

import pytest

from conftest import FIXTURES, alterar
from validador_nfe import ler_nfe, validar
from validador_nfe.cli import main
from validador_nfe.regras import BaseRegras, Contexto, ErroBase, Perfil
from validador_nfe.regras.base import ler_csv, ler_tipi

NC = Perfil(regime_pis_cofins="nao_cumulativo")


@pytest.fixture
def base() -> BaseRegras:
    return BaseRegras.da_pasta()


def divergencias(xml: bytes, base, perfil=NC):
    return [d for d in validar(ler_nfe(xml), base, perfil) if d.codigo.startswith("D")]


def test_base_padrao_carrega(base):
    assert len(base) >= 11


def test_regra_mais_especifica_vence(base):
    ctx = dict(tributo="ICMS", data=date(2026, 11, 20), uf_origem="SP", uf_destino="MG", cfop="6102")
    assert base.buscar(Contexto(**ctx, origem_mercadoria="0")).aliquota == Decimal("12")
    assert base.buscar(Contexto(**ctx, origem_mercadoria="1")).aliquota == Decimal("4")
    assert base.buscar(Contexto(**{**ctx, "uf_destino": "BA"}, origem_mercadoria="0")).aliquota == Decimal("7")


def test_vigencia_e_respeitada(base):
    ctx = Contexto(tributo="CBS", data=date(2027, 3, 1))
    assert base.buscar(ctx) is None  # a regra de teste vale só em 2026


def test_nota_correta_sem_divergencias_de_regra(xml_ok, base):
    assert divergencias(xml_ok.encode(), base) == []


def test_aliquota_interna_errada_vira_alerta_em_regra_generica(xml_ok, base):
    xml = alterar(xml_ok, ("<pICMS>18.00</pICMS><vICMS>45.00</vICMS>", "<pICMS>12.00</pICMS><vICMS>30.00</vICMS>"),
                  ("<vICMS>45.00</vICMS><vICMSDeson>", "<vICMS>30.00</vICMS><vICMSDeson>"))
    (d,) = divergencias(xml, base)
    assert d.codigo == "D001" and d.severidade.value == "alerta"
    assert d.esperado == "18" and d.diferenca == Decimal("-15.00")
    assert "SP-ICMS-INTERNA" in d.fundamento


def test_interestadual_importado_exige_4(xml_ok, base):
    xml = alterar(
        xml_ok,
        ("<idDest>1</idDest>", "<idDest>2</idDest>"),
        ("<UF>SP</UF></enderDest>", "<UF>PR</UF></enderDest>"),
        ("<CFOP>5102</CFOP>", "<CFOP>6102</CFOP>"),
        ("<CFOP>5405</CFOP>", "<CFOP>6404</CFOP>"),
        ("<orig>0</orig><CST>00</CST>", "<orig>1</orig><CST>00</CST>"),
        ("<pICMS>18.00</pICMS><vICMS>45.00</vICMS>", "<pICMS>12.00</pICMS><vICMS>30.00</vICMS>"),
    )
    (d,) = [d for d in divergencias(xml, base) if d.campo == "pICMS"]
    assert d.esperado == "4" and "Resolução do Senado 13/2012" in d.fundamento


def test_pis_cofins_conforme_regime(xml_ok, base):
    assert divergencias(xml_ok.encode(), base, Perfil()) == []  # sem regime, não confere
    cumulativo = divergencias(xml_ok.encode(), base, Perfil(regime_pis_cofins="cumulativo"))
    assert {(d.campo, d.esperado) for d in cumulativo} == {("pPIS", "0.65"), ("pCOFINS", "3.00")}


def test_cbs_fora_da_aliquota_de_teste(xml_ok, base):
    xml = alterar(xml_ok, ("<pCBS>0.90</pCBS><vCBS>2.25</vCBS>", "<pCBS>8.80</pCBS><vCBS>22.00</vCBS>"))
    (d,) = divergencias(xml, base)
    assert d.campo == "pCBS" and d.esperado == "0.90"


def test_ipi_pela_tipi(xml_ok, tmp_path):
    tipi = tmp_path / "tipi.csv"
    tipi.write_text("ncm;aliquota\n73181500;6.5\n22021000;NT\n", encoding="utf-8")
    base = BaseRegras(ler_tipi(tipi, date(2022, 4, 1)))
    (d,) = divergencias(xml_ok.encode(), base)
    assert d.campo == "pIPI" and d.esperado == "6.5" and d.severidade.value == "erro"

    xml = alterar(xml_ok, ("<IPINT><CST>53</CST></IPINT>",
                           "<IPITrib><CST>50</CST><vBC>50.00</vBC><pIPI>5.00</pIPI><vIPI>2.50</vIPI></IPITrib>"))
    assert "D002" in [d.codigo for d in divergencias(xml, base)]


def test_regra_sem_fundamento_e_recusada(tmp_path):
    arq = tmp_path / "ruim.csv"
    arq.write_text("id;tributo;vigencia_inicio;aliquota;fundamento\nX;ICMS;2026-01-01;18;\n", encoding="utf-8")
    with pytest.raises(ErroBase, match="fundamento"):
        ler_csv(arq)


def test_cli_com_regras(tmp_path):
    saida = tmp_path / "r.json"
    assert main([str(FIXTURES / "nfe_ok.xml"), "--regime-pis-cofins", "nao_cumulativo", "--json", str(saida)]) == 0
