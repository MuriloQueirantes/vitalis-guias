"""Motor de conferência de guias: regras determinísticas.

Cada verificação devolve um Achado com severidade:
- PENDENTE: sabemos o que está errado e o que corrigir. A guia não segue até corrigir.
- REVISAR:  precisa de decisão humana (informação ambígua ou fora das regras).
- AVISO:    não impede o envio, só informa.

Status final da guia: REVISAR > PENDENTE > OK.
Nada aqui altera a guia. O motor aponta; quem corrige é a pessoa responsável.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from .dados import achar_convenio, achar_procedimento, parse_data, parse_int, parse_valor, sem_acento
from .observacao import ler_observacao

RECEPCAO = "Recepção"
FINANCEIRO = "Financeiro"
CLINICO = "Profissional que atendeu"

# Conselho esperado por procedimento (dicionário: CREFITO para fisioterapeuta, CRM para médico)
CONSELHO_POR_PROCEDIMENTO = {
    "50000470": "CREFITO",
    "50000560": "CREFITO",
    "50000012": "CREFITO",
    "20103301": "CRM",
    "40201015": "CRM",
}

ROTULOS = {
    "CAMPO_OBRIGATORIO": "Campo obrigatório faltando",
    "AUTORIZACAO_VENCIDA": "Autorização vencida",
    "AUTORIZACAO_VERBAL": "Autorização verbal sem número",
    "LIMITE_SESSOES": "Sessão acima do limite da autorização",
    "NAO_COBERTO": "Procedimento não coberto pelo convênio",
    "DUPLICIDADE": "Guia duplicada",
    "FATURAR_PARTICULAR": "Paciente optou por particular",
    "CODIGO_DIVERGENTE": "Procedimento lançado diferente do realizado",
    "CONSELHO_INCOMPATIVEL": "Registro do profissional incompatível",
    "VALOR_DIVERGENTE": "Valor diferente da tabela",
    "DESCRICAO_DIVERGENTE": "Descrição não bate com o código",
    "PRAZO_ENVIO": "Fora do prazo de envio",
    "VALIDADE_INCONSISTENTE": "Validade impossível para o convênio",
    "DATA_INVALIDA": "Data ilegível ou inconsistente",
    "CONVENIO_DESCONHECIDO": "Convênio fora da tabela",
    "PROCEDIMENTO_DESCONHECIDO": "Procedimento fora da tabela",
    "OBSERVACAO_NAO_RECONHECIDA": "Observação que precisa ser lida",
    "REMARCACAO": "Sessão remarcada",
}


@dataclass
class Achado:
    codigo: str
    severidade: str  # PENDENTE | REVISAR | AVISO
    motivo: str
    corrigir: str
    responsavel: str

    @property
    def tipo(self) -> str:
        return ROTULOS.get(self.codigo, self.codigo)


@dataclass
class Decisao:
    id_guia: str
    status: str  # OK | PENDENTE | REVISAR
    convenio: str
    unidade: str
    valor: float
    data_conferencia: str | None
    data_limite_envio: str | None
    achados: list[Achado] = field(default_factory=list)

    @property
    def problemas(self) -> list[Achado]:
        return [a for a in self.achados if a.severidade != "AVISO"]

    @property
    def avisos(self) -> list[Achado]:
        return [a for a in self.achados if a.severidade == "AVISO"]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["achados"] = [dict(asdict(a), tipo=a.tipo) for a in self.achados]
        return d


def _br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "?"


def somar_dias_uteis(inicio: date, dias: int) -> date:
    """Soma dias úteis (seg-sex). Feriados não entram: não temos o calendário da cidade."""
    atual = inicio
    while dias > 0:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            dias -= 1
    return atual


def chave_duplicidade(g: dict) -> tuple | None:
    """Mesmo paciente, mesmo dia, mesmo procedimento, mesma autorização e mesma sessão = mesma cobrança."""
    data, _ = parse_data(g.get("data_atendimento"))
    if not data or not g.get("paciente"):
        return None
    return (
        g.get("paciente", "").strip().upper(),
        data,
        re.sub(r"\D", "", g.get("procedimento_codigo", "")),
        g.get("numero_autorizacao", "").strip().upper(),
        parse_int(g.get("sessao_numero_na_autorizacao")),
    )


def verificar_guia(guia: dict, regras: dict, base: list[dict] | None = None, hoje: date | None = None) -> Decisao:
    """Confere uma guia contra as regras do convênio.

    base: outras guias já lançadas (para detectar duplicidade).
    hoje: data da conferência quando a guia não traz data_lancamento.
    """
    g = {k: (str(v).strip() if v is not None else "") for k, v in guia.items()}
    achados: list[Achado] = []

    def add(codigo, sev, motivo, corrigir, resp):
        achados.append(Achado(codigo, sev, motivo, corrigir, resp))

    obs = ler_observacao(g.get("observacao_recepcao"))

    # ---------- datas ----------
    dt_atend, atend_fora = parse_data(g.get("data_atendimento"))
    dt_lanc, _ = parse_data(g.get("data_lancamento"))
    dt_conf = dt_lanc or hoje or date.today()

    if not dt_atend:
        add("DATA_INVALIDA", "REVISAR", "Data do atendimento vazia ou ilegível.",
            "Informar a data do atendimento no formato AAAA-MM-DD.", RECEPCAO)
    elif atend_fora:
        add("DATA_INVALIDA", "AVISO",
            f"Data do atendimento digitada fora do padrão ('{g.get('data_atendimento')}'); lida como {_br(dt_atend)}.",
            "Padronizar a data no sistema (AAAA-MM-DD).", RECEPCAO)
    if dt_atend and dt_lanc and dt_lanc < dt_atend:
        add("DATA_INVALIDA", "REVISAR",
            f"Guia lançada ({_br(dt_lanc)}) antes do atendimento ({_br(dt_atend)}).",
            "Conferir as duas datas.", RECEPCAO)

    # ---------- convênio e procedimento ----------
    conv = achar_convenio(g.get("convenio", ""), regras)
    proc = achar_procedimento(g.get("procedimento_codigo") or g.get("procedimento_descricao", ""), regras)
    valor, valor_fora = parse_valor(g.get("valor"))

    if not conv:
        add("CONVENIO_DESCONHECIDO", "REVISAR", f"Convênio '{g.get('convenio')}' não está nas regras cadastradas.",
            "Confirmar o convênio do paciente; se for novo, cadastrar as regras antes de faturar.", FINANCEIRO)
    if not proc:
        add("PROCEDIMENTO_DESCONHECIDO", "REVISAR",
            f"Procedimento '{g.get('procedimento_codigo') or g.get('procedimento_descricao')}' não está na tabela.",
            "Confirmar o código do procedimento realizado.", CLINICO)

    valor_guia = valor if valor is not None else (proc["valor_referencia"] if proc else 0.0)

    # observação que muda a guia inteira
    if obs.categoria == "FATURAR_PARTICULAR":
        add("FATURAR_PARTICULAR", "PENDENTE", f"Recepção anotou: \"{obs.texto}\"",
            "Não enviar ao convênio. Cancelar a guia e cobrar o atendimento como particular.", RECEPCAO)
    elif obs.categoria == "CODIGO_DIVERGENTE":
        add("CODIGO_DIVERGENTE", "REVISAR", f"Recepção anotou: \"{obs.texto}\"",
            "Confirmar com o profissional o procedimento realizado e lançar o código certo. "
            "Se o procedimento não estiver na tabela do convênio, ele não é faturável por esta guia.", CLINICO)
    elif obs.categoria == "NAO_RECONHECIDA":
        add("OBSERVACAO_NAO_RECONHECIDA", "REVISAR", f"Observação fora dos padrões conhecidos: \"{obs.texto}\"",
            "Alguém precisa ler a observação e decidir se ela muda a guia.", RECEPCAO)
    elif obs.categoria == "REMARCACAO":
        add("REMARCACAO", "AVISO", f"Recepção anotou: \"{obs.texto}\"",
            "Validade conferida contra a data em que o atendimento de fato aconteceu.", RECEPCAO)

    if proc:
        cod = proc["codigo"]
        desc = g.get("procedimento_descricao", "")
        if desc and sem_acento(desc) != sem_acento(proc["descricao"]):
            add("DESCRICAO_DIVERGENTE", "PENDENTE",
                f"Código {cod} é '{proc['descricao']}', mas a descrição lançada é '{desc}'.",
                "Confirmar qual procedimento foi feito e corrigir código ou descrição.", RECEPCAO)
        if valor is None and g.get("valor"):
            add("VALOR_DIVERGENTE", "PENDENTE", f"Valor ilegível: '{g.get('valor')}'.",
                f"Lançar o valor de tabela (R$ {proc['valor_referencia']:.2f}).", RECEPCAO)
        elif valor is not None and abs(valor - proc["valor_referencia"]) > 0.009:
            add("VALOR_DIVERGENTE", "PENDENTE",
                f"Valor R$ {valor:.2f} diferente da tabela (R$ {proc['valor_referencia']:.2f}).",
                "Corrigir para o valor de referência do procedimento.", FINANCEIRO)
        elif valor_fora:
            add("VALOR_DIVERGENTE", "AVISO", f"Valor digitado fora do padrão ('{g.get('valor')}'); lido como R$ {valor:.2f}.",
                "Padronizar o valor com ponto decimal.", RECEPCAO)

        # conselho do profissional x procedimento
        registro = g.get("profissional_registro", "").upper()
        esperado = CONSELHO_POR_PROCEDIMENTO.get(cod)
        if registro and esperado and esperado not in registro:
            add("CONSELHO_INCOMPATIVEL", "REVISAR",
                f"'{proc['descricao']}' exige registro {esperado}, mas o profissional lançado tem '{g.get('profissional_registro')}'.",
                "Confirmar quem fez o atendimento e se o procedimento lançado é o correto.", CLINICO)

    if conv:
        nome = conv["nome"]

        # procedimento coberto (a observação do convênio só entra quando fala de cobertura)
        nota_cobertura = f" {conv['observacao']}" if "cobre" in sem_acento(conv.get("observacao", "")) else ""
        if proc and obs.categoria != "FATURAR_PARTICULAR" and proc["codigo"] not in conv["procedimentos_cobertos"]:
            add("NAO_COBERTO", "PENDENTE",
                f"{nome} não cobre '{proc['descricao']}' ({proc['codigo']}).{nota_cobertura}",
                "Não enviar ao convênio: faturar como particular ou confirmar o procedimento correto.", FINANCEIRO)

        # campos obrigatórios
        aceita_verbal = "verbal" in sem_acento(conv.get("observacao", ""))
        for campo in conv["campos_obrigatorios"]:
            if g.get(campo):
                continue
            if campo == "numero_autorizacao" and obs.categoria == "AUTORIZACAO_VERBAL":
                if aceita_verbal and dt_atend:
                    limite = somar_dias_uteis(dt_atend, 5)
                    if dt_conf <= limite:
                        add("AUTORIZACAO_VERBAL", "PENDENTE",
                            f"Autorização verbal (protocolo {obs.protocolo or 'não informado'}) sem número lançado. "
                            f"{nome} aceita até 5 dias úteis.",
                            f"Lançar o número da autorização até {_br(limite)} e antes do envio.", RECEPCAO)
                    else:
                        add("AUTORIZACAO_VERBAL", "REVISAR",
                            f"Autorização verbal passou dos 5 dias úteis ({_br(limite)}) sem número lançado.",
                            "Confirmar com o convênio se a autorização ainda vale antes de enviar.", FINANCEIRO)
                    continue
                add("CAMPO_OBRIGATORIO", "PENDENTE",
                    f"Autorização verbal anotada, mas {nome} não aceita autorização verbal.",
                    "Obter a autorização formal e lançar o número.", RECEPCAO)
                continue
            add("CAMPO_OBRIGATORIO", "PENDENTE", f"Campo obrigatório para {nome} vazio: {campo}.",
                f"Preencher '{campo}' antes do envio.", RECEPCAO)

        # validade da autorização (inclusive) contra a data do atendimento
        dt_val, _ = parse_data(g.get("autorizacao_validade"))
        if g.get("autorizacao_validade") and not dt_val:
            add("DATA_INVALIDA", "PENDENTE", f"Validade da autorização ilegível: '{g.get('autorizacao_validade')}'.",
                "Corrigir a data de validade.", RECEPCAO)
        if dt_val and dt_atend:
            if dt_val < dt_atend:
                if obs.categoria == "AUTORIZACAO_NOVA_NAO_LANCADA":
                    corrigir = ("A recepção anotou que o paciente trouxe autorização nova"
                                f"{' (validade ' + obs.validade_citada + ')' if obs.validade_citada else ''}. "
                                "Lançar o número e a validade da autorização nova antes do envio.")
                else:
                    corrigir = "Pedir nova autorização ao convênio e lançar o número antes do envio."
                add("AUTORIZACAO_VENCIDA", "PENDENTE",
                    f"Autorização válida até {_br(dt_val)}, atendimento em {_br(dt_atend)}.", corrigir, RECEPCAO)
            elif (dt_val - dt_atend).days > conv["validade_maxima_autorizacao_dias"]:
                add("VALIDADE_INCONSISTENTE", "REVISAR",
                    f"Validade {_br(dt_val)} está {(dt_val - dt_atend).days} dias depois do atendimento; "
                    f"{nome} emite autorização de no máximo {conv['validade_maxima_autorizacao_dias']} dias.",
                    "Conferir a data de validade digitada.", RECEPCAO)

        # limite de sessões
        sessao = parse_int(g.get("sessao_numero_na_autorizacao"))
        limite_conv = conv["limite_sessoes_por_autorizacao"]
        limite_guia = parse_int(g.get("autorizacao_sessoes_limite"))
        if limite_guia and limite_guia != limite_conv:
            add("LIMITE_SESSOES", "AVISO",
                f"Guia informa limite de {limite_guia} sessões; a regra do {nome} é {limite_conv}.",
                "Conferir o limite lançado.", RECEPCAO)
        if sessao and sessao > limite_conv:
            add("LIMITE_SESSOES", "PENDENTE",
                f"Sessão nº {sessao} numa autorização que cobre no máximo {limite_conv} ({nome}).",
                "Pedir nova autorização (e reavaliação, se o convênio exigir) e relançar a sessão nela.", RECEPCAO)
        elif sessao and sessao == limite_conv and "reavaliacao" in sem_acento(conv.get("observacao", "")):
            add("LIMITE_SESSOES", "AVISO", f"Última sessão desta autorização ({sessao}/{limite_conv}).",
                f"{conv['observacao']} Agendar antes da próxima sessão.", RECEPCAO)

        # prazo de envio, contado da data do atendimento
        if dt_atend:
            limite_envio = dt_atend + timedelta(days=conv["prazo_envio_dias"])
            if dt_conf > limite_envio:
                add("PRAZO_ENVIO", "REVISAR",
                    f"Prazo de envio do {nome} venceu em {_br(limite_envio)} ({conv['prazo_envio_dias']} dias do atendimento).",
                    "Avaliar com o financeiro se ainda há como enviar; o convênio tende a recusar.", FINANCEIRO)

    # duplicidade contra o que já foi lançado
    chave = chave_duplicidade(g)
    if chave and base:
        for outra in base:
            if outra.get("id_guia") == g.get("id_guia"):
                continue
            if chave_duplicidade(outra) == chave:
                add("DUPLICIDADE", "PENDENTE",
                    f"Mesmo paciente, data, procedimento, autorização e sessão da guia {outra.get('id_guia')}.",
                    f"Não enviar: cancelar esta guia (a {outra.get('id_guia')} já cobre este atendimento).", RECEPCAO)
                break

    if any(a.severidade == "REVISAR" for a in achados):
        status = "REVISAR"
    elif any(a.severidade == "PENDENTE" for a in achados):
        status = "PENDENTE"
    else:
        status = "OK"

    limite_envio_str = None
    if conv and dt_atend:
        limite_envio_str = (dt_atend + timedelta(days=conv["prazo_envio_dias"])).isoformat()

    return Decisao(
        id_guia=g.get("id_guia") or "(nova)",
        status=status,
        convenio=conv["nome"] if conv else g.get("convenio", ""),
        unidade=g.get("unidade", ""),
        valor=round(valor_guia, 2),
        data_conferencia=dt_conf.isoformat(),
        data_limite_envio=limite_envio_str,
        achados=achados,
    )


def verificar_lote(guias: list[dict], regras: dict) -> list[Decisao]:
    """Confere um lote. Na duplicidade, a guia lançada primeiro fica como original e as seguintes são marcadas."""
    ordem = sorted(
        range(len(guias)),
        key=lambda i: (parse_data(guias[i].get("data_lancamento"))[0] or date.max, guias[i].get("id_guia", "")),
    )
    decisoes: dict[int, Decisao] = {}
    vistas: list[dict] = []
    for i in ordem:
        decisoes[i] = verificar_guia(guias[i], regras, base=vistas)
        vistas.append(guias[i])
    return [decisoes[i] for i in range(len(guias))]
