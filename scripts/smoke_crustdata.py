"""Crustdata REST smoke test (P2). One tiny real call per endpoint the app uses.

Run:  .venv/bin/python scripts/smoke_crustdata.py
Needs CRUSTDATA_API_KEY in .env. Costs about 4 credits in total. Prints the exact response field names and
the X-Credits-Used header so that docs/notes/crustdata-rest.md can be re-checked against the live API.
"""
from __future__ import annotations

import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
KEY = os.environ.get("CRUSTDATA_API_KEY")
if not KEY:
    sys.exit("CRUSTDATA_API_KEY missing: create .env from .env.example first")
BASE = "https://api.crustdata.com"
HEADERS = {
    "Authorization": f"Bearer {KEY}",
    "x-api-version": os.environ.get("CRUSTDATA_API_VERSION", "2025-11-01"),
    "Content-Type": "application/json",
}


def paths(obj, prefix="", out=None):
    """Dotted leaf paths of a JSON object (lists are summarized by their first element)."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            paths(v, f"{prefix}{k}.", out)
    elif isinstance(obj, list):
        if obj:
            paths(obj[0], f"{prefix}[].", out)
        else:
            out.append(prefix.rstrip(".") + " = []")
    else:
        out.append(f"{prefix.rstrip('.')} = {json.dumps(obj)[:60]}")
    return out


def call(client: httpx.Client, path: str, body: dict) -> object:
    r = client.post(BASE + path, headers=HEADERS, json=body, timeout=30)
    print(f"\n=== POST {path} -> {r.status_code}  X-Credits-Used={r.headers.get('X-Credits-Used')}  "
          f"X-Request-Id={r.headers.get('X-Request-Id')}")
    if r.status_code != 200:
        print(r.text[:800])
        return None
    data = r.json()
    if isinstance(data, dict):
        print("top-level keys:", list(data.keys()))
    else:
        print("top-level: array of", len(data))
    for p in paths(data)[:80]:
        print("  ", p)
    return data


def main() -> None:
    with httpx.Client() as c:
        cs = call(c, "/company/search", {
            "search": {"query": "IT services and staffing companies in India hiring recruiters", "mode": "hybrid"},
            "filters": {"op": "and", "conditions": [
                {"field": "locations.country", "type": "=", "value": "India"},
                {"field": "headcount.total", "type": "=>", "value": 200}]},
            "fields": ["crustdata_company_id", "basic_info.name", "basic_info.primary_domain",
                       "basic_info.employee_count_range", "taxonomy.professional_network_industry",
                       "taxonomy.professional_network_industries", "headcount.total", "headcount.growth_percent",
                       "locations.country", "locations.headquarters", "metadata"],
            "limit": 2,
        })
        companies = (cs or {}).get("companies") or []
        if not companies:
            sys.exit("company_search returned nothing; stop here")
        cid = companies[0]["crustdata_company_id"]

        call(c, "/job/search", {
            "filters": {"field": "company.basic_info.company_id", "type": "=", "value": cid},
            "fields": ["crustdata_job_id", "job_details.title", "job_details.url", "job_details.category",
                       "company.basic_info.crustdata_company_id", "company.basic_info.name",
                       "location.country", "location.city", "metadata.date_added"],
            "sorts": [{"field": "metadata.date_added", "order": "desc"}],
            "limit": 2,
        })

        ps = call(c, "/person/search", {
            "filters": {"op": "and", "conditions": [
                {"field": "experience.employment_details.current.company_id", "type": "=", "value": cid},
                {"op": "or", "conditions": [
                    {"field": "experience.employment_details.current.title", "type": "(.)", "value": "talent acquisition"},
                    {"field": "experience.employment_details.current.title", "type": "(.)", "value": "human resources"},
                    {"field": "experience.employment_details.current.title", "type": "(.)", "value": "recruit"}]}]},
            "fields": ["crustdata_person_id", "basic_profile.name", "basic_profile.headline",
                       "basic_profile.current_title", "basic_profile.location", "contact.has_business_email",
                       "social_handles.professional_network_identifier.profile_url",
                       "experience.employment_details.current"],
            "limit": 3,
        })
        profiles = (ps or {}).get("profiles") or []
        with_email = [p for p in profiles if (p.get("contact") or {}).get("has_business_email")]
        pick = (with_email or profiles or [None])[0]
        if not pick:
            print("\nno person found for this company; skipping person_enrich")
            return
        url = pick["social_handles"]["professional_network_identifier"]["profile_url"]
        pe = call(c, "/person/enrich", {
            "professional_network_profile_urls": [url],
            "fields": ["crustdata_person_id", "basic_profile.name", "basic_profile.current_title",
                       "contact.business_emails", "social_handles.professional_network_identifier.profile_url"],
        })
        if pe:
            statuses = [e.get("status") for row in pe for m in row.get("matches", [])
                        for e in ((m.get("person_data") or {}).get("contact") or {}).get("business_emails", [])]
            print("\nbusiness-email statuses seen:", statuses,
                  "(docs: deliverable | catch_all | invalid | unknown)")


if __name__ == "__main__":
    main()
