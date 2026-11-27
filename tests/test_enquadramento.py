from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook

from validador_nfe import tipi
from validador_nfe.enquadramento import enquadrar
from validador_nfe.leitor import ler_nfe
from validador_nfe.regras import BaseRegras, Perfil
from validador_nfe.regras.base import PASTA_PADRAO
from validador_nfe.relatorio import gerar_excel, gerar_json
from validador_nfe.validador import validar_arquivo

from test_tipi import planilha

FIXTURES = Path(__file__).parent / "fixtures"
XML_OK = (FIXTURES / "nfe_ok.xml").read_text(encoding="utf-8")


@pytest.fixture
def base_com_tipi(tmp_path, monkeypatch):
    monkeypatch.setattr(tipi, "MINIMO_NCMS", 1)
    tipi.importar(planilha([("7318.15.00", None, 5), ("2202.10.00", None, "NT")]), tmp_path, "t",
                  hoje=date(2024, 1, 1))
    return BaseRegras.da_pasta(PASTA_PADRAO, pasta_tipi_usuario=tmp_path)


def _linhas(e):
    return {linha.tributo: linha for linha in e.linhas}


def test_enquadramento_nota_ok(base_com_tipi):
    nota = ler_nfe(FIXTURES / "nfe_ok.xml")
    i1, i2 = enquadrar(nota, base_com_tipi, Perfil("nao_cumulativo"))
    l1 = _linhas(i1)
    assert l1["NCM"].situacao == "Válido" and l1["NCM"].origem == "base"
    assert "7318.15.00" in l1["NCM"].detalhe
    assert l1["CBS / IBS"].situacao == "Enquadrado" and not l1["CBS / IBS"].divergente
    assert l1["ICMS / ICMS-ST"].situacao == "Aplicável" and l1["ICMS / ICMS-ST"].origem == "base"
    assert l1["PIS / COFINS"].origem == "base"
    assert l1["IPI"].situacao == "Tributado" and not l1["IPI"].divergente
    assert i1.base_legal  # fundamentos das regras usadas

    l2 = _linhas(i2)
    assert l2["IPI"].situacao == "Não tributado (NT)"
    assert l2["CEST"].situacao == "03.007.00"
    assert l2["ICMS / ICMS-ST"].situacao == "ST já recolhida"


def test_ncm_fora_da_tipi(base_com_tipi):
    from conftest import alterar

    xml = alterar(XML_OK, ("<NCM>73181500</NCM>", "<NCM>99999999</NCM>"))
    (e, _) = enquadrar(ler_nfe(xml), base_com_tipi)
    ncm = _linhas(e)["NCM"]
    assert ncm.situacao == "Não encontrado" and ncm.divergente


def test_sem_tipi_e_sem_regime_mostra_conforme_a_nota():
    base = BaseRegras.da_pasta(PASTA_PADRAO, usar_tipi_versionada=False)
    (e, _) = enquadrar(ler_nfe(FIXTURES / "nfe_ok.xml"), base)
    l = _linhas(e)
    assert l["NCM"].origem == "nota" and "TIPI não disponível" in l["NCM"].detalhe
    assert l["PIS / COFINS"].origem == "nota" and "regime" in l["PIS / COFINS"].detalhe


def test_monofasico():
    from conftest import alterar

    xml = alterar(XML_OK, ("<PIS><PISAliq><CST>01</CST><vBC>50.00</vBC><pPIS>1.65</pPIS><vPIS>0.83</vPIS></PISAliq></PIS>",
                           "<PIS><PISNT><CST>04</CST></PISNT></PIS>"))
    base = BaseRegras.da_pasta(PASTA_PADRAO, usar_tipi_versionada=False)
    (_, e2) = enquadrar(ler_nfe(xml), base, Perfil("nao_cumulativo"))
    assert _linhas(e2)["PIS / COFINS"].situacao == "Monofásico"


def test_relatorios_trazem_enquadramento(base_com_tipi, tmp_path):
    r = validar_arquivo(FIXTURES / "nfe_ok.xml", base=base_com_tipi, perfil=Perfil("nao_cumulativo"))
    assert len(r.enquadramentos) == 2
    gerar_json([r], tmp_path / "r.json")
    import json

    dados = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert dados["notas"][0]["enquadramento"][0]["linhas"][0]["tributo"] == "NCM"
    gerar_excel([r], tmp_path / "r.xlsx")
    ws = load_workbook(tmp_path / "r.xlsx")["Enquadramento"]
    assert ws.max_row == 1 + 2 * 6
