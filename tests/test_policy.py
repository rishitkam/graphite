from graphite.policy import Assessment, Reply, actions, file_report, should_stop, route


def names(acts):
    return [a["action"] for a in acts]


def test_routes_follow_section_2():
    assert route("DECLINE_TRANSACTION", 100) == "L1"
    assert route("BLOCK_CARD", 2500) == "L1"
    assert route("BLOCK_CARD", 2500.01) == "L2"
    assert route("BLOCK_ALL_CARDS", 10) == "L2"
    assert route("FILE_REPORT", 10) == "L2"
    assert route("CREATE_CASE", 10**6) == "auto"


def test_r1_weak_signal_verifies_before_any_block():
    a = Assessment(fraud_probability=0.45, exposure_usd=80, independent_evidence=1)
    acts = names(actions(a))
    assert "VERIFY_WITH_CUSTOMER" in acts
    assert "BLOCK_CARD" not in acts
    assert "CREATE_CASE" in acts  # 3a: evidence requested and p >= 0.30


def test_3b_example_denial_flips_to_block_and_case():
    a = Assessment(fraud_probability=0.80, exposure_usd=80, independent_evidence=2, reply=Reply.DENIED)
    acts = names(actions(a))
    assert acts[:2] == ["BLOCK_CARD", "CREATE_CASE"]
    assert "FILE_REPORT" not in acts  # under $1,000 and nothing shared


def test_r2_denial_with_shared_device_files_report():
    a = Assessment(fraud_probability=0.86, exposure_usd=268.43, independent_evidence=3,
                   reply=Reply.DENIED, card_testing=True, large_purchase_cleared=True,
                   shared_origin="device SAMSUNG SM-G892A", connected_cards=["C00877-K1"])
    acts = actions(a)
    by_name = {x["action"]: x for x in acts}
    assert by_name["BLOCK_CARD"]["route"] == "L1"
    assert by_name["FILE_REPORT"]["route"] == "L2"
    assert "MONITOR_CONNECTED_CARDS" in by_name


def test_r3_confirmation_closes():
    a = Assessment(fraud_probability=0.10, exposure_usd=0, independent_evidence=2, reply=Reply.CONFIRMED)
    assert names(actions(a)) == ["CLOSE_NO_FRAUD"]


def test_r4_no_reply_escalates_over_500():
    a = Assessment(fraud_probability=0.55, exposure_usd=620, independent_evidence=1, reply=Reply.NO_REPLY)
    acts = names(actions(a))
    assert acts[:2] == ["MONITOR_CARD", "DECLINE_TRANSACTION"]
    assert "ESCALATE_TO_ANALYST" in acts


def test_r7_recurring_dispute_never_blocks():
    a = Assessment(fraud_probability=0.20, exposure_usd=49, independent_evidence=2,
                   customer_disputed=True, recurring_match=True)
    acts = names(actions(a))
    assert acts == ["CREATE_CASE", "VERIFY_WITH_CUSTOMER", "WARN_CUSTOMER"]


def test_r9_undocumented_coordinated():
    a = Assessment(fraud_probability=0.88, exposure_usd=300, independent_evidence=3,
                   pattern="undocumented", coordinated=True)
    acts = names(actions(a))
    assert {"CREATE_CASE", "FILE_REPORT", "ESCALATE_TO_ANALYST"} <= set(acts)


def test_r10_never_block_all_on_one_card():
    a = Assessment(fraud_probability=0.95, exposure_usd=900, independent_evidence=3,
                   reply=Reply.DENIED, customer_cards_confirmed_fraud=1)
    assert "BLOCK_ALL_CARDS" not in names(actions(a))


def test_stopping_needs_two_independent_pieces():
    assert should_stop(Assessment(0.90, 100, 1)) == (False, "")
    assert should_stop(Assessment(0.90, 100, 2))[0]
    assert should_stop(Assessment(0.10, 0, 2))[0]
    assert not should_stop(Assessment(0.50, 100, 5))[0]


def test_report_needs_strong_suspicion_first():
    assert file_report(Assessment(0.40, 5000, 1))[0] is False
    assert file_report(Assessment(0.90, 1200, 2))[0] is True
