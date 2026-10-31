"""Composio smoke test (PLAN.md P3 checklist item 1).

Usage (from the repo root):
  .venv/bin/python scripts/smoke_composio.py schemas          # print each tool's argument names (free)
  .venv/bin/python scripts/smoke_composio.py send             # email STAND_IN_EMAIL, print thread id
  .venv/bin/python scripts/smoke_composio.py thread <id>      # read a thread back, normalized
  .venv/bin/python scripts/smoke_composio.py freebusy         # busy blocks + computed slots, next 7 days
  .venv/bin/python scripts/smoke_composio.py event            # 20-min event tomorrow with STAND_IN_EMAIL
  .venv/bin/python scripts/smoke_composio.py meet             # GOOGLEMEET_CREATE_MEET alone

Only ever sends to STAND_IN_EMAIL. Never prints secrets.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app import calendar_io, mail  # noqa: E402
from app.config import S  # noqa: E402

SLUGS = [mail.SLUG_SEND, mail.SLUG_REPLY, mail.SLUG_THREAD, calendar_io.SLUG_FREEBUSY,
         "GOOGLECALENDAR_FIND_FREE_SLOTS", calendar_io.SLUG_CREATE, calendar_io.SLUG_LIST,
         "GOOGLECALENDAR_FIND_EVENT", "GOOGLECALENDAR_PATCH_EVENT", calendar_io.SLUG_MEET]
TZ = ZoneInfo("Asia/Kolkata")


def show(label, obj, limit=3000):
    s = json.dumps(obj, indent=2, default=str)
    print(f"--- {label} ---\n{s[:limit]}{' …' if len(s) > limit else ''}")


def schemas():
    c = mail._composio()
    for slug in SLUGS:
        try:
            t = c.tools.get_raw_composio_tool_by_slug(slug)
            d = t.model_dump() if hasattr(t, "model_dump") else dict(t)
            params = (d.get("input_parameters") or {})
            props = params.get("properties") or {}
            req = params.get("required") or []
            print(f"\n{slug}  (version {d.get('version')})")
            for k, v in props.items():
                print(f"  {'*' if k in req else ' '} {k}: {v.get('type')}  {str(v.get('description', ''))[:90]}")
        except Exception as e:
            print(f"\n{slug}: NOT AVAILABLE ({e})")


async def send():
    to = S.STAND_IN_EMAIL
    data = await mail.execute(mail.SLUG_SEND, {
        "recipient_email": to, "subject": "Kingslayers smoke test",
        "body": "Smoke test from the Kingslayers build. Reply 'interested' to test the inbox.",
        "is_html": False})
    show("send response", data)
    print("message_id:", mail.find_key(data, "id", "messageId"), " thread_id:", mail.find_key(data, "threadId"))


async def thread(tid):
    raw = await mail.execute(mail.SLUG_THREAD, {"thread_id": tid})
    show("raw thread", raw, 4000)
    show("normalized", await mail.fetch_thread(tid))


async def freebusy():
    now = datetime.now(TZ)
    end = now + timedelta(days=7)
    busy = await calendar_io.busy_intervals(now, end)
    show("busy", [(a.isoformat(), b.isoformat()) for a, b in busy])
    slots = calendar_io.compute_slots(now, end, busy, calendar_io.DEFAULT_PREFS)
    print(f"{len(slots)} free slots; first 5:")
    for a, b in slots[:5]:
        print("  ", a.astimezone(TZ).strftime("%a %d %b %H:%M"), "-", b.astimezone(TZ).strftime("%H:%M"))


async def event():
    start = (datetime.now(TZ) + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
    data = await mail.execute(calendar_io.SLUG_CREATE, {
        "calendar_id": "primary", "summary": "Kingslayers smoke test",
        "description": "Smoke test [kingslayers-mtg:smoke]",
        "start_datetime": start.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": "Asia/Kolkata",
        "event_duration_hour": 0, "event_duration_minutes": 20,
        "attendees": [S.STAND_IN_EMAIL], "create_meeting_room": True, "send_updates": "all"})
    show("create event response", data, 5000)
    ev = calendar_io._event_obj(data)
    print("event_id:", ev.get("id") or mail.find_key(data, "id"), " meet_link:", calendar_io._meet_link(ev))


async def meet():
    data = await mail.execute(calendar_io.SLUG_MEET, {})
    show("create meet response", data)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "schemas"
    if not (S.COMPOSIO_API_KEY and S.COMPOSIO_USER_ID and S.STAND_IN_EMAIL):
        sys.exit("Set COMPOSIO_API_KEY, COMPOSIO_USER_ID and STAND_IN_EMAIL in .env first")
    if cmd == "schemas":
        schemas()
    elif cmd == "thread":
        asyncio.run(thread(sys.argv[2]))
    else:
        asyncio.run({"send": send, "freebusy": freebusy, "event": event, "meet": meet}[cmd]())
