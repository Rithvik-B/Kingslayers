"""Crustdata REST client (P2, PLAN.md §6.2). Field names come from docs/notes/crustdata-rest.md; none are guessed.

Endpoints: POST /company/search, /job/search, /person/search, /person/enrich on https://api.crustdata.com.
/person/contact/enrich is disabled on our key, so business emails come from /person/enrich with
fields=["contact.business_emails"].

Credits: read from the X-Credits-Used response header when present, otherwise estimated per result.
CreditCeilingReached is raised as soon as credits_used passes S.CREDIT_CEILING_PER_RUN.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import S

log = logging.getLogger(__name__)

BASE_URL = "https://api.crustdata.com"
TIMEOUT_S = 15.0
ENRICH_SPACING_S = 4.2  # /person/enrich is limited to 15 requests per minute

# Response whitelists (each group costs per result; see the notes for the price sheet).
COMPANY_FIELDS = [
    "crustdata_company_id", "basic_info.name", "basic_info.primary_domain", "basic_info.employee_count_range",
    "basic_info.description", "taxonomy.professional_network_industry", "taxonomy.professional_network_industries",
    "headcount.total", "headcount.growth_percent", "headcount.growth_absolute",
    "locations.country", "locations.headquarters", "locations.state", "metadata",
]
JOB_FIELDS = [
    "crustdata_job_id", "job_details.title", "job_details.url", "job_details.category",
    "company.basic_info.crustdata_company_id", "company.basic_info.name",
    "location.country", "location.city", "metadata.date_added",
]
PERSON_FIELDS = [
    "crustdata_person_id", "basic_profile.name", "basic_profile.headline", "basic_profile.current_title",
    "basic_profile.location", "contact.has_business_email",
    "social_handles.professional_network_identifier.profile_url", "experience.employment_details.current",
]
ENRICH_FIELDS = [
    "crustdata_person_id", "basic_profile.name", "basic_profile.current_title", "contact.business_emails",
    "social_handles.professional_network_identifier.profile_url",
]

# Per-result estimates, used only when the X-Credits-Used header is missing.
EST_COMPANY = 0.33   # base 0.03 + headcount 0.2 + taxonomy 0.1
EST_JOB = 0.03
EST_PERSON = 0.23    # base + experience group
EST_ENRICH = 2.0     # base 1 + business email 1


class CrustdataError(Exception):
    """A non-retryable or twice-failed Crustdata call."""


class CreditCeilingReached(Exception):
    """credits_used passed S.CREDIT_CEILING_PER_RUN; discovery stops and keeps what's done."""


def cond(field: str, op: str, value: Any) -> dict:
    return {"field": field, "type": op, "value": value}


def group(op: str, conditions: list[dict]) -> dict | None:
    conditions = [c for c in conditions if c]
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"op": op, "conditions": conditions}


def company_id_of(company: dict) -> int | None:
    """The Crustdata company id of a raw /company/search row (or of our stored `raw` JSON)."""
    cid = company.get("crustdata_company_id")
    if cid is None:
        cid = (company.get("basic_info") or {}).get("crustdata_company_id")
    try:
        return int(cid) if cid is not None else None
    except (TypeError, ValueError):
        return None


class CrustdataClient:
    def __init__(self) -> None:
        self.credits_used: float = 0.0
        self.requests: int = 0
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT_S)
        self._enrich_lock = asyncio.Lock()
        self._last_enrich_at = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    # ----------------------------------------------------------------------------- transport

    def _headers(self) -> dict:
        if not S.CRUSTDATA_API_KEY:
            raise CrustdataError("CRUSTDATA_API_KEY is not set")
        return {
            "Authorization": f"Bearer {S.CRUSTDATA_API_KEY}",
            "x-api-version": S.CRUSTDATA_API_VERSION or "2025-11-01",
            "Content-Type": "application/json",
        }

    def _check_ceiling(self) -> None:
        if self.credits_used > float(S.CREDIT_CEILING_PER_RUN):
            raise CreditCeilingReached(
                f"credits_used {self.credits_used:.2f} > ceiling {S.CREDIT_CEILING_PER_RUN}")

    async def _post(self, path: str, body: dict, *, estimate: float, count_results) -> Any:
        """POST with a 15 s timeout; one retry on 429/5xx/timeouts with backoff. Returns the parsed JSON."""
        self._check_ceiling()
        last: Exception | None = None
        for attempt in (1, 2):
            try:
                r = await self._http.post(path, json=body, headers=self._headers())
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = e
                log.warning("crustdata %s attempt %d transport error: %s", path, attempt, e)
            else:
                if r.status_code == 200:
                    data = r.json()
                    header = r.headers.get("X-Credits-Used")
                    try:
                        credits = float(header) if header not in (None, "") else estimate * count_results(data)
                    except ValueError:
                        credits = estimate * count_results(data)
                    self.credits_used += credits
                    self.requests += 1
                    log.info("crustdata %s ok credits=%.2f total=%.2f req=%s", path, credits, self.credits_used,
                             r.headers.get("X-Request-Id"))
                    self._check_ceiling()
                    return data
                if r.status_code == 429 or r.status_code >= 500:
                    last = CrustdataError(f"{path} -> {r.status_code}: {r.text[:300]}")
                    log.warning("crustdata %s attempt %d: %s", path, attempt, last)
                    if attempt == 1:
                        retry_after = r.headers.get("Retry-After")
                        try:
                            await asyncio.sleep(min(float(retry_after), 30.0) if retry_after else 2.0)
                        except ValueError:
                            await asyncio.sleep(2.0)
                        continue
                else:
                    raise CrustdataError(f"{path} -> {r.status_code}: {r.text[:500]}")
            if attempt == 1:
                await asyncio.sleep(1.5)
        raise CrustdataError(f"{path} failed twice: {last}")

    # ----------------------------------------------------------------------------- endpoints

    async def company_search(self, *, query: str, filters: dict | None, limit: int) -> list[dict]:
        """Ranked natural-language search with optional hard filters. `filters` is a Crustdata condition or
        group (see cond()/group()). Returns the raw `companies` rows. limit is capped at 100 by the API."""
        body: dict = {"fields": COMPANY_FIELDS, "limit": max(1, min(int(limit), 100))}
        if query and query.strip():
            body["search"] = {"query": query.strip(), "mode": "hybrid"}
        if filters:
            body["filters"] = filters
        if "search" not in body and "filters" not in body:
            raise CrustdataError("company_search needs a query or filters")
        data = await self._post("/company/search", body, estimate=EST_COMPANY,
                                count_results=lambda d: len(d.get("companies") or []))
        return list(data.get("companies") or [])

    async def job_search(self, *, company: dict, keywords: list[str], limit: int = 10) -> list[dict]:
        """Open job postings at `company` whose title fuzzy-matches any keyword (all postings if no keywords).
        Newest first. Returns the raw `job_listings` rows."""
        cid = company_id_of(company)
        if cid is None:
            raise CrustdataError("job_search: company has no crustdata_company_id")
        title_or = group("or", [cond("job_details.title", "(.)", k) for k in keywords if k and k.strip()])
        filters = group("and", [cond("company.basic_info.company_id", "=", cid), title_or])
        body = {"filters": filters, "fields": JOB_FIELDS,
                "sorts": [{"field": "metadata.date_added", "order": "desc"}],
                "limit": max(1, min(int(limit), 100))}
        data = await self._post("/job/search", body, estimate=EST_JOB,
                                count_results=lambda d: len(d.get("job_listings") or []))
        return list(data.get("job_listings") or [])

    async def job_search_many(self, *, companies: list[dict], keywords: list[str], limit: int = 300) -> tuple[dict[int, list[dict]], bool]:
        """One /job/search over many companies (`in` filter, newest first). Returns ({company_id: jobs}, complete)
        where complete is True when total_count <= limit, i.e. every matching posting came back and an absent
        company really has zero matching roles. Saves 59 calls against the 30 rpm limit for a 60-company run."""
        ids = [i for i in (company_id_of(c) for c in companies) if i is not None]
        if not ids:
            return {}, True
        title_or = group("or", [cond("job_details.title", "(.)", k) for k in keywords if k and k.strip()])
        filters = group("and", [cond("company.basic_info.company_id", "in", ids), title_or])
        body = {"filters": filters, "fields": JOB_FIELDS,
                "sorts": [{"field": "metadata.date_added", "order": "desc"}],
                "limit": max(1, min(int(limit), 1000))}
        data = await self._post("/job/search", body, estimate=EST_JOB,
                                count_results=lambda d: len(d.get("job_listings") or []))
        jobs = list(data.get("job_listings") or [])
        by_company: dict[int, list[dict]] = {i: [] for i in ids}
        for j in jobs:
            cid = company_id_of(j.get("company") or {})
            if cid in by_company:
                by_company[cid].append(j)
        total = data.get("total_count")
        complete = total is not None and int(total) <= len(jobs)
        return by_company, complete

    async def person_search(self, *, company: dict, titles: list[str], limit: int = 5,
                            verified_only: bool = False) -> list[dict]:
        """People currently at `company` whose current title fuzzy-matches any of `titles`.
        verified_only adds the filter experience.employment_details.current.business_email_verified = true, so
        the people returned already have a verified business email at this employer (enrich then returns
        status deliverable). Returns the raw `profiles` rows (with contact.has_business_email and the profile_url)."""
        cid = company_id_of(company)
        if cid is None:
            raise CrustdataError("person_search: company has no crustdata_company_id")
        title_or = group("or", [cond("experience.employment_details.current.title", "(.)", t)
                                for t in titles if t and t.strip()])
        verified = cond("experience.employment_details.current.business_email_verified", "=", True) if verified_only else None
        filters = group("and", [cond("experience.employment_details.current.company_id", "=", cid), verified, title_or])
        body = {"filters": filters, "fields": PERSON_FIELDS, "limit": max(1, min(int(limit), 100))}
        data = await self._post("/person/search", body, estimate=EST_PERSON,
                                count_results=lambda d: len(d.get("profiles") or []))
        return list(data.get("profiles") or [])

    async def person_enrich(self, *, linkedin_url: str) -> dict:
        """Enrich one person with contact.business_emails. Spaced 4.2 s apart (15 rpm).
        Returns the entry for this URL: {"matched_on", "match_type", "match_status", "matches": [...]}."""
        async with self._enrich_lock:
            wait = self._last_enrich_at + ENRICH_SPACING_S - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_enrich_at = time.monotonic()
            body = {"professional_network_profile_urls": [linkedin_url], "fields": ENRICH_FIELDS}
            data = await self._post("/person/enrich", body, estimate=EST_ENRICH,
                                    count_results=lambda d: sum(1 for row in (d or []) if row.get("matches")))
        rows = data if isinstance(data, list) else []
        return rows[0] if rows else {"matched_on": linkedin_url, "match_status": "not_found", "matches": []}


# ----------------------------------------------------------------------------- response accessors

def business_emails(enrich_entry: dict) -> list[dict]:
    """[{email, status, crustdata_company_id, last_updated}] from a person_enrich entry (empty if none)."""
    for m in enrich_entry.get("matches") or []:
        contact = (m.get("person_data") or {}).get("contact") or {}
        emails = contact.get("business_emails") or []
        if emails:
            return list(emails)
    return []


def profile_url(person: dict) -> str | None:
    return ((person.get("social_handles") or {}).get("professional_network_identifier") or {}).get("profile_url")
