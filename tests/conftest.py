from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def xml_ok() -> str:
    return (FIXTURES / "nfe_ok.xml").read_text(encoding="utf-8")


def alterar(xml: str, *trocas: tuple[str, str]) -> bytes:
    """Aplica trocas de texto no XML de exemplo, falhando se o trecho não existir."""
    for antigo, novo in trocas:
        assert antigo in xml, f"trecho não encontrado no XML de teste: {antigo}"
        xml = xml.replace(antigo, novo, 1)
    return xml.encode("utf-8")
