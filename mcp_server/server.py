"""MCP da conferência de guias da Clínica Vitalis.

Ferramentas:
  consultar_regra   -> o que um convênio exige e se cobre um procedimento
  verificar_guia    -> decisão (OK / PENDENTE / REVISAR), motivo e o que corrigir
  listar_convenios  -> convênios e procedimentos cadastrados
  relatorio_lote    -> relatório de terça do lote de agosto

Fonte dos dados: data/regras_convenio.json e data/guias.csv (lidos direto do repositório).
O MCP usa o mesmo motor do painel web (pacote vitalis), então a decisão é a mesma nos dois.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from vitalis.dados import achar_convenio, achar_procedimento, carregar_guias, carregar_regras  # noqa: E402
from vitalis.motor import verificar_guia as motor_verificar  # noqa: E402
from vitalis.motor import verificar_lote  # noqa: E402
from vitalis.relatorio import relatorio_markdown  # noqa: E402

REGRAS = carregar_regras()
GUIAS = carregar_guias()

mcp = MCPServer("vitalis-guias")


@mcp.tool()
def consultar_regra(convenio: str, procedimento: str = "") -> dict:
    """Consulta a regra de um convênio (Vitalcard, Saúde Interior, Plano Bem).

    Args:
        convenio: nome do convênio (acento e maiúscula não importam).
        procedimento: opcional. Código (ex.: 50000470) ou descrição exata do procedimento.
            Se informado, a resposta diz se o convênio cobre e qual o valor de referência.
    """
    conv = achar_convenio(convenio, REGRAS)
    if not conv:
        return {"erro": f"Convênio '{convenio}' não cadastrado.",
                "convenios_cadastrados": [c["nome"] for c in REGRAS["convenios"]]}
    resposta = {
        "convenio": conv["nome"],
        "campos_obrigatorios": conv["campos_obrigatorios"],
        "validade_maxima_autorizacao_dias": conv["validade_maxima_autorizacao_dias"],
        "limite_sessoes_por_autorizacao": conv["limite_sessoes_por_autorizacao"],
        "prazo_envio_dias": conv["prazo_envio_dias"],
        "observacao": conv.get("observacao", ""),
        "definicoes": REGRAS.get("definicoes", {}),
    }
    if procedimento:
        proc = achar_procedimento(procedimento, REGRAS)
        if not proc:
            resposta["procedimento"] = {"erro": f"Procedimento '{procedimento}' não está na tabela.",
                                        "tabela": REGRAS["procedimentos"]}
        else:
            resposta["procedimento"] = {
                "codigo": proc["codigo"],
                "descricao": proc["descricao"],
                "valor_referencia": proc["valor_referencia"],
                "coberto": proc["codigo"] in conv["procedimentos_cobertos"],
            }
    else:
        resposta["procedimentos_cobertos"] = [
            p for p in REGRAS["procedimentos"] if p["codigo"] in conv["procedimentos_cobertos"]
        ]
    return resposta


@mcp.tool()
def verificar_guia(guia: dict | None = None, id_guia: str = "") -> dict:
    """Confere uma guia antes do envio ao convênio e devolve a decisão com motivo e correção.

    Passe OU o id de uma guia do lote de agosto (ex.: G-2608-0030), OU a guia como objeto com
    os campos que tiver: id_guia, unidade, data_atendimento, paciente, convenio, carteirinha, cid,
    procedimento_codigo, procedimento_descricao, numero_autorizacao, autorizacao_validade,
    autorizacao_sessoes_limite, sessao_numero_na_autorizacao, profissional, profissional_registro,
    valor, observacao_recepcao, data_lancamento.

    Campo desconhecido deve ficar vazio, nunca inventado: campo vazio é conferido como ausente.
    Status: OK (pode enviar), PENDENTE (erro conhecido, corrigir antes), REVISAR (uma pessoa decide).
    """
    if id_guia and not guia:
        achada = next((g for g in GUIAS if g["id_guia"].upper() == id_guia.strip().upper()), None)
        if not achada:
            return {"erro": f"Guia {id_guia} não encontrada no lote de agosto."}
        decisoes = verificar_lote(GUIAS, REGRAS)  # duplicidade depende da ordem do lote
        d = next(x for x in decisoes if x.id_guia == achada["id_guia"])
        return {"guia": achada, **d.to_dict()}
    if not guia:
        return {"erro": "Informe 'guia' (objeto com os campos) ou 'id_guia'."}
    d = motor_verificar(guia, REGRAS, base=GUIAS)
    return d.to_dict()


@mcp.tool()
def listar_convenios() -> dict:
    """Lista convênios cadastrados e a tabela de procedimentos (código, descrição, valor)."""
    return {"convenios": [c["nome"] for c in REGRAS["convenios"]], "procedimentos": REGRAS["procedimentos"],
            "versao_regras": REGRAS.get("versao")}


@mcp.tool()
def relatorio_lote() -> str:
    """Relatório de terça (markdown) das 80 guias de agosto: verificadas, problemas por tipo e valor em risco."""
    return relatorio_markdown(verificar_lote(GUIAS, REGRAS))


if __name__ == "__main__":
    mcp.run()
