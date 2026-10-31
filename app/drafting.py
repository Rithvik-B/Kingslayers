"""Email drafts and the claim gate (P2, PLAN.md §6.5).

generate_drafts(campaign_id): one typed, evidence-cited draft per READY (or HELD, not yet sent) contact, all in
    parallel. Reads product.profile, voice.style and outreach.rules from memory at call time.
claim_gate(sentences, allowed_evidence_ids, profile): drops uncited prospect facts and product facts whose
    profile_field is not in the current profile. NEEDS_REVIEW if no prospect fact or no CTA is left.
opt_out_line(campaign): the opt-out sentence code appends to every body.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from sqlalchemy import delete, select

from app import journal, llm, memory
from app.config import S
from app.db import session
from app.models import Campaign, Company, Contact, Evidence, Message

log = logging.getLogger(__name__)

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["prospect_fact", "product_fact", "hypothesis", "cta"]},
                    "text": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "profile_field": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["type", "text", "evidence_ids", "profile_field"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["subject", "sentences"],
    "additionalProperties": False,
}

DRAFT_SYSTEM = """You write short, honest B2B cold emails as a list of typed sentences. Output only JSON matching the schema.

Sentence types:
- prospect_fact: a fact about the prospect's company or role. It MUST cite one or more evidence_ids from the
  facts you were given, and say only what that evidence says. Include exactly one concrete "why now" fact
  (open roles or headcount growth) when such evidence exists.
- product_fact: a claim about the seller's product. profile_field MUST name the product-profile field it comes
  from, e.g. "value_proposition", "capabilities[0]", "problems[1]". Say only what that field says.
- hypothesis: your guess about their situation, worded as a question or with "might". No evidence needed.
- cta: exactly one, asking for a 20-minute call.

Rules: at most the given word limit in total. No greeting, no sign-off and no opt-out line (code adds them).
No invented customers, metrics, relationships, dates or availability. Follow the seller's rules exactly.
Plain, specific, no hype. Each sentence stands alone; they are joined in order."""

_INDEX_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\]|\.(\d+))?$")


def profile_field_value(profile: dict | None, path: str | None) -> Any | None:
    """Resolve 'value_proposition', 'capabilities[2]' or 'capabilities.2' against the profile. None if absent."""
    if not profile or not path:
        return None
    m = _INDEX_RE.match(path.strip())
    if not m:
        return None
    key, idx = m.group(1), m.group(2) or m.group(3)
    if key not in profile:
        return None
    val = profile[key]
    if idx is None:
        return None if val in (None, "", []) else val
    if not isinstance(val, list):
        return None
    i = int(idx)
    return val[i] if 0 <= i < len(val) else None


def claim_gate(sentences: list[dict], allowed_evidence_ids: set[str], profile: dict) -> tuple[list[dict], str, list[str]]:
    kept: list[dict] = []
    notes: list[str] = []
    for s in sentences or []:
        t = (s.get("type") or "").strip()
        text = (s.get("text") or "").strip()
        if not text:
            continue
        if t == "prospect_fact":
            ids = [i for i in (s.get("evidence_ids") or []) if i in allowed_evidence_ids]
            if not ids:
                notes.append(f"dropped uncited prospect fact: \"{text[:80]}\"")
                continue
            kept.append({**s, "evidence_ids": ids})
        elif t == "product_fact":
            if profile_field_value(profile, s.get("profile_field")) is None:
                notes.append(f"dropped product fact with unknown profile field {s.get('profile_field')!r}: \"{text[:80]}\"")
                continue
            kept.append(s)
        elif t in ("hypothesis", "cta"):
            kept.append(s)
        else:
            notes.append(f"dropped sentence of unknown type {t!r}")
    n_fact = sum(1 for s in kept if s["type"] == "prospect_fact")
    n_cta = sum(1 for s in kept if s["type"] == "cta")
    status = "PASS"
    if n_fact < 1:
        status = "NEEDS_REVIEW"
        notes.append("no cited prospect fact left")
    if n_cta < 1:
        status = "NEEDS_REVIEW"
        notes.append("no call to action left")
    return kept, status, notes


def opt_out_line(campaign) -> str:
    line = "If this isn't relevant, just reply 'remove me' and I won't email again."
    if getattr(campaign, "delivery_mode", "STAND_IN") == "LIVE":
        consent = getattr(campaign, "consent", None) or {}
        sender = consent.get("sender_name") or S.SELLER_NAME
        address = consent.get("postal_address") or ""
        return f"{line} {sender}{', ' + address if address else ''}".strip()
    return line


def _first_name(name: str) -> str:
    parts = (name or "").strip().split()
    return parts[0] if parts else "there"


def build_body(contact_name: str, sentences: list[dict], campaign) -> str:
    text = " ".join(s["text"].strip() for s in sentences if s.get("text"))
    return f"Hi {_first_name(contact_name)},\n\n{text}\n\n{opt_out_line(campaign)}\n\n{S.SELLER_NAME}"


def _word_count(sentences: list[dict]) -> int:
    return sum(len((s.get("text") or "").split()) for s in sentences)


async def _draft_one(campaign, contact: Contact, company: Company, facts: list[dict], profile: dict, voice: dict,
                     rules: list, featured_id: str | None) -> None:
    max_words = int(voice.get("max_words") or 110)
    prompt = {
        "product_profile": profile,
        "voice": {"tone": voice.get("tone") or "plain and direct", "max_words": max_words, "avoid": voice.get("avoid") or []},
        "seller_rules": rules,
        "contact": {"name": contact.name, "title": contact.title, "role": contact.role},
        "company": {"name": company.name, "industry": company.industry, "headcount": company.headcount},
        "facts": facts,
    }
    allowed = {f["evidence_id"] for f in facts}
    sentences: list[dict] = []
    subject = ""
    try:
        out = await llm.complete_json(DRAFT_SYSTEM, "Write the email from this input:\n\n" + json.dumps(prompt, indent=1), DRAFT_SCHEMA)
        subject = (out.get("subject") or "").strip()[:150]
        sentences = out.get("sentences") or []
    except llm.LLMError as e:
        journal.log(campaign.id, "error", f"Draft generation failed for {contact.name}: {e}", contact_id=contact.id)
    kept, status, notes = claim_gate(sentences, allowed, profile)
    if not subject:
        status = "NEEDS_REVIEW"
        notes.append("no subject")
    if _word_count(kept) > max_words:
        notes.append(f"{_word_count(kept)} words, over the {max_words}-word limit")
    body = build_body(contact.name, kept, campaign)

    is_featured = contact.id == featured_id
    hold = campaign.delivery_mode == "STAND_IN" and status == "PASS" and not is_featured
    with session() as s:
        s.execute(delete(Message).where(Message.contact_id == contact.id, Message.kind == "initial",
                                        Message.status.in_(["DRAFT", "HELD"])))
        s.add(Message(campaign_id=campaign.id, contact_id=contact.id, direction="out", kind="initial", subject=subject,
                      body=body, sentences=kept, gate_status=status, gate_notes=notes,
                      status="HELD" if hold else "DRAFT"))
        c = s.get(Contact, contact.id)
        if hold:
            c.state = "HELD"
        elif c.state == "HELD" and is_featured:
            c.state = "READY"
    journal.log(campaign.id, "draft",
                f"Draft for {contact.name}: {status}, {len(kept)} sentences kept, {len(sentences) - len(kept)} dropped"
                + (" · HELD (stand-in delivers 1)" if hold else ""),
                contact_id=contact.id, data={"notes": notes})


async def generate_drafts(campaign_id: str) -> None:
    # live reads: the seller's latest profile, voice and rules apply to these drafts
    profile = memory.get(campaign_id, "product.profile") or {}
    voice = memory.get(campaign_id, "voice.style") or {"tone": "plain and direct", "max_words": 110, "avoid": []}
    rules = memory.get(campaign_id, "outreach.rules") or []

    with session() as s:
        campaign = s.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError(f"campaign {campaign_id} not found")
        contacts = s.scalars(select(Contact).where(Contact.campaign_id == campaign_id,
                                                   Contact.state.in_(["READY", "HELD"]))).all()
        companies = {c.id: c for c in s.scalars(select(Company).where(Company.campaign_id == campaign_id)).all()}
        featured = next((c.id for c in contacts if c.featured), None)
        if featured is None and contacts:
            order = {"T1": 0, "T2": 1, "T3": 2, "T4": 3}
            ready = sorted((c for c in contacts if c.state == "READY" and c.company_id in companies),
                           key=lambda c: (order.get(companies[c.company_id].tier, 9), companies[c.company_id].rank or 999))
            if ready:
                ready[0].featured = True
                featured = ready[0].id
        evidence = s.scalars(select(Evidence).where(Evidence.campaign_id == campaign_id)).all()
    if not contacts:
        journal.log(campaign_id, "draft", "No READY contacts to draft for")
        return
    if not profile:
        journal.log(campaign_id, "warning", "product.profile missing from memory; drafts will have no product facts")

    by_subject: dict[str, list[dict]] = {}
    for e in evidence:
        if e.field_path == "contact.business_emails.status":
            continue  # a receipt for the UI, not a fact to write about
        by_subject.setdefault(e.subject_id, []).append({"evidence_id": e.id, "field": e.field_path, "value": e.value})

    journal.log(campaign_id, "draft", f"Drafting {len(contacts)} emails with the claim gate "
                f"({len(rules)} seller rule{'s' if len(rules) != 1 else ''}, max {voice.get('max_words', 110)} words)")
    tasks = []
    for contact in contacts:
        company = companies.get(contact.company_id)
        if company is None:
            continue
        facts = by_subject.get(company.id, []) + by_subject.get(contact.id, [])
        tasks.append(_draft_one(campaign, contact, company, facts, profile, voice, rules, featured))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    failed = [r for r in results if isinstance(r, Exception)]
    for r in failed:
        log.error("draft task failed: %r", r)
    journal.log(campaign_id, "draft", f"Drafts done: {len(results) - len(failed)} written, {len(failed)} failed")
