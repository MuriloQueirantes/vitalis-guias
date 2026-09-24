# Vitalis · Conferência de guias antes do envio

Prova técnica da Expert Integrado (Consultor de Negócios com IA): as guias de convênio da Clínica Vitalis.

**O problema:** a recepção lança a guia enquanto atende WhatsApp, telefone e balcão. O financeiro confere
no fim do mês, em planilha. O erro só aparece ~60 dias depois, quando o convênio glosa. A Carla não consegue
conferir 900 guias por mês.

**O que foi construído:** uma conferência que roda **antes** do envio, guia por guia, sem depender de alguém
lembrar, e um relatório de terça para o Dr. Renato com quantas guias foram verificadas, quantas têm problema,
de que tipo e quanto dinheiro está em risco.

| O quê | Onde |
|---|---|
| Painel com as 80 guias de agosto | https://vitalis-guias-lyart.vercel.app |
| Conferir guia nova (formulário / CSV) | https://vitalis-guias-lyart.vercel.app/nova |
| Relatório de terça | https://vitalis-guias-lyart.vercel.app/relatorio |
| API (guia em JSON → decisão) | `POST https://vitalis-guias-lyart.vercel.app/api/verificar` |
| MCP | [`mcp_server/server.py`](mcp_server/server.py) |
| Skill | [`skills/conferir-guia/SKILL.md`](skills/conferir-guia/SKILL.md) |
| Motor de regras | [`vitalis/motor.py`](vitalis/motor.py) |
| Testes (gabarito das 80 guias) | [`tests/`](tests/) |

## Resultado no lote de agosto

| | Guias |
|---|---:|
| Verificadas | 80 |
| OK para enviar | 44 |
| Pendente (erro conhecido, correção descrita) | 33 |
| Revisar (uma pessoa precisa decidir) | 3 |
| **Valor em risco** | **R$ 2.642,00 de R$ 5.694,00** |

Problemas por tipo: autorização vencida (13), campo obrigatório faltando (7), sessão acima do limite (6),
procedimento não coberto (5), guia duplicada (2), registro do profissional incompatível (2), procedimento
lançado diferente do realizado (1), paciente optou por particular (1), autorização verbal sem número (1).

## Como funciona

```
 guia nova ──► entrada (formulário / CSV / API JSON / MCP / Skill)
                 │
                 ▼
          vitalis/dados.py       normaliza o que a recepção digitou (data DD/MM, valor com vírgula,
                 │               convênio sem acento). Nunca inventa: o que não dá pra ler vira vazio.
                 ▼
          vitalis/observacao.py  lê o texto livre da recepção e classifica em categorias conhecidas
                 │               (particular, código errado, autorização por telefone, autorização nova,
                 │               remarcação, recado sem impacto). Texto desconhecido → REVISAR.
                 ▼
          vitalis/motor.py       regras do regras_convenio.json + duplicidade contra o que já foi lançado
                 │
                 ▼
    OK / PENDENTE / REVISAR  +  motivo  +  o que corrigir  +  quem corrige  +  prazo de envio
                 │
                 ▼
          vitalis/relatorio.py   relatório de terça (verificadas, problemas por tipo, R$ em risco, lista de ação)
```

**Status**
- **OK**: pode seguir para o convênio.
- **PENDENTE**: o erro é conhecido e a correção está descrita (ex.: autorização vencida → pedir nova e lançar).
- **REVISAR**: precisa de decisão de uma pessoa (ex.: recepção anotou que o procedimento real foi outro).

O motor **aponta**; não altera a guia, não escolhe código, não inventa número de autorização.

### Onde entra IA e onde não entra

- **Regra não é IA.** Validade, campo obrigatório, cobertura, limite de sessões, prazo e duplicidade são
  comparações objetivas. Código determinístico é mais barato, dá sempre a mesma resposta e dá pra explicar
  guia por guia. Não faz sentido perguntar para um LLM se 17/08 vem antes de 21/08.
- **IA entra na borda, onde o texto é bagunçado.** Na Skill, quem opera cola a guia do jeito que a recepção
  escreveu ("fisio dia 20/09, autorizado por telefone, protocolo 88123...") e o Claude transforma isso em
  campos, **sem inventar o que falta**, e chama o MCP. A decisão sempre volta para o mesmo motor.
- **No painel, a observação da recepção é lida por padrões conhecidos**, não por LLM. Com 80 guias os padrões
  são poucos e estáveis; texto novo que o motor não reconhece vai para uma pessoa (REVISAR), em vez de a
  máquina adivinhar. Se o volume de observações novas crescer, o próximo passo é classificar a observação
  com um LLM numa lista fechada de categorias, medindo contra as decisões humanas antes de ligar.

## Por que algumas guias caíram onde caíram

| Guia | Decisão | Por quê |
|---|---|---|
| 0001, 0020 | OK | Validade no mesmo dia do atendimento. A regra diz "até a data de validade, inclusive". |
| 0016, 0027 | OK (aviso) | Data digitada em DD/MM/AAAA. É formato, não erro: normalizo e aviso. |
| 0065 | OK (aviso) | Valor "62,00" com vírgula. Mesmo tratamento. |
| 0009, 0012… | OK | Saúde Interior não exige CID; CID vazio não é problema nesse convênio. |
| 0034 | OK (aviso) | "Sessão remarcada de 12/08, autorização era da data original." A validade (30/08) cobre a data real do atendimento (24/08), que é o que a regra compara. |
| 0005 | OK (aviso) | Sessão 10 de 10 na Vitalcard: passa, mas a próxima exige reavaliação médica e nova autorização. |
| 0027 × 0057, 0059 × 0076 | a 2ª é PENDENTE | Mesmo paciente, data, procedimento, autorização e sessão. A primeira lançada fica como original; a segunda não deve ser enviada. |
| 0030 | PENDENTE | Autorização vencida, mas a recepção anotou que o paciente trouxe uma nova (validade 30/09). A correção é lançar a nova, não pedir outra. |
| 0041 | PENDENTE | Sem número de autorização, mas com protocolo de autorização por telefone. Saúde Interior aceita por até 5 dias úteis, desde que o número seja lançado antes do envio. |
| 0051, 0061 | PENDENTE | Saúde Interior sem número de autorização e **sem** protocolo: campo obrigatório faltando. |
| 0039 | PENDENTE | Paciente pediu para faturar particular. Não enviar ao convênio. |
| 0002, 0024, 0035 | PENDENTE | Consulta no Plano Bem, que não cobre consulta ("faturada como particular"). |
| 0006, 0007 | PENDENTE | Infiltração na Vitalcard, que não cobre infiltração. A 0006 também está na sessão 15 de 10. |
| 0069 | REVISAR | Lançada como consulta ortopédica, mas a recepção anotou que foi drenagem linfática. Drenagem não está na tabela: alguém precisa confirmar o que foi feito. |
| 0045, 0074 | REVISAR | "Reavaliação fisioterapêutica" lançada com profissional de CRM. Pelo dicionário, fisioterapia é CREFITO. Pode ser erro de profissional ou de procedimento; uma pessoa decide. |

Esclarecimentos da prova aplicados: validade só contra a data do atendimento (não há data de concessão);
conferência simulada na data de lançamento; prazo de envio contado da data do atendimento; confiro o que a
guia declara, sem supor histórico de autorizações fora do recorte.

## Rodar local

Requer Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn app:app --reload        # painel em http://localhost:8000
uv run pytest -q                       # 100 testes
```

## MCP: instalação

Ferramentas: `consultar_regra(convenio, procedimento?)`, `verificar_guia(guia? | id_guia?)`,
`listar_convenios()`, `relatorio_lote()`. Fonte: `data/regras_convenio.json` e `data/guias.csv`, lidos direto.

```bash
git clone <este repositório> && cd vitalis-guias && uv sync

# Claude Code
claude mcp add vitalis-guias -- uv run --directory "$(pwd)" python mcp_server/server.py
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "vitalis-guias": {
      "command": "uv",
      "args": ["run", "--directory", "/caminho/para/vitalis-guias", "python", "mcp_server/server.py"]
    }
  }
}
```

Teste sem cliente: `uv run python scripts/testar_mcp.py` (sobe o servidor via stdio, lista as ferramentas e chama duas).

## Skill: instalação

A Skill está em [`skills/conferir-guia/SKILL.md`](skills/conferir-guia/SKILL.md) e usa o MCP acima.

```bash
# Claude Code (projeto): copie a pasta para .claude/skills/
mkdir -p .claude/skills && cp -r skills/conferir-guia .claude/skills/
```

No Claude.ai/Desktop: compacte a pasta `conferir-guia` em .zip e envie em Configurações → Capacidades → Skills.
Depois é só colar a guia: "confere essa guia: G-2609-0107 Norte 18/09 P-1026 plano bem ...".

## Como fiz

**Tempo:** ~4 horas, somando construção, revisão e vídeo.

**Ferramentas e por quê**
- **Python.** Dá pra ler do começo ao fim, e datas e CSV já vêm na biblioteca padrão.
- **FastAPI**, publicado na **Vercel** (plano gratuito). Painel, formulário e API no mesmo app, sem servidor para manter e sem custo.
- **SDK oficial de MCP para Python** (`mcp` 2.x, `MCPServer`), via stdio. Roda local no Claude Code ou no Claude Desktop, lendo os arquivos da prova direto.
- **Skill** em `SKILL.md`, o formato padrão de Skills do Claude.
- **pytest** para os testes.
- **Claude Code** como par de programação.
- **Sem banco e sem chave de API.** Nada no repositório precisa de segredo.

**O que a IA gerou e o que eu decidi.** O código foi escrito com o Claude Code a partir das minhas instruções: estrutura, HTML do painel, servidor MCP e testes. Eu revisei e assumi as decisões abaixo:

1. **Regra no núcleo, IA na borda.** Nenhum LLM decide status de guia. As regras do convênio são código determinístico e testado. A IA entra onde o texto é bagunçado (a Skill), e a decisão volta sempre para o mesmo motor. Um motivo é o custo: 900 guias por mês não precisam de um modelo decidindo o que uma comparação de datas resolve. O outro é explicar ao Dr. Renato por que cada guia caiu onde caiu.
2. **Três status em vez de "certo/errado".** PENDENTE quando sei o que corrigir; REVISAR quando uma pessoa precisa decidir. Cada problema diz quem corrige (recepção, financeiro ou profissional). Assim a lista de ação sai pronta para distribuir, e o relatório mostra onde está o gargalo.
3. **Formato não é erro.** Data em DD/MM/AAAA e valor com vírgula são normalizados e viram só aviso. Se a ferramenta acusar o que não é problema, a recepção para de confiar nela. Foi o que aconteceu com o robô de 2024.
4. **Na dúvida, não assume.** Observação que o motor não reconhece e casos fora da regra (reavaliação fisioterapêutica lançada com CRM, procedimento real que não está na tabela) vão para REVISAR, não para OK nem para PENDENTE.
5. **A autorização verbal da Saúde Interior não é "campo faltando".** Com protocolo e dentro de 5 dias úteis, é PENDENTE com data-limite para lançar o número. Sem protocolo, é campo obrigatório faltando.
6. **Duplicidade: a primeira guia lançada é a original.** Só a segunda é barrada. Senão as duas deixariam de ser enviadas e o atendimento não seria cobrado.
7. **O motor aprende com o que cai em REVISAR.** No teste da Skill, a frase "paciente disse que vai pagar do bolso" caiu em REVISAR, porque o motor não conhecia essa expressão. Era o comportamento certo. Confirmado que significa particular, eu mesmo acrescentei o padrão `do bolso` em `vitalis/observacao.py` e escrevi o teste. O ciclo é esse: REVISAR → uma pessoa confirma → vira regra com teste.

**O que ficou de fora e por quê**
- **Integração real com o sistema de gestão.** Não temos acesso à API dele. Em produção, a entrada seria um gatilho (webhook ou uma leitura a cada X minutos) chamando a mesma função que hoje atende `POST /api/verificar`.
- **Banco e histórico semanal.** O painel não guarda as guias novas; o relatório é do lote. Em produção entraria um Postgres, para acompanhar semana a semana e medir quantas guias foram barradas antes do envio versus a glosa que volta 60 dias depois.
- **Login no painel.** Os dados são fictícios. Com dado real de paciente, o painel não fica aberto.
- **Feriados na conta de dias úteis.** Falta o calendário da cidade; hoje conta só segunda a sexta.
- **LLM classificando a observação no painel.** Com poucos padrões, regra resolve e é auditável. Vira o próximo passo se aparecerem muitas observações novas, e só depois de medir contra as decisões humanas.

**Como testei**
- Conferi as 80 guias à mão contra `regras_convenio.json` e escrevi o gabarito de cada uma em `tests/test_motor.py`. O motor bate com o gabarito nas 80.
- Criei casos de guia nova que tentam quebrar a conferência: guia vazia, data "ontem", valor "abc", convênio sem acento, observação desconhecida, prazo de envio vencido, autorização verbal fora dos 5 dias úteis, duplicata de guia de agosto.
- Testei as rotas do painel e da API (inclusive JSON inválido e CSV vazio) e as ferramentas do MCP. São 100 testes: `uv run pytest -q`.
- Testei o MCP pelo protocolo de verdade (`scripts/testar_mcp.py`) e depois o painel publicado, com uma chamada em cada rota.
- Testei a Skill de ponta a ponta no Claude Code, colando guias no formato de WhatsApp. Esse teste achou um falso positivo: a descrição abreviada ("fisio musculoesquelética") era acusada como erro. Corrigi: agora só é problema quando a descrição aponta para **outro** procedimento da tabela.

**Dúvidas em aberto: como interpretei (e o que eu confirmaria com a clínica)**
- G-0045 e G-0074: quem fez a "reavaliação fisioterapêutica" lançada com o Dr. Otávio (CRM)? Era para ser consulta ou reavaliação com fisioterapeuta?
- G-0034: o convênio vincula a autorização à data agendada, ou só a validade conta?
- Os 5 dias úteis da autorização verbal contam do atendimento ou do protocolo?
- Drenagem linfática (G-0069): a clínica fatura por algum convênio? Não está na tabela.
