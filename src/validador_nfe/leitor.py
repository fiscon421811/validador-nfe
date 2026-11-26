"""Leitura do XML da NF-e (modelo 55) para o modelo canônico.

Aceita tanto o XML da nota (<NFe>) quanto o processado (<nfeProc>).
A validação contra o XSD oficial é opcional: os schemas são baixados do Portal da NF-e
e apontados por `caminho_xsd`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree

from validador_nfe.modelo import Item, Nota, Participante, Tributo

NS = "http://www.portalfiscal.inf.br/nfe"


class ErroLeitura(Exception):
    """O arquivo não é uma NF-e legível."""


def _sem_namespace(raiz: etree._Element) -> etree._Element:
    for el in raiz.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    etree.cleanup_namespaces(raiz)
    return raiz


def _txt(el: etree._Element | None, caminho: str) -> str | None:
    if el is None:
        return None
    achado = el.find(caminho)
    if achado is None or achado.text is None:
        return None
    return achado.text.strip()


def _dec(el: etree._Element | None, caminho: str) -> Decimal | None:
    valor = _txt(el, caminho)
    if valor is None or valor == "":
        return None
    try:
        return Decimal(valor)
    except InvalidOperation as exc:
        raise ErroLeitura(f"Valor numérico inválido em {caminho}: {valor!r}") from exc


def _dec0(el: etree._Element | None, caminho: str) -> Decimal:
    return _dec(el, caminho) or Decimal("0")


def _primeiro_filho(el: etree._Element | None) -> etree._Element | None:
    if el is None:
        return None
    for filho in el:
        if isinstance(filho.tag, str):
            return filho
    return None


def _data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def validar_xsd(caminho_xml: Path, caminho_xsd: Path) -> list[str]:
    """Valida o XML contra o XSD oficial. Retorna a lista de erros (vazia se válido)."""
    schema = etree.XMLSchema(etree.parse(str(caminho_xsd)))
    doc = etree.parse(str(caminho_xml))
    raiz = doc.getroot()
    alvo = raiz.find(f"{{{NS}}}NFe") if raiz.tag == f"{{{NS}}}nfeProc" else raiz
    if schema.validate(etree.ElementTree(alvo)):
        return []
    return [f"linha {e.line}: {e.message}" for e in schema.error_log]


def _ler_icms(icms: etree._Element | None, item: Item) -> None:
    grupo = _primeiro_filho(icms)
    if grupo is None:
        return
    item.origem = _txt(grupo, "orig")
    item.cst_icms = _txt(grupo, "CST")
    item.csosn = _txt(grupo, "CSOSN")
    situacao = item.cst_icms or item.csosn
    if _txt(grupo, "vBC") is not None or _txt(grupo, "vICMS") is not None:
        item.tributos["ICMS"] = Tributo(
            nome="ICMS",
            cst=situacao,
            base=_dec(grupo, "vBC"),
            aliquota=_dec(grupo, "pICMS"),
            valor=_dec(grupo, "vICMS"),
            reducao_base=_dec(grupo, "pRedBC"),
        )
    if _txt(grupo, "vBCST") is not None or _txt(grupo, "vICMSST") is not None:
        item.tributos["ICMS_ST"] = Tributo(
            nome="ICMS_ST",
            cst=situacao,
            base=_dec(grupo, "vBCST"),
            aliquota=_dec(grupo, "pICMSST"),
            valor=_dec(grupo, "vICMSST"),
            reducao_base=_dec(grupo, "pRedBCST"),
            mva=_dec(grupo, "pMVAST"),
        )
    if _txt(grupo, "vFCP") is not None:
        item.tributos["FCP"] = Tributo(
            nome="FCP",
            cst=situacao,
            base=_dec(grupo, "vBCFCP") or _dec(grupo, "vBC"),
            aliquota=_dec(grupo, "pFCP"),
            valor=_dec(grupo, "vFCP"),
        )


def _ler_ipi(ipi: etree._Element | None, item: Item) -> None:
    if ipi is None:
        return
    trib = ipi.find("IPITrib")
    nt = ipi.find("IPINT")
    grupo = trib if trib is not None else nt
    if grupo is None:
        return
    item.tributos["IPI"] = Tributo(
        nome="IPI",
        cst=_txt(grupo, "CST"),
        base=_dec(grupo, "vBC"),
        aliquota=_dec(grupo, "pIPI"),
        valor=_dec(grupo, "vIPI"),
    )


def _ler_pis_cofins(el: etree._Element | None, nome: str, item: Item) -> None:
    grupo = _primeiro_filho(el)
    if grupo is None:
        return
    item.tributos[nome] = Tributo(
        nome=nome,
        cst=_txt(grupo, "CST"),
        base=_dec(grupo, "vBC"),
        aliquota=_dec(grupo, f"p{nome}"),
        valor=_dec(grupo, f"v{nome}"),
    )


def _ler_ibscbs(el: etree._Element | None, item: Item) -> None:
    """Grupo IBSCBS da Reforma Tributária (NT 2025.002). Leitura tolerante a variações de versão."""
    if el is None:
        return
    item.tem_grupo_ibscbs = True
    item.cst_ibscbs = _txt(el, "CST")
    item.cclasstrib = _txt(el, "cClassTrib")
    g = el.find("gIBSCBS")
    if g is None:
        return
    base = _dec(g, "vBC")
    for nome, caminho, aliq in (
        ("IBS_UF", "gIBSUF", "pIBSUF"),
        ("IBS_MUN", "gIBSMun", "pIBSMun"),
        ("CBS", "gCBS", "pCBS"),
    ):
        sub = g.find(caminho)
        if sub is None:
            continue
        item.tributos[nome] = Tributo(
            nome=nome,
            cst=item.cst_ibscbs,
            base=base,
            aliquota=_dec(sub, aliq),
            valor=_dec(sub, f"v{nome.replace('_UF', 'UF').replace('_MUN', 'Mun')}"),
        )


def _ler_item(det: etree._Element) -> Item:
    prod = det.find("prod")
    imposto = det.find("imposto")
    if prod is None:
        raise ErroLeitura("Item sem grupo <prod>")
    item = Item(
        numero=int(det.get("nItem", "0")),
        codigo=_txt(prod, "cProd") or "",
        descricao=_txt(prod, "xProd") or "",
        ncm=_txt(prod, "NCM") or "",
        cest=_txt(prod, "CEST"),
        cfop=_txt(prod, "CFOP") or "",
        quantidade=_dec0(prod, "qCom"),
        valor_unitario=_dec0(prod, "vUnCom"),
        valor_produto=_dec0(prod, "vProd"),
        valor_desconto=_dec0(prod, "vDesc"),
        valor_frete=_dec0(prod, "vFrete"),
        valor_seguro=_dec0(prod, "vSeg"),
        valor_outros=_dec0(prod, "vOutro"),
        compoe_total=_txt(prod, "indTot") != "0",
    )
    if imposto is not None:
        _ler_icms(imposto.find("ICMS"), item)
        _ler_ipi(imposto.find("IPI"), item)
        _ler_pis_cofins(imposto.find("PIS"), "PIS", item)
        _ler_pis_cofins(imposto.find("COFINS"), "COFINS", item)
        _ler_ibscbs(imposto.find("IBSCBS"), item)
        item.tem_difal = imposto.find("ICMSUFDest") is not None
    return item


def ler_nfe(origem: str | Path | bytes) -> Nota:
    """Lê uma NF-e a partir de um caminho de arquivo ou dos bytes do XML."""
    arquivo: str | None = None
    try:
        if isinstance(origem, bytes):
            raiz = etree.fromstring(origem)
        else:
            arquivo = str(origem)
            raiz = etree.parse(arquivo).getroot()
    except etree.XMLSyntaxError as exc:
        raise ErroLeitura(f"XML malformado: {exc}") from exc

    raiz = _sem_namespace(raiz)
    inf = raiz.find(".//infNFe")
    if inf is None:
        raise ErroLeitura("Grupo <infNFe> não encontrado: o arquivo não parece ser uma NF-e")

    ide = inf.find("ide")
    emit = inf.find("emit")
    dest = inf.find("dest")
    ender_emit = emit.find("enderEmit") if emit is not None else None
    ender_dest = dest.find("enderDest") if dest is not None else None

    chave = inf.get("Id", "")
    chave = chave[3:] if chave.startswith("NFe") else (chave or None)

    totais: dict[str, Decimal] = {}
    icms_tot = inf.find("total/ICMSTot")
    if icms_tot is not None:
        for filho in icms_tot:
            if isinstance(filho.tag, str) and filho.text:
                totais[filho.tag] = Decimal(filho.text.strip())
    ibscbs_tot = inf.find("total/IBSCBSTot")
    if ibscbs_tot is not None:
        for el in ibscbs_tot.iter():
            if isinstance(el.tag, str) and len(el) == 0 and el.text:
                try:
                    totais[f"IBSCBS.{el.tag}"] = Decimal(el.text.strip())
                except InvalidOperation:
                    pass

    return Nota(
        chave=chave,
        numero=_txt(ide, "nNF"),
        serie=_txt(ide, "serie"),
        modelo=_txt(ide, "mod"),
        data_emissao=_data(_txt(ide, "dhEmi")),
        tipo=_txt(ide, "tpNF"),
        destino=_txt(ide, "idDest"),
        consumidor_final=_txt(ide, "indFinal") == "1",
        finalidade=_txt(ide, "finNFe"),
        emitente=Participante(
            cnpj_cpf=_txt(emit, "CNPJ") or _txt(emit, "CPF"),
            nome=_txt(emit, "xNome"),
            uf=_txt(ender_emit, "UF"),
            ie=_txt(emit, "IE"),
            crt=_txt(emit, "CRT"),
        ),
        destinatario=Participante(
            cnpj_cpf=_txt(dest, "CNPJ") or _txt(dest, "CPF") or _txt(dest, "idEstrangeiro"),
            nome=_txt(dest, "xNome"),
            uf=_txt(ender_dest, "UF"),
            ie=_txt(dest, "IE"),
            ind_ie_dest=_txt(dest, "indIEDest"),
        ),
        itens=[_ler_item(det) for det in inf.findall("det")],
        totais=totais,
        arquivo=arquivo,
    )
