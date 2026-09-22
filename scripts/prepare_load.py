"""Shape the raw dataset into narrow CSVs, one per vertex or edge type.

All the fiddly transforms live here, where they can be checked in pandas,
so the GSQL loading job is just column-to-attribute mapping.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "load"

TX_COLS = [
    "TransactionID", "TransactionAmt", "ProductCD", "card4", "card6",
    "addr1", "addr2", "dist1", "dist2", "P_emaildomain",
    "customer_id", "ts", "channel", "risk_score",
]
ID_COLS = ["TransactionID", "DeviceType", "DeviceInfo", "id_15", "id_23", "id_30", "id_31", "id_33"]


def card_ids(tx):
    # Transactions carry no card_id. Within a customer, card type (card6)
    # sorted alphabetically gives K1, K2, ... Verified against every labeled
    # transaction in the closed cases and all 20 exam cases.
    card_type = tx["card6"].fillna("NA")
    k = card_type.groupby(tx["customer_id"]).rank(method="dense").astype(int)
    return tx["customer_id"] + "-K" + k.astype(str)


def device_keys(ident):
    # DeviceInfo alone is too coarse (thousands of identical phone models),
    # so a profile is DeviceInfo + OS + browser + screen, the same format the
    # README uses for connected_device_profiles. Rows with no DeviceInfo get
    # no profile: a browser version on its own links hundreds of unrelated
    # customers and would make every ring query light up on noise.
    parts = ident[["DeviceInfo", "id_30", "id_31", "id_33"]].fillna("")
    key = parts.agg(" | ".join, axis=1)
    return key.where(ident["DeviceInfo"].notna())


def write(df, name):
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"{name:<16} {len(df):>9,}")


def main():
    OUT.mkdir(exist_ok=True)

    tx = pd.read_csv(DATA / "transactions.csv", usecols=TX_COLS, dtype=str, engine="pyarrow")
    tx["card_id"] = card_ids(tx)

    write(tx[["customer_id"]].drop_duplicates(), "customers")
    write(
        tx.groupby("card_id", as_index=False)
        .agg(customer_id=("customer_id", "first"), card_network=("card4", "first"), card_type=("card6", "first")),
        "cards",
    )
    write(
        tx.rename(columns={
            "TransactionID": "txn_id", "TransactionAmt": "amount",
            "ProductCD": "product_cd",
        })[["txn_id", "card_id", "amount", "ts", "product_cd", "channel",
            "risk_score", "addr1", "addr2", "dist1", "dist2"]],
        "transactions",
    )

    email = tx.dropna(subset=["P_emaildomain"])
    write(email[["TransactionID", "P_emaildomain"]].rename(columns={"TransactionID": "txn_id", "P_emaildomain": "domain"}), "tx_email")

    region = tx.dropna(subset=["addr1"])
    write(region[["TransactionID", "addr1"]].rename(columns={"TransactionID": "txn_id", "addr1": "region_code"}), "tx_region")

    seq = tx[["TransactionID", "card_id", "ts"]].sort_values(["card_id", "ts", "TransactionID"])
    seq["next_txn_id"] = seq.groupby("card_id")["TransactionID"].shift(-1)
    write(seq.dropna(subset=["next_txn_id"])[["TransactionID", "next_txn_id"]].rename(columns={"TransactionID": "txn_id"}), "tx_next")

    ident = pd.read_csv(DATA / "identity.csv", usecols=ID_COLS, dtype=str)
    ident["device_key"] = device_keys(ident)
    ident = ident.dropna(subset=["device_key"])
    write(
        ident.groupby("device_key", as_index=False).agg(
            device_type=("DeviceType", "first"), device_info=("DeviceInfo", "first"),
            os=("id_30", "first"), browser=("id_31", "first"), screen=("id_33", "first"),
        ),
        "devices",
    )
    write(
        ident[["TransactionID", "device_key", "id_15", "id_23"]].rename(
            columns={"TransactionID": "txn_id", "id_15": "device_seen", "id_23": "proxy_type"}
        ),
        "tx_device",
    )

    cc = pd.read_csv(DATA / "closed_cases_history.csv", dtype=str)
    write(cc.rename(columns={"txn_ids": "txn_ids_raw", "connected_card_ids": "connected_card_ids_raw"}), "closed_cases")
    write(
        cc.assign(txn_id=cc["txn_ids"].str.split("|")).explode("txn_id")[["case_id", "txn_id"]],
        "cc_involves",
    )
    write(cc[["case_id", "card_id"]], "cc_on_card")
    conn = cc.dropna(subset=["connected_card_ids"])
    write(
        conn.assign(card_id=conn["connected_card_ids"].str.split("|")).explode("card_id")[["case_id", "card_id"]],
        "cc_connected",
    )


if __name__ == "__main__":
    main()
