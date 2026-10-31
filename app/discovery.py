"""ICP generation and the discovery pipeline (P2, PLAN.md §6.4).

generate_profile_and_icp(campaign_id): one LLM call, then writes product.profile, gtm.icp and voice.style to
    seller-wide memory (source agent:discovery). Non-machine-checkable constraints are forced to PREFERRED.
run_discovery(campaign_id): reads gtm.icp from memory now, finds companies on live Crustdata, scores them
    deterministically with a receipt (evidence row) for every observed field, finds and enriches contacts,
    picks the featured contact, then calls drafting.generate_drafts. Journals every stage.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app import drafting, journal, llm, memory, scoring
from app.config import S
from app.crustdata import (CreditCeilingReached, CrustdataClient, CrustdataError, business_emails, company_id_of,
                           cond, group, profile_url)
from app.db import session
from app.models import Campaign, Company, Contact, Evidence, Message

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------------- ICP generation

_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": _STR}
_EXPECTED = {"anyOf": [{"type": "string"}, {"type": "number"},
                       {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "null"}]}}]}

CONSTRAINT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": _STR,
        "field": {"type": "string", "enum": ["country", "headcount", "industry", "open_roles", "headcount_growth_12m", "other"]},
        "type": {"type": "string", "enum": ["MANDATORY", "PREFERRED"]},
        "operator": {"type": "string", "enum": ["eq", "in", "between", "gte"]},
        "expected": _EXPECTED,
        "weight": {"type": "number"},
        "importance": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
        "relaxable": {"type": "boolean"},
        "rationale": _STR,
    },
    "required": ["id", "field", "type", "operator", "expected", "weight", "importance", "relaxable", "rationale"],
    "additionalProperties": False,
}

ICP_SCHEMA = {
    "type": "object",
    "properties": {
        "product_profile": {
            "type": "object",
            "properties": {"name": _STR, "category": _STR, "value_proposition": _STR, "capabilities": _STR_LIST,
                           "target_departments": _STR_LIST, "problems": _STR_LIST},
            "required": ["name", "category", "value_proposition", "capabilities", "target_departments", "problems"],
            "additionalProperties": False,
        },
        "voice": {
            "type": "object",
            "properties": {"tone": _STR, "max_words": {"type": "integer"}, "avoid": _STR_LIST},
            "required": ["tone", "max_words", "avoid"],
            "additionalProperties": False,
        },
        "icp": {
            "type": "object",
            "properties": {"nl_query": _STR, "person_titles": _STR_LIST, "job_keywords": _STR_LIST,
                           "constraints": {"type": "array", "items": CONSTRAINT_SCHEMA}},
            "required": ["nl_query", "person_titles", "job_keywords", "constraints"],
            "additionalProperties": False,
        },
    },
    "required": ["product_profile", "voice", "icp"],
    "additionalProperties": False,
}

ICP_SYSTEM = """You are a B2B go-to-market analyst. From a seller's product description you produce a product profile,
a writing voice for cold emails, and an Ideal Customer Profile (ICP) that a program will run against Crustdata's
company database. Output only JSON matching the schema.

Machine-checkable constraint fields (the program can verify these from Crustdata data):
- country: expected is a full country name such as "India" (operator eq, or in with a list).
- headcount: operator between with expected [min, max] (max may be null), or gte with a number.
- industry: operator in with a list of LinkedIn industry names, e.g. "IT Services and IT Consulting",
  "Staffing and Recruiting", "Software Development", "Financial Services", "Hospitals and Health Care",
  "Retail", "Manufacturing", "Banking", "Insurance", "Telecommunications", "Pharmaceutical Manufacturing".
  Matching is exact, so list several plausible names.
- open_roles: operator gte with a number; counts current job postings whose title matches job_keywords.
- headcount_growth_12m: operator gte with a percent number (12-month headcount growth).
Any other criterion uses field "other" and cannot be MANDATORY.

Rules: 2 to 6 constraints. Use MANDATORY only for hard requirements stated or clearly implied by the product
(for example the market country and the minimum company size). Weights are 1 to 5. importance low + relaxable
true marks a preference the program may drop if too few companies qualify. nl_query is a plain-language
description of the target companies (what they do, where, their situation). person_titles are 4 to 8 job titles
of the buyer or champion to search for. job_keywords are 2 to 5 words that appear in the titles of the job
postings that signal the pain the product solves. voice.max_words is 90 to 110. Invent no customers or metrics."""


def _normalize_icp(icp: dict) -> tuple[dict, int]:
    """Force non-machine-checkable constraints to PREFERRED and label them. Returns (icp, machine_count)."""
    seen: set[str] = set()
    machine = 0
    for i, c in enumerate(icp.get("constraints") or []):
        cid = str(c.get("id") or f"c{i + 1}").strip() or f"c{i + 1}"
        while cid in seen:
            cid += "_"
        seen.add(cid)
        c["id"] = cid
        try:
            c["weight"] = max(0.0, float(c.get("weight", 1)))
        except (TypeError, ValueError):
            c["weight"] = 1.0
        if scoring.is_machine_checkable(c.get("field")):
            machine += 1
        else:
            c["field"] = "other"
            c["type"] = "PREFERRED"
            r = str(c.get("rationale") or "")
            if not r.lower().startswith("not machine-checkable"):
                c["rationale"] = f"not machine-checkable: {r}".rstrip(": ")
    icp["person_titles"] = [t for t in (icp.get("person_titles") or []) if t and t.strip()]
    icp["job_keywords"] = [k for k in (icp.get("job_keywords") or []) if k and k.strip()]
    return icp, machine


async def generate_profile_and_icp(campaign_id: str) -> None:
    with session() as s:
        camp = s.get(Campaign, campaign_id)
        if camp is None:
            raise ValueError(f"campaign {campaign_id} not found")
        product_text = camp.product_text
    journal.log(campaign_id, "icp", "Generating product profile, ICP and voice from the product description")
    out = await llm.complete_json(ICP_SYSTEM, f"Product description:\n\n{product_text}", ICP_SCHEMA)
    profile = out["product_profile"]
    voice = out["voice"]
    voice["max_words"] = int(voice.get("max_words") or 110)
    icp, machine = _normalize_icp(out["icp"])
    n = len(icp["constraints"])

    memory.put(None, "product.profile", profile, kind="profile", source="agent:discovery",
               rationale="Inferred from the product description; drives which product claims drafts may make.")
    memory.put(None, "gtm.icp", icp, kind="icp", source="agent:discovery",
               rationale=f"Inferred from the product description: {machine} of {n} constraints are machine-checkable.")
    memory.put(None, "voice.style", voice, kind="voice", source="agent:discovery",
               rationale="Tone and length inferred from the product and audience.")
    journal.log(campaign_id, "icp",
                f"Profile, ICP and voice saved to memory: {n} constraints ({machine} machine-checkable), "
                f"{len(icp['person_titles'])} titles, {len(icp['job_keywords'])} job keywords",
                data={"nl_query": icp.get("nl_query")})


# ----------------------------------------------------------------------------- discovery pipeline

_ECON_BUYER = ("chro", "chief people", "chief human", "vp people", "vp, people", "vp of people", "vice president people",
               "vice president, people", "vice president of people", "chief talent", "cpo", "head of people")
_CHAMPION_LEVEL = ("head", "vp", "vice president", "director", "lead", "manager")
_CHAMPION_AREA = ("talent", "recruit", "hr", "human resource", "people", "hiring")


def role_for_title(title: str) -> str:
    t = f" {(title or '').lower()} "
    if any(k in t for k in _ECON_BUYER):
        return "ECONOMIC_BUYER"
    if any(k in t for k in _CHAMPION_LEVEL) and any(k in t for k in _CHAMPION_AREA):
        return "CHAMPION"
    return "OTHER"


def _company_filters(icp: dict) -> dict | None:
    """Mandatory country and headcount constraints become Crustdata hard filters."""
    conds: list[dict] = []
    for c in icp.get("constraints") or []:
        if (c.get("type") or "").upper() != "MANDATORY":
            continue
        f, op, exp = c.get("field"), (c.get("operator") or "eq").lower(), c.get("expected")
        if f == "country" and exp not in (None, "any", ""):
            vals = exp if isinstance(exp, list) else [exp]
            conds.append(cond("locations.country", "in" if len(vals) > 1 else "=", vals if len(vals) > 1 else vals[0]))
        elif f == "headcount":
            if op == "between" and isinstance(exp, list):
                lo = exp[0] if len(exp) > 0 else None
                hi = exp[1] if len(exp) > 1 else None
                if lo is not None:
                    conds.append(cond("headcount.total", "=>", lo))
                if hi is not None:
                    conds.append(cond("headcount.total", "=<", hi))
            elif op == "gte" and exp not in (None, "any", ""):
                conds.append(cond("headcount.total", "=>", exp if not isinstance(exp, list) else exp[0]))
    return group("and", conds)


def _add_evidence(s, campaign_id: str, subject_type: str, subject_id: str, endpoint: str, field_path: str,
                  value: Any, raw_excerpt: Any, source_url: str | None = None) -> str:
    ev = Evidence(campaign_id=campaign_id, subject_type=subject_type, subject_id=subject_id, endpoint=endpoint,
                  field_path=field_path, value=json.dumps(value) if not isinstance(value, str) else value,
                  source_url=source_url, raw_excerpt=raw_excerpt, retrieved_at=datetime.now(timezone.utc))
    s.add(ev)
    s.flush()
    return ev.id


def _evaluate_all(constraints: list[dict], company: dict, jobs: list[dict] | None) -> list[dict]:
    out = []
    for c in constraints:
        verdict, observed, path = scoring.evaluate(c, company, jobs)
        out.append({"constraint_id": c["id"], "field": c.get("field"), "type": c.get("type"),
                    "weight": c.get("weight", 1), "importance": c.get("importance"),
                    "relaxable": bool(c.get("relaxable")), "verdict": verdict, "observed": observed,
                    "field_path": path, "evidence_id": None})
    return out


def _set_status(campaign_id: str, status: str, **extra) -> None:
    with session() as s:
        camp = s.get(Campaign, campaign_id)
        camp.status = status
        for k, v in extra.items():
            setattr(camp, k, v)


def _clear_previous(campaign_id: str) -> None:
    """A re-run replaces the previous discovery: companies, evidence, un-emailed contacts and their drafts."""
    with session() as s:
        keep = {c.id for c in s.scalars(select(Contact).where(Contact.campaign_id == campaign_id,
                                                               Contact.thread_id.is_not(None))).all()}
        gone = [c.id for c in s.scalars(select(Contact).where(Contact.campaign_id == campaign_id)).all()
                if c.id not in keep]
        if gone:
            s.execute(delete(Message).where(Message.contact_id.in_(gone), Message.status.in_(["DRAFT", "HELD"])))
            s.execute(delete(Contact).where(Contact.id.in_(gone)))
        s.execute(delete(Evidence).where(Evidence.campaign_id == campaign_id))
        s.execute(delete(Company).where(Company.campaign_id == campaign_id))


async def run_discovery(campaign_id: str) -> None:
    with session() as s:
        camp = s.get(Campaign, campaign_id)
        if camp is None:
            raise ValueError(f"campaign {campaign_id} not found")
        if not camp.icp_approved:
            raise ValueError("ICP not approved")
        delivery_mode = camp.delivery_mode

    limit = int(S.DISCOVERY_COMPANY_LIMIT)
    _clear_previous(campaign_id)
    _set_status(campaign_id, "DISCOVERING")

    # 1. live read of the ICP, so a seller's edit applies to this run
    icp = memory.get(campaign_id, "gtm.icp")
    if not icp:
        _set_status(campaign_id, "FAILED")
        journal.log(campaign_id, "error", "No ICP in memory (gtm.icp); generate it first")
        return
    constraints = list(icp.get("constraints") or [])
    keywords = list(icp.get("job_keywords") or [])
    titles = list(icp.get("person_titles") or [])
    journal.log(campaign_id, "discovery", f"Discovery started on live Crustdata: target {limit} companies",
                data={"nl_query": icp.get("nl_query"), "constraints": [c["id"] for c in constraints]})

    client = CrustdataClient()
    try:
        # 2. company search
        search_limit = min(3 * limit, 60)
        filters = _company_filters(icp)
        companies = await client.company_search(query=icp.get("nl_query") or "", filters=filters, limit=search_limit)
        journal.log(campaign_id, "discovery", f"/company/search returned {len(companies)} companies "
                    f"({client.credits_used:.1f} credits so far)", data={"filters": filters})
        if not companies:
            _set_status(campaign_id, "READY", discovery_ran_at=datetime.now(timezone.utc), credits_used=client.credits_used)
            journal.log(campaign_id, "warning", "No companies matched; edit gtm.icp in Memory and re-run")
            return

        # 3. job postings: one batched call, then per-company calls only for the companies it could not cover
        jobs_by_id: dict[int, list[dict] | None] = {}
        try:
            batched, complete = await client.job_search_many(companies=companies, keywords=keywords, limit=300)
            jobs_by_id.update(batched)
            if not complete:
                missing = [c for c in companies if not batched.get(company_id_of(c))]
                sem = asyncio.Semaphore(5)

                async def one(c):
                    async with sem:
                        try:
                            return company_id_of(c), await client.job_search(company=c, keywords=keywords, limit=10)
                        except CreditCeilingReached:
                            raise
                        except CrustdataError as e:
                            log.warning("job_search failed for %s: %s", company_id_of(c), e)
                            return company_id_of(c), None

                for cid, jobs in await asyncio.gather(*(one(c) for c in missing)):
                    jobs_by_id[cid] = jobs
        except CreditCeilingReached:
            raise
        except CrustdataError as e:
            log.warning("batched job_search failed: %s", e)
            jobs_by_id = {company_id_of(c): None for c in companies}
        n_with_jobs = sum(1 for v in jobs_by_id.values() if v)
        journal.log(campaign_id, "discovery", f"/job/search: {n_with_jobs} of {len(companies)} companies have matching "
                    f"open roles ({client.credits_used:.1f} credits so far)")

        # 4. evaluate, score, shortfall
        evaluated = [(c, _evaluate_all(constraints, c, jobs_by_id.get(company_id_of(c)))) for c in companies]

        def qualified(rows):
            return [r for r in rows if scoring.score(r[1])["tier"] in ("T1", "T2", "T3")]

        dropped: list[str] = []
        if len(qualified(evaluated)) < limit:
            dropped = [c["id"] for c in constraints if (c.get("type") or "").upper() == "PREFERRED"
                       and c.get("relaxable") and (c.get("importance") or "").lower() == "low"]
            if dropped:
                evaluated = [(c, [r for r in crit if r["constraint_id"] not in dropped]) for c, crit in evaluated]
                memory.record_decision(campaign_id, "decision.shortfall_relaxed", {"dropped": dropped},
                                       source="agent:discovery",
                                       rationale=f"Fewer than {limit} companies qualified, so the low-importance "
                                                 f"relaxable preferences were dropped for this run")
                journal.log(campaign_id, "decision", f"Shortfall: relaxed {', '.join(dropped)}")

        # write companies + evidence
        rows: list[dict] = []
        with session() as s:
            for raw, crit in evaluated:
                sc = scoring.score(crit)
                cid = company_id_of(raw)
                jobs = jobs_by_id.get(cid)
                bi, hc, loc, tax = (raw.get("basic_info") or {}), (raw.get("headcount") or {}), \
                    (raw.get("locations") or {}), (raw.get("taxonomy") or {})
                growth = (hc.get("growth_percent") or {}).get("12m")
                inds = tax.get("professional_network_industries") or []
                company = Company(
                    campaign_id=campaign_id, crustdata_id=str(cid), name=bi.get("name") or f"company {cid}",
                    domain=bi.get("primary_domain"), industry=(tax.get("professional_network_industry") or (inds[0] if inds else None)),
                    country=loc.get("country"), city=None, headcount=hc.get("total"),
                    headcount_growth_12m=growth, fit=sc["fit"], coverage=sc["coverage"], tier=sc["tier"],
                    why_now=[], criteria=[], raw=raw)
                s.add(company)
                s.flush()
                ev_ids: dict[str, str] = {}
                if loc.get("country") is not None:
                    ev_ids["locations.country"] = _add_evidence(s, campaign_id, "company", company.id, "/company/search",
                                                                "locations.country", loc["country"], {"locations": loc})
                if hc.get("total") is not None:
                    ev_ids["headcount.total"] = _add_evidence(s, campaign_id, "company", company.id, "/company/search",
                                                              "headcount.total", hc["total"], {"headcount": {"total": hc["total"]}})
                if growth is not None:
                    ev_ids["headcount.growth_percent.12m"] = _add_evidence(
                        s, campaign_id, "company", company.id, "/company/search", "headcount.growth_percent.12m",
                        round(float(growth), 1), {"headcount": {"growth_percent": hc.get("growth_percent")},
                                                  "growth_calculation_date": (raw.get("metadata") or {}).get("growth_calculation_date")})
                if inds or tax.get("professional_network_industry"):
                    ev_ids["taxonomy.professional_network_industries"] = _add_evidence(
                        s, campaign_id, "company", company.id, "/company/search", "taxonomy.professional_network_industries",
                        inds or [tax.get("professional_network_industry")], {"taxonomy": tax})
                if jobs is not None:
                    excerpt = [{"title": (j.get("job_details") or {}).get("title"), "url": (j.get("job_details") or {}).get("url"),
                                "date_added": (j.get("metadata") or {}).get("date_added")} for j in jobs[:10]]
                    ev_ids["job_listings[].job_details.title"] = _add_evidence(
                        s, campaign_id, "company", company.id, "/job/search", "job_listings[].job_details.title",
                        f"{len(jobs)} open role(s) matching {', '.join(keywords) or 'any title'}"
                        + (": " + "; ".join(e["title"] for e in excerpt[:3] if e["title"]) if excerpt else ""),
                        {"keywords": keywords, "count": len(jobs), "job_listings": excerpt},
                        source_url=(excerpt[0]["url"] if excerpt and excerpt[0].get("url") else None))
                for r in crit:
                    r["evidence_id"] = ev_ids.get(r.get("field_path") or "")
                why_now = []
                if jobs:
                    why_now.append({"label": f"{len(jobs)} open {keywords[0] if keywords else 'hiring'} role{'s' if len(jobs) != 1 else ''}",
                                    "evidence_id": ev_ids.get("job_listings[].job_details.title")})
                if growth is not None and float(growth) > 0:
                    why_now.append({"label": f"+{float(growth):.0f}% headcount in 12m",
                                    "evidence_id": ev_ids.get("headcount.growth_percent.12m")})
                company.criteria = crit
                company.why_now = why_now
                rows.append({"id": company.id, "crustdata_id": str(cid), "name": company.name, "tier": sc["tier"],
                             "fit": sc["fit"], "coverage": sc["coverage"], "raw": raw})
            # ranking
            rows.sort(key=scoring.rank_key)
            rank = 0
            for r in rows:
                comp = s.get(Company, r["id"])
                if r["tier"] in ("EXCLUDED", "NEEDS_EVIDENCE"):
                    comp.rank = None
                else:
                    rank += 1
                    comp.rank = rank
                    r["rank"] = rank
        n_q = sum(1 for r in rows if r["tier"] in ("T1", "T2", "T3"))
        eligible = [r for r in rows if r["tier"] not in ("EXCLUDED", "NEEDS_EVIDENCE")]
        journal.log(campaign_id, "discovery", f"Scored {len(rows)} companies: {limit} target · {n_q} qualified "
                    f"(T1–T3), {len(eligible)} eligible, {sum(1 for r in rows if r['tier'] == 'EXCLUDED')} excluded, "
                    f"{sum(1 for r in rows if r['tier'] == 'NEEDS_EVIDENCE')} need evidence",
                    data={"dropped": dropped})

        # 6. people at the top companies
        top = eligible[:limit]
        sem = asyncio.Semaphore(5)

        async def people(r):
            async with sem:
                try:
                    return r, await client.person_search(company=r["raw"], titles=titles, limit=5)
                except CreditCeilingReached:
                    raise
                except CrustdataError as e:
                    log.warning("person_search failed for %s: %s", r["name"], e)
                    return r, []

        found = await asyncio.gather(*(people(r) for r in top))
        role_rank = {"CHAMPION": 0, "ECONOMIC_BUYER": 0, "OTHER": 1}
        contact_ids: list[tuple[str, dict]] = []  # (contact_id, person row)
        with session() as s:
            for r, persons in found:
                persons = sorted(persons, key=lambda p: (0 if (p.get("contact") or {}).get("has_business_email") else 1,
                                                         role_rank[role_for_title((p.get("basic_profile") or {}).get("current_title") or "")]))
                for p in persons[:max(1, int(S.CONTACTS_PER_COMPANY))]:
                    bp = p.get("basic_profile") or {}
                    title = bp.get("current_title") or bp.get("headline") or ""
                    contact = Contact(campaign_id=campaign_id, company_id=r["id"], crustdata_person_id=str(p.get("crustdata_person_id") or ""),
                                      name=bp.get("name") or "Unknown", title=title, role=role_for_title(title),
                                      linkedin_url=profile_url(p), state="UNREACHABLE", raw=p)
                    s.add(contact)
                    s.flush()
                    if title:
                        _add_evidence(s, campaign_id, "contact", contact.id, "/person/search", "basic_profile.current_title",
                                      title, {"basic_profile": {"name": bp.get("name"), "current_title": title,
                                                                "headline": bp.get("headline")},
                                              "company": r["name"]}, source_url=profile_url(p))
                    contact_ids.append((contact.id, p))
        journal.log(campaign_id, "discovery", f"/person/search: {len(contact_ids)} contacts at {len(top)} companies "
                    f"({client.credits_used:.1f} credits so far)")

        # 7. business emails (15 rpm; the client paces the calls)
        accepted = {x.strip().lower() for x in S.ACCEPTED_EMAIL_STATUSES}
        n_ready = 0
        for contact_id, p in contact_ids:
            url = profile_url(p)
            has = (p.get("contact") or {}).get("has_business_email")
            if not url or has is False:
                journal.log(campaign_id, "contact", "No business email on record → UNREACHABLE (manual task)", contact_id=contact_id)
                continue
            try:
                entry = await client.person_enrich(linkedin_url=url)
            except CreditCeilingReached:
                raise
            except CrustdataError as e:
                log.warning("person_enrich failed: %s", e)
                journal.log(campaign_id, "warning", f"/person/enrich failed: {e}", contact_id=contact_id)
                continue
            emails = business_emails(entry)
            with session() as s:
                contact = s.get(Contact, contact_id)
                company = s.get(Company, contact.company_id)
                target_cid = str(company.crustdata_id) if company else None
                chosen = None
                for e in emails:  # prefer an accepted status at the target company, then any accepted
                    if (e.get("status") or "").lower() in accepted and str(e.get("crustdata_company_id")) == target_cid:
                        chosen = e
                        break
                if chosen is None:
                    chosen = next((e for e in emails if (e.get("status") or "").lower() in accepted), None)
                status = (chosen or (emails[0] if emails else {})).get("status")
                if chosen and chosen.get("email"):
                    contact.verified_email = chosen["email"]
                    contact.email_status = chosen.get("status")
                    contact.state = "READY"
                    n_ready += 1
                else:
                    contact.email_status = status
                    contact.state = "UNREACHABLE"
                if emails:
                    _add_evidence(s, campaign_id, "contact", contact_id, "/person/enrich", "contact.business_emails.status",
                                  status or "unknown",
                                  {"match_status": entry.get("match_status"),
                                   "business_emails": [{"status": e.get("status"), "crustdata_company_id": e.get("crustdata_company_id")} for e in emails]})
                journal.log(campaign_id, "contact",
                            f"Email status {status or 'none'} → {'READY' if contact.state == 'READY' else 'UNREACHABLE'}",
                            contact_id=contact_id)
        journal.log(campaign_id, "discovery", f"/person/enrich: {n_ready} of {len(contact_ids)} contacts have an accepted "
                    f"business email ({client.credits_used:.1f} credits so far)")

        # 8. featured contact
        _pick_featured(campaign_id)

        # 9. drafts
        try:
            await drafting.generate_drafts(campaign_id)
        except Exception as e:  # drafting must never lose the discovery results
            log.exception("drafting failed")
            journal.log(campaign_id, "error", f"Drafting failed: {e}")

    except CreditCeilingReached as e:
        journal.log(campaign_id, "warning", f"Credit ceiling reached ({e}); stopped and kept what was done")
    except Exception as e:
        log.exception("discovery failed")
        _set_status(campaign_id, "FAILED", credits_used=client.credits_used)
        journal.log(campaign_id, "error", f"Discovery failed: {e}")
        await client.aclose()
        return

    # 10. done
    await client.aclose()
    with session() as s:
        camp = s.get(Campaign, campaign_id)
        camp.status = "READY"
        camp.discovery_ran_at = datetime.now(timezone.utc)
        camp.credits_used = float(camp.credits_used or 0) + client.credits_used
    journal.log(campaign_id, "discovery", f"Discovery done: {client.credits_used:.1f} credits, {client.requests} requests")


def _pick_featured(campaign_id: str) -> None:
    with session() as s:
        contacts = s.scalars(select(Contact).where(Contact.campaign_id == campaign_id)).all()
        companies = {c.id: c for c in s.scalars(select(Company).where(Company.campaign_id == campaign_id)).all()}
        for c in contacts:
            c.featured = False
        ready = [c for c in contacts if c.state == "READY" and c.company_id in companies]
        if not ready:
            journal.log(campaign_id, "decision", "No READY contact to feature: every contact lacks an accepted business email")
            return
        order = {"T1": 0, "T2": 1, "T3": 2, "T4": 3}
        ready.sort(key=lambda c: (order.get(companies[c.company_id].tier, 9), companies[c.company_id].rank or 999))
        pick = ready[0]
        pick.featured = True
        tier = companies[pick.company_id].tier
        company_name = companies[pick.company_id].name
        s.flush()
        rationale = (f"Top {tier} with a verified email" if tier in ("T1", "T2")
                     else f"No T1/T2 contact has a verified email; best available is {tier}")
        memory.record_decision(campaign_id, "decision.featured_contact",
                               {"contact_id": pick.id, "name": pick.name, "company": company_name},
                               source="agent:discovery", rationale=rationale)
        journal.log(campaign_id, "decision", f"Featured {pick.name} at {company_name} ({rationale})", contact_id=pick.id)
