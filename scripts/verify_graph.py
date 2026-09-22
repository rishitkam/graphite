"""Check every vertex and edge count in the graph against the source CSVs."""

import sys
from pathlib import Path

import pandas as pd

from graphite.tg import connect

LOAD = Path(__file__).resolve().parent.parent / "data" / "load"


def rows(name, col=None):
    df = pd.read_csv(LOAD / f"{name}.csv", dtype=str)
    return df[col].nunique() if col else len(df)


def main():
    c = connect()
    expected = {
        ("v", "Customer"): rows("customers"),
        ("v", "Card"): rows("cards"),
        ("v", "Transaction"): rows("transactions"),
        ("v", "DeviceProfile"): rows("devices"),
        ("v", "EmailDomain"): rows("tx_email", "domain"),
        ("v", "BillingRegion"): rows("tx_region", "region_code"),
        ("v", "ClosedCase"): rows("closed_cases"),
        ("e", "OWNS"): rows("cards"),
        ("e", "MADE"): rows("transactions"),
        ("e", "PURCHASER_EMAIL"): rows("tx_email"),
        ("e", "BILLED_IN"): rows("tx_region"),
        ("e", "NEXT"): rows("tx_next"),
        ("e", "FROM_DEVICE"): rows("tx_device"),
        ("e", "INVOLVES"): rows("cc_involves"),
        ("e", "ON_CARD"): rows("cc_on_card"),
        ("e", "CONNECTED_TO"): rows("cc_connected"),
    }
    failed = 0
    for (kind, name), want in expected.items():
        got = c.getVertexCount(name) if kind == "v" else c.getEdgeCount(name)
        ok = got == want
        failed += not ok
        print(f"{name:<16} {got:>9,}  {'ok' if ok else f'EXPECTED {want:,}'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
