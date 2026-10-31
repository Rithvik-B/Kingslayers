"""Composio Gmail plus the recipient guard (PLAN.md §6.7).

check_recipient is the safety core. It fails closed: anything it can't prove is allowed raises
RecipientGuardError, and send_email runs it immediately before every Composio call.
"""
from __future__ import annotations

import asyncio
import base64
import re
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parseaddr
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from app import db, journal
from app import models as m
from app.config import S

SEND_TIMEOUT_S = 45
LIVE_DAILY_INITIAL_CAP = 10

# Composio tool slugs (verified in scripts/smoke_composio.py, see docs/notes/composio-tools.md).
SLUG_SEND = "GMAIL_SEND_EMAIL"
SLUG_REPLY = "GMAIL_REPLY_TO_THREAD"
SLUG_THREAD = "GMAIL_FETCH_MESSAGE_BY_THREAD_ID"


class RecipientGuardError(Exception):
    """The recipient isn't allowed. Never caught and ignored."""


class MailError(Exception):
    """The send failed, timed out, or was already attempted."""


def norm_email(addr: str | None) -> str:
    return parseaddr(addr or "")[1].strip().lower()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- recipient guard

def delivered_recipient(campaign, contact) -> str:
    mode = getattr(campaign, "delivery_mode", None)
    if mode == "STAND_IN":
        if not norm_email(S.STAND_IN_EMAIL):
            raise RecipientGuardError("STAND_IN_EMAIL is not set")
        return S.STAND_IN_EMAIL.strip()
    if mode == "LIVE":
        if not norm_email(contact.verified_email):
            raise RecipientGuardError("contact has no verified email")
        return contact.verified_email.strip()
    raise RecipientGuardError(f"unknown delivery_mode {mode!r}")


def _delivered_contact_ids(campaign_id: str) -> set[str]:
    with db.session() as s:
        rows = s.query(m.Contact.id).filter(
            m.Contact.campaign_id == campaign_id, m.Contact.delivered_to.isnot(None)
        ).all()
        return {r[0] for r in rows}


def _live_initials_today() -> int:
    """Initial sends (sent or in flight) today, Asia/Kolkata, across every LIVE campaign."""
    tz = ZoneInfo(S.TIMEZONE or "Asia/Kolkata")
    start_local = datetime.combine(datetime.now(tz).date(), time(0, 0), tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc)
    with db.session() as s:
        rows = (
            s.query(m.Message.created_at)
            .join(m.Campaign, m.Campaign.id == m.Message.campaign_id)
            .filter(
                m.Campaign.delivery_mode == "LIVE",
                m.Message.direction == "out",
                m.Message.kind == "initial",
                m.Message.status.in_(("PENDING", "SENT", "UNKNOWN")),
            )
            .all()
        )
    return sum(1 for (c,) in rows if c and _aware(c) >= start_utc)


def _consent_end(consent: dict) -> date | None:
    raw = consent.get("end_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def check_recipient(campaign, contact, to_email: str, *, initial: bool) -> None:
    """Raise RecipientGuardError unless sending to `to_email` is allowed. Fails closed."""
    to = norm_email(to_email)
    if not to:
        raise RecipientGuardError("empty recipient")
    mode = getattr(campaign, "delivery_mode", None)

    if mode == "STAND_IN":
        stand_in = norm_email(S.STAND_IN_EMAIL)
        if not stand_in:
            raise RecipientGuardError("STAND_IN_EMAIL is not set")
        if to != stand_in:
            raise RecipientGuardError(f"STAND_IN campaign may only send to the stand-in, not {to}")
        return

    if mode != "LIVE":
        raise RecipientGuardError(f"unknown delivery_mode {mode!r}")

    # LIVE: every flag is read now, at call time.
    if not bool(S.OUTBOUND_ENABLED):
        raise RecipientGuardError("OUTBOUND_ENABLED is false")
    if bool(S.DEMO_MODE):
        raise RecipientGuardError("DEMO_MODE is on: LIVE sends are refused")
    consent = campaign.consent or None
    if not isinstance(consent, dict) or not consent.get("authorized"):
        raise RecipientGuardError("LIVE campaign has no consent record")
    end = _consent_end(consent)
    if end is None:
        raise RecipientGuardError("consent has no valid end_date")
    if end < datetime.now(ZoneInfo(S.TIMEZONE or "Asia/Kolkata")).date():
        raise RecipientGuardError("consent has expired")
    if not contact.verified_email or to != norm_email(contact.verified_email):
        raise RecipientGuardError("LIVE recipient must be the contact's verified email")

    delivered = _delivered_contact_ids(campaign.id)
    if initial:
        if contact.id in delivered:
            raise RecipientGuardError("initial already delivered to this contact")
        try:
            max_sends = int(consent.get("max_sends", 5))
        except (TypeError, ValueError):
            raise RecipientGuardError("consent max_sends is invalid")
        if len(delivered) >= max_sends:
            raise RecipientGuardError(f"consent cap reached ({max_sends} contacts)")
        if _live_initials_today() >= LIVE_DAILY_INITIAL_CAP:
            raise RecipientGuardError(f"daily cap reached ({LIVE_DAILY_INITIAL_CAP} initial sends)")
    else:
        if contact.id not in delivered:
            raise RecipientGuardError("follow-on email to a contact that was never delivered")


# ---------------------------------------------------------------- Composio plumbing

_client = None


def _composio():
    global _client
    if _client is None:
        from composio import Composio

        _client = Composio(api_key=S.COMPOSIO_API_KEY)
    return _client


def _execute_sync(slug: str, arguments: dict) -> dict:
    res = _composio().tools.execute(
        slug, user_id=S.COMPOSIO_USER_ID, arguments=arguments, dangerously_skip_version_check=True
    )
    if hasattr(res, "model_dump"):
        res = res.model_dump()
    if not isinstance(res, dict):
        res = {"data": res, "successful": True}
    if res.get("successful") is False or res.get("error"):
        raise MailError(f"{slug} failed: {res.get('error') or res}")
    return res.get("data") or {}


async def execute(slug: str, arguments: dict, *, timeout: float = SEND_TIMEOUT_S) -> dict:
    """Run one Composio tool off the event loop. Raises MailError or asyncio.TimeoutError."""
    return await asyncio.wait_for(asyncio.to_thread(_execute_sync, slug, arguments), timeout)


def find_key(obj, *names):
    """Depth-first search for the first non-empty value under any of `names`."""
    if isinstance(obj, dict):
        for n in names:
            if obj.get(n):
                return obj[n]
        for v in obj.values():
            hit = find_key(v, *names)
            if hit:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = find_key(v, *names)
            if hit:
                return hit
    return None


# ---------------------------------------------------------------- send

def _claim(campaign, contact, *, kind, subject, body, thread_id, idempotency_key):
    """Write the PENDING row. Returns (message_id, existing_row_dict | None)."""
    with db.session() as s:
        existing = s.query(m.Message).filter(m.Message.idempotency_key == idempotency_key).first()
        if existing:
            return existing.id, {
                "status": existing.status,
                "message_id": existing.provider_message_id,
                "thread_id": existing.thread_id,
            }
    try:
        with db.session() as s:
            row = m.Message(
                campaign_id=campaign.id,
                contact_id=contact.id,
                direction="out",
                kind=kind,
                subject=subject,
                body=body,
                status="PENDING",
                idempotency_key=idempotency_key,
                thread_id=thread_id,
                created_at=utcnow(),
            )
            s.add(row)
            s.flush()
            return row.id, None
    except IntegrityError:
        raise MailError(f"send {idempotency_key} is already in flight")


def _finish(row_id: str, **fields) -> None:
    with db.session() as s:
        row = s.get(m.Message, row_id)
        for k, v in fields.items():
            setattr(row, k, v)


async def send_email(campaign, contact, *, kind: str, subject: str, body: str,
                     thread_id: str | None, idempotency_key: str) -> dict:
    """Send one email (new thread, or a reply in `thread_id`). Returns {"message_id", "thread_id"}."""
    to = delivered_recipient(campaign, contact)
    row_id, existing = _claim(campaign, contact, kind=kind, subject=subject, body=body,
                              thread_id=thread_id, idempotency_key=idempotency_key)
    if existing:
        if existing["status"] == "SENT":
            return {"message_id": existing["message_id"], "thread_id": existing["thread_id"],
                    "duplicate": True}
        raise MailError(f"send {idempotency_key} was already attempted ({existing['status']}); not re-sending")

    try:
        check_recipient(campaign, contact, to, initial=(kind == "initial"))
    except RecipientGuardError as e:
        _finish(row_id, status="FAILED")
        journal.log(campaign.id, "guard", f"Recipient guard blocked {kind}: {e}", contact_id=contact.id)
        raise

    if thread_id:
        slug, args = SLUG_REPLY, {"thread_id": thread_id, "recipient_email": to,
                                  "message_body": body, "is_html": False}
    else:
        slug, args = SLUG_SEND, {"recipient_email": to, "subject": subject, "body": body,
                                 "is_html": False}
    try:
        data = await execute(slug, args)
    except asyncio.TimeoutError:
        _finish(row_id, status="UNKNOWN")
        journal.log(campaign.id, "error", f"{kind} send timed out; marked UNKNOWN, not retried",
                    contact_id=contact.id)
        raise MailError(f"{kind} send timed out (status UNKNOWN; check Gmail before retrying)")
    except Exception as e:
        _finish(row_id, status="FAILED")
        journal.log(campaign.id, "error", f"{kind} send failed: {e}", contact_id=contact.id)
        raise MailError(f"{kind} send failed: {e}") from e

    msg_id = find_key(data, "id", "messageId", "message_id")
    new_thread = find_key(data, "threadId", "thread_id") or thread_id
    _finish(row_id, status="SENT", provider_message_id=msg_id, thread_id=new_thread, sent_at=utcnow())
    return {"message_id": msg_id, "thread_id": new_thread}


# ---------------------------------------------------------------- read

def _b64(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
    except Exception:
        return ""


def _payload_text(payload: dict) -> str:
    """Text from a raw Gmail API payload: prefer text/plain, else text/html."""
    plain, html = [], []

    def walk(p):
        mt = p.get("mimeType", "")
        data = (p.get("body") or {}).get("data")
        if data and mt == "text/plain":
            plain.append(_b64(data))
        elif data and mt == "text/html":
            html.append(_b64(data))
        for part in p.get("parts") or []:
            walk(part)

    walk(payload or {})
    if plain:
        return "\n".join(plain)
    if html:
        return "\n".join(html)
    return ""


def _headers(payload: dict) -> dict:
    return {h.get("name", "").lower(): h.get("value", "") for h in (payload or {}).get("headers") or []}


def _normalize_message(raw: dict) -> dict:
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else None
    hdr = _headers(payload) if payload else {}
    text = raw.get("messageText") or raw.get("text") or raw.get("body") or ""
    if not text and payload:
        text = _payload_text(payload)
    if not isinstance(text, str):
        text = str(text)
    return {
        "id": raw.get("messageId") or raw.get("id") or raw.get("message_id"),
        "from": raw.get("sender") or raw.get("from") or hdr.get("from", ""),
        "to": raw.get("to") or hdr.get("to", ""),
        "date": raw.get("messageTimestamp") or raw.get("date") or hdr.get("date") or raw.get("internalDate"),
        "subject": raw.get("subject") or hdr.get("subject", ""),
        "text": text,
        "label_ids": raw.get("labelIds") or raw.get("label_ids") or [],
    }


async def fetch_thread(thread_id: str) -> list[dict]:
    """Every message in a thread, oldest first: [{id, from, to, date, subject, text, label_ids}]."""
    data = await execute(SLUG_THREAD, {"thread_id": thread_id}, timeout=30)
    msgs = None
    if isinstance(data, dict):
        msgs = data.get("messages")
        if msgs is None:
            inner = data.get("response_data") or data.get("thread") or {}
            msgs = inner.get("messages") if isinstance(inner, dict) else None
    elif isinstance(data, list):
        msgs = data
    out = [_normalize_message(x) for x in (msgs or []) if isinstance(x, dict)]
    return [x for x in out if x["id"]]


