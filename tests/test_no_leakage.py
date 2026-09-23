"""The eval is only honest if nothing after the investigation time leaks in.

These run against the local data and, where marked, the live graph.
"""

import pandas as pd
import pytest

from graphite import alerts, data, situation

HISTORY = ["online", "has_device", "device_new", "proxy", "device_uses_on_card", "region_share",
           "product_share", "email_share", "amount_vs_avg", "history_len", "txns_72h_before", "small_auths_1h", "risk_score"]


@pytest.fixture(scope="module")
def cases():
    return alerts.eval_alerts(("dev",))[:8]


def t_plus(txn_id, hours):
    return str(pd.Timestamp(data.alert_record(txn_id)["ts"]) + pd.Timedelta(hours=hours))


def test_situation_history_ignores_the_future(cases):
    for a in cases:
        now = situation.features(a.flagged_txn_id, t_plus(a.flagged_txn_id, 6))
        later = situation.features(a.flagged_txn_id, t_plus(a.flagged_txn_id, 24 * 60))
        assert {k: now[k] for k in HISTORY} == {k: later[k] for k in HISTORY}, a.case_id


def test_after_window_is_capped_at_six_hours(cases):
    for a in cases:
        six = situation.features(a.flagged_txn_id, t_plus(a.flagged_txn_id, 6))
        month = situation.features(a.flagged_txn_id, t_plus(a.flagged_txn_id, 24 * 30))
        assert six["txns_after"] == month["txns_after"], a.case_id


def test_eval_and_dev_are_disjoint_and_excluded_from_memory():
    held = alerts.holdout()
    dev = {k for k, v in held.items() if v == "dev"}
    test = {k for k, v in held.items() if v != "dev"}
    assert dev and test and not dev & test
    assert alerts.holdout_ids() == dev | test


def test_matched_slice_has_no_score_signal():
    v = [a for a in alerts.eval_alerts() if a.eval_slice == "matched"]
    best = max(sum((a.risk_score < t) == (a.label == "fraud") for a in v) / len(v) for t in [i / 100 for i in range(101)])
    assert best <= 0.55


@pytest.mark.graph
def test_card_window_never_returns_the_future(cases):
    from graphite import graph_tools as g
    for a in cases:
        t_end = t_plus(a.flagged_txn_id, 6)
        rows = g.card_window(a.card_id, t_end, 30)
        assert all(r["ts"] <= t_end for r in rows), a.case_id


@pytest.mark.graph
def test_memory_never_returns_held_out_or_future_cases(cases):
    from graphite import evidence
    from graphite import graph_tools as g
    held = alerts.holdout_ids()
    closed = data.closed_cases().set_index("case_id")["closed_at"]
    for a in cases:
        t_end = t_plus(a.flagged_txn_id, 6)
        hits = g.similar_situations(evidence.situation.vector(a.flagged_txn_id, t_end, evidence._scaling()), t_end, held, 15)
        hits += g.structural_precedent(a.flagged_txn_id, t_end, held, 10)
        for h in hits:
            assert h["case_id"] not in held, a.case_id
            assert closed[h["case_id"]] < t_end, a.case_id
