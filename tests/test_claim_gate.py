from types import SimpleNamespace

from app.drafting import build_body, claim_gate, opt_out_line, profile_field_value

PROFILE = {
    "name": "TalentFlow",
    "category": "AI recruiting software",
    "value_proposition": "Cuts time-to-hire when hiring volume spikes",
    "capabilities": ["Screens applicants", "Coordinates pipelines"],
    "target_departments": ["Talent acquisition"],
    "problems": ["Slow screening"],
}
ALLOWED = {"ev1", "ev2"}


def s(type_, text, evidence_ids=(), profile_field=None):
    return {"type": type_, "text": text, "evidence_ids": list(evidence_ids), "profile_field": profile_field}


def test_uncited_prospect_fact_is_dropped():
    kept, status, notes = claim_gate([
        s("prospect_fact", "You have 12 open recruiter roles.", ["ev1"]),
        s("prospect_fact", "You raised a Series B last month.", ["made-up"]),
        s("cta", "Open to a 20-minute call next week?"),
    ], ALLOWED, PROFILE)
    assert [k["text"] for k in kept] == ["You have 12 open recruiter roles.", "Open to a 20-minute call next week?"]
    assert status == "PASS"
    assert any("uncited" in n for n in notes)


def test_no_prospect_fact_left_is_needs_review():
    kept, status, notes = claim_gate([
        s("prospect_fact", "You raised a Series B.", []),
        s("hypothesis", "Screening might be the bottleneck?"),
        s("cta", "Worth a 20-minute call?"),
    ], ALLOWED, PROFILE)
    assert status == "NEEDS_REVIEW"
    assert [k["type"] for k in kept] == ["hypothesis", "cta"]


def test_no_cta_is_needs_review():
    kept, status, _ = claim_gate([s("prospect_fact", "12 open roles.", ["ev2"])], ALLOWED, PROFILE)
    assert status == "NEEDS_REVIEW" and len(kept) == 1


def test_bad_profile_field_is_dropped():
    kept, status, notes = claim_gate([
        s("prospect_fact", "12 open roles.", ["ev1"]),
        s("product_fact", "TalentFlow integrates with Workday.", [], "integrations[0]"),
        s("product_fact", "TalentFlow screens applicants.", [], "capabilities[0]"),
        s("product_fact", "TalentFlow does magic.", [], "capabilities[7]"),
        s("cta", "20 minutes next week?"),
    ], ALLOWED, PROFILE)
    assert [k["text"] for k in kept] == ["12 open roles.", "TalentFlow screens applicants.", "20 minutes next week?"]
    assert status == "PASS"
    assert sum("unknown profile field" in n for n in notes) == 2


def test_profile_field_value_paths():
    assert profile_field_value(PROFILE, "value_proposition") == PROFILE["value_proposition"]
    assert profile_field_value(PROFILE, "capabilities[1]") == "Coordinates pipelines"
    assert profile_field_value(PROFILE, "capabilities.1") == "Coordinates pipelines"
    assert profile_field_value(PROFILE, "capabilities[2]") is None
    assert profile_field_value(PROFILE, "pricing") is None
    assert profile_field_value({}, "name") is None


def test_opt_out_and_body():
    stand_in = SimpleNamespace(delivery_mode="STAND_IN", consent=None)
    live = SimpleNamespace(delivery_mode="LIVE", consent={"sender_name": "Asha Rao", "postal_address": "12 MG Road, Bengaluru"})
    assert opt_out_line(stand_in) == "If this isn't relevant, just reply 'remove me' and I won't email again."
    assert opt_out_line(live).endswith("Asha Rao, 12 MG Road, Bengaluru")
    body = build_body("Priya Nair", [s("prospect_fact", "A.", ["ev1"]), s("cta", "B?")], stand_in)
    assert body.startswith("Hi Priya,\n\nA. B?\n\nIf this isn't relevant")
