"""Testes das portas de entrada: painel web (FastAPI) e ferramentas do MCP."""

from fastapi.testclient import TestClient

from app import app
from mcp_server import server as mcp

cliente = TestClient(app)


def test_paginas_abrem():
    for rota in ("/", "/nova", "/relatorio", "/relatorio.md", "/api/guias", "/api/relatorio", "/?status=REVISAR"):
        assert cliente.get(rota).status_code == 200, rota


def test_api_verificar_guia_nova():
    r = cliente.post("/api/verificar", json={"convenio": "Plano Bem", "procedimento_codigo": "20103301",
                                              "data_atendimento": "2026-09-20", "data_lancamento": "2026-09-20"})
    assert r.status_code == 200
    assert r.json()["status"] in {"PENDENTE", "REVISAR"}


def test_api_verificar_json_invalido():
    assert cliente.post("/api/verificar", content="não é json").status_code == 400
    assert cliente.post("/api/verificar", json=[1, 2]).status_code == 400


def test_formulario_guia_nova():
    r = cliente.post("/nova", data={"convenio": "Vitalcard", "data_atendimento": "2026-09-20"})
    assert r.status_code == 200 and "Decisão" in r.text


def test_lote_csv():
    csv = open("data/guias.csv", encoding="utf-8").read()
    r = cliente.post("/lote", data={"texto": csv})
    assert r.status_code == 200 and "80" in r.text
    assert cliente.post("/lote", data={"texto": ""}).status_code == 200  # vazio não quebra


def test_mcp_consultar_regra():
    r = mcp.consultar_regra("plano bem", "20103301")
    assert r["procedimento"]["coberto"] is False
    assert "erro" in mcp.consultar_regra("Unimed")


def test_mcp_verificar_por_id_e_por_objeto():
    assert mcp.verificar_guia(id_guia="G-2608-0057")["status"] == "PENDENTE"
    assert mcp.verificar_guia(id_guia="G-2608-0001")["status"] == "OK"
    assert "erro" in mcp.verificar_guia()
    d = mcp.verificar_guia(guia={"convenio": "Vitalcard", "procedimento_codigo": "40201015"})
    assert d["status"] != "OK"
