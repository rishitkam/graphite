"""Every graph query the pipelines make goes through the official TigerGraph
MCP server (tigergraph-mcp), as the brief requires.

One persistent MCP session over stdio, kept on a background event loop so the
synchronous pipeline code can call it like a function. The server exposes
tigergraph__run_installed_query; its result is the same list pyTigerGraph
would return, so nothing downstream changes.
"""

import asyncio
import json
import os
import threading
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
GRAPH = os.getenv("TIGERGRAPH_GRAPH_NAME") or "Graphite"


class _Session:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.error = None
        threading.Thread(target=self._serve, daemon=True).start()
        self.ready.wait(60)
        if self.error:
            raise self.error

    def _serve(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    async def _main(self):
        host = (os.getenv("TIGERGRAPH_HOST") or "http://localhost").rstrip("/")
        env = dict(os.environ, TG_HOST=host, TG_GRAPHNAME=GRAPH,
                   TG_USERNAME=os.getenv("TIGERGRAPH_USERNAME") or "tigergraph",
                   TG_PASSWORD=os.getenv("TIGERGRAPH_PASSWORD") or "tigergraph",
                   TG_RESTPP_PORT="14240", TG_GS_PORT="14240")
        params = StdioServerParameters(command=str(ROOT / ".venv" / "bin" / "tigergraph-mcp"), args=[], env=env)
        try:
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    self.session = s
                    self.stop = asyncio.Event()
                    self.ready.set()
                    await self.stop.wait()
        except Exception as e:  # surfaced to the caller waiting on ready
            self.error = e
            self.ready.set()

    def call(self, tool, args, timeout=120):
        fut = asyncio.run_coroutine_threadsafe(self.session.call_tool(tool, args), self.loop)
        return fut.result(timeout)


_session = None
_lock = threading.Lock()


def session():
    global _session
    with _lock:
        if _session is None:
            _session = _Session()
    return _session


def _unwrap(result):
    # The server wraps the JSON in a markdown fence and sometimes adds notes
    # after it, so read the first complete JSON object and ignore the rest.
    text = result.content[0].text
    body, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    if not body.get("success", True):
        raise RuntimeError(f"MCP query failed: {body.get('error') or body}")
    return body["data"]["result"]


def run_installed_query(name, params):
    return _unwrap(session().call("tigergraph__run_installed_query",
                                  {"graph_name": GRAPH, "query_name": name, "params": params}))
