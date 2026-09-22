import os

import pyTigerGraph as tg
from dotenv import load_dotenv

load_dotenv()


def connect():
    return tg.TigerGraphConnection(
        host=os.getenv("TIGERGRAPH_HOST") or "http://localhost",
        graphname=os.getenv("TIGERGRAPH_GRAPH_NAME") or "Graphite",
        username=os.getenv("TIGERGRAPH_USERNAME") or "tigergraph",
        password=os.getenv("TIGERGRAPH_PASSWORD") or "tigergraph",
        restppPort="14240",
        gsPort="14240",
    )
