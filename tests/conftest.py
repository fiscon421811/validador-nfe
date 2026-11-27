from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def dados_isolados(tmp_path, monkeypatch):
    """Os testes não enxergam nenhuma TIPI real.

    Nem a baixada pelo app (pasta de dados do usuário) nem a embutida em `regras/tipi/` pelo script do
    executável: as notas de teste são fictícias e cada teste monta a sua própria TIPI quando precisa.
    """
    monkeypatch.setenv("VALIDADOR_DADOS", str(tmp_path / "dados"))
    from validador_nfe import tipi
    from validador_nfe.regras.base import PASTA_PADRAO

    embutida = (PASTA_PADRAO / "tipi").resolve()
    original = tipi.listar_versoes

    def sem_embutida(*pastas):
        return original(*[p for p in pastas if not p or Path(p).resolve() != embutida])

    monkeypatch.setattr(tipi, "listar_versoes", sem_embutida)


@pytest.fixture
def xml_ok() -> str:
    return (FIXTURES / "nfe_ok.xml").read_text(encoding="utf-8")


def alterar(xml: str, *trocas: tuple[str, str]) -> bytes:
    """Aplica trocas de texto no XML de exemplo, falhando se o trecho não existir."""
    for antigo, novo in trocas:
        assert antigo in xml, f"trecho não encontrado no XML de teste: {antigo}"
        xml = xml.replace(antigo, novo, 1)
    return xml.encode("utf-8")
