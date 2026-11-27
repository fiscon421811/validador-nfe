# Base de regras

Cada arquivo `.csv` (separador `;`, linhas iniciadas por `#` são comentários) é carregado pelo validador.

| Coluna | Uso |
| --- | --- |
| id | identificador único da regra |
| tributo | ICMS, IPI, PIS, COFINS, CBS, IBS_UF, IBS_MUN |
| vigencia_inicio / vigencia_fim | período em que a regra vale (fim vazio = aberta), comparado com a data de emissão |
| uf_origem, uf_destino, origem_mercadoria, tipo_destinatario, regime, cfop, ncm, cest | chaves de busca; vazio = qualquer; alternativas com `\|`; `ncm` e `cfop` casam por prefixo |
| cst | CST(s) a que a regra se aplica (PIS/COFINS, IBS/CBS) |
| aliquota, reducao_base, mva | resultado esperado, em % |
| fundamento | obrigatório: base legal da regra |
| observacao | livre |

Entre várias regras que casam, vence a mais específica (CEST > NCM mais longo > origem > destino...).
Regras sem NCM/CEST são **genéricas**: divergência contra elas sai como alerta, porque pode haver exceção
ainda não cadastrada. Divergência contra regra com NCM/CEST sai como erro.

**Status:** todas as regras foram escritas a partir de legislação conhecida em 2026-11 e precisam de
revisão de um profissional antes do uso em produção.

IPI: exporte a TIPI oficial para um CSV `ncm;aliquota` (use `NT` para não tributado) e passe com `--tipi`.
