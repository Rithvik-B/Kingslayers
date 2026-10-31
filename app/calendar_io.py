"""Composio Google Calendar plus the recipient guard (PLAN.md §6.8).

Slot length, working hours, buffers and the timezone come from memory `scheduling.prefs`, read at
call time. Slots are computed here from the seller's free/busy, so they're deterministic.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import journal, memory
from app import mail

SLUG_FREEBUSY = "GOOGLECALENDAR_FREE_BUSY_QUERY"
SLUG_CREATE = "GOOGLECALENDAR_CREATE_EVENT"
SLUG_LIST = "GOOGLECALENDAR_EVENTS_LIST"
SLUG_MEET = "GOOGLEMEET_CREATE_MEET"

DEFAULT_PREFS = {"working_hours": [9, 18], "slot_minutes": 20, "buffer_minutes": 10,
                 "days_ahead": 7, "timezone": "Asia/Kolkata"}


def prefs(campaign_id: str | None = None) -> dict:
    p = dict(DEFAULT_PREFS)
    got = memory.get(campaign_id, "scheduling.prefs", None)
    if isinstance(got, dict):
        p.update({k: v for k, v in got.items() if v is not None})
    return p


def marker(meeting_id: str) -> str:
    return f"[kingslayers-mtg:{meeting_id}]"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(v) -> datetime | None:
    if isinstance(v, dict):
        v = v.get("dateTime") or v.get("date")
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def busy_intervals(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    data = await mail.execute(SLUG_FREEBUSY, {
        "timeMin": _iso(start), "timeMax": _iso(end), "items": [{"id": "primary"}],
    }, timeout=30)
    cals = mail.find_key(data, "calendars") or {}
    out = []
    for cal in (cals.values() if isinstance(cals, dict) else []):
        if cal.get("errors"):
            raise mail.MailError(f"free/busy error: {cal['errors']}")
        for b in cal.get("busy") or []:
            s, e = _parse_dt(b.get("start")), _parse_dt(b.get("end"))
            if s and e:
                out.append((s, e))
    return sorted(out)


def compute_slots(start: datetime, end: datetime, busy: list[tuple[datetime, datetime]],
                  p: dict) -> list[tuple[datetime, datetime]]:
    """Free weekday slots inside working hours, `buffer_minutes` clear of every busy block."""
    tz = ZoneInfo(p["timezone"])
    slot = timedelta(minutes=int(p["slot_minutes"]))
    buf = timedelta(minutes=int(p["buffer_minutes"]))
    step = slot + buf
    h0, h1 = (int(x) for x in p["working_hours"])
    earliest = max(start, datetime.now(timezone.utc) + timedelta(hours=1))
    day = start.astimezone(tz).date()
    last_day = end.astimezone(tz).date()
    out = []
    while day <= last_day:
        if day.weekday() < 5:
            t = datetime.combine(day, time(h0, 0), tzinfo=tz)
            close = datetime.combine(day, time(h1, 0), tzinfo=tz)
            while t + slot <= close:
                s, e = t, t + slot
                if s >= earliest and e <= end and not any(
                        s < be + buf and e > bs - buf for bs, be in busy):
                    out.append((s, e))
                t += step
        day += timedelta(days=1)
    return out


async def free_slots(start: datetime, end: datetime, *, campaign_id: str | None = None
                     ) -> list[tuple[datetime, datetime]]:
    p = prefs(campaign_id)
    busy = await busy_intervals(start, end)
    return compute_slots(start, end, busy, p)


async def is_free(start: datetime, end: datetime, *, campaign_id: str | None = None) -> bool:
    p = prefs(campaign_id)
    buf = timedelta(minutes=int(p["buffer_minutes"]))
    busy = await busy_intervals(start - buf, end + buf)
    return not any(start < be + buf and end > bs - buf for bs, be in busy)


def _meet_link(ev: dict) -> str | None:
    if not isinstance(ev, dict):
        return None
    if ev.get("hangoutLink"):
        return ev["hangoutLink"]
    for ep in (ev.get("conferenceData") or {}).get("entryPoints") or []:
        if ep.get("entryPointType") == "video" and ep.get("uri"):
            return ep["uri"]
    return None


def _event_obj(data) -> dict:
    """The event dict inside a Composio response, wherever it sits."""
    if isinstance(data, dict):
        for k in ("response_data", "event", "data"):
            if isinstance(data.get(k), dict) and data[k].get("id"):
                return data[k]
        if data.get("id"):
            return data
    return {}


async def _find_existing(meeting_id: str, start: datetime) -> dict | None:
    day0 = start - timedelta(hours=14)
    day1 = start + timedelta(hours=14)
    try:
        data = await mail.execute(SLUG_LIST, {
            "calendarId": "primary", "timeMin": _iso(day0), "timeMax": _iso(day1),
            "q": f"kingslayers-mtg:{meeting_id}", "singleEvents": True,
        }, timeout=30)
    except Exception:
        return None
    items = mail.find_key(data, "items") or []
    for ev in items if isinstance(items, list) else []:
        if ev.get("status") != "cancelled" and marker(meeting_id) in (ev.get("description") or ""):
            return ev
    return None


async def _fallback_meet() -> str | None:
    """Personal Gmail may get no Meet link from CREATE_EVENT: make a real Meet space instead."""
    try:
        data = await mail.execute(SLUG_MEET, {}, timeout=30)
    except Exception:
        return None
    link = mail.find_key(data, "meetingUri", "meeting_uri")
    return link if isinstance(link, str) and link.startswith("https://meet.google.com/") else None


async def create_meeting(campaign, contact, meeting_id: str, *, start: datetime, end: datetime,
                         title: str, description: str) -> dict:
    """Create the invite (idempotent by the marker in the description). Returns {event_id, meet_link}."""
    attendee = mail.delivered_recipient(campaign, contact)
    mail.check_recipient(campaign, contact, attendee, initial=False)

    existing = await _find_existing(meeting_id, start)
    if existing:
        journal.log(campaign.id, "calendar", "Event already existed for this meeting; reused it",
                    contact_id=contact.id)
        return {"event_id": existing.get("id"), "meet_link": _meet_link(existing)}

    p = prefs(campaign.id)
    tz = ZoneInfo(p["timezone"])
    desc = f"{description}\n\n{marker(meeting_id)}"
    minutes = int((end - start).total_seconds() // 60)
    mail.check_recipient(campaign, contact, attendee, initial=False)
    data = await mail.execute(SLUG_CREATE, {
        "calendar_id": "primary",
        "summary": title,
        "description": desc,
        "start_datetime": start.astimezone(tz).strftime("%Y-%m-%dT%H:%M:%S"),
        "timezone": p["timezone"],
        "event_duration_hour": minutes // 60,
        "event_duration_minutes": minutes % 60,
        "attendees": [attendee],
        "create_meeting_room": True,
        "send_updates": "all",
    }, timeout=45)
    ev = _event_obj(data)
    event_id = ev.get("id") or mail.find_key(data, "id")
    link = _meet_link(ev) or mail.find_key(data, "hangoutLink")
    if event_id and not link:
        link = await _fallback_meet()
        if link:
            await _attach_link(event_id, link, desc)
            journal.log(campaign.id, "calendar", "No Meet link on the event; created a Meet space and added it",
                        contact_id=contact.id)
    return {"event_id": event_id, "meet_link": link}


async def _attach_link(event_id: str, link: str, desc: str) -> None:
    try:
        await mail.execute("GOOGLECALENDAR_PATCH_EVENT", {
            "calendar_id": "primary", "event_id": event_id, "location": link,
            "description": f"Google Meet: {link}\n\n{desc}", "send_updates": "all",
        }, timeout=30)
    except Exception:
        pass


def tz_now(campaign_id: str | None = None) -> datetime:
    return datetime.now(ZoneInfo(prefs(campaign_id)["timezone"]))


