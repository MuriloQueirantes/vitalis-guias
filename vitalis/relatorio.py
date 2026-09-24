"""Relatório de terça do Dr. Renato: poucos números, e o que fazer com eles."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from .motor import Decisao


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def resumo(decisoes: list[Decisao]) -> dict:
    total = len(decisoes)
    com_problema = [d for d in decisoes if d.status != "OK"]
    valor_total = sum(d.valor for d in decisoes)
    valor_risco = sum(d.valor for d in com_problema)

    por_tipo: dict[str, dict] = defaultdict(lambda: {"guias": 0, "valor": 0.0})
    for d in com_problema:
        for tipo in {a.tipo for a in d.problemas}:  # uma guia conta uma vez por tipo
            por_tipo[tipo]["guias"] += 1
            por_tipo[tipo]["valor"] += d.valor

    def agrupar(chave):
        out: dict[str, dict] = defaultdict(lambda: {"guias": 0, "com_problema": 0, "valor_risco": 0.0})
        for d in decisoes:
            k = getattr(d, chave) or "?"
            out[k]["guias"] += 1
            if d.status != "OK":
                out[k]["com_problema"] += 1
                out[k]["valor_risco"] += d.valor
        return dict(sorted(out.items()))

    por_responsavel = Counter()
    for d in com_problema:
        for resp in {a.responsavel for a in d.problemas}:
            por_responsavel[resp] += 1

    return {
        "verificadas": total,
        "ok": sum(d.status == "OK" for d in decisoes),
        "pendentes": sum(d.status == "PENDENTE" for d in decisoes),
        "revisar": sum(d.status == "REVISAR" for d in decisoes),
        "com_problema": len(com_problema),
        "valor_total": round(valor_total, 2),
        "valor_risco": round(valor_risco, 2),
        "por_tipo": dict(sorted(por_tipo.items(), key=lambda kv: -kv[1]["valor"])),
        "por_unidade": agrupar("unidade"),
        "por_convenio": agrupar("convenio"),
        "por_responsavel": dict(por_responsavel.most_common()),
    }


def relatorio_markdown(decisoes: list[Decisao], titulo: str = "Lote de agosto/2026", guias_mes: int = 900) -> str:
    r = resumo(decisoes)
    n = r["verificadas"] or 1
    pct = r["com_problema"] / n
    linhas = [
        f"# Conferência de guias antes do envio — {titulo}",
        f"_Gerado em {date.today().strftime('%d/%m/%Y')} pela conferência automática._",
        "",
        "## Em uma linha",
        f"De **{r['verificadas']} guias verificadas**, **{r['com_problema']} ({pct:.0%}) não podem ser enviadas como estão**. "
        f"Isso é **{_brl(r['valor_risco'])}** de {_brl(r['valor_total'])} lançados ({r['valor_risco'] / (r['valor_total'] or 1):.0%}) "
        "em guias que não deveriam sair como estão (glosa, recusa ou cobrança indevida).",
        "",
        "| | Guias | |",
        "|---|---:|---|",
        f"| OK para enviar | {r['ok']} | segue |",
        f"| Pendente | {r['pendentes']} | erro conhecido, a correção está descrita |",
        f"| Revisar | {r['revisar']} | precisa de decisão de uma pessoa |",
        "",
        "## De que tipo são os problemas",
        "| Tipo | Guias | Valor em risco |",
        "|---|---:|---:|",
    ]
    for tipo, v in r["por_tipo"].items():
        linhas.append(f"| {tipo} | {v['guias']} | {_brl(v['valor'])} |")
    linhas += [
        "",
        "_Uma guia pode ter mais de um problema; por isso a soma por tipo passa do total._",
        "",
        "## Onde",
        "| Unidade | Guias | Com problema | Valor em risco |",
        "|---|---:|---:|---:|",
    ]
    for k, v in r["por_unidade"].items():
        linhas.append(f"| {k} | {v['guias']} | {v['com_problema']} | {_brl(v['valor_risco'])} |")
    linhas += ["", "| Convênio | Guias | Com problema | Valor em risco |", "|---|---:|---:|---:|"]
    for k, v in r["por_convenio"].items():
        linhas.append(f"| {k} | {v['guias']} | {v['com_problema']} | {_brl(v['valor_risco'])} |")

    linhas += ["", "## Quem precisa agir", "| Responsável | Guias |", "|---|---:|"]
    for k, v in r["por_responsavel"].items():
        linhas.append(f"| {k} | {v} |")

    linhas += ["", "## Lista de ação", "| Guia | Unidade | Status | Problema | O que fazer | Quem |", "|---|---|---|---|---|---|"]
    ordem = {"REVISAR": 0, "PENDENTE": 1}
    for d in sorted([d for d in decisoes if d.status != "OK"], key=lambda d: (ordem[d.status], d.id_guia)):
        for a in d.problemas:
            linhas.append(f"| {d.id_guia} | {d.unidade} | {d.status} | {a.tipo} | {a.corrigir} | {a.responsavel} |")

    if guias_mes:
        media = r["valor_risco"] / (r["com_problema"] or 1)
        linhas += [
            "",
            "## Leitura para o mês (estimativa)",
            f"Se o recorte de agosto representar o mês, das ~{guias_mes} guias cerca de **{pct * guias_mes:.0f}** sairiam com erro, "
            f"algo como **{_brl(pct * guias_mes * media)}/mês** em guias que hoje só descobrimos ~60 dias depois, na glosa. "
            "É premissa, não medida: o recorte é pequeno e o valor por guia do recorte é o de uma sessão.",
        ]
    return "\n".join(linhas)
