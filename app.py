"""Painel web da conferência de guias (FastAPI).

Rotas:
  GET  /                  painel com as 80 guias de agosto e a decisão de cada uma
  GET  /nova              formulário para conferir uma guia nova (ou colar CSV)
  POST /nova              devolve a decisão
  POST /lote              sobe um CSV inteiro e gera o relatório daquele lote
  GET  /relatorio         relatório de terça do Dr. Renato (HTML)   /relatorio.md (texto)
  POST /api/verificar     guia em JSON -> decisão em JSON (porta de entrada para o sistema de gestão)
  GET  /api/guias         decisões do lote de agosto em JSON
  GET  /api/relatorio     números do relatório em JSON
"""

from __future__ import annotations

import html
from datetime import date

import markdown
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from vitalis.dados import COLUNAS, carregar_guias, carregar_regras, ler_csv
from vitalis.motor import Decisao, verificar_guia, verificar_lote
from vitalis.relatorio import relatorio_markdown, resumo

app = FastAPI(title="Vitalis · Conferência de guias")

REGRAS = carregar_regras()
GUIAS = carregar_guias()
DECISOES = verificar_lote(GUIAS, REGRAS)
LIMITE_UPLOAD = 2_000_000  # 2 MB

e = html.escape

CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f7f9;color:#1b1f24}
main{max-width:1200px;margin:0 auto;padding:20px 16px 60px}
nav a{margin-right:16px;color:#1b4f8a;text-decoration:none;font-weight:600}
h1{font-size:1.5rem;margin:.4em 0} h2{font-size:1.15rem;margin-top:1.6em}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.card{background:#fff;border:1px solid #dde1e6;border-radius:8px;padding:12px 16px;min-width:150px}
.card b{display:block;font-size:1.5rem}
table{border-collapse:collapse;width:100%;background:#fff;font-size:.88rem}
th,td{border-bottom:1px solid #e5e8eb;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#eef1f4;position:sticky;top:0}
.OK{color:#1a7f37;font-weight:700}.PENDENTE{color:#b35900;font-weight:700}.REVISAR{color:#c62828;font-weight:700}
.aviso{color:#57606a;font-size:.82rem}
form.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;background:#fff;padding:16px;border:1px solid #dde1e6;border-radius:8px}
label{font-size:.8rem;color:#57606a;display:block}
input,textarea,select{width:100%;box-sizing:border-box;padding:6px;border:1px solid #c9ced4;border-radius:4px;font:inherit}
button{background:#1b4f8a;color:#fff;border:0;border-radius:6px;padding:8px 16px;font-weight:600;cursor:pointer}
.box{background:#fff;border:1px solid #dde1e6;border-radius:8px;padding:16px;margin:12px 0}
.wrap{overflow-x:auto}
"""


def pagina(titulo: str, corpo: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(titulo)}</title><style>{CSS}</style></head>
<body><main><nav><a href="/">Guias de agosto</a><a href="/nova">Conferir guia nova</a><a href="/relatorio">Relatório de terça</a></nav>
{corpo}</main></body></html>""")


def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def linha_decisao(d: Decisao, guia: dict | None = None) -> str:
    probs = "".join(f"<div><b>{e(a.tipo)}:</b> {e(a.motivo)}<br><i>Corrigir:</i> {e(a.corrigir)} "
                    f"<span class='aviso'>({e(a.responsavel)})</span></div>" for a in d.problemas)
    avisos = "".join(f"<div class='aviso'>ⓘ {e(a.motivo)}</div>" for a in d.avisos)
    obs = e((guia or {}).get("observacao_recepcao", ""))
    return (f"<tr><td>{e(d.id_guia)}</td><td>{e(d.unidade)}</td><td>{e(d.convenio)}</td>"
            f"<td class='{d.status}'>{d.status}</td><td>{brl(d.valor)}</td><td>{probs or '—'}{avisos}</td>"
            f"<td class='aviso'>{obs}</td></tr>")


def cards(r: dict) -> str:
    return f"""<div class="cards">
<div class="card">Verificadas<b>{r['verificadas']}</b></div>
<div class="card">OK<b class="OK">{r['ok']}</b></div>
<div class="card">Pendentes<b class="PENDENTE">{r['pendentes']}</b></div>
<div class="card">Revisar<b class="REVISAR">{r['revisar']}</b></div>
<div class="card">Valor em risco<b>{brl(r['valor_risco'])}</b></div></div>"""


@app.get("/", response_class=HTMLResponse)
def painel(status: str | None = None):
    r = resumo(DECISOES)
    filtro = (status or "").upper()
    pares = [(d, g) for d, g in zip(DECISOES, GUIAS) if not filtro or d.status == filtro]
    linhas = "".join(linha_decisao(d, g) for d, g in pares)
    filtros = " · ".join(f"<a href='/?status={s}'>{s}</a>" for s in ("OK", "PENDENTE", "REVISAR"))
    return pagina("Vitalis · Guias de agosto", f"""
<h1>Conferência de guias antes do envio — agosto/2026</h1>
<p>Cada guia foi conferida na data em que foi lançada, contra as regras do convênio (<code>regras_convenio.json</code>).
Nada é enviado nem alterado: o painel aponta o problema, o que corrigir e quem corrige.</p>
{cards(r)}
<p>Filtrar: <a href="/">todas</a> · {filtros}</p>
<div class="wrap"><table><tr><th>Guia</th><th>Unidade</th><th>Convênio</th><th>Status</th><th>Valor</th><th>Problema e correção</th><th>Observação da recepção</th></tr>
{linhas}</table></div>""")


def campo_input(nome: str, valor: str = "") -> str:
    if nome == "observacao_recepcao":
        return f"<div><label>{nome}</label><textarea name='{nome}' rows='2'>{e(valor)}</textarea></div>"
    return f"<div><label>{nome}</label><input name='{nome}' value='{e(valor)}'></div>"


EXEMPLO = {
    "id_guia": "G-2609-0001", "unidade": "Centro", "data_atendimento": date.today().isoformat(), "paciente": "P-2001",
    "convenio": "Vitalcard", "carteirinha": "123456789", "cid": "M54.5", "procedimento_codigo": "50000470",
    "procedimento_descricao": "Sessão de fisioterapia musculoesquelética", "numero_autorizacao": "AUT123456",
    "autorizacao_validade": "", "autorizacao_sessoes_limite": "10", "sessao_numero_na_autorizacao": "3",
    "profissional": "Diego Farias", "profissional_registro": "CREFITO-3 221078-F", "valor": "62.00",
    "observacao_recepcao": "", "data_lancamento": date.today().isoformat(),
}


@app.get("/nova", response_class=HTMLResponse)
def nova_form():
    campos = "".join(campo_input(c, EXEMPLO.get(c, "")) for c in COLUNAS)
    return pagina("Conferir guia nova", f"""
<h1>Conferir uma guia nova</h1>
<p>Preencha como a recepção lançou (datas em AAAA-MM-DD ou DD/MM/AAAA). A guia é conferida contra as regras e contra as 80 guias
de agosto (duplicidade). Se <code>data_lancamento</code> ficar vazio, a conferência usa a data de hoje.</p>
<form class="grid" method="post" action="/nova">{campos}<div><button type="submit">Conferir</button></div></form>
<h2>Ou cole um CSV (mesmas colunas, com cabeçalho)</h2>
<form class="box" method="post" action="/lote" enctype="multipart/form-data">
<textarea name="texto" rows="6" placeholder="id_guia,unidade,data_atendimento,..."></textarea>
<p>ou arquivo: <input type="file" name="arquivo" accept=".csv" style="width:auto"></p>
<button type="submit">Conferir lote</button></form>""")


@app.post("/nova", response_class=HTMLResponse)
async def nova_post(request: Request):
    form = await request.form()
    guia = {c: str(form.get(c, "")) for c in COLUNAS}
    d = verificar_guia(guia, REGRAS, base=GUIAS)
    campos = "".join(campo_input(c, guia.get(c, "")) for c in COLUNAS)
    return pagina("Decisão da guia", f"""
<h1>Decisão: <span class="{d.status}">{d.status}</span></h1>
<div class="wrap"><table><tr><th>Guia</th><th>Unidade</th><th>Convênio</th><th>Status</th><th>Valor</th><th>Problema e correção</th><th>Observação</th></tr>
{linha_decisao(d, guia)}</table></div>
<p class="aviso">Conferida em {e(d.data_conferencia or '')}. Prazo de envio ao convênio: {e(d.data_limite_envio or 'não calculado')}.</p>
<h2>Corrigir e conferir de novo</h2>
<form class="grid" method="post" action="/nova">{campos}<div><button type="submit">Conferir</button></div></form>""")


@app.post("/lote", response_class=HTMLResponse)
async def lote(texto: str = Form(""), arquivo: UploadFile | None = File(None)):
    conteudo = texto
    if arquivo is not None and arquivo.filename:
        bruto = await arquivo.read(LIMITE_UPLOAD + 1)
        if len(bruto) > LIMITE_UPLOAD:
            return pagina("Erro", "<h1>Arquivo grande demais</h1><p>Limite de 2 MB.</p>")
        conteudo = bruto.decode("utf-8-sig", errors="replace")
    try:
        guias = ler_csv(conteudo) if conteudo.strip() else []
    except Exception as exc:  # CSV malformado não derruba o servidor
        return pagina("Erro", f"<h1>Não consegui ler o CSV</h1><p>{e(str(exc))}</p>")
    if not guias:
        return pagina("Erro", "<h1>Nenhuma guia encontrada</h1><p>Confira se o CSV tem cabeçalho.</p>")
    decisoes = verificar_lote(guias, REGRAS)
    linhas = "".join(linha_decisao(d, g) for d, g in zip(decisoes, guias))
    rel = markdown.markdown(relatorio_markdown(decisoes, titulo="lote enviado", guias_mes=0), extensions=["tables"])
    return pagina("Lote conferido", f"""{cards(resumo(decisoes))}
<div class="wrap"><table><tr><th>Guia</th><th>Unidade</th><th>Convênio</th><th>Status</th><th>Valor</th><th>Problema e correção</th><th>Observação</th></tr>
{linhas}</table></div><div class="box">{rel}</div>""")


@app.get("/relatorio", response_class=HTMLResponse)
def relatorio_html():
    corpo = markdown.markdown(relatorio_markdown(DECISOES), extensions=["tables"])
    return pagina("Relatório de terça", f"<div class='box'>{corpo}</div><p><a href='/relatorio.md'>versão em texto</a></p>")


@app.get("/relatorio.md", response_class=PlainTextResponse)
def relatorio_texto():
    return relatorio_markdown(DECISOES)


@app.post("/api/verificar")
async def api_verificar(request: Request):
    try:
        corpo = await request.json()
    except Exception:
        return JSONResponse({"erro": "Envie a guia como JSON."}, status_code=400)
    if not isinstance(corpo, dict):
        return JSONResponse({"erro": "O JSON deve ser um objeto com os campos da guia."}, status_code=400)
    return verificar_guia(corpo, REGRAS, base=GUIAS).to_dict()


@app.get("/api/guias")
def api_guias():
    return [d.to_dict() for d in DECISOES]


@app.get("/api/relatorio")
def api_relatorio():
    return resumo(DECISOES)
