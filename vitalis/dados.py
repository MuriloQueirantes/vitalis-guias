"""Leitura dos arquivos da Carla e normalização do que a recepção digitou.

Tudo que é "limpeza" de entrada fica aqui, separado das regras de negócio (motor.py).
A normalização nunca inventa dado: se não dá pra entender o valor, devolve None
e o motor trata como campo ausente/ilegível.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"
ARQ_GUIAS = PASTA_DADOS / "guias.csv"
ARQ_REGRAS = PASTA_DADOS / "regras_convenio.json"

COLUNAS = [
    "id_guia", "unidade", "data_atendimento", "paciente", "convenio", "carteirinha", "cid",
    "procedimento_codigo", "procedimento_descricao", "numero_autorizacao", "autorizacao_validade",
    "autorizacao_sessoes_limite", "sessao_numero_na_autorizacao", "profissional",
    "profissional_registro", "valor", "observacao_recepcao", "data_lancamento",
]


def carregar_regras(caminho: Path = ARQ_REGRAS) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def ler_csv(texto: str) -> list[dict]:
    """Lê CSV (com cabeçalho) a partir de texto. Aceita vírgula ou ponto e vírgula."""
    texto = texto.lstrip("﻿")
    primeira = texto.splitlines()[0] if texto.strip() else ""
    sep = ";" if primeira.count(";") > primeira.count(",") else ","
    leitor = csv.DictReader(io.StringIO(texto), delimiter=sep)
    return [{(k or "").strip(): (v or "").strip() for k, v in linha.items()} for linha in leitor]


def carregar_guias(caminho: Path = ARQ_GUIAS) -> list[dict]:
    return ler_csv(caminho.read_text(encoding="utf-8"))


# ---------- normalização de campos ----------

def sem_acento(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn").lower().strip()


def parse_data(valor) -> tuple[date | None, bool]:
    """Devolve (data, estava_fora_do_padrao). Aceita AAAA-MM-DD, DD/MM/AAAA e DD-MM-AAAA."""
    if valor is None:
        return None, False
    if isinstance(valor, date):
        return valor, False
    txt = str(valor).strip()
    if not txt:
        return None, False
    try:
        return datetime.strptime(txt, "%Y-%m-%d").date(), False
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(txt, fmt).date(), True
        except ValueError:
            continue
    return None, True


def parse_valor(valor) -> tuple[float | None, bool]:
    """Devolve (valor, estava_fora_do_padrao). Aceita '62.00', '62,00', 'R$ 62,00'."""
    if valor is None or str(valor).strip() == "":
        return None, False
    if isinstance(valor, (int, float)):
        return float(valor), False
    txt = str(valor).strip()
    try:
        return float(txt), False
    except ValueError:
        pass
    limpo = re.sub(r"[^\d,.-]", "", txt)
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo), True
    except ValueError:
        return None, True


def parse_int(valor) -> int | None:
    if valor is None:
        return None
    m = re.search(r"\d+", str(valor))
    return int(m.group()) if m else None


def achar_convenio(nome: str, regras: dict) -> dict | None:
    """Casa o nome do convênio tolerando acento, caixa e espaço ('saude interior' = 'Saúde Interior')."""
    alvo = re.sub(r"\s+", "", sem_acento(nome or ""))
    if not alvo:
        return None
    for conv in regras["convenios"]:
        if re.sub(r"\s+", "", sem_acento(conv["nome"])) == alvo:
            return conv
    return None


def achar_procedimento(codigo_ou_nome: str, regras: dict) -> dict | None:
    """Acha o procedimento pelo código (só dígitos) ou pela descrição exata sem acento."""
    txt = (codigo_ou_nome or "").strip()
    if not txt:
        return None
    digitos = re.sub(r"\D", "", txt)
    for p in regras["procedimentos"]:
        if digitos and p["codigo"] == digitos:
            return p
    for p in regras["procedimentos"]:
        if sem_acento(p["descricao"]) == sem_acento(txt):
            return p
    return None
