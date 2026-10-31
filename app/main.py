"""FastAPI app: every route in PLAN.md §7, the background inbox loop, and the static page.

P2's and P3's modules are imported inside the route functions so the app starts before they're pushed.
"""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app import journal, memory
from app.config import S
from app.db import init_db, session
from app.models import (
    Campaign,
    Company,
    Contact,
    Evidence,
    Journal,
    Meeting,
    Memory,
    Message,
    ProcessedMessage,
    Suppression,
)

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Kingslayers Sales Agent")


@app.exception_handler(ModuleNotFoundError)
async def _missing_module(request: Request, exc: ModuleNotFoundError):
    """A teammate's module isn't pushed yet: say which one instead of a bare 500."""
    owner = {"discovery": "P2", "drafting": "P2", "llm": "P2", "crustdata": "P2", "scoring": "P2",
             "outreach": "P3", "inbox": "P3", "booking": "P3", "mail": "P3", "calendar_io": "P3", "gates": "P3"}
    name = (exc.name or "").removeprefix("app.")
    if name in owner:
        detail = f"app.{name} is not pushed yet (owner: {owner[name]})"
    else:
        detail = f"missing package: {exc.name} (run .venv/bin/pip install -r requirements.txt)"
    return JSONResponse({"detail": detail}, status_code=503)


@app.exception_handler(Exception)
async def _any_error(request: Request, exc: Exception):
    return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)


# ---------- startup and background loop ----------

async def _inbox_loop() -> None:
    while True:
        try:
            from app import inbox  # P3

            await inbox.inbox_pass()
        except Exception as e:  # never crash the loop
            print(f"[inbox loop] {type(e).__name__}: {e}")
        await asyncio.sleep(15)


@app.on_event("startup")
async def _startup() -> None:
    init_db()
    memory.ensure_defaults()
    asyncio.create_task(_inbox_loop())


# ---------- helpers ----------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mask(email: str) -> str:
    if not email or "@" not in email:
        return "(unset)"
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _campaign_or_404(db, campaign_id: str) -> Campaign:
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise HTTPException(404, "campaign not found")
    return c


def _contact_or_404(db, contact_id: str) -> Contact:
    c = db.get(Contact, contact_id)
    if c is None:
        raise HTTPException(404, "contact not found")
    return c


def _contact_dict(c: Contact) -> dict:
    """Never expose verified_email."""
    return {
        "id": c.id,
        "campaign_id": c.campaign_id,
        "company_id": c.company_id,
        "name": c.name,
        "title": c.title,
        "role": c.role,
        "linkedin_url": c.linkedin_url,
        "email_verified": bool(c.verified_email),
        "email_status": c.email_status,
        "state": c.state,
        "featured": c.featured,
        "thread_id": c.thread_id,
    }


def _campaign_dict(db, c: Campaign) -> dict:
    cid = c.id
    discovered = db.scalar(select(func.count()).select_from(Company).where(Company.campaign_id == cid)) or 0
    qualified = db.scalar(
        select(func.count()).select_from(Company)
        .where(Company.campaign_id == cid, Company.tier.in_(["T1", "T2", "T3", "T4"]))
    ) or 0
    contacts = db.scalar(select(func.count()).select_from(Contact).where(Contact.campaign_id == cid)) or 0
    verified = db.scalar(
        select(func.count()).select_from(Contact)
        .where(Contact.campaign_id == cid, Contact.verified_email.is_not(None))
    ) or 0
    emailed = db.scalar(
        select(func.count()).select_from(Message)
        .where(Message.campaign_id == cid, Message.kind == "initial", Message.status == "SENT")
    ) or 0
    drafted = db.scalar(
        select(func.count()).select_from(Message)
        .where(Message.campaign_id == cid, Message.kind == "initial", Message.direction == "out")
    ) or 0
    held = db.scalar(
        select(func.count()).select_from(Message)
        .where(Message.campaign_id == cid, Message.kind == "initial", Message.status == "HELD")
    ) or 0
    replied = db.scalar(
        select(func.count(func.distinct(Message.contact_id))).select_from(Message)
        .where(Message.campaign_id == cid, Message.direction == "in")
    ) or 0
    booked = db.scalar(
        select(func.count()).select_from(Meeting).where(Meeting.campaign_id == cid, Meeting.status == "BOOKED")
    ) or 0
    return {
        "id": c.id,
        "name": c.name,
        "product_text": c.product_text,
        "icp_approved": c.icp_approved,
        "delivery_mode": c.delivery_mode,
        "status": c.status,
        "paused": c.paused,
        "discovery_ran_at": c.discovery_ran_at.isoformat() if c.discovery_ran_at else None,
        "credits_used": c.credits_used,
        "consent": c.consent,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "stand_in_masked": _mask(S.STAND_IN_EMAIL),
        "funnel": {
            "discovered": discovered,
            "qualified": qualified,
            "target": S.DISCOVERY_COMPANY_LIMIT,
            "contacts": contacts,
            "verified": verified,
            "emailed": emailed,
            "drafted": drafted,
            "held": held,
            "replied": replied,
            "booked": booked,
        },
    }


# ---------- static ----------

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------- campaigns ----------

class CampaignIn(BaseModel):
    name: str
    product_text: str
    delivery_mode: str = "STAND_IN"


@app.post("/api/campaigns")
def create_campaign(body: CampaignIn):
    if body.delivery_mode not in ("STAND_IN", "LIVE"):
        raise HTTPException(400, "delivery_mode must be STAND_IN or LIVE")
    if body.delivery_mode == "LIVE" and (S.DEMO_MODE or not S.OUTBOUND_ENABLED):
        raise HTTPException(403, "LIVE campaigns are refused: DEMO_MODE is on or OUTBOUND_ENABLED is off")
    with session() as db:
        c = Campaign(name=body.name, product_text=body.product_text, delivery_mode=body.delivery_mode)
        db.add(c)
        db.flush()
        out = _campaign_dict(db, c)
    journal.log(out["id"], "campaign", f"Campaign created in {body.delivery_mode} mode.")
    return out


@app.get("/api/campaigns")
def list_campaigns():
    with session() as db:
        rows = db.scalars(select(Campaign).order_by(Campaign.created_at.desc())).all()
        return [_campaign_dict(db, c) for c in rows]


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: str):
    with session() as db:
        return _campaign_dict(db, _campaign_or_404(db, campaign_id))


@app.post("/api/campaigns/{campaign_id}/icp")
async def generate_icp(campaign_id: str):
    with session() as db:
        _campaign_or_404(db, campaign_id)
    from app import discovery  # P2

    await discovery.generate_profile_and_icp(campaign_id)
    return {
        "product_profile": memory.get(campaign_id, "product.profile"),
        "icp": memory.get(campaign_id, "gtm.icp"),
        "voice": memory.get(campaign_id, "voice.style"),
    }


@app.post("/api/campaigns/{campaign_id}/icp/approve")
def approve_icp(campaign_id: str):
    with session() as db:
        c = _campaign_or_404(db, campaign_id)
        c.icp_approved = True
    memory.record_decision(campaign_id, "decision.icp_approved", {"approved": True},
                           source="user", rationale="Seller approved the ICP in the UI")
    journal.log(campaign_id, "icp", "ICP approved by the seller.")
    return {"ok": True}


async def _run_discovery_bg(campaign_id: str) -> None:
    try:
        from app import discovery  # P2

        await discovery.run_discovery(campaign_id)
    except Exception as e:
        journal.log(campaign_id, "error", f"Discovery failed: {type(e).__name__}: {e}")
        with session() as db:
            c = db.get(Campaign, campaign_id)
            if c is not None:
                c.status = "FAILED"


@app.post("/api/campaigns/{campaign_id}/discover")
def discover(campaign_id: str, bg: BackgroundTasks):
    with session() as db:
        c = _campaign_or_404(db, campaign_id)
        if not c.icp_approved:
            raise HTTPException(400, "approve the ICP first")
        c.status = "DISCOVERING"
    bg.add_task(_run_discovery_bg, campaign_id)
    return {"started": True}


@app.get("/api/campaigns/{campaign_id}/companies")
def list_companies(campaign_id: str):
    with session() as db:
        _campaign_or_404(db, campaign_id)
        companies = db.scalars(
            select(Company).where(Company.campaign_id == campaign_id)
            .order_by(Company.rank.is_(None), Company.rank.asc())
        ).all()
        contacts = db.scalars(select(Contact).where(Contact.campaign_id == campaign_id)).all()
        by_company: dict[str, list[dict]] = {}
        for ct in contacts:
            by_company.setdefault(ct.company_id, []).append(_contact_dict(ct))
        ranked, needs_evidence, excluded = [], [], []
        for co in companies:
            d = {
                "id": co.id,
                "crustdata_id": co.crustdata_id,
                "name": co.name,
                "domain": co.domain,
                "industry": co.industry,
                "country": co.country,
                "city": co.city,
                "headcount": co.headcount,
                "headcount_growth_12m": co.headcount_growth_12m,
                "fit": co.fit,
                "coverage": co.coverage,
                "tier": co.tier,
                "rank": co.rank,
                "why_now": co.why_now or [],
                "criteria": co.criteria or [],
                "contacts": by_company.get(co.id, []),
            }
            if co.tier == "NEEDS_EVIDENCE":
                needs_evidence.append(d)
            elif co.tier == "EXCLUDED":
                excluded.append(d)
            else:
                ranked.append(d)
        return {"ranked": ranked, "needs_evidence": needs_evidence, "excluded": excluded}


@app.get("/api/companies/{company_id}")
def company_detail(company_id: str):
    """Everything stored about one company: profile, criteria with receipts, signals, contacts, drafts."""
    with session() as db:
        co = db.get(Company, company_id)
        if co is None:
            raise HTTPException(404, "company not found")
        contacts = db.scalars(select(Contact).where(Contact.company_id == company_id)).all()
        ev_rows = db.scalars(select(Evidence).where(Evidence.subject_id.in_([company_id] + [c.id for c in contacts]))).all()
        evidence = [{
            "id": e.id, "subject_type": e.subject_type, "endpoint": e.endpoint, "field_path": e.field_path,
            "value": e.value, "source_url": e.source_url, "retrieved_at": e.retrieved_at.isoformat() if e.retrieved_at else None,
        } for e in ev_rows]
        out_contacts = []
        for ct in contacts:
            msgs = db.scalars(
                select(Message).where(Message.contact_id == ct.id).order_by(Message.created_at.asc())
            ).all()
            meeting = db.scalars(select(Meeting).where(Meeting.contact_id == ct.id).order_by(Meeting.created_at.desc())).first()
            d = _contact_dict(ct)
            d["messages"] = [{
                "id": m.id, "direction": m.direction, "kind": m.kind, "subject": m.subject, "body": m.body,
                "status": m.status, "gate_status": m.gate_status, "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                "received_at": m.received_at.isoformat() if m.received_at else None,
            } for m in msgs]
            d["meeting"] = {"status": meeting.status, "start_at": meeting.start_at.isoformat() if meeting.start_at else None,
                            "meet_link": meeting.meet_link} if meeting else None
            d["reach"] = ("Verified business email on file; the agent emails them and handles the reply."
                          if ct.verified_email else
                          "No verified email. Reach out via their LinkedIn profile (manual task), or re-run with a wider email policy.")
            out_contacts.append(d)
        raw = co.raw or {}
        return {
            "id": co.id, "crustdata_id": co.crustdata_id, "name": co.name, "domain": co.domain,
            "website": (f"https://{co.domain}" if co.domain and not co.domain.startswith("http") else co.domain),
            "industry": co.industry, "country": co.country, "city": co.city, "headcount": co.headcount,
            "headcount_growth_12m": co.headcount_growth_12m, "fit": co.fit, "coverage": co.coverage, "tier": co.tier,
            "rank": co.rank, "why_now": co.why_now or [], "criteria": co.criteria or [],
            "description": raw.get("description") or raw.get("about") or raw.get("summary") or raw.get("short_description"),
            "linkedin_url": raw.get("linkedin_profile_url") or raw.get("linkedin_url") or (raw.get("social_handles") or {}).get("linkedin"),
            "raw": raw, "evidence": evidence, "contacts": out_contacts,
        }


@app.get("/api/evidence/{evidence_id}")
def get_evidence(evidence_id: str):
    with session() as db:
        e = db.get(Evidence, evidence_id)
        if e is None:
            raise HTTPException(404, "evidence not found")
        return {
            "id": e.id,
            "subject_type": e.subject_type,
            "subject_id": e.subject_id,
            "endpoint": e.endpoint,
            "field_path": e.field_path,
            "value": e.value,
            "source_url": e.source_url,
            "raw_excerpt": e.raw_excerpt,
            "retrieved_at": e.retrieved_at.isoformat() if e.retrieved_at else None,
        }


# ---------- contacts and drafts ----------

def _profile_field(profile: Any, path: str):
    """Resolve 'capabilities[2]' or 'value_proposition' against the profile dict."""
    import re

    cur = profile
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path or ""):
        if part.startswith("["):
            idx = int(part[1:-1])
            if not isinstance(cur, list) or idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
    return cur


@app.get("/api/contacts/{contact_id}/draft")
def get_draft(contact_id: str):
    with session() as db:
        ct = _contact_or_404(db, contact_id)
        msg = db.scalars(
            select(Message)
            .where(Message.contact_id == contact_id, Message.kind == "initial", Message.direction == "out")
            .order_by(Message.created_at.desc())
        ).first()
        if msg is None:
            raise HTTPException(404, "no draft yet")
        ev_rows = db.scalars(select(Evidence).where(Evidence.subject_id.in_([ct.company_id, ct.id]))).all()
        ev = {e.id: {"value": e.value, "field_path": e.field_path, "endpoint": e.endpoint} for e in ev_rows}
        profile = memory.get(ct.campaign_id, "product.profile") or {}
        sentences = []
        for s in msg.sentences or []:
            d = dict(s)
            d["cited"] = [{"evidence_id": i, **ev[i]} for i in (s.get("evidence_ids") or []) if i in ev]
            if s.get("type") == "product_fact" and s.get("profile_field"):
                d["profile_value"] = _profile_field(profile, s["profile_field"])
            sentences.append(d)
        return {
            "message_id": msg.id,
            "contact": _contact_dict(ct),
            "subject": msg.subject,
            "body": msg.body,
            "sentences": sentences,
            "gate_status": msg.gate_status,
            "gate_notes": msg.gate_notes or [],
            "status": msg.status,
            "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
        }


@app.post("/api/contacts/{contact_id}/feature")
def feature_contact(contact_id: str):
    with session() as db:
        ct = _contact_or_404(db, contact_id)
        sent = db.scalar(
            select(func.count()).select_from(Message)
            .where(Message.campaign_id == ct.campaign_id, Message.kind == "initial", Message.status == "SENT")
        )
        if sent:
            raise HTTPException(400, "an email was already sent on this campaign")
        for other in db.scalars(select(Contact).where(Contact.campaign_id == ct.campaign_id, Contact.featured)).all():
            other.featured = False
            if other.state == "READY" and ct.campaign_id and other.id != ct.id:
                pass
        ct.featured = True
        # the newly featured contact's draft becomes deliverable; the previous one is held
        for m in db.scalars(
            select(Message).where(Message.campaign_id == ct.campaign_id, Message.kind == "initial",
                                  Message.status.in_(["DRAFT", "HELD"]))
        ).all():
            m.status = "DRAFT" if m.contact_id == ct.id else "HELD"
        for c2 in db.scalars(select(Contact).where(Contact.campaign_id == ct.campaign_id,
                                                   Contact.state.in_(["READY", "HELD"]))).all():
            c2.state = "READY" if c2.id == ct.id else "HELD"
        cid, name = ct.campaign_id, ct.name
    memory.record_decision(cid, "decision.featured_contact", {"contact_id": contact_id, "name": name},
                           source="user", rationale="Seller starred this contact")
    journal.log(cid, "feature", f"Featured contact set to {name}.", contact_id=contact_id)
    return {"ok": True}


@app.post("/api/contacts/{contact_id}/send")
async def send_contact(contact_id: str):
    with session() as db:
        ct = _contact_or_404(db, contact_id)
        msg = db.scalars(
            select(Message).where(Message.contact_id == contact_id, Message.kind == "initial",
                                  Message.direction == "out").order_by(Message.created_at.desc())
        ).first()
        if msg is None:
            raise HTTPException(400, "no draft to send")
        if msg.gate_status != "PASS":
            raise HTTPException(400, "draft did not pass the claim gate")
        if msg.status == "HELD":
            raise HTTPException(400, "this draft is HELD (not the featured contact)")
        msg.send_approved_at = _now()
        cid = ct.campaign_id
    memory.record_decision(cid, "decision.send_approved", {"contact_id": contact_id},
                           source="user", rationale="Seller clicked Send")
    from app import outreach  # P3

    try:
        await outreach.send_initial(contact_id)
    except Exception as e:
        journal.log(cid, "error", f"Send blocked: {type(e).__name__}: {e}", contact_id=contact_id)
        raise HTTPException(400, f"{type(e).__name__}: {e}")
    return {"ok": True}


@app.post("/api/inbox/check")
async def inbox_check():
    from app import inbox  # P3

    n = await inbox.inbox_pass()
    return {"processed": n}


@app.post("/api/contacts/{contact_id}/human/{action}")
async def human_action(contact_id: str, action: str):
    if action not in ("treat_interested", "suppress", "dismiss"):
        raise HTTPException(400, "unknown action")
    with session() as db:
        ct = _contact_or_404(db, contact_id)
        cid = ct.campaign_id
        if action == "dismiss":
            ct.state = "WAITING"
    if action == "suppress":
        from app import inbox  # P3: suppresses by the logical key and records the campaign's real mode

        inbox.suppress_contact(contact_id, "seller clicked Suppress")
    memory.record_decision(cid, "decision.human_action", {"contact_id": contact_id, "action": action},
                           source="user", rationale="Seller resolved a NEEDS_HUMAN reply")
    journal.log(cid, "human", f"Seller chose '{action}'.", contact_id=contact_id)
    if action == "treat_interested":
        from app import booking  # P3

        try:
            await booking.offer_slots(contact_id)
        except Exception as e:
            journal.log(cid, "error", f"Slot offer blocked: {type(e).__name__}: {e}", contact_id=contact_id)
            raise HTTPException(400, f"{type(e).__name__}: {e}")
    return {"ok": True}


@app.post("/api/campaigns/{campaign_id}/pause")
def pause(campaign_id: str):
    with session() as db:
        _campaign_or_404(db, campaign_id).paused = True
    journal.log(campaign_id, "pause", "Campaign paused. No sends, slot offers or bookings until resumed.")
    return {"paused": True}


@app.post("/api/campaigns/{campaign_id}/resume")
def resume(campaign_id: str):
    with session() as db:
        _campaign_or_404(db, campaign_id).paused = False
    journal.log(campaign_id, "pause", "Campaign resumed.")
    return {"paused": False}


@app.get("/api/campaigns/{campaign_id}/journal")
def get_journal(campaign_id: str, limit: int = 200):
    with session() as db:
        rows = db.scalars(
            select(Journal).where(Journal.campaign_id == campaign_id).order_by(Journal.at.desc()).limit(limit)
        ).all()
        return [
            {"id": j.id, "at": j.at.isoformat() if j.at else None, "kind": j.kind, "text": j.text,
             "contact_id": j.contact_id, "data": j.data}
            for j in rows
        ]


@app.get("/api/campaigns/{campaign_id}/meetings")
def get_meetings(campaign_id: str):
    with session() as db:
        rows = db.scalars(
            select(Meeting).where(Meeting.campaign_id == campaign_id).order_by(Meeting.created_at.desc())
        ).all()
        out = []
        for m in rows:
            ct = db.get(Contact, m.contact_id)
            co = db.get(Company, ct.company_id) if ct else None
            accepted = db.get(Message, m.accepted_message_id) if m.accepted_message_id else None
            out.append({
                "id": m.id,
                "contact": _contact_dict(ct) if ct else None,
                "company_name": co.name if co else None,
                "slots_offered": m.slots_offered,
                "start_at": m.start_at.isoformat() if m.start_at else None,
                "end_at": m.end_at.isoformat() if m.end_at else None,
                "event_id": m.event_id,
                "meet_link": m.meet_link,
                "status": m.status,
                "accepted_text": accepted.body if accepted else None,
                "error": m.error,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            })
        return out


# ---------- memory ----------

class MemoryEdit(BaseModel):
    campaign_id: str | None = None
    key: str
    value: Any


@app.get("/api/memory")
def get_memory(campaign_id: str | None = None):
    return memory.snapshot(campaign_id or None)


@app.put("/api/memory")
def put_memory(body: MemoryEdit):
    current = memory.get(body.campaign_id, body.key)
    if current is not None and type(current) is not type(body.value):
        raise HTTPException(400, f"value must be a {type(current).__name__}, like the current value")
    item_id = memory.edit(body.campaign_id, body.key, body.value)
    if body.campaign_id:
        journal.log(body.campaign_id, "memory", f"Seller edited {body.key}.")
    return {"id": item_id, "value": memory.get(body.campaign_id, body.key)}


@app.post("/api/campaigns/{campaign_id}/drafts/regenerate")
async def regenerate_drafts(campaign_id: str):
    with session() as db:
        _campaign_or_404(db, campaign_id)
        # drop unsent drafts so generate_drafts writes fresh ones
        unsent = db.scalars(
            select(Message).where(Message.campaign_id == campaign_id, Message.kind == "initial",
                                  Message.direction == "out", Message.status.in_(["DRAFT", "HELD"]))
        ).all()
        for m in unsent:
            db.delete(m)
    from app import drafting  # P2

    await drafting.generate_drafts(campaign_id)
    journal.log(campaign_id, "drafts", "Drafts regenerated from the current Seller Memory.")
    return {"ok": True}


@app.get("/api/memory/history")
def memory_history(key: str, campaign_id: str | None = None):
    return memory.history(campaign_id or None, key)


@app.post("/api/memory/{item_id}/revert")
def memory_revert(item_id: str):
    try:
        return {"id": memory.revert(item_id)}
    except KeyError:
        raise HTTPException(404, "memory item not found")


@app.get("/api/memory/export", response_class=PlainTextResponse)
def memory_export(campaign_id: str | None = None):
    import json

    snap = memory.snapshot(campaign_id or None)
    lines = ["# Seller Memory: product, GTM, voice, rules, decisions", ""]
    for kind, items in snap["knowledge"].items():
        lines.append(f"## {kind}")
        for it in items:
            lock = " (edited by you)" if it["locked"] else ""
            lines.append(f"### {it['key']} v{it['version']} · {it['source']}{lock}")
            lines.append("```json")
            lines.append(json.dumps(it["value"], indent=2))
            lines.append("```")
        lines.append("")
    lines.append("## decisions")
    for d in snap["decisions"]:
        who = "YOU" if d["source"] == "user" else "AGENT"
        lines.append(f"- {d['created_at']} [{who}] {d['key']}: {json.dumps(d['value'])} — {d['rationale'] or ''}")
    return "\n".join(lines)


# ---------- demo and consent ----------

@app.post("/api/demo/reset")
def demo_reset():
    with session() as db:
        ids = [c.id for c in db.scalars(select(Campaign).where(Campaign.delivery_mode == "STAND_IN")).all()]
        if ids:
            for model in (Company, Contact, Evidence, Message, Meeting, Journal):
                db.execute(delete(model).where(model.campaign_id.in_(ids)))
            db.execute(delete(Memory).where(Memory.campaign_id.in_(ids)))  # keeps seller-wide memory
            db.execute(delete(Suppression).where(Suppression.source_campaign_id.in_(ids),
                                                 Suppression.source_mode == "STAND_IN"))
            contact_ids = select(Contact.id).where(Contact.campaign_id.in_(ids))
            db.execute(delete(ProcessedMessage).where(ProcessedMessage.contact_id.in_(contact_ids)))
            db.execute(delete(Campaign).where(Campaign.id.in_(ids)))
    return {"deleted_campaigns": len(ids)}


class ConsentIn(BaseModel):
    sender_name: str
    company: str
    postal_address: str
    max_sends: int = 5
    end_date: str
    authorized: bool


@app.post("/api/campaigns/{campaign_id}/consent")
def set_consent(campaign_id: str, body: ConsentIn):
    if not body.authorized:
        raise HTTPException(400, "consent requires authorized=true")
    with session() as db:
        c = _campaign_or_404(db, campaign_id)
        if c.delivery_mode != "LIVE":
            raise HTTPException(400, "consent only applies to LIVE campaigns")
        c.consent = {**body.model_dump(), "recorded_at": _now().isoformat()}
    journal.log(campaign_id, "consent", f"LIVE consent recorded: max {body.max_sends} sends until {body.end_date}.")
    return {"ok": True}
