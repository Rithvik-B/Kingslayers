"""Send gates (PLAN.md §6.6). Run right before every external action."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app import db
from app import models as m
from app.config import S
from app.mail import norm_email


class GateError(Exception):
    """A gate refused the action. The message is shown to the seller."""


SENDABLE_STATES = {
    "initial": {"READY"},
    "slot_offer": {"WAITING", "SCHEDULING"},
    "confirmation": {"WAITING", "SCHEDULING"},
    "book": {"WAITING", "SCHEDULING"},
}
LIVE_DAILY_INITIAL_CAP = 10


def accepted_statuses() -> set[str]:
    raw = S.ACCEPTED_EMAIL_STATUSES
    items = raw if isinstance(raw, (list, tuple, set)) else str(raw or "").split(",")
    return {str(x).strip().lower() for x in items if str(x).strip()}


def contact_key(contact) -> str:
    """The logical suppression key: the real prospect's email, never the stand-in address."""
    email = norm_email(contact.verified_email)
    return email or f"contact:{contact.id}"


def is_suppressed(contact) -> bool:
    keys = {f"contact:{contact.id}"}
    if norm_email(contact.verified_email):
        keys.add(norm_email(contact.verified_email))
    with db.session() as s:
        return s.query(m.Suppression).filter(m.Suppression.contact_key.in_(keys)).first() is not None


def _initial_attempted(contact_id: str) -> bool:
    with db.session() as s:
        return s.query(m.Message).filter(
            m.Message.contact_id == contact_id,
            m.Message.direction == "out",
            m.Message.kind == "initial",
            m.Message.status.in_(("PENDING", "SENT", "UNKNOWN")),
        ).first() is not None


def _delivered_ids(campaign_id: str) -> set[str]:
    with db.session() as s:
        return {r[0] for r in s.query(m.Contact.id).filter(
            m.Contact.campaign_id == campaign_id, m.Contact.delivered_to.isnot(None)).all()}


def can_send(campaign, contact, kind: str) -> tuple[bool, str]:
    if kind not in SENDABLE_STATES:
        return False, f"unknown action {kind!r}"
    # 1. pause
    if campaign.paused:
        return False, "Campaign is paused"
    # 2. verified email
    if not contact.verified_email:
        return False, "Contact has no verified email"
    if str(contact.email_status or "").strip().lower() not in accepted_statuses():
        return False, f"Email status {contact.email_status!r} is not accepted"
    # 3. suppression
    if is_suppressed(contact):
        return False, "Contact is suppressed"
    # 4. state
    if contact.state not in SENDABLE_STATES[kind]:
        return False, f"Contact state {contact.state} does not allow {kind}"
    # 5. caps
    delivered = _delivered_ids(campaign.id)
    if kind == "initial":
        if contact.delivered_to or _initial_attempted(contact.id):
            return False, "Initial email already sent to this contact"
        if campaign.delivery_mode == "STAND_IN":
            if delivered - {contact.id}:
                return False, "STAND_IN delivers to 1 contact per campaign; one is already delivered"
        elif campaign.delivery_mode == "LIVE":
            consent = campaign.consent if isinstance(campaign.consent, dict) else None
            if not consent:
                return False, "LIVE campaign has no consent record"
            if len(delivered) >= int(consent.get("max_sends", 5)):
                return False, "Consent send cap reached"
            from app.mail import _live_initials_today
            if _live_initials_today() >= LIVE_DAILY_INITIAL_CAP:
                return False, f"Daily cap of {LIVE_DAILY_INITIAL_CAP} initial sends reached"
        else:
            return False, f"Unknown delivery mode {campaign.delivery_mode!r}"
    elif contact.id not in delivered:
        return False, "Contact was never delivered an initial email"
    # 6. time window
    if campaign.delivery_mode == "LIVE":
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        if now.weekday() >= 5 or not (9 <= now.hour < 18):
            return False, "LIVE sends only Mon-Fri 09:00-18:00 IST"
    return True, "ok"


def require(campaign, contact, kind: str) -> None:
    ok, reason = can_send(campaign, contact, kind)
    if not ok:
        raise GateError(reason)
