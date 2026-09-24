---
name: conferir-guia
description: Confere uma guia de convênio da Clínica Vitalis antes do envio. Use quando alguém da recepção, do financeiro ou a Carla colar os dados de uma guia (do jeito que a recepção escreveu, em qualquer formato) e quiser saber se está OK ou pendente, o motivo e o que corrigir. Usa o MCP vitalis-guias.
---

# Conferir guia de convênio (Clínica Vitalis)

Quem usa: recepção, financeiro e Carla, no dia a dia, antes de a guia ir para o convênio.
Quem decide: o MCP `vitalis-guias` (ferramenta `verificar_guia`), com regras fixas por convênio.
Seu papel: ler o texto como a pessoa colou, montar a guia sem inventar nada, chamar o MCP e
explicar a resposta em português simples.

## Passo a passo

1. **Leia o que foi colado.** Pode vir como linha de CSV, lista de campos, mensagem de WhatsApp ou
   texto corrido ("paciente P-1044, Plano Bem, consulta orto dia 06/08, aut AUT320436 até 23/08...").
   Se forem várias guias, trate uma por vez.

2. **Monte o objeto da guia** com estes campos (use só os que aparecerem no texto):
   `id_guia, unidade, data_atendimento, paciente, convenio, carteirinha, cid, procedimento_codigo,
   procedimento_descricao, numero_autorizacao, autorizacao_validade, autorizacao_sessoes_limite,
   sessao_numero_na_autorizacao, profissional, profissional_registro, valor, observacao_recepcao,
   data_lancamento`.
   - Datas: converta para AAAA-MM-DD. Se o ano não vier, use o ano corrente e diga que assumiu.
   - Procedimento: se vier só o nome ("fisio", "consulta orto", "infiltração"), chame
     `listar_convenios` e use o código cuja descrição corresponde. Se houver dúvida entre dois
     códigos, **pergunte** em vez de escolher.
   - Qualquer recado da recepção (atraso, particular, autorização por telefone, código errado...)
     vai inteiro em `observacao_recepcao`, com as palavras dela. O motor lê esse campo.
   - Campo que não apareceu fica **vazio**. Nunca complete número de autorização, CID, carteirinha,
     registro ou validade por conta própria. Campo vazio é o motor que decide se é problema.

3. **Chame `verificar_guia`** passando `guia` com o objeto montado. Se a pessoa só citar o número de
   uma guia do lote de agosto (ex.: "G-2608-0030"), passe `id_guia`.

4. **Se a pessoa perguntar por que** ou quiser saber a regra, chame `consultar_regra` com o convênio e
   o procedimento e cite a regra.

5. **Responda neste formato**, curto, sem jargão técnico:

```
Guia <id ou "sem id"> — <✅ OK | ⚠️ PENDENTE | 🔎 REVISAR>

Motivo: <o que o motor encontrou, em uma frase por problema>
O que corrigir: <a ação, por problema>
Quem corrige: <Recepção | Financeiro | Profissional que atendeu>
Prazo de envio ao convênio: <data_limite_envio, se veio>
<Se você assumiu algo ao montar a guia (ex.: ano da data), diga aqui.>
```

## Regras que você não quebra

- A decisão é a do MCP. Não troque PENDENTE por OK nem "alivie" um problema.
- Não diga "pode enviar" se o status não for OK.
- Não altere a guia nem sugira código de procedimento ou número de autorização que não veio da pessoa.
- REVISAR significa que uma pessoa precisa decidir. Diga quem e sobre o quê; não decida no lugar dela.
- Se o MCP não responder, diga que a conferência não rodou. Não confira "de cabeça".

## Exemplos

**Entrada colada:**
> G-2609-0107 Norte 18/09 P-1026 plano bem cart 728909716 cid M79.7 fisio musculoesq 50000470
> aut AUT222999 validade 04/09 limite 12 sessão 3 Elaine Moura CREFITO-3 133455-F 62,00

**Resposta esperada:**
```
Guia G-2609-0107 — ⚠️ PENDENTE

Motivo: a autorização venceu em 04/09/2026 e o atendimento foi em 18/09/2026.
O que corrigir: pedir nova autorização ao Plano Bem e lançar o número antes do envio.
Quem corrige: Recepção
Prazo de envio ao convênio: 18/10/2026
Assumi o ano de 2026 para as datas.
```

**Entrada colada:**
> paciente P-1041, saude interior, fisio dia 20/09, autorizado por telefone protocolo 88123 aguardando número, sessão 4 de 20, Heitor Salles CREFITO-3 156740-F, carteirinha 877857320

**Resposta esperada:**
```
Guia sem id — ⚠️ PENDENTE

Motivo: autorização por telefone (protocolo 88123) ainda sem número. A Saúde Interior aceita isso por
até 5 dias úteis. A validade da autorização também não foi informada.
O que corrigir: lançar o número da autorização até 25/09/2026 (e antes do envio) e preencher a validade.
Quem corrige: Recepção
Prazo de envio ao convênio: 04/11/2026
Assumi o ano de 2026 para a data.
```
