"""Import with AI: reading documents, asking Claude (faked here), and turning
the answer into a request the office checks before it touches an event."""

import html
import io
import json
import threading
import zipfile
from datetime import date, timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic
import httpx2
import pytest
from PIL import Image

from backline import ai_import, intake, util
from backline import db as dbm

from .conftest import query

REAL_SEND = ai_import._send
KEY = "sk-ant-test-0000000000000abcd"
PDF = b"%PDF-1.4\n% a tech rider\n"


def blank_answers():
    return {name: [] if q.kind == "chips" and q.multiple else 0 if q.kind == "int" else ""
            for name, q in intake.QUESTIONS.items()}


def ai_result(answers=None, quotes=(), other=(), match=0, reason="", summary="Email asking for a quote."):
    a = blank_answers()
    a.update(answers or {})
    return {"summary": summary, "answers": a, "quotes": [{"field": f, "quote": q} for f, q in quotes],
            "other_details": list(other), "matching_event_id": match, "match_reason": reason}


def reply(result=None, model="claude-opus-5-5", stop="end_turn", usage=None, text=None):
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": model, "stop_reason": stop,
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "text", "text": json.dumps(result or ai_result()) if text is None else text}],
            "usage": usage or {"input_tokens": 5000, "output_tokens": 1500}}


class FakeClaude:
    def __init__(self):
        self.calls, self.replies = [], []

    def __call__(self, params):
        self.calls.append(params)
        answer = self.replies.pop(0) if self.replies else reply()
        if isinstance(answer, Exception):
            raise answer
        return answer

    def text_sent(self, n=-1):
        return "\n".join(b["text"] for b in self.calls[n]["messages"][0]["content"] if b["type"] == "text")


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    fake = FakeClaude()
    monkeypatch.setattr(ai_import, "_send", fake)
    return fake


def _import(client, pasted="", files=(), follow=True, **extra):
    data = {"pasted": pasted, **extra}
    if files:
        data["files"] = [(io.BytesIO(content), name) for name, content in files]
    return client.post("/requests/import", data=data, content_type="multipart/form-data", follow_redirects=follow)


def _api_error(cls, status, message):
    body = {"type": "error", "error": {"type": "error", "message": message}}
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(message, response=httpx2.Response(status, request=request, json=body), body=body)


GALA = {
    "name": "Priya Raman", "organization": "Lakeview Youth Arts Fund", "email": "priya.raman@example.org",
    "phone": "(773) 555-0148", "event_name": "Spring Gala", "event_date": "2030-04-18", "attendance": 300,
    "venue_name": "Harborview Ballroom", "venue_address": "500 N Harbor Dr, Chicago", "load_in_time": "1:00 PM",
    "load_out_time": "23:59", "doors_time": "18:00", "needs": ["Microphones for speeches", "Live band support"],
    "tech": "yes, someone to run the sound", "setting": "indoors", "mic_count": 5, "access": ["Loading dock"],
    "parking": "Two spaces at the Wells St dock.", "gear_details": "Podium mic\n4 handheld wireless",
}


# --- Setup and the upload page -------------------------------------------------------

def test_without_a_key_it_explains_the_setup(client, app):
    page = client.get("/requests/import").data.decode()
    assert "isn't set up yet" in page and "Settings → AI import" in page
    assert 'disabled>Read with AI' in page
    resp = _import(client, pasted="Party on June 5")
    assert b"Add your Anthropic API key as ANTHROPIC_API_KEY" in resp.data
    assert not query(app, "SELECT * FROM client_requests")
    page = client.get("/settings/ai").data.decode()
    assert "Not set up" in page and "ANTHROPIC_API_KEY" in page and "Check connection" not in page


def test_import_needs_something_to_read(client, claude, app):
    resp = _import(client)
    assert b"Choose at least one file, or paste some text." in resp.data
    assert not claude.calls


def test_inbox_and_event_pages_link_to_import(client, make):
    assert "Import with AI" in client.get("/requests").data.decode()
    event_id = make("events", title="Rooftop party", event_date="2030-06-01", status="hold")
    page = client.get(f"/events/{event_id}?tab=documents").data.decode()
    assert f"/requests/import?event={event_id}" in page and "Read it with AI" in page


# --- Reading documents into a request -------------------------------------------------

def test_documents_become_a_request_to_check(client, claude, app, make):
    make("events", title="Spring Gala", event_date="2030-04-18", status="inquiry")
    claude.replies.append(reply(ai_result(
        GALA, quotes=[("load_in_time", "Load-in from 1 PM"), ("attendance", "about 300 guests"),
                      ("name", "Priya Raman, Events")],
        other=["Crew meals provided at 5 PM", "  "], summary="Email from the gala's coordinator with the venue details.")))
    resp = _import(client, pasted="Hi! Load-in from 1 PM...", files=[("Gala rider.pdf", PDF)])
    page = resp.data.decode()
    assert "Read. Check what the AI found" in page and "Imported documents #1" in page

    params = claude.calls[0]
    assert params["model"] == "claude-opus-5-5" and params["max_tokens"] == ai_import.MAX_TOKENS
    assert params["betas"] == ["server-side-fallback-2026-07-01"] and params["fallbacks"] == "default"
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"]["effort"] == "medium"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert "Chicago Sound and Backline" in params["system"]
    content = params["messages"][0]["content"]
    pdf_block = next(b for b in content if b["type"] == "document")
    assert pdf_block["title"] == "Gala rider.pdf" and pdf_block["source"]["media_type"] == "application/pdf"
    assert ai_import.base64.b64decode(pdf_block["source"]["data"]) == PDF
    sent = claude.text_sent()
    assert '<file name="Pasted text">' in sent and f"Today is {util.today():%A, %B %-d, %Y}" in sent
    assert "| 2030-04-18 | Spring Gala |" in sent

    row = query(app, "SELECT * FROM client_requests", one=True)
    assert row["source"] == "import" and row["status"] == "new" and row["name"] == "Priya Raman"
    a = json.loads(row["answers"])
    assert a["load_in_time"] == "13:00" and a["load_out_time"] == "23:59"  # "1:00 PM" made form-shaped
    assert a["tech"] == intake.TECH_ON_SITE and a["setting"] == "Indoors"  # choices matched despite capitals
    assert a["attendance"] == 300 and a["needs"] == [intake.SPEECH_MICS, intake.BAND]
    assert "end_date" not in a and "description" not in a  # blank answers are left out
    ai = json.loads(row["ai_details"])
    assert ai["model"] == "claude-opus-5-5" and ai["by"] == "admin" and ai["other"] == ["Crew meals provided at 5 PM"]
    assert ai["quotes"]["load_in_time"] == "Load-in from 1 PM" and ai["files"] == ["Pasted text.txt", "Gala rider.pdf"]
    assert ai["cost"] == pytest.approx(5000 * 4 / 1e6 + 1500 * 20 / 1e6)
    names = [f["original_name"] for f in query(app, "SELECT * FROM client_request_files ORDER BY id")]
    assert names == ["Pasted text.txt", "Gala rider.pdf"]
    usage = query(app, "SELECT * FROM ai_usage", one=True)
    assert usage["outcome"] == "ok" and usage["request_id"] == row["id"] and usage["input_tokens"] == 5000

    assert "“Load-in from 1 PM”" in page and "“about 300 guests”" in page and "“Priya Raman, Events”" in page
    assert "Crew meals provided at 5 PM" in page and "Claude Opus 5.5 read Pasted text.txt, Gala rider.pdf" in page
    assert "cost 5¢" in page
    inbox = client.get("/requests").data.decode()
    assert "AI import" in inbox and "Priya Raman" in inbox


def test_bad_answers_are_left_out_like_on_the_form(client, claude, app):
    claude.replies.append(reply(ai_result({
        "email": "priya at example dot org", "event_date": "June 5th", "end_date": "2030-04-18",
        "start_time": "evening", "attendance": 0, "mic_count": 4, "venue_name": "  Harborview  ",
    }, quotes=[("email", "priya at example dot org"), ("venue_name", "Harborview Ballroom"), ("bogus", "x")])))
    _import(client, pasted="notes")
    row = query(app, "SELECT * FROM client_requests", one=True)
    a = json.loads(row["answers"])
    assert a == {"end_date": "2030-04-18", "mic_count": 4, "venue_name": "Harborview"}
    assert json.loads(row["ai_details"])["quotes"] == {"venue_name": "Harborview Ballroom"}
    assert row["name"] == "Imported documents"


def test_a_matched_event_is_suggested_and_adding_only_fills_blanks(client, claude, app, make):
    client_id = make("clients", name="Lakeview Youth Arts Fund")
    gala = make("events", title="Spring Gala", event_date="2030-04-18", status="inquiry", client_id=client_id,
                guest_count=250, notes="Asked for a quote.")
    claude.replies.append(reply(ai_result(GALA, other=["Crew meals at 5 PM"], match=gala,
                                          reason="Same organization and date.")))
    page = _import(client, files=[("Gala details.pdf", PDF)]).data.decode()
    assert "The AI thinks this is about" in page and "Same organization and date." in page
    assert f'<option value="{gala}" selected>' in page and "Create a new inquiry instead" in page
    row = query(app, "SELECT * FROM client_requests", one=True)
    assert row["suggested_event_id"] == gala

    resp = client.post(f"/requests/{row['id']}/add-to-event", data={"event_id": gala}, follow_redirects=True)
    assert b"Added request #1 to this event" in resp.data
    event = query(app, "SELECT * FROM events WHERE id = ?", (gala,), one=True)
    assert event["guest_count"] == 250  # already there: not overwritten
    assert event["load_in_time"] == "13:00" and event["doors_time"] == "18:00" and event["client_id"] == client_id
    assert event["notes"].startswith("Asked for a quote.")
    assert "From documents read by AI (request #1)" in event["notes"] and "Audience (from the request): 300" in event["notes"]
    assert "Also in the documents:\n- Crew meals at 5 PM" in event["notes"]
    venue = query(app, "SELECT * FROM venues WHERE id = ?", (event["venue_id"],), one=True)
    assert venue["name"] == "Harborview Ballroom"
    doc = query(app, "SELECT * FROM event_files WHERE event_id = ?", (gala,), one=True)
    assert doc["uploaded_by"] == "AI import" and doc["description"] == "Read by AI (request #1)" and not doc["crew_visible"]


def test_unknown_or_cancelled_matches_are_ignored(client, claude, app, make):
    gone = make("events", title="Old show", event_date="2030-04-18", status="cancelled")
    claude.replies += [reply(ai_result(match=gone, reason="Same date")), reply(ai_result(match=9999))]
    _import(client, pasted="one")
    _import(client, pasted="two")
    rows = query(app, "SELECT suggested_event_id, ai_details FROM client_requests")
    assert [r["suggested_event_id"] for r in rows] == [None, None]
    assert json.loads(rows[0]["ai_details"])["match_reason"] == ""
    assert "Old show" not in claude.text_sent(0)


def test_importing_from_an_event_page_targets_that_event(client, claude, app, make):
    old = make("events", title="Last year's gala", event_date=(util.today() - timedelta(days=400)).isoformat(),
               status="completed")
    page = client.get(f"/requests/import?event={old}").data.decode()
    assert f'<option value="{old}" selected>' in page
    _import(client, pasted="Updated timeline attached", event=str(old))
    assert f"The office says these documents are about event {old} (Last year's gala" in claude.text_sent()
    assert f"{old} | " in claude.text_sent()  # listed even though it's long past
    assert query(app, "SELECT suggested_event_id FROM client_requests", one=True)["suggested_event_id"] == old


def test_documents_without_a_client_can_still_become_an_inquiry(client, claude, app):
    claude.replies.append(reply(ai_result({"venue_name": "Harborview Ballroom", "event_date": "2030-05-02",
                                           "event_type": "Wedding"})))
    _import(client, files=[("Venue tech pack.pdf", PDF)])
    page = client.get("/requests/1").data.decode()
    assert "The documents didn't say who the client is." in page
    page = client.get("/requests/1/convert").data.decode()
    assert "New client:" not in page and '<option value="" selected>No client yet</option>' in page
    assert 'value="Wedding"' in page
    resp = client.post("/requests/1/convert", data={"title": "Wedding", "event_type": "Wedding",
                                                    "event_date": "2030-05-02", "client": "new", "venue": "new"})
    assert b"Choose a client." in resp.data
    resp = client.post("/requests/1/convert", data={"title": "Wedding", "event_type": "Wedding",
                                                    "event_date": "2030-05-02", "client": "", "venue": "new"})
    assert resp.status_code == 302
    event = query(app, "SELECT * FROM events", one=True)
    assert event["client_id"] is None and event["status"] == "inquiry"
    assert event["notes"].startswith("From documents read by AI (request #1)") and "Contact:" not in event["notes"]
    with app.app_context():
        assert intake.title_for({}) == "New inquiry"
    # Adding more documents without a contact doesn't invent a client either.
    claude.replies.append(reply(ai_result({"load_in_time": "15:00"})))
    _import(client, pasted="Load-in at 3")
    client.post("/requests/2/add-to-event", data={"event_id": event["id"]})
    event = query(app, "SELECT * FROM events", one=True)
    assert event["client_id"] is None and event["load_in_time"] == "15:00"
    assert not query(app, "SELECT * FROM clients")


def test_form_requests_still_read_the_same(anon, client, app):
    anon.post("/request", data={"name": "Dev Patel", "phone": "(773) 555-0163"})
    page = client.get("/requests/1").data.decode()
    assert "Request #1" in page and "What the AI found" not in page and "Dev Patel" in page
    row = query(app, "SELECT source, suggested_event_id FROM client_requests", one=True)
    assert row == {"source": "form", "suggested_event_id": None}


# --- When things go wrong ------------------------------------------------------------------

@pytest.mark.parametrize("error, message", [
    (lambda: _api_error(anthropic.AuthenticationError, 401, "invalid x-api-key"), "didn't accept the API key"),
    (lambda: _api_error(anthropic.NotFoundError, 404, "model not found"), "isn't available on your Anthropic account"),
    (lambda: _api_error(anthropic.RateLimitError, 429, "slow down"), "Wait a minute"),
    (lambda: _api_error(anthropic.BadRequestError, 400, "Your credit balance is too low to access the API."),
     "out of credit"),
    (lambda: _api_error(anthropic.BadRequestError, 400, "The PDF specified was not valid."),
     "Anthropic couldn't read these documents: The PDF specified was not valid."),
    (lambda: _api_error(anthropic.InternalServerError, 529, "Overloaded"), "busy or having trouble"),
    (lambda: anthropic.APITimeoutError(httpx2.Request("POST", "https://api.anthropic.com")), "took too long"),
    (lambda: anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")),
     "Couldn't reach Anthropic"),
])
def test_anthropic_errors_are_explained(client, claude, app, error, message):
    claude.replies.append(error())
    resp = _import(client, pasted="Some notes", files=[("rider.pdf", PDF)])
    page = html.unescape(resp.data.decode())
    assert message in page and "Choose the files again" in page and "Some notes" in page
    assert not query(app, "SELECT * FROM client_requests") and not query(app, "SELECT * FROM client_request_files")


@pytest.mark.parametrize("answer, message, outcome", [
    (reply(stop="refusal", text=""), "declined to read these documents", "declined"),
    (reply(stop="max_tokens", text='{"summary": "cut'), "more in them than the AI could write out", "too long"),
    (reply(text="not json"), "came back garbled", "unreadable answer"),
])
def test_unusable_answers_are_reported_and_still_counted(client, claude, app, answer, message, outcome):
    claude.replies.append(answer)
    assert message in _import(client, pasted="notes").data.decode()
    assert not query(app, "SELECT * FROM client_requests")
    assert query(app, "SELECT outcome FROM ai_usage", one=True)["outcome"] == outcome


def test_unexpected_errors_are_not_hidden(client, claude):
    claude.replies.append(ValueError("bug"))
    with pytest.raises(ValueError):
        _import(client, pasted="notes")


# --- Models and cost ---------------------------------------------------------------------------

def test_haiku_has_no_fallback_and_its_own_prices(client, claude, app):
    with app.app_context():
        dbm.set_setting("ai_model", "claude-haiku-5-5")
    claude.replies.append(reply(model="claude-haiku-5-5", usage={"input_tokens": 120_000, "output_tokens": 2000}))
    _import(client, pasted="long tech pack")
    assert "betas" not in claude.calls[0] and "fallbacks" not in claude.calls[0]
    assert claude.calls[0]["model"] == "claude-haiku-5-5"
    cost = query(app, "SELECT cost FROM ai_usage", one=True)["cost"]
    assert cost == pytest.approx(120_000 * 0.50 / 1e6 + 2000 * 2.50 / 1e6)  # long prompts cost more on Haiku


def test_cost_counts_every_attempt_when_a_fallback_answers(app):
    message = reply(model="claude-opus-4-8", usage={
        "input_tokens": 1000, "output_tokens": 500,
        "iterations": [
            {"type": "message", "input_tokens": 1000, "output_tokens": 0, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0},
            {"type": "fallback_message", "model": "claude-opus-4-8", "input_tokens": 1000, "output_tokens": 500,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        ]})
    tokens_in, tokens_out, cost = ai_import.usage_of(message, "claude-opus-5-5")
    assert (tokens_in, tokens_out) == (2000, 500)
    assert float(cost) == pytest.approx(1000 * 4 / 1e6 + (1000 * 5 + 500 * 25) / 1e6)


@pytest.mark.parametrize("cost, text", [(0, "under 1¢"), (0.004, "under 1¢"), (0.042, "4¢"), (0.5, "50¢"),
                                        (12.3, "$12.30")])
def test_cost_text(cost, text):
    assert ai_import.cost_text(cost) == text


def test_settings_page(client, claude, app, monkeypatch):
    page = client.get("/settings/ai").data.decode()
    assert "Set up" in page and "…abcd" in page and KEY not in page
    assert 'value="claude-opus-5-5" checked' in page
    resp = client.post("/settings/ai", data={"model": "claude-sonnet-5-5"}, follow_redirects=True)
    assert b"AI import will use Claude Sonnet 5.5." in resp.data
    client.post("/settings/ai", data={"model": "gpt-4"})
    with app.app_context():
        assert ai_import.current_model() == "claude-sonnet-5-5"
    page = client.get("/requests/import").data.decode()
    assert "Uses Claude Sonnet 5.5: about 2¢" in page

    monkeypatch.setattr(ai_import, "_check", lambda model: "Claude Sonnet 5.5")
    resp = client.post("/settings/ai", data={"action": "check"}, follow_redirects=True)
    assert b"Connected. Claude Sonnet 5.5 is ready" in resp.data

    def bad_key(_model):
        raise _api_error(anthropic.AuthenticationError, 401, "invalid x-api-key")

    monkeypatch.setattr(ai_import, "_check", bad_key)
    resp = client.post("/settings/ai", data={"action": "check"}, follow_redirects=True)
    assert b"didn&#39;t accept the API key" in resp.data


def test_spending_by_month(client, app):
    today = util.today()
    last_month = today.replace(day=1) - timedelta(days=3)
    with app.app_context():
        for when, cost in ((today, 0.13), (today, 0.04), (last_month, 0.5), (date(2020, 1, 5), 1.0)):
            dbm.insert("ai_usage", {"created_at": f"{when.isoformat()}T10:00:00", "model": "claude-opus-5-5",
                                    "cost": cost})
        spent = ai_import.spending()
    assert spent["this_month"] == {"count": 2, "cost": pytest.approx(0.17)}
    assert spent["last_month"] == {"count": 1, "cost": pytest.approx(0.5)}
    assert spent["all_time"]["count"] == 4
    page = client.get("/settings/ai").data.decode()
    assert "2 imports · about 17¢" in page


# --- Reading different kinds of files ----------------------------------------------------------

def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in members.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_word_documents():
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = ("<w:p><w:r><w:t>Gala tech notes</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Doors</w:t><w:tab/><w:t>6:00 PM</w:t></w:r></w:p>"
            "<w:sdt><w:sdtContent><w:p><w:r><w:t>Inside a content control</w:t></w:r></w:p></w:sdtContent></w:sdt>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Ch 1</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>Podium</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:sectPr/>")
    data = _zip({"word/document.xml": f'<?xml version="1.0"?><w:document {ns}><w:body>{body}</w:body></w:document>'})
    (part,), keep, notes = ai_import.read_file("Tech notes.docx", data)
    assert part == {"kind": "text", "name": "Tech notes.docx",
                    "text": "Gala tech notes\nDoors\t6:00 PM\nInside a content control\nCh 1 | Podium"}
    with pytest.raises(ai_import.Problem, match="couldn't be opened as a Word file"):
        ai_import.read_file("broken.docx", b"not a zip")


def test_excel_workbooks():
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    data = _zip({
        "xl/workbook.xml": f'<workbook {ns} {rel}><sheets><sheet name="Inputs" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Type="ws" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml": f"<sst {ns}><si><t>Ch</t></si><si><t>Source</t></si><si><r><t>Ki</t></r><r><t>ck</t></r></si></sst>",
        "xl/styles.xml": f'<styleSheet {ns}><numFmts><numFmt numFmtId="164" formatCode="h:mm AM/PM"/></numFmts>'
                         '<cellXfs><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/></cellXfs></styleSheet>',
        "xl/worksheets/sheet1.xml": f"""<worksheet {ns}><sheetData>
            <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
            <row r="2"><c r="A2"><v>1</v></c><c r="B2" t="s"><v>2</v></c><c r="D2" t="inlineStr"><is><t>Beta 91A</t></is></c></row>
            <row r="3"></row>
            <row r="4"><c r="A4" t="inlineStr"><is><t>Show</t></is></c><c r="B4" s="1"><v>47100</v></c><c r="C4" s="2"><v>0.75</v></c><c r="D4" t="b"><v>1</v></c></row>
        </sheetData></worksheet>""",
    })
    (part,), _keep, _notes = ai_import.read_file("Input list.xlsx", data)
    show = (date(1899, 12, 30) + timedelta(days=47100)).isoformat()
    assert part["text"] == f"Sheet: Inputs\nCh\tSource\n1\tKick\t\tBeta 91A\nShow\t{show}\t18:00\tTRUE"


def _png(size, mode="RGB"):
    out = io.BytesIO()
    Image.new(mode, size, (200, 30, 30, 0) if mode == "RGBA" else (200, 30, 30)).save(out, "PNG")
    return out.getvalue()


def test_emails_with_attachments():
    msg = EmailMessage()
    msg["From"] = "Priya Raman <priya.raman@example.org>"
    msg["To"] = "office@example.com"
    msg["Subject"] = "Gala details"
    msg.set_content("Hi! Load-in from 1 PM through the dock on Wells St.")
    msg.add_attachment(PDF, maintype="application", subtype="pdf", filename="Stage plot.pdf")
    msg.add_attachment(_png((40, 20)), maintype="image", subtype="png", filename="logo.png", disposition="inline",
                       cid="<logo1@example.org>")
    msg.add_attachment(b"zz", maintype="application", subtype="octet-stream", filename="Budget.pages")
    forwarded = EmailMessage()
    forwarded["From"] = "events@harborview.example.com"
    forwarded["Subject"] = "Venue notes"
    forwarded.set_content("The freight elevator must be booked.")
    msg.add_attachment(forwarded)
    parts, keep, notes = ai_import.read_file("Gala.eml", msg.as_bytes())
    assert [p["kind"] for p in parts] == ["text", "pdf", "text"]
    assert parts[0]["text"].startswith("From: Priya Raman <priya.raman@example.org>\nTo: office@example.com\n"
                                       "Subject: Gala details\n\nHi! Load-in from 1 PM")
    assert "Subject: Venue notes" in parts[2]["text"] and "freight elevator" in parts[2]["text"]
    assert [name for name, _data in keep] == ["Stage plot.pdf", "Forwarded email.eml"]
    assert notes == ["Skipped Budget.pages (attached to Gala.eml): the AI can't read that kind of file."]

    html_only = EmailMessage()
    html_only["Subject"] = "Timeline"
    html_only.set_content("<html><head><style>p{}</style></head><body><p>Doors&nbsp;6 PM</p><table><tr><td>7:00</td>"
                          "<td>Dinner</td></tr></table><script>x()</script></body></html>", subtype="html")
    (part,), _keep, _notes = ai_import.read_file("t.eml", html_only.as_bytes())
    assert part["text"] == "Subject: Timeline\n\nDoors 6 PM\n\n 7:00 Dinner"


def test_images():
    (part,), _keep, _notes = ai_import.read_file("plot.png", _png((800, 600), "RGBA"))
    assert part["media_type"] == "image/png"  # small enough: sent as it is
    (part,), _keep, _notes = ai_import.read_file("Stage photo.jpg", _png((3000, 2000)))  # mislabeled, and huge
    assert part["media_type"] == "image/jpeg"
    with Image.open(io.BytesIO(part["data"])) as img:
        assert img.size == (1568, 1045)
    with pytest.raises(ai_import.Problem, match="iPhone photo"):
        ai_import.read_file("IMG_0042.HEIC", b"\x00\x00\x00\x18ftypheic" + b"0" * 64)
    with pytest.raises(ai_import.Problem, match="doesn't look like a JPG"):
        ai_import.read_file("fake.jpg", b"hello")


@pytest.mark.parametrize("name, data, message", [
    ("old.doc", b"\xd0\xcf\x11\xe0", "Save or export it as a PDF"),
    ("plot.vwx", b"x", "can't read plot.vwx"),
    ("empty.pdf", b"", "empty.pdf is empty"),
    ("fake.pdf", b"<html>", "doesn't look like a PDF"),
    ("blank.txt", b"   \n", "no text the AI can read"),
    ("huge.txt", b"a" * (ai_import.MAX_TEXT_CHARS + 1), "too long to read in one go"),
])
def test_files_the_ai_cant_read(name, data, message):
    with pytest.raises(ai_import.Problem, match=message):
        ai_import.read_file(name, data)


def test_text_files_in_other_encodings():
    (part,), _keep, _notes = ai_import.read_file("notes.txt", "Café stage — 6 PM".encode("cp1252"))
    assert part["text"] == "Café stage — 6 PM"


def test_upload_limits(client, claude, app):
    resp = _import(client, files=[(f"page{i}.pdf", PDF) for i in range(ai_import.MAX_FILES + 1)])
    assert f"Import up to {ai_import.MAX_FILES} files at a time.".encode() in resp.data
    big = b"%PDF" + b"0" * (ai_import.MAX_TOTAL_MB * 1024 * 1024)
    resp = _import(client, files=[("big.pdf", big)])
    assert b"add up to more than 20 MB" in resp.data
    resp = _import(client, files=[("plot.vwx", b"cad")])
    assert b"The AI can&#39;t read plot.vwx" in resp.data
    assert not claude.calls


# --- The request sent to Anthropic -----------------------------------------------------------------

def test_every_question_is_explained_to_the_ai():
    assert set(ai_import.FIELD_HELP) == set(intake.QUESTIONS)


def test_schema_stays_within_structured_output_limits(app):
    def walk(node):
        if isinstance(node, dict):
            assert "anyOf" not in node and not isinstance(node.get("type"), list)
            if node.get("type") == "object":
                assert node["additionalProperties"] is False and set(node["required"]) == set(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    with app.app_context():
        walk(ai_import.schema())


class _FakeAnthropicServer(BaseHTTPRequestHandler):
    """Speaks just enough of the Messages API (streaming) for the real SDK."""

    seen, answer = [], ""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                "body": body})
        events = [
            {"type": "message_start", "message": {
                "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"], "content": [],
                "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 2400, "output_tokens": 1}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": type(self).answer}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
             "usage": {"output_tokens": 800}},
            {"type": "message_stop"},
        ]
        payload = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


def test_the_real_sdk_sends_what_we_expect(client, app, monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAnthropicServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _FakeAnthropicServer.seen = []
    _FakeAnthropicServer.answer = json.dumps(ai_result({"name": "Priya Raman", "venue_name": "Harborview Ballroom"}))
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(ai_import, "_send", REAL_SEND)
    try:
        resp = _import(client, pasted="Gala at Harborview", files=[("rider.pdf", PDF)])
    finally:
        server.shutdown()
    assert b"Read. Check what the AI found" in resp.data and b"Harborview Ballroom" in resp.data
    (call,) = _FakeAnthropicServer.seen
    assert call["path"].startswith("/v1/messages")
    assert call["headers"]["x-api-key"] == KEY
    assert "server-side-fallback-2026-07-01" in call["headers"]["anthropic-beta"]
    body = call["body"]
    assert body["stream"] is True and body["fallbacks"] == "default" and body["model"] == "claude-opus-5-5"
    assert body["output_config"]["format"]["schema"]["properties"]["answers"]["properties"]["needs"]["type"] == "array"
    assert [b["type"] for b in body["messages"][0]["content"]] == ["text", "document", "text"]
    usage = query(app, "SELECT * FROM ai_usage", one=True)
    assert (usage["input_tokens"], usage["output_tokens"]) == (2400, 800)


# --- Gear from riders --------------------------------------------------------------------------------

def test_rider_gear_is_matched_to_inventory_and_checked_on_the_event(client, claude, app, make):
    sm58 = make("inventory_items", name="Shure SM58", category="Microphones", quantity=10, rental_rate=8)
    svt = make("inventory_items", name="Ampeg SVT-CL + SVT-810E", category="Bass Amps", make="Ampeg", quantity=1,
               rental_rate=125)
    make("inventory_items", name="Old snake", category="Cables & Snakes", status="retired")
    other = make("events", title="Other show", event_date="2030-06-01", status="confirmed")
    make("event_gear", event_id=other, item_id=svt, quantity=1)
    show = make("events", title="Velvet Owls", event_date="2030-06-01", status="confirmed")
    make("event_gear", event_id=show, item_id=sm58, quantity=4)
    claude.replies.append(reply(ai_result({"event_date": "2030-06-01"}, match=show, reason="Same band and date") | {
        "gear": [
            {"requested": "Shure SM58", "quantity": 6, "inventory_id": sm58, "match": "same", "quote": "6x SM58"},
            {"requested": "Ampeg SVT-VR + 8x10", "quantity": 1, "inventory_id": svt, "match": "substitute",
             "quote": "Bass: Ampeg SVT-VR or similar"},
            {"requested": "Leslie 122", "quantity": 1, "inventory_id": 0, "match": "none", "quote": "Leslie 122"},
            {"requested": "Mystery box", "quantity": 0, "inventory_id": 99999, "match": "same", "quote": ""},
        ]}))
    page = _import(client, files=[("Velvet Owls rider.pdf", PDF)]).data.decode()
    sent = claude.text_sent()
    assert f"{sm58} | Shure SM58 | Microphones | - | 10" in sent and "Old snake" not in sent
    assert "Gear from the documents" in page and "substitute" in page and "not in inventory" in page
    assert '<span class="error">0</span>' in page  # the only SVT is out on the other show
    gear = json.loads(query(app, "SELECT ai_details FROM client_requests", one=True)["ai_details"])["gear"]
    assert gear[3] == {"requested": "Mystery box", "quantity": 1, "item_id": None, "match": "none", "quote": ""}

    resp = client.post("/requests/1/add-to-event", data={"event_id": show})
    assert resp.headers["Location"].endswith(f"/events/{show}?tab=gear")
    page = client.get(f"/events/{show}").data.decode()
    assert "4 gear items read from documents are waiting to be checked." in page
    page = client.get(f"/events/{show}?tab=gear").data.decode()
    assert "Gear from the documents" in page and "Already on the gear list: 4" in page
    rows = query(app, "SELECT * FROM gear_suggestions ORDER BY id")
    assert [(r["item_id"], r["match"], r["status"]) for r in rows] == [
        (sm58, "same", "pending"), (svt, "substitute", "pending"), (None, "none", "pending"),
        (None, "none", "pending")]
    assert f'<option value="{svt}" selected>' in page and '<option value="sub" selected>' in page

    ids = [r["id"] for r in rows]
    resp = client.post(f"/events/{show}/gear/suggestions", data={
        "action": "add", f"item_{ids[0]}": str(sm58), f"qty_{ids[0]}": "6", f"item_{ids[1]}": str(svt),
        f"qty_{ids[1]}": "1", f"item_{ids[2]}": "sub", f"qty_{ids[2]}": "1", f"item_{ids[3]}": ""},
        follow_redirects=True)
    assert ("Gear list updated: added 1 item, raised the quantity on 1, added 1 sub-rental line, left out 1."
            in resp.data.decode())
    lines = query(app, "SELECT item_id, description, quantity, rate, notes FROM event_gear WHERE event_id = ? "
                       "ORDER BY id", (show,))
    assert lines == [
        {"item_id": sm58, "description": None, "quantity": 6, "rate": None, "notes": None},
        {"item_id": svt, "description": None, "quantity": 1, "rate": 125, "notes": "Asked for: Ampeg SVT-VR + 8x10"},
        {"item_id": None, "description": "Leslie 122", "quantity": 1, "rate": None, "notes": "From the documents"},
    ]
    assert [r["status"] for r in query(app, "SELECT status FROM gear_suggestions ORDER BY id")] == [
        "added", "added", "added", "dismissed"]
    page = client.get(f"/events/{show}?tab=gear").data.decode()
    assert "Gear from the documents" not in page and "waiting to be checked" not in page


def test_gear_suggestions_can_be_dismissed_and_follow_a_new_inquiry(client, claude, app, make):
    mic = make("inventory_items", name="Shure SM57", category="Microphones", quantity=16)
    claude.replies.append(reply(ai_result({"name": "Jess", "event_date": "2030-07-01"}) | {"gear": [
        {"requested": "SM57", "quantity": 8, "inventory_id": mic, "match": "same", "quote": "8 x SM57"}]}))
    _import(client, pasted="Rider: 8 x SM57")
    page = client.get("/requests/1").data.decode()
    assert "on Mon, Jul 1, 2030" in page and ">16<" in page  # free on the date they gave
    resp = client.post("/requests/1/convert", data={"title": "Jess show", "event_date": "2030-07-01", "client": "new",
                                                    "venue": ""})
    event_id = query(app, "SELECT id FROM events", one=True)["id"]
    assert resp.headers["Location"].endswith(f"/events/{event_id}?tab=gear")
    client.post(f"/events/{event_id}/gear/suggestions", data={"action": "dismiss"})
    assert query(app, "SELECT status FROM gear_suggestions", one=True)["status"] == "dismissed"
    assert not query(app, "SELECT * FROM event_gear")
