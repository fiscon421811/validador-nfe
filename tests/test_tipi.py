import io
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from openpyxl import Workbook

from conftest import FIXTURES
from validador_nfe import ler_nfe, tipi, validar
from validador_nfe.regras import BaseRegras, Contexto
from validador_nfe.regras.base import PASTA_PADRAO
from validador_nfe.sessao import Sessao


def planilha(linhas) -> bytes:
    """Planilha no formato da TIPI: títulos, cabeçalho, capítulos, posições, NCMs e ex-tarifários."""
    wb = Workbook()
    ws = wb.active
    ws.append(["TABELA DE INCIDÊNCIA DO IMPOSTO SOBRE PRODUTOS INDUSTRIALIZADOS"])
    ws.append([])
    ws.append(["NCM", "EX", "DESCRIÇÃO", "ALÍQUOTA (%)"])
    ws.append(["73", None, "Obras de ferro fundido, ferro ou aço", None])
    ws.append(["73.18", None, "Parafusos, pinos ou pernos", None])
    for ncm, ex, aliq in linhas:
        ws.append([ncm, ex, "descrição", aliq])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


BASICA = [("7318.15.00", None, 6.5), ("2202.10.00", None, "NT"), ("8471.30.12", None, 0), ("8471.30.12", "01", 5)]


@pytest.fixture(autouse=True)
def minimo_pequeno(monkeypatch):
    monkeypatch.setattr(tipi, "MINIMO_NCMS", 1)


def test_ler_planilha():
    linhas = tipi.ler_planilha(planilha(BASICA))
    assert [(x.ncm, x.ex, x.aliquota) for x in linhas] == [
        ("73181500", "", "6.5"), ("22021000", "", "NT"), ("84713012", "", "0"), ("84713012", "01", "5")]


def test_planilha_invalida():
    with pytest.raises(tipi.ErroTipi):
        tipi.ler_planilha(b"isto nao e xlsx")


def test_planilha_pequena_demais_nao_e_gravada(tmp_path, monkeypatch):
    monkeypatch.setattr(tipi, "MINIMO_NCMS", 100)
    with pytest.raises(tipi.ErroTipi, match="NCMs"):
        tipi.importar(planilha(BASICA), tmp_path, "teste")
    assert tipi.listar_versoes(tmp_path) == []


def test_importar_versoes_e_mudancas(tmp_path):
    r1 = tipi.importar(planilha(BASICA), tmp_path, "teste", hoje=date(2026, 1, 10))
    assert r1.atualizou and r1.mudancas is None
    assert not tipi.importar(planilha(BASICA), tmp_path, "teste").atualizou  # mesma planilha

    nova = [("7318.15.00", None, 9.75), ("2202.10.00", None, "NT"), ("9999.99.99", None, 3)]
    r2 = tipi.importar(planilha(nova), tmp_path, "teste", hoje=date(2026, 11, 20))
    assert r2.atualizou
    assert r2.mudancas.alterados == [("73181500", "6.5", "9.75")]
    assert r2.mudancas.novos == ["99999999"]
    assert set(r2.mudancas.removidos) == {"84713012", "84713012 ex 01"}
    assert r2.relatorio.exists()


def test_vigencia_por_versao(tmp_path):
    tipi.importar(planilha(BASICA), tmp_path, "t", hoje=date(2026, 1, 10))
    tipi.importar(planilha([("7318.15.00", None, 9.75)]), tmp_path, "t", hoje=date(2026, 11, 20))
    base = BaseRegras.da_pasta(PASTA_PADRAO, pasta_tipi_usuario=tmp_path)
    ctx = dict(tributo="IPI", ncm="73181500")
    assert base.buscar(Contexto(data=date(2026, 6, 1), **ctx)).aliquota == Decimal("6.5")
    assert base.buscar(Contexto(data=date(2026, 11, 25), **ctx)).aliquota == Decimal("9.75")
    assert "20/11/2026" in base.tipi_descricao


def test_ipi_conferido_sem_carregar_nada(tmp_path, monkeypatch):
    monkeypatch.setenv("VALIDADOR_DADOS", str(tmp_path))
    tipi.importar(planilha(BASICA), tipi.pasta_dados(), "t", hoje=date(2024, 1, 1))
    s = Sessao()
    s.carregar([FIXTURES / "nfe_ok.xml"])
    (d,) = [d for d in s.resultados[0].divergencias if d.campo == "pIPI"]
    assert d.esperado == "6.5" and d.encontrado == "5.00"


def test_atualizar_usa_link_conhecido_e_respeita_intervalo(tmp_path):
    conteudo = planilha(BASICA)
    chamadas = []

    def baixar(url):
        chamadas.append(url)
        if url == tipi.LINKS_TIPI[1]:
            return conteudo
        raise OSError("HTTP Error 404: Not Found")

    r = tipi.atualizar(tmp_path, baixar=baixar)
    assert r.atualizou and chamadas == tipi.LINKS_TIPI[:2]
    assert not tipi.atualizar(tmp_path, baixar=baixar).atualizou  # já verificou hoje
    assert tipi.precisa_verificar(tmp_path, agora=datetime.now() + timedelta(days=2))


def test_procura_link_na_pagina_quando_enderecos_mudam(tmp_path):
    conteudo = planilha(BASICA)

    def baixar(url):
        if url == tipi.PAGINAS_TIPI[0]:
            return b'<a href="/receitafederal/arquivos/nova-tipi-excel.xlsx/view">TIPI</a><a href="/x.pdf">x</a>'
        if url == "https://www.gov.br/receitafederal/arquivos/nova-tipi-excel.xlsx/@@download/file":
            return conteudo
        if url in tipi.LINKS_TIPI:
            return b"<html>pagina de erro</html>"  # 200 com HTML no lugar da planilha
        raise OSError("404")

    link, dados = tipi.baixar_planilha(baixar)
    assert link.endswith("nova-tipi-excel.xlsx/@@download/file") and dados == conteudo


def test_url_definida_pelo_usuario(monkeypatch):
    monkeypatch.setenv("VALIDADOR_TIPI_URL", "https://exemplo/tipi.xlsx")
    assert tipi.candidatos() == ["https://exemplo/tipi.xlsx"]


def test_falha_de_rede_nao_quebra(tmp_path):
    def baixar(url):
        raise OSError("sem internet")

    r = tipi.atualizar(tmp_path, baixar=baixar, forcar=True)
    assert not r.atualizou and "sem internet" in r.mensagem


def test_linha_de_comando_importa(tmp_path):
    arq = tmp_path / "tipi.xlsx"
    arq.write_bytes(planilha(BASICA))
    assert tipi.main(["--pasta", str(tmp_path / "v"), "--importar", str(arq), "--embutida"]) == 0
    (v,) = tipi.listar_versoes(tmp_path / "v")
    assert v.embutida and v.ncms == 3
