"""Deterministic scoring (P2, PLAN.md §6.3). No LLM here: every verdict is computed from Crustdata fields.

evaluate(constraint, company, jobs) -> (verdict PASS|FAIL|UNKNOWN, observed_value, field_path)
score(criteria) -> {"fit": float | None, "coverage": float, "tier": str}
rank_key(row) -> sort key: tier, then fit (None last), then coverage, then crustdata_id

`company` is the raw /company/search row (docs/notes/crustdata-rest.md). `jobs` is the list of
/job/search rows already filtered by the ICP's job keywords, or None if the job search did not run.
"""
from __future__ import annotations

from typing import Any

MACHINE_FIELDS = ("country", "headcount", "industry", "open_roles", "headcount_growth_12m")
TIER_ORDER = {"T1": 0, "T2": 1, "T3": 2, "T4": 3, "NEEDS_EVIDENCE": 4, "EXCLUDED": 5}

# Crustdata returns locations.country as ISO alpha-3 (e.g. IND) but accepts full names in filters.
_COUNTRY_ALIASES = {
    "ind": "india", "in": "india", "india": "india",
    "usa": "united states", "us": "united states", "united states": "united states",
    "united states of america": "united states",
    "gbr": "united kingdom", "uk": "united kingdom", "gb": "united kingdom", "united kingdom": "united kingdom",
    "sgp": "singapore", "sg": "singapore", "singapore": "singapore",
    "are": "united arab emirates", "uae": "united arab emirates", "ae": "united arab emirates",
    "united arab emirates": "united arab emirates",
    "aus": "australia", "au": "australia", "australia": "australia",
    "can": "canada", "ca": "canada", "canada": "canada",
    "deu": "germany", "de": "germany", "germany": "germany",
}


def is_machine_checkable(field: str | None) -> bool:
    return field in MACHINE_FIELDS


def _norm_country(v: Any) -> str:
    s = str(v or "").strip().lower()
    return _COUNTRY_ALIASES.get(s, s)


def _norm(v: Any) -> str:
    return str(v or "").strip().lower()


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple, set)) else [v]


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _observe(field: str, company: dict, jobs: list[dict] | None) -> tuple[Any, str | None]:
    """The observed value and the Crustdata field path for a machine-checkable field."""
    if field == "country":
        return (company.get("locations") or {}).get("country"), "locations.country"
    if field == "headcount":
        return (company.get("headcount") or {}).get("total"), "headcount.total"
    if field == "headcount_growth_12m":
        return ((company.get("headcount") or {}).get("growth_percent") or {}).get("12m"), "headcount.growth_percent.12m"
    if field == "industry":
        tax = company.get("taxonomy") or {}
        inds = tax.get("professional_network_industries") or _as_list(tax.get("professional_network_industry"))
        return (inds or None), "taxonomy.professional_network_industries"
    if field == "open_roles":
        if jobs is None:
            return None, "job_listings[].job_details.title"
        return len(jobs), "job_listings[].job_details.title"
    return None, None


def _compare(field: str, operator: str, expected: Any, observed: Any) -> str:
    """PASS or FAIL (never UNKNOWN: the caller handles missing observations)."""
    op = (operator or "eq").lower()
    if expected in (None, "any", "", []):
        return "PASS"

    if field == "country":
        exp = {_norm_country(x) for x in _as_list(expected)}
        hit = _norm_country(observed) in exp
        return ("FAIL" if hit else "PASS") if op == "not_in" else ("PASS" if hit else "FAIL")

    if field == "industry":
        exp = {_norm(x) for x in _as_list(expected)}
        obs = {_norm(x) for x in _as_list(observed)}
        if op == "not_in":
            return "FAIL" if obs & exp else "PASS"
        return "PASS" if obs & exp else "FAIL"

    # numeric fields: headcount, headcount_growth_12m, open_roles
    o = _num(observed)
    if o is None:
        return "FAIL"
    if op == "between":
        lo, hi = (list(expected) + [None, None])[:2] if isinstance(expected, (list, tuple)) else (expected, None)
        lo_n, hi_n = _num(lo), _num(hi)
        if lo_n is not None and o < lo_n:
            return "FAIL"
        if hi_n is not None and o > hi_n:
            return "FAIL"
        return "PASS"
    if op == "gte":
        e = _num(expected if not isinstance(expected, (list, tuple)) else expected[0])
        return "PASS" if e is None or o >= e else "FAIL"
    if op == "in":
        return "PASS" if o in {_num(x) for x in _as_list(expected)} else "FAIL"
    if op == "not_in":
        return "FAIL" if o in {_num(x) for x in _as_list(expected)} else "PASS"
    # eq
    e = _num(expected if not isinstance(expected, (list, tuple)) else expected[0])
    return "PASS" if e is not None and o == e else "FAIL"


def evaluate(constraint: dict, company: dict, jobs: list[dict] | None) -> tuple[str, object, str | None]:
    """Returns (verdict, observed_value, field_path). Non-machine-checkable fields are always UNKNOWN."""
    field = constraint.get("field")
    if not is_machine_checkable(field):
        return "UNKNOWN", None, None
    observed, path = _observe(field, company, jobs)
    if observed is None:
        return "UNKNOWN", None, path
    if field == "open_roles" and constraint.get("expected") in (None, "any", ""):
        # "has open roles" defaults to count >= 1
        return ("PASS" if int(observed) >= 1 else "FAIL"), observed, path
    verdict = _compare(field, constraint.get("operator") or "eq", constraint.get("expected"), observed)
    return verdict, observed, path


def score(criteria: list[dict]) -> dict:
    """criteria: [{type: MANDATORY|PREFERRED, weight, verdict: PASS|FAIL|UNKNOWN, ...}]."""
    mandatory = [c for c in criteria if (c.get("type") or "").upper() == "MANDATORY"]
    preferred = [c for c in criteria if (c.get("type") or "").upper() != "MANDATORY"]

    all_pref_weight = sum(max(0.0, _num(c.get("weight")) or 0.0) for c in preferred)
    known = sum(max(0.0, _num(c.get("weight")) or 0.0) for c in preferred if c.get("verdict") in ("PASS", "FAIL"))
    passed = sum(max(0.0, _num(c.get("weight")) or 0.0) for c in preferred if c.get("verdict") == "PASS")

    fit = (100.0 * passed / known) if known > 0 else None
    coverage = (100.0 * known / all_pref_weight) if all_pref_weight > 0 else 100.0

    if any(c.get("verdict") == "FAIL" for c in mandatory):
        tier = "EXCLUDED"
    elif any(c.get("verdict") != "PASS" for c in mandatory):
        tier = "NEEDS_EVIDENCE"
    elif preferred and all(c.get("verdict") == "PASS" for c in preferred) and coverage >= 80:
        tier = "T1"
    elif not preferred:
        tier = "T1"
    elif fit is not None and fit >= 80 and coverage >= 60:
        tier = "T2"
    elif fit is not None and fit >= 60 and coverage >= 50:
        tier = "T3"
    else:
        tier = "T4"

    return {"fit": None if fit is None else round(fit, 1), "coverage": round(coverage, 1), "tier": tier}


def rank_key(row: dict) -> tuple:
    """Sort key for ranking: tier, then fit (None last), then coverage, then crustdata_id."""
    fit = row.get("fit")
    return (
        TIER_ORDER.get(row.get("tier"), 9),
        0 if fit is not None else 1,
        -(fit or 0.0),
        -(row.get("coverage") or 0.0),
        str(row.get("crustdata_id") or ""),
    )
