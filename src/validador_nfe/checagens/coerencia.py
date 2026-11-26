"""Checagens de coerência entre campos: CST × CRT, CFOP × destino, ST, IBS/CBS."""

from __future__ import annotations

import re
from decimal import Decimal

from validador_nfe import parametros as p
from validador_nfe.divergencia import Divergencia, Severidade
from validador_nfe.modelo import Item, Nota

_ZERO = Decimal("0")


def _d(codigo, severidade, mensagem, item=None, **extra) -> Divergencia:
    return Divergencia(codigo=codigo, severidade=severidade, mensagem=mensagem, item=item, **extra)


def _checar_crt(nota: Nota, item: Item) -> list[Divergencia]:
    crt = nota.emitente.crt
    if crt is None:
        return []
    if crt in p.CRT_USA_CSOSN and item.cst_icms and not item.csosn:
        return [_d("C001", Severidade.ERRO, "Emitente do Simples Nacional (CRT 1 ou 4) informou CST em vez de CSOSN",
                   item.numero, campo="ICMS/CST", esperado="CSOSN", encontrado=f"CST {item.cst_icms}",
                   fundamento="MOC da NF-e, rejeição 590")]
    if crt not in p.CRT_USA_CSOSN and item.csosn and not item.cst_icms:
        return [_d("C001", Severidade.ERRO, f"Emitente com CRT {crt} informou CSOSN em vez de CST",
                   item.numero, campo="ICMS/CSOSN", esperado="CST", encontrado=f"CSOSN {item.csosn}",
                   fundamento="MOC da NF-e, rejeição 591")]
    return []


_DIGITO_CFOP_SAIDA = {"1": "5", "2": "6", "3": "7"}
_DIGITO_CFOP_ENTRADA = {"1": "1", "2": "2", "3": "3"}
_NOME_DESTINO = {"1": "interna", "2": "interestadual", "3": "com o exterior"}


def _checar_cfop(nota: Nota, item: Item) -> list[Divergencia]:
    saida = []
    cfop = item.cfop
    if not re.fullmatch(r"[1-7]\d{3}", cfop or ""):
        return [_d("C002", Severidade.ERRO, "CFOP com formato inválido", item.numero,
                   campo="CFOP", encontrado=cfop)]
    if nota.tipo == "1" and cfop[0] not in "567":
        saida.append(_d("C002", Severidade.ERRO, "Nota de saída com CFOP de entrada", item.numero,
                        campo="CFOP", esperado="5xxx, 6xxx ou 7xxx", encontrado=cfop))
    if nota.tipo == "0" and cfop[0] not in "123":
        saida.append(_d("C002", Severidade.ERRO, "Nota de entrada com CFOP de saída", item.numero,
                        campo="CFOP", esperado="1xxx, 2xxx ou 3xxx", encontrado=cfop))
    mapa = _DIGITO_CFOP_SAIDA if nota.tipo == "1" else _DIGITO_CFOP_ENTRADA
    esperado = mapa.get(nota.destino or "")
    if esperado and cfop[0] in "123567" and cfop[0] != esperado:
        saida.append(_d("C003", Severidade.ERRO,
                        f"CFOP incompatível com operação {_NOME_DESTINO[nota.destino]} (idDest {nota.destino})",
                        item.numero, campo="CFOP", esperado=f"{esperado}xxx", encontrado=cfop,
                        fundamento="MOC da NF-e, rejeições 518 a 523"))
    return saida


def _checar_destino(nota: Nota) -> list[Divergencia]:
    uf_e, uf_d = nota.emitente.uf, nota.destinatario.uf
    if not uf_e or not uf_d or uf_d == "EX":
        return []
    if nota.destino == "1" and uf_e != uf_d:
        return [_d("C004", Severidade.ERRO, "Operação marcada como interna, mas as UFs são diferentes",
                   campo="idDest", esperado="2", encontrado="1")]
    if nota.destino == "2" and uf_e == uf_d:
        return [_d("C004", Severidade.ERRO, "Operação marcada como interestadual, mas as UFs são iguais",
                   campo="idDest", esperado="1", encontrado="2")]
    return []


def _checar_ncm(item: Item) -> list[Divergencia]:
    if re.fullmatch(r"\d{8}", item.ncm) or item.ncm == "00":
        return []
    return [_d("C005", Severidade.ERRO, "NCM deve ter 8 dígitos", item.numero, campo="NCM", encontrado=item.ncm)]


def _checar_st(item: Item) -> list[Divergencia]:
    saida = []
    st = item.tributo("ICMS_ST")
    valor_st = st.valor if st and st.valor is not None else _ZERO
    situacao = item.cst_icms or item.csosn
    if situacao in p.CST_COM_ST | p.CSOSN_COM_ST and valor_st <= _ZERO:
        saida.append(_d("C006", Severidade.ERRO, f"CST/CSOSN {situacao} exige ICMS-ST retido, mas vICMSST está zerado",
                        item.numero, campo="vICMSST", esperado="> 0", encontrado=str(valor_st)))
    if situacao in p.CST_ST_ANTERIOR | p.CSOSN_ST_ANTERIOR and valor_st > _ZERO:
        saida.append(_d("C006", Severidade.ERRO, f"CST/CSOSN {situacao} indica ST já recolhida, mas há novo destaque de ST",
                        item.numero, campo="vICMSST", esperado="0", encontrado=str(valor_st)))
    if item.cest is None and situacao in p.CST_COM_ST | p.CST_ST_ANTERIOR | p.CSOSN_COM_ST | p.CSOSN_ST_ANTERIOR:
        saida.append(_d("C007", Severidade.ALERTA, "Item com ST sem CEST informado", item.numero, campo="CEST",
                        fundamento="Convênio ICMS 142/2018"))
    return saida


def _checar_cst_icms(nota: Nota, item: Item) -> list[Divergencia]:
    saida = []
    icms = item.tributo("ICMS")
    cst = item.cst_icms
    if cst is None:
        return []
    valor = icms.valor if icms and icms.valor is not None else _ZERO
    if cst in p.CST_TRIBUTADO_INTEGRAL:
        if valor <= _ZERO:
            saida.append(_d("C008", Severidade.ERRO, "CST 00 (tributada integralmente) sem ICMS destacado",
                            item.numero, campo="vICMS", esperado="> 0", encontrado=str(valor)))
        if icms and icms.reducao_base:
            saida.append(_d("C008", Severidade.ERRO, "CST 00 com redução de base informada; o CST correto seria 20",
                            item.numero, campo="CST", esperado="20", encontrado="00"))
    if cst in p.CST_COM_REDUCAO and not (icms and icms.reducao_base):
        saida.append(_d("C008", Severidade.ALERTA, f"CST {cst} indica redução de base, mas pRedBC não foi informado",
                        item.numero, campo="pRedBC"))
    if cst in p.CST_SEM_ICMS and valor > _ZERO:
        saida.append(_d("C008", Severidade.ERRO, f"CST {cst} (isenta, não tributada ou suspensa) com ICMS destacado",
                        item.numero, campo="vICMS", esperado="0", encontrado=str(valor)))
    if (nota.destino == "2" and icms and icms.aliquota and icms.aliquota > _ZERO
            and icms.aliquota not in p.ALIQUOTAS_INTERESTADUAIS):
        saida.append(_d("C009", Severidade.ALERTA,
                        "Alíquota de ICMS em operação interestadual diferente de 4%, 7% ou 12%",
                        item.numero, campo="pICMS", esperado="4, 7 ou 12", encontrado=str(icms.aliquota),
                        fundamento="Resoluções do Senado 22/1989 e 13/2012"))
    return saida


def _checar_difal(nota: Nota, item: Item) -> list[Divergencia]:
    if (nota.tipo == "1" and nota.destino == "2" and nota.consumidor_final
            and nota.destinatario.ind_ie_dest == "9" and not item.tem_difal):
        return [_d("C010", Severidade.ALERTA,
                   "Venda interestadual a não contribuinte sem grupo de DIFAL (ICMSUFDest)", item.numero,
                   campo="ICMSUFDest", fundamento="EC 87/2015 e LC 190/2022")]
    return []


def _checar_pis_cofins(item: Item) -> list[Divergencia]:
    pis, cofins = item.tributo("PIS"), item.tributo("COFINS")
    if pis and cofins and pis.cst and cofins.cst and pis.cst != cofins.cst:
        return [_d("C011", Severidade.ALERTA, "CST de PIS e de COFINS diferentes no mesmo item", item.numero,
                   campo="PIS/COFINS CST", esperado=pis.cst, encontrado=cofins.cst)]
    return []


def _checar_ibscbs(nota: Nota, item: Item) -> list[Divergencia]:
    saida = []
    emissao = nota.data_emissao.date() if nota.data_emissao else None
    if emissao is None or emissao < p.INICIO_IBSCBS:
        return []
    regime_normal = nota.emitente.crt not in p.CRT_USA_CSOSN
    if not item.tem_grupo_ibscbs:
        if regime_normal:
            saida.append(_d("C012", Severidade.ALERTA, "Nota emitida a partir de 2026 sem grupo IBSCBS no item",
                            item.numero, campo="IBSCBS", fundamento="LC 214/2025 e NT 2025.002"))
        return saida
    cst, ccl = item.cst_ibscbs or "", item.cclasstrib or ""
    if not re.fullmatch(r"\d{3}", cst):
        saida.append(_d("C013", Severidade.ERRO, "CST do IBS/CBS deve ter 3 dígitos", item.numero,
                        campo="IBSCBS/CST", encontrado=cst or "(vazio)"))
    if not re.fullmatch(r"\d{6}", ccl):
        saida.append(_d("C013", Severidade.ERRO, "cClassTrib deve ter 6 dígitos", item.numero,
                        campo="IBSCBS/cClassTrib", encontrado=ccl or "(vazio)"))
    elif cst and not ccl.startswith(cst):
        saida.append(_d("C014", Severidade.ALERTA, "cClassTrib não pertence ao CST informado (os 3 primeiros dígitos diferem)",
                        item.numero, campo="IBSCBS/cClassTrib", esperado=f"{cst}xxx", encontrado=ccl))
    if emissao.year == 2026 and cst == "000":
        for nome, aliq_teste in p.ALIQUOTAS_TESTE_2026.items():
            trib = item.tributo(nome)
            if trib is None or trib.aliquota is None:
                continue
            if trib.aliquota != aliq_teste:
                saida.append(_d("C015", Severidade.ALERTA, f"{nome}: alíquota diferente da alíquota de teste de 2026",
                                item.numero, campo=f"p{nome}", esperado=str(aliq_teste),
                                encontrado=str(trib.aliquota), fundamento=p.FUNDAMENTO_TESTE_2026))
    return saida


def checar_coerencia(nota: Nota) -> list[Divergencia]:
    saida = _checar_destino(nota)
    for item in nota.itens:
        saida += _checar_crt(nota, item)
        saida += _checar_cfop(nota, item)
        saida += _checar_ncm(item)
        saida += _checar_cst_icms(nota, item)
        saida += _checar_st(item)
        saida += _checar_difal(nota, item)
        saida += _checar_pis_cofins(item)
        saida += _checar_ibscbs(nota, item)
    return saida
