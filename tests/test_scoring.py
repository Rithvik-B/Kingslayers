from app.scoring import evaluate, rank_key, score

COMPANY = {
    "crustdata_company_id": 44625,
    "basic_info": {"name": "ITCONS e-Solutions Limited", "primary_domain": "itconsinc.com"},
    "headcount": {"total": 417, "growth_percent": {"1m": 0.97, "3m": 1.21, "6m": 1.21, "12m": 7.2}},
    "locations": {"country": "IND", "headquarters": "Noida, Uttar Pradesh, India"},
    "taxonomy": {"professional_network_industry": "Staffing and Recruiting",
                 "professional_network_industries": ["Staffing and Recruiting", "Administrative and Support Services"]},
}
JOBS = [{"job_details": {"title": "Sr. Recruitment Executive", "url": "https://in.indeed.com/viewjob?jk=x"}}]


def c(**kw):
    base = {"id": "c", "field": "other", "type": "PREFERRED", "operator": "eq", "expected": "any", "weight": 1}
    base.update(kw)
    return base


def test_zero_evaluable_criteria():
    crit = [dict(c(id="a", weight=2), verdict="UNKNOWN"), dict(c(id="b", weight=1), verdict="UNKNOWN")]
    s = score(crit)
    assert s["fit"] is None
    assert s["coverage"] == 0
    assert s["tier"] == "T4"


def test_zero_weights():
    crit = [dict(c(id="a", weight=0), verdict="PASS"), dict(c(id="b", weight=0), verdict="FAIL")]
    s = score(crit)
    assert s["fit"] is None
    assert s["coverage"] == 100  # no preferred weight to cover
    assert s["tier"] == "T4"


def test_mandatory_fail_is_excluded():
    crit = [dict(c(id="m", type="MANDATORY"), verdict="FAIL"), dict(c(id="p"), verdict="PASS")]
    assert score(crit)["tier"] == "EXCLUDED"


def test_mandatory_unknown_is_needs_evidence():
    crit = [dict(c(id="m", type="MANDATORY"), verdict="UNKNOWN"), dict(c(id="p"), verdict="PASS")]
    assert score(crit)["tier"] == "NEEDS_EVIDENCE"


def test_t1_t2_t3():
    assert score([dict(c(id="a"), verdict="PASS"), dict(c(id="b"), verdict="PASS")])["tier"] == "T1"
    s = score([dict(c(id="a", weight=4), verdict="PASS"), dict(c(id="b", weight=1), verdict="FAIL")])
    assert s["fit"] == 80.0 and s["tier"] == "T2"
    s = score([dict(c(id="a", weight=3), verdict="PASS"), dict(c(id="b", weight=2), verdict="FAIL")])
    assert s["fit"] == 60.0 and s["tier"] == "T3"


def test_evaluate_country_normalizes_iso3():
    v, obs, path = evaluate(c(field="country", type="MANDATORY", expected="India"), COMPANY, None)
    assert (v, obs, path) == ("PASS", "IND", "locations.country")
    v, _, _ = evaluate(c(field="country", operator="in", expected=["United States", "Singapore"]), COMPANY, None)
    assert v == "FAIL"


def test_evaluate_headcount_between_and_gte():
    assert evaluate(c(field="headcount", operator="between", expected=[200, 5000]), COMPANY, None)[0] == "PASS"
    assert evaluate(c(field="headcount", operator="between", expected=[1000, None]), COMPANY, None)[0] == "FAIL"
    assert evaluate(c(field="headcount", operator="gte", expected=200), COMPANY, None)[0] == "PASS"
    assert evaluate(c(field="headcount", operator="gte", expected=200), {"headcount": {}}, None)[0] == "UNKNOWN"


def test_evaluate_industry_exact_match_any():
    v, obs, path = evaluate(c(field="industry", operator="in", expected=["staffing and recruiting"]), COMPANY, None)
    assert v == "PASS" and path == "taxonomy.professional_network_industries"
    assert evaluate(c(field="industry", operator="in", expected=["Banking"]), COMPANY, None)[0] == "FAIL"


def test_evaluate_open_roles_and_growth():
    v, obs, _ = evaluate(c(field="open_roles", operator="gte", expected=1), COMPANY, JOBS)
    assert (v, obs) == ("PASS", 1)
    assert evaluate(c(field="open_roles", operator="gte", expected=1), COMPANY, [])[0] == "FAIL"
    assert evaluate(c(field="open_roles", operator="gte", expected=1), COMPANY, None)[0] == "UNKNOWN"
    assert evaluate(c(field="headcount_growth_12m", operator="gte", expected=5), COMPANY, None)[0] == "PASS"
    assert evaluate(c(field="headcount_growth_12m", operator="gte", expected=10), COMPANY, None)[0] == "FAIL"


def test_non_machine_field_is_unknown():
    assert evaluate(c(field="other", type="MANDATORY"), COMPANY, JOBS) == ("UNKNOWN", None, None)
    assert evaluate(c(field="uses_ats"), COMPANY, JOBS) == ("UNKNOWN", None, None)


def test_rank_order():
    rows = [
        {"tier": "T2", "fit": 90, "coverage": 70, "crustdata_id": "b"},
        {"tier": "T1", "fit": 100, "coverage": 100, "crustdata_id": "a"},
        {"tier": "T2", "fit": None, "coverage": 0, "crustdata_id": "c"},
        {"tier": "EXCLUDED", "fit": 100, "coverage": 100, "crustdata_id": "d"},
    ]
    assert [r["crustdata_id"] for r in sorted(rows, key=rank_key)] == ["a", "b", "c", "d"]
