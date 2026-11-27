from conftest import FIXTURES

from validador_nfe.sessao import Sessao, listar_xml


def test_listar_xml_de_pasta_e_arquivo():
    assert len(listar_xml([FIXTURES])) == 2
    assert listar_xml([FIXTURES / "nfe_ok.xml", FIXTURES / "nao_existe.txt"]) == [FIXTURES / "nfe_ok.xml"]


def test_carregar_nao_duplica():
    s = Sessao()
    assert s.carregar([FIXTURES]) == 2
    assert s.carregar([FIXTURES / "nfe_ok.xml"]) == 0
    assert s.resumo()["notas_com_erros"] == 1


def test_mudar_regime_revalida():
    s = Sessao()
    s.carregar([FIXTURES / "nfe_ok.xml"])
    assert s.resultados[0].situacao == "ok"
    s.definir_regime("cumulativo")
    assert s.resultados[0].situacao == "com alertas"
    s.definir_regime("")
    assert s.resultados[0].situacao == "ok"


def test_exportar_e_limpar(tmp_path):
    s = Sessao()
    s.carregar([FIXTURES])
    s.exportar_excel(tmp_path / "r.xlsx")
    s.exportar_json(tmp_path / "r.json")
    assert (tmp_path / "r.xlsx").exists() and (tmp_path / "r.json").exists()
    s.limpar()
    assert s.resumo()["notas"] == 0
