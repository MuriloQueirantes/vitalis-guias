"""Leitura da observação livre que a recepção escreveu.

Decisão de projeto: a observação é classificada por padrões conhecidos, não por LLM.
- O que já sabemos que muda a guia (particular, código errado, autorização por telefone,
  autorização nova ainda não lançada, remarcação) vira uma categoria com regra.
- O que já sabemos que é só recado (atraso, recibo, exame, confirmação) é ignorado.
- Qualquer outro texto vira "NAO_RECONHECIDA": a guia vai pra um humano ler.
  Na dúvida, não assume.

A leitura de texto bagunçado com IA acontece na Skill (quem opera cola a guia e o
Claude interpreta), mas a decisão sempre volta pra este motor via MCP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .dados import sem_acento

# Ordem importa: a primeira categoria que casar vence.
PADROES: list[tuple[str, list[str]]] = [
    ("FATURAR_PARTICULAR", [r"particular", r"nao quer usar o convenio", r"sem convenio", r"do bolso"]),
    ("CODIGO_DIVERGENTE", [r"procedimento realizado foi", r"codigo certo", r"codigo errado", r"lancar o codigo"]),
    ("AUTORIZACAO_VERBAL", [r"por telefone", r"verbal", r"protocolo"]),
    ("AUTORIZACAO_NOVA_NAO_LANCADA", [r"autorizacao nova", r"nova autorizacao", r"numero ainda nao lancado"]),
    ("REMARCACAO", [r"remarcad"]),
    ("SEM_IMPACTO", [
        r"chegou .*atrasad", r"atrasad", r"recibo", r"reembolso", r"exame", r"prontuario",
        r"confirmad[oa]", r"whats", r"^ok\.?$",
    ]),
]


@dataclass
class LeituraObservacao:
    categoria: str          # VAZIA, SEM_IMPACTO, NAO_RECONHECIDA ou uma das categorias acima
    texto: str
    protocolo: str | None = None
    validade_citada: str | None = None  # ex.: "30/09" quando a recepção cita a validade nova


def ler_observacao(texto: str | None) -> LeituraObservacao:
    texto = (texto or "").strip()
    if not texto:
        return LeituraObservacao("VAZIA", texto)
    norm = sem_acento(texto)
    categoria = "NAO_RECONHECIDA"
    for cat, padroes in PADROES:
        if any(re.search(p, norm) for p in padroes):
            categoria = cat
            break
    protocolo = None
    m = re.search(r"protocolo\s*(?:n[ºo.]*\s*)?(\d+)", norm)
    if m:
        protocolo = m.group(1)
    validade = None
    m = re.search(r"validade\s*(\d{1,2}/\d{1,2}(?:/\d{2,4})?)", norm)
    if m:
        validade = m.group(1)
    return LeituraObservacao(categoria, texto, protocolo, validade)
