"""Testes do motor.

1) Gabarito: conferi as 80 guias à mão contra regras_convenio.json e anotei o problema esperado
   de cada uma. O teste garante que o motor chega na mesma decisão.
2) Guia nova: entradas estranhas não podem derrubar a conferência.
"""

from datetime import date

import pytest

from vitalis.dados import carregar_guias, carregar_regras
from vitalis.motor import verificar_guia, verificar_lote

REGRAS = carregar_regras()
GUIAS = carregar_guias()
DECISOES = {d.id_guia: d for d in verificar_lote(GUIAS, REGRAS)}

# id -> (status esperado, códigos de problema esperados)
GABARITO = {
    "0002": ("PENDENTE", {"NAO_COBERTO"}),               # Plano Bem não cobre consulta
    "0004": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0006": ("PENDENTE", {"NAO_COBERTO", "LIMITE_SESSOES"}),  # Vitalcard não cobre infiltração; sessão 15/10
    "0007": ("PENDENTE", {"NAO_COBERTO"}),
    "0008": ("PENDENTE", {"LIMITE_SESSOES"}),
    "0013": ("PENDENTE", {"CAMPO_OBRIGATORIO"}),         # sem registro do profissional
    "0014": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0021": ("PENDENTE", {"CAMPO_OBRIGATORIO"}),         # Vitalcard exige CID
    "0023": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0024": ("PENDENTE", {"NAO_COBERTO"}),
    "0026": ("PENDENTE", {"LIMITE_SESSOES"}),
    "0028": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0030": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),       # autorização nova ainda não lançada
    "0031": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0032": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0033": ("PENDENTE", {"CAMPO_OBRIGATORIO"}),
    "0035": ("PENDENTE", {"NAO_COBERTO"}),
    "0039": ("PENDENTE", {"FATURAR_PARTICULAR"}),        # paciente quer particular
    "0041": ("PENDENTE", {"AUTORIZACAO_VERBAL"}),        # Saúde Interior aceita verbal por 5 dias úteis
    "0045": ("REVISAR", {"CONSELHO_INCOMPATIVEL"}),      # reavaliação fisioterapêutica com CRM
    "0046": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0047": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0049": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0050": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0051": ("PENDENTE", {"CAMPO_OBRIGATORIO"}),
    "0056": ("PENDENTE", {"CAMPO_OBRIGATORIO", "LIMITE_SESSOES"}),
    "0057": ("PENDENTE", {"DUPLICIDADE"}),               # duplicata da 0027
    "0061": ("PENDENTE", {"CAMPO_OBRIGATORIO"}),
    "0063": ("PENDENTE", {"CAMPO_OBRIGATORIO"}),
    "0064": ("PENDENTE", {"LIMITE_SESSOES"}),
    "0069": ("REVISAR", {"CODIGO_DIVERGENTE"}),          # foi drenagem linfática
    "0072": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0074": ("REVISAR", {"CONSELHO_INCOMPATIVEL"}),
    "0075": ("PENDENTE", {"AUTORIZACAO_VENCIDA"}),
    "0076": ("PENDENTE", {"DUPLICIDADE"}),               # duplicata da 0059
    "0077": ("PENDENTE", {"LIMITE_SESSOES"}),
}


@pytest.mark.parametrize("guia", GUIAS, ids=lambda g: g["id_guia"])
def test_gabarito(guia):
    num = guia["id_guia"][-4:]
    d = DECISOES[guia["id_guia"]]
    status, codigos = GABARITO.get(num, ("OK", set()))
    assert d.status == status
    assert {a.codigo for a in d.problemas} == codigos


def test_armadilhas_que_devem_passar():
    # validade no próprio dia do atendimento vale (inclusive)
    assert DECISOES["G-2608-0001"].status == "OK"
    assert DECISOES["G-2608-0020"].status == "OK"
    # data em DD/MM/AAAA e valor com vírgula são normalizados, não são erro
    assert DECISOES["G-2608-0016"].status == "OK"
    assert DECISOES["G-2608-0065"].status == "OK"
    # Saúde Interior não exige CID
    assert DECISOES["G-2608-0009"].status == "OK"
    # remarcação: a validade cobre a data real do atendimento
    assert DECISOES["G-2608-0034"].status == "OK"
    # a primeira guia lançada do par duplicado fica como original
    assert DECISOES["G-2608-0027"].status == "OK"
    assert DECISOES["G-2608-0059"].status == "OK"


def test_guia_vazia_nao_quebra():
    d = verificar_guia({}, REGRAS, hoje=date(2026, 9, 1))
    assert d.status == "REVISAR"


def test_guia_com_lixo_nao_quebra():
    d = verificar_guia({"convenio": "vitalcard", "data_atendimento": "ontem", "valor": "abc",
                        "procedimento_codigo": "xyz", "sessao_numero_na_autorizacao": "dez"}, REGRAS)
    assert d.status == "REVISAR"


def test_convenio_sem_acento_e_minusculo():
    g = dict(next(x for x in GUIAS if x["id_guia"] == "G-2608-0009"), convenio="saude interior", id_guia="NOVA")
    assert verificar_guia(g, REGRAS).convenio == "Saúde Interior"


def test_guia_nova_duplicada_contra_o_lote():
    g = dict(next(x for x in GUIAS if x["id_guia"] == "G-2608-0003"), id_guia="G-NOVA")
    d = verificar_guia(g, REGRAS, base=GUIAS)
    assert "DUPLICIDADE" in {a.codigo for a in d.problemas}


def test_prazo_de_envio_vencido():
    g = dict(next(x for x in GUIAS if x["id_guia"] == "G-2608-0003"), id_guia="G-NOVA", data_lancamento="2026-10-30")
    d = verificar_guia(g, REGRAS)
    assert "PRAZO_ENVIO" in {a.codigo for a in d.problemas}


def test_autorizacao_verbal_fora_dos_5_dias_uteis():
    g = dict(next(x for x in GUIAS if x["id_guia"] == "G-2608-0041"), id_guia="G-NOVA", data_lancamento="2026-09-10")
    d = verificar_guia(g, REGRAS)
    assert d.status == "REVISAR"


def test_observacao_desconhecida_vai_pra_humano():
    g = dict(next(x for x in GUIAS if x["id_guia"] == "G-2608-0003"), id_guia="G-NOVA",
             observacao_recepcao="Paciente disse que o plano foi cancelado mês passado.")
    assert verificar_guia(g, REGRAS).status == "REVISAR"


def test_descricao_abreviada_nao_e_erro_mas_descricao_de_outro_procedimento_e():
    base = dict(next(x for x in GUIAS if x["id_guia"] == "G-2608-0003"), id_guia="G-NOVA", paciente="P-9999")
    base["procedimento_codigo"] = "50000470"
    abreviada = verificar_guia(dict(base, procedimento_descricao="fisioterapia musculoesquelética"), REGRAS)
    assert "DESCRICAO_DIVERGENTE" not in {a.codigo for a in abreviada.problemas}
    trocada = verificar_guia(dict(base, procedimento_descricao="Consulta ortopédica"), REGRAS)
    assert "DESCRICAO_DIVERGENTE" in {a.codigo for a in trocada.problemas}


def test_pagar_do_bolso_e_particular():
    # Padrão ensinado depois que a frase caiu em REVISAR no teste da Skill.
    g = dict(next(x for x in GUIAS if x["id_guia"] == "G-2608-0003"), id_guia="G-NOVA", paciente="P-9999",
             observacao_recepcao="Paciente disse que vai pagar do bolso dessa vez")
    d = verificar_guia(g, REGRAS)
    assert d.status == "PENDENTE"
    assert {a.codigo for a in d.problemas} == {"FATURAR_PARTICULAR"}
