"""Reply stripping, opt-out, slot parsing (PLAN.md §9, P3)."""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(_HERE.parent), str(_HERE)]

import asyncio

import pytest

from app import inbox
from app.booking import parse_slot_choice
from app.inbox import is_opt_out, strip_reply
from test_guard import load, make_campaign, make_contact, tdb  # noqa: F401

OPT_OUT_LINE = "If this isn't relevant, just reply 'remove me' and I won't email again."


def test_interested_reply_quoting_opt_out_is_not_suppressed():
    raw = ("Interested, send times\n\n"
           "On Sat, 31 Oct 2026 at 14:40, Kingslayers Demo <seller@example.com> wrote:\n"
           "> Hi Asha, saw you're hiring 12 recruiters...\n"
           f"> {OPT_OUT_LINE}\n")
    text = strip_reply(raw)
    assert text == "Interested, send times"
    assert not is_opt_out(text)


def test_wrapped_gmail_header_and_html_quote():
    raw = ("Sounds good\n\nOn Sat, 31 Oct 2026 at 14:40, Kingslayers Demo <\nseller@example.com> wrote:\n"
           f"> {OPT_OUT_LINE}\n")
    assert strip_reply(raw) == "Sounds good"
    html = (f'<div dir="ltr">Yes, interested</div><br><div class="gmail_quote">On Sat... wrote:'
            f'<blockquote>{OPT_OUT_LINE}</blockquote></div>')
    assert strip_reply(html) == "Yes, interested"


def test_slot_reply_quoting_slot_list_parses_2():
    raw = ("2\n\nOn Sat, 31 Oct 2026 at 14:45, Kingslayers Demo <seller@example.com> wrote:\n"
           "> 1) Mon 2 Nov, 11:00–11:20 IST\n> 2) Tue 3 Nov, 11:00–11:20 IST\n"
           "> 3) Wed 4 Nov, 11:00–11:20 IST\n> Reply with 1, 2 or 3.\n")
    assert parse_slot_choice(strip_reply(raw)) == 2


@pytest.mark.parametrize("text,want", [
    ("2", 2), ("option 2", 2), ("#2", 2), ("2.", 2), ("Option 2 please", 2), ("2 works for me", 2),
    ("(3)", 3), ("1!", 1), ("the second one", 2), ("Slot #3", 3), ("Let's do option 1, thanks", 1),
    ("4", None), ("", None), ("1 or 2 both fine", None), ("how about 11:00 tomorrow", None),
])
def test_parse_slot_choice_variants(text, want):
    assert parse_slot_choice(text) == want


@pytest.mark.parametrize("text,want", [
    ("remove me", True), ("Please unsubscribe me", True), ("stop emailing me", True),
    ("opt out", True), ("Not interested, stop.", True), ("Interested, send times", False),
    ("Not interested right now", False),
])
def test_is_opt_out(text, want):
    assert is_opt_out(text) is want


def test_empty_after_strip_goes_to_needs_human(tdb, monkeypatch):
    called = []
    monkeypatch.setattr(inbox, "classify", lambda t: called.append(t))
    cid = make_campaign(tdb)
    ct = make_contact(tdb, cid, state="WAITING", delivered_to="standin@example.com", thread_id="t1")
    raw = "On Sat, 31 Oct 2026 at 14:40, Kingslayers Demo <seller@example.com> wrote:\n> hello\n"
    out = asyncio.run(inbox.handle_reply(ct, {"id": "g1", "from": "standin@example.com", "text": raw}))
    assert out == "empty"
    assert load(tdb, "Contact", ct).state == "NEEDS_HUMAN"
    assert called == []
