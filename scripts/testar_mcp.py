"""Sobe o MCP via stdio (como o Claude faz), lista as ferramentas e chama duas delas.

Uso: uv run python scripts/testar_mcp.py
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

RAIZ = Path(__file__).resolve().parent.parent


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(RAIZ / "mcp_server" / "server.py")])
    async with stdio_client(params) as (leitura, escrita):
        async with ClientSession(leitura, escrita) as sessao:
            await sessao.initialize()
            ferramentas = await sessao.list_tools()
            print("Ferramentas:", [t.name for t in ferramentas.tools])

            r = await sessao.call_tool("consultar_regra", {"convenio": "plano bem", "procedimento": "20103301"})
            print("\nconsultar_regra(plano bem, 20103301):\n", r.content[0].text[:400])

            r = await sessao.call_tool("verificar_guia", {"id_guia": "G-2608-0030"})
            d = json.loads(r.content[0].text)
            print("\nverificar_guia(G-2608-0030):", d["status"])
            for a in d["achados"]:
                print(" -", a["tipo"], "|", a["corrigir"])


asyncio.run(main())
