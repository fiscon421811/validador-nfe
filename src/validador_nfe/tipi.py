"""TIPI: leitura da planilha oficial, versões guardadas e atualização automática.

Como funciona:
- Cada versão da TIPI vira um CSV `ncm;ex;aliquota` + um JSON de metadados (data, hash, fonte).
- Versões vêm de dois lugares: as embutidas no app (`regras/tipi/`, geradas no build) e as
  baixadas depois (pasta de dados do usuário). A mais nova vale a partir da data em que foi
  detectada; a anterior passa a valer até a véspera. Assim notas antigas continuam sendo
  conferidas com a TIPI da época em que o app a conhecia.
- A atualização baixa a planilha da Receita Federal, compara o hash com a última versão e, se
  mudou, grava a nova versão e um relatório do que mudou (NCM novo, removido, alíquota alterada).

A data real de vigência de cada alteração está no decreto que a publicou. A data de detecção
é uma aproximação: notas emitidas entre a publicação e a detecção podem ser conferidas contra
a alíquota anterior.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path

from openpyxl import load_workbook

# Páginas da Receita Federal onde o link da planilha da TIPI é procurado. Se a Receita mudar o
# endereço, ajuste aqui ou defina VALIDADOR_TIPI_URL com o link direto do .xlsx.
PAGINAS_TIPI = [
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/legislacao/documentos-e-arquivos/tipi",
    "https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/tipi",
]
INTERVALO_VERIFICACAO = timedelta(hours=24)
MINIMO_NCMS = 5000  # uma planilha válida da TIPI tem cerca de 10 mil NCMs
INICIO_DECRETO_ATUAL = date(2022, 4, 1)  # Decreto 11.158/2022
USER_AGENT = "validador-nfe (verificacao da TIPI)"


class ErroTipi(Exception):
    pass


@dataclass(frozen=True)
class LinhaTipi:
    ncm: str
    ex: str
    aliquota: str  # número em % ou "NT"


@dataclass
class VersaoTipi:
    arquivo: Path
    detectada_em: date
    hash: str
    fonte: str
    ncms: int
    embutida: bool = False

    @property
    def nome(self) -> str:
        return f"{self.detectada_em:%d/%m/%Y} ({self.ncms} NCMs)"


@dataclass
class Mudancas:
    novos: list[str] = field(default_factory=list)
    removidos: list[str] = field(default_factory=list)
    alterados: list[tuple[str, str, str]] = field(default_factory=list)  # ncm, antes, depois

    @property
    def total(self) -> int:
        return len(self.novos) + len(self.removidos) + len(self.alterados)

    def resumo(self) -> str:
        return (f"{len(self.alterados)} alíquotas alteradas, {len(self.novos)} NCMs novos, "
                f"{len(self.removidos)} NCMs removidos")


# ---------------------------------------------------------------- pastas

def pasta_dados() -> Path:
    """Onde ficam as versões baixadas: VALIDADOR_DADOS, %LOCALAPPDATA%\\ValidadorNFe ou ~/.local/share."""
    if os.environ.get("VALIDADOR_DADOS"):
        base = Path(os.environ["VALIDADOR_DADOS"])
    elif sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"]) / "ValidadorNFe"
    else:
        base = Path.home() / ".local" / "share" / "validador-nfe"
    return base / "tipi"


# ---------------------------------------------------------------- leitura da planilha

def _normalizar_ncm(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _normalizar_aliquota(valor) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip().upper().replace("%", "").replace(",", ".")
    if texto == "":
        return None
    if texto == "NT":
        return "NT"
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return None
    return format(numero.normalize(), "f")


def ler_planilha(conteudo: bytes) -> list[LinhaTipi]:
    """Lê a planilha .xlsx da TIPI. Procura a linha de cabeçalho com NCM e ALÍQUOTA."""
    try:
        wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - qualquer falha do openpyxl vira erro de TIPI
        raise ErroTipi(f"não é uma planilha .xlsx válida: {exc}") from exc
    linhas: list[LinhaTipi] = []
    for ws in wb.worksheets:
        col_ncm = col_ex = col_aliq = None
        for row in ws.iter_rows(values_only=True):
            celulas = [str(c).strip().upper() if c is not None else "" for c in row]
            if col_ncm is None:
                for i, c in enumerate(celulas):
                    if c.startswith("NCM"):
                        col_ncm = i
                    elif c.startswith("EX"):
                        col_ex = i
                    elif "ALÍQ" in c or "ALIQ" in c:
                        col_aliq = i
                if col_ncm is None or col_aliq is None:
                    col_ncm = col_ex = col_aliq = None
                continue
            ncm = _normalizar_ncm(row[col_ncm] if col_ncm < len(row) else None)
            if len(ncm) != 8:
                continue  # capítulos, posições e linhas de texto
            aliq = _normalizar_aliquota(row[col_aliq] if col_aliq < len(row) else None)
            if aliq is None:
                continue
            ex = str(row[col_ex]).strip() if col_ex is not None and col_ex < len(row) and row[col_ex] else ""
            linhas.append(LinhaTipi(ncm, ex, aliq))
    wb.close()
    if not linhas:
        raise ErroTipi("nenhuma linha de NCM com alíquota encontrada (cabeçalho NCM/ALÍQUOTA não achado)")
    return linhas


# ---------------------------------------------------------------- versões em disco

def _gravar_csv(linhas: list[LinhaTipi], destino: Path) -> None:
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ncm", "ex", "aliquota"])
        for linha in sorted(linhas, key=lambda x: (x.ncm, x.ex)):
            w.writerow([linha.ncm, linha.ex, linha.aliquota])


def ler_csv_tipi(caminho: Path) -> list[LinhaTipi]:
    with open(caminho, encoding="utf-8", newline="") as f:
        return [LinhaTipi(r["ncm"], r.get("ex", "") or "", r["aliquota"]) for r in csv.DictReader(f, delimiter=";")]


def listar_versoes(*pastas: Path) -> list[VersaoTipi]:
    """Versões encontradas nas pastas, da mais antiga para a mais nova, sem repetir hash."""
    vistas: dict[str, VersaoTipi] = {}
    for pasta in pastas:
        if not pasta or not pasta.is_dir():
            continue
        for meta in pasta.glob("tipi_*.json"):
            dados = json.loads(meta.read_text(encoding="utf-8"))
            csv_ = meta.with_suffix(".csv")
            if not csv_.exists():
                continue
            v = VersaoTipi(arquivo=csv_, detectada_em=date.fromisoformat(dados["detectada_em"]),
                           hash=dados["hash"], fonte=dados.get("fonte", ""), ncms=dados.get("ncms", 0),
                           embutida=dados.get("embutida", False))
            if v.hash not in vistas or v.detectada_em < vistas[v.hash].detectada_em:
                vistas[v.hash] = v
    return sorted(vistas.values(), key=lambda v: (v.detectada_em, v.hash))


def salvar_versao(linhas: list[LinhaTipi], conteudo_hash: str, pasta: Path, fonte: str,
                  detectada_em: date | None = None, embutida: bool = False) -> VersaoTipi:
    pasta.mkdir(parents=True, exist_ok=True)
    detectada_em = detectada_em or date.today()
    base = pasta / f"tipi_{detectada_em:%Y%m%d}_{conteudo_hash[:12]}"
    _gravar_csv(linhas, base.with_suffix(".csv"))
    ncms = len({x.ncm for x in linhas})
    meta = {"detectada_em": detectada_em.isoformat(), "hash": conteudo_hash, "fonte": fonte, "ncms": ncms,
            "embutida": embutida, "gravada_em": datetime.now().isoformat(timespec="seconds")}
    base.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return VersaoTipi(base.with_suffix(".csv"), detectada_em, conteudo_hash, fonte, ncms, embutida)


def comparar(antes: list[LinhaTipi], depois: list[LinhaTipi]) -> Mudancas:
    a = {(x.ncm, x.ex): x.aliquota for x in antes}
    d = {(x.ncm, x.ex): x.aliquota for x in depois}
    m = Mudancas()
    m.novos = sorted(f"{k[0]}{' ex ' + k[1] if k[1] else ''}" for k in d.keys() - a.keys())
    m.removidos = sorted(f"{k[0]}{' ex ' + k[1] if k[1] else ''}" for k in a.keys() - d.keys())
    m.alterados = sorted((f"{k[0]}{' ex ' + k[1] if k[1] else ''}", a[k], d[k])
                         for k in a.keys() & d.keys() if a[k] != d[k])
    return m


def gravar_relatorio_mudancas(m: Mudancas, pasta: Path, quando: date) -> Path:
    destino = pasta / f"mudancas_{quando:%Y%m%d}.csv"
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["tipo", "ncm", "aliquota_antes", "aliquota_depois"])
        for ncm, antes, depois in m.alterados:
            w.writerow(["alterado", ncm, antes, depois])
        for ncm in m.novos:
            w.writerow(["novo", ncm, "", ""])
        for ncm in m.removidos:
            w.writerow(["removido", ncm, "", ""])
    return destino


# ---------------------------------------------------------------- download

class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href:
                self.links.append(href)


def _baixar(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - URLs fixas da Receita
        return r.read()


def encontrar_link_planilha(baixar: Callable[[str], bytes] = _baixar) -> str:
    if os.environ.get("VALIDADOR_TIPI_URL"):
        return os.environ["VALIDADOR_TIPI_URL"]
    erros = []
    for pagina in PAGINAS_TIPI:
        try:
            html = baixar(pagina).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            erros.append(f"{pagina}: {exc}")
            continue
        parser = _Links()
        parser.feed(html)
        candidatos = [link for link in parser.links if re.search(r"\.xlsx?(\?|$|/@@download)", link, re.I)
                      or "tipi" in link.lower() and "xls" in link.lower()]
        if candidatos:
            return urllib.parse.urljoin(pagina, candidatos[0])
        erros.append(f"{pagina}: nenhum link de planilha na página")
    raise ErroTipi("link da planilha da TIPI não encontrado. " + " | ".join(erros))


@dataclass
class ResultadoAtualizacao:
    atualizou: bool
    mensagem: str
    versao: VersaoTipi | None = None
    mudancas: Mudancas | None = None
    relatorio: Path | None = None


def _estado(pasta: Path) -> dict:
    arq = pasta / "estado.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}


def _gravar_estado(pasta: Path, estado: dict) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def precisa_verificar(pasta: Path | None = None, agora: datetime | None = None) -> bool:
    pasta = pasta or pasta_dados()
    ultima = _estado(pasta).get("ultima_verificacao")
    agora = agora or datetime.now()
    return ultima is None or agora - datetime.fromisoformat(ultima) >= INTERVALO_VERIFICACAO


def importar(conteudo: bytes, pasta: Path, fonte: str, pastas_existentes: list[Path] | None = None,
             hoje: date | None = None, embutida: bool = False) -> ResultadoAtualizacao:
    """Registra uma planilha da TIPI como nova versão, se ela for diferente da última conhecida."""
    hoje = hoje or date.today()
    conteudo_hash = hashlib.sha256(conteudo).hexdigest()
    versoes = listar_versoes(pasta, *(pastas_existentes or []))
    if versoes and versoes[-1].hash == conteudo_hash:
        return ResultadoAtualizacao(False, f"TIPI já está atualizada (versão de {versoes[-1].nome})", versoes[-1])
    if any(v.hash == conteudo_hash for v in versoes):
        return ResultadoAtualizacao(False, "Esta planilha já foi importada antes", None)
    linhas = ler_planilha(conteudo)
    ncms = len({x.ncm for x in linhas})
    if ncms < MINIMO_NCMS:
        raise ErroTipi(f"planilha com só {ncms} NCMs; esperado mais de {MINIMO_NCMS}. Versão não gravada.")
    nova = salvar_versao(linhas, conteudo_hash, pasta, fonte, hoje, embutida)
    if not versoes:
        return ResultadoAtualizacao(True, f"TIPI carregada: {ncms} NCMs", nova)
    mudancas = comparar(ler_csv_tipi(versoes[-1].arquivo), linhas)
    relatorio = gravar_relatorio_mudancas(mudancas, pasta, hoje)
    return ResultadoAtualizacao(True, f"TIPI atualizada: {mudancas.resumo()}", nova, mudancas, relatorio)


def atualizar(pasta: Path | None = None, pastas_existentes: list[Path] | None = None,
              baixar: Callable[[str], bytes] = _baixar, forcar: bool = False) -> ResultadoAtualizacao:
    """Verifica a TIPI na Receita (no máximo uma vez por dia, salvo `forcar`)."""
    pasta = pasta or pasta_dados()
    if not forcar and not precisa_verificar(pasta):
        return ResultadoAtualizacao(False, "Verificação da TIPI já feita nas últimas 24 horas")
    estado = _estado(pasta)
    estado["ultima_verificacao"] = datetime.now().isoformat(timespec="seconds")
    try:
        link = encontrar_link_planilha(baixar)
        conteudo = baixar(link)
        resultado = importar(conteudo, pasta, link, pastas_existentes)
        estado["ultimo_resultado"] = resultado.mensagem
        return resultado
    except Exception as exc:  # noqa: BLE001 - falha de rede não pode derrubar o app
        estado["ultimo_resultado"] = f"falha: {exc}"
        return ResultadoAtualizacao(False, f"Não foi possível verificar a TIPI: {exc}")
    finally:
        _gravar_estado(pasta, estado)


def periodos(versoes: list[VersaoTipi]) -> list[tuple[VersaoTipi, date, date | None]]:
    """Vigência atribuída a cada versão: a primeira desde o decreto atual, as demais desde a detecção."""
    saida = []
    for i, v in enumerate(versoes):
        inicio = INICIO_DECRETO_ATUAL if i == 0 else v.detectada_em
        fim = versoes[i + 1].detectada_em - timedelta(days=1) if i + 1 < len(versoes) else None
        saida.append((v, inicio, fim))
    return saida


def main(argv: list[str] | None = None) -> int:
    """Uso: python -m validador_nfe.tipi [--pasta DIR] [--importar arquivo.xlsx] [--embutida]"""
    import argparse

    p = argparse.ArgumentParser(prog="validador_nfe.tipi", description="Baixa ou importa a TIPI oficial")
    p.add_argument("--pasta", type=Path, default=None, help="onde gravar (padrão: pasta de dados do usuário)")
    p.add_argument("--importar", type=Path, help="planilha .xlsx já baixada, em vez de baixar")
    p.add_argument("--embutida", action="store_true", help="marca a versão como embutida no app (build)")
    args = p.parse_args(argv)
    pasta = args.pasta or pasta_dados()
    try:
        if args.importar:
            r = importar(args.importar.read_bytes(), pasta, str(args.importar), embutida=args.embutida)
        else:
            link = encontrar_link_planilha()
            print(f"Baixando {link}")
            r = importar(_baixar(link), pasta, link, embutida=args.embutida)
    except (ErroTipi, OSError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    print(r.mensagem)
    if r.relatorio:
        print(f"Mudanças em {r.relatorio}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["ErroTipi", "LinhaTipi", "Mudancas", "VersaoTipi", "atualizar", "comparar", "importar",
           "ler_planilha", "listar_versoes", "pasta_dados", "periodos"]
