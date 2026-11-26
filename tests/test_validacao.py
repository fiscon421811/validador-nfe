from decimal import Decimal

import pytest

from conftest import FIXTURES, alterar
from validador_nfe import ler_nfe, validar
from validador_nfe.cli import main
from validador_nfe.leitor import ErroLeitura


def codigos(xml: bytes) -> list[str]:
    return [d.codigo for d in validar(ler_nfe(xml))]


def test_leitura_do_modelo_canonico(xml_ok):
    nota = ler_nfe(xml_ok.encode())
    assert nota.chave == "35261100000000000191550010000012341000012345"
    assert nota.emitente.uf == "SP" and nota.emitente.crt == "3"
    assert len(nota.itens) == 2
    item = nota.itens[0]
    assert item.ncm == "73181500" and item.cst_icms == "00"
    assert item.tributo("ICMS").valor == Decimal("45.00")
    assert item.tributo("CBS").aliquota == Decimal("0.90")
    assert item.cclasstrib == "000001"
    assert nota.totais["vNF"] == Decimal("312.50")


def test_nota_correta_nao_tem_divergencias(xml_ok):
    assert validar(ler_nfe(xml_ok.encode())) == []


def test_xml_que_nao_e_nfe():
    with pytest.raises(ErroLeitura):
        ler_nfe(b"<outro/>")


@pytest.mark.parametrize(
    "trocas, esperado",
    [
        ([("<vProd>250.00</vProd><indTot>", "<vProd>260.00</vProd><indTot>")], "E001"),
        ([("<vICMS>45.00</vICMS></ICMS00>", "<vICMS>46.00</vICMS></ICMS00>")], "E002"),
        ([("<vICMS>45.00</vICMS><vICMSDeson>", "<vICMS>40.00</vICMS><vICMSDeson>")], "E003"),
        ([("<vNF>312.50</vNF>", "<vNF>300.00</vNF>")], "E004"),
        ([("<CRT>3</CRT>", "<CRT>1</CRT>")], "C001"),
        ([("<CFOP>5102</CFOP>", "<CFOP>1102</CFOP>")], "C002"),
        ([("<CFOP>5102</CFOP>", "<CFOP>6102</CFOP>")], "C003"),
        ([("<UF>SP</UF></enderDest>", "<UF>RJ</UF></enderDest>")], "C004"),
        ([("<NCM>73181500</NCM>", "<NCM>731815</NCM>")], "C005"),
        ([("<CST>60</CST>", "<CST>10</CST>")], "C006"),
        ([("<CEST>0300700</CEST>", "")], "C007"),
        ([("<CST>00</CST><modBC>3</modBC>", "<CST>40</CST><modBC>3</modBC>")], "C008"),
        ([("<CST>01</CST><vBC>50.00</vBC><pCOFINS>", "<CST>06</CST><vBC>50.00</vBC><pCOFINS>")], "C011"),
        ([("<cClassTrib>000001</cClassTrib>", "<cClassTrib>200001</cClassTrib>")], "C014"),
        ([("<pCBS>0.90</pCBS><vCBS>2.25</vCBS>", "<pCBS>8.80</pCBS><vCBS>22.00</vCBS>")], "C015"),
    ],
)
def test_cada_checagem_dispara(xml_ok, trocas, esperado):
    assert esperado in codigos(alterar(xml_ok, *trocas))


def test_interestadual_com_aliquota_interna_e_sem_difal(xml_ok):
    xml = alterar(
        xml_ok,
        ("<idDest>1</idDest>", "<idDest>2</idDest>"),
        ("<indFinal>0</indFinal>", "<indFinal>1</indFinal>"),
        ("<UF>SP</UF></enderDest>", "<UF>MG</UF></enderDest>"),
        ("<indIEDest>1</indIEDest>", "<indIEDest>9</indIEDest>"),
        ("<CFOP>5102</CFOP>", "<CFOP>6102</CFOP>"),
        ("<CFOP>5405</CFOP>", "<CFOP>6404</CFOP>"),
    )
    resultado = codigos(xml)
    assert "C009" in resultado  # 18% em operação interestadual
    assert "C010" in resultado  # falta DIFAL
    assert "C003" not in resultado and "C004" not in resultado


def test_sem_grupo_ibscbs_em_2026(xml_ok):
    inicio, fim = xml_ok.index("<IBSCBS>"), xml_ok.index("</IBSCBS>") + len("</IBSCBS>")
    xml = (xml_ok[:inicio] + xml_ok[fim:]).encode()
    assert "C012" in codigos(xml)


def test_antes_de_2026_nao_cobra_ibscbs(xml_ok):
    inicio, fim = xml_ok.index("<IBSCBS>"), xml_ok.index("</IBSCBS>") + len("</IBSCBS>")
    xml = (xml_ok[:inicio] + xml_ok[fim:]).replace("2026-11-20", "2025-11-20").encode()
    assert "C012" not in codigos(xml)


def test_cli_gera_relatorios(tmp_path):
    saida_json, saida_xlsx = tmp_path / "r.json", tmp_path / "r.xlsx"
    codigo = main([str(FIXTURES), "--json", str(saida_json), "--xlsx", str(saida_xlsx)])
    assert codigo == 1  # a pasta de exemplo tem uma nota com erros
    assert saida_json.exists() and saida_xlsx.exists()
    assert '"notas": 2' in saida_json.read_text(encoding="utf-8")
