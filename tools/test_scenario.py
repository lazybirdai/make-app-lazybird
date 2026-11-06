"""Create or update the Lazybird test scenarios on Make and run them.

Every module maps outputs of the ones before it, and filters check the rest, so a run where all
operations finish means every module returned what it should. The main scenario creates and deletes two
cloned voices.

Usage: python3 -I tools/test_scenario.py main|error [run]
Env: MAKE_API_TOKEN, MAKE_API_BASE, MAKE_TEAM_ID, MAKE_CONNECTION_ID (a Lazybird connection on Make),
     MAKE_SCENARIO_ID / MAKE_ERROR_SCENARIO_ID (optional; without one a new scenario is created and
     its ID printed).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

APP = "app#lazybird-7fp8is"
CONN = int(os.environ["MAKE_CONNECTION_ID"])
TEAM = int(os.environ["MAKE_TEAM_ID"])


def call(method, path, body=None):
    req = urllib.request.Request(os.environ["MAKE_API_BASE"] + path,
                                 json.dumps(body).encode() if body is not None else None, method=method)
    req.add_header("Authorization", "Token " + os.environ["MAKE_API_TOKEN"])
    req.add_header("User-Agent", "make-app-lazybird-test/1.0")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=400) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:1500]


def mod(i, name, mapper, checks=(), x=0, y=0):
    """A Lazybird module; `checks` become a filter in front of it, so a missing output stops the run."""
    m = {"id": i, "module": f"{APP}:{name}", "version": 1, "parameters": {"__IMTCONN__": CONN},
         "mapper": mapper, "metadata": {"designer": {"x": x, "y": y}}}
    if checks:
        m["filter"] = {"name": f"check before {name}", "conditions": [[
            {"a": a, "o": o, **({"b": b} if b is not None else {})} for a, o, b in checks]]}
    return m


def chain(start, steps, y=0):
    return [mod(start + n, *step, x=300 * (start + n - 1), y=y) for n, step in enumerate(steps)]


ELYSSIA = "tgJ2Hes6DauwTg8kFrRPLN"
SPEECH = ("Every great story starts with a single line. This one was made in Make, carried from a spreadsheet row "
          "to a finished voiceover without anyone pressing record, and it sounds just as calm and clear as a studio take.")
# Route 1 works on one voice: each step maps the outputs before it and the filters check the rest.
route1 = chain(3, [
    ("getVoice", {"voiceId": ELYSSIA}, [("{{1.plan.tier}}", "exist", None),
                                        ("{{1.credits.remaining}}", "number:greaterorequal", "0")]),
    ("makeApiCall", {"url": "/v2/voices/{{3.id}}", "method": "GET"}, [("{{3.displayName}}", "exist", None)]),
    ("generateSpeech", {"voiceId": "{{4.body.voice.id}}", "inputType": "text", "text": SPEECH,
                        "fileName": "make-test.mp3", "speed": 1}, [("{{4.statusCode}}", "number:equal", "200")]),
    ("designVoice", {"description": "Calm middle-aged male narrator, warm and clear",
                     "text": "The river had carried stories down from the mountains for a thousand years, and tonight it carried one more."},
     [("{{5.fileName}}", "text:equal", "make-test.mp3"), ("{{length(5.data)}}", "number:greater", "10000")]),
    ("cloneVoice", {"name": "Make test file clone", "sampleSource": "file", "fileName": "{{5.fileName}}",
                    "data": "{{5.data}}", "rightsConfirmed": True}),
    ("deleteVoice", {"voiceId": "{{7.id}}"}),
    ("cloneVoice", {"name": "Make test URL clone", "sampleSource": "url", "sampleUrl": "{{6.sampleUrl}}",
                    "rightsConfirmed": True}),
    ("deleteVoice", {"voiceId": "{{9.id}}"}),
    ("makeApiCall", {"url": "/v2/me", "method": "GET"},
     [("{{8.voiceId}}", "text:equal", "{{7.id}}"), ("{{10.voiceId}}", "text:equal", "{{9.id}}")]),
])
# Route 2 ends with a search that needs two pages, so the log shows the cursor pagination.
route2 = chain(12, [("searchVoices", {"section": "library", "limit": 120})], y=300)
SCENARIOS = {
    "main": ("Lazybird app test", "MAKE_SCENARIO_ID", [
        mod(1, "getAccount", {}),
        {"id": 2, "module": "builtin:BasicRouter", "version": 1, "mapper": None,
         "metadata": {"designer": {"x": 300, "y": 0}}, "routes": [{"flow": route1}, {"flow": route2}]},
    ], 1 + len(route1) + len(route2)),
    # A voice ID that doesn't exist, to show the error message users get.
    "error": ("Lazybird app test: error", "MAKE_ERROR_SCENARIO_ID", [mod(1, "getVoice", {"voiceId": "not-a-voice"})], 1),
}
which = sys.argv[1] if len(sys.argv) > 1 else "main"
name, sid_env, flow, modules = SCENARIOS[which]
blueprint = {"name": name, "flow": flow, "metadata": {
    "version": 1, "scenario": {"roundtrips": 1, "maxErrors": 3, "autoCommit": True, "autoCommitTriggerLast": True,
                               "sequential": False, "confidential": False, "dataloss": False, "dlq": False,
                               "freshVariables": False}, "designer": {"orphans": []}}}

sid = os.environ.get(sid_env)
if sid:
    s, r = call("PATCH", f"/scenarios/{sid}?confirmed=true", {"blueprint": json.dumps(blueprint)})
else:
    s, r = call("POST", "/scenarios?confirmed=true", {"blueprint": json.dumps(blueprint), "teamId": TEAM,
                                                     "scheduling": json.dumps({"type": "on-demand"})})
    if s == 200:
        sid = r["scenario"]["id"]
print("scenario", s, json.dumps(r)[:400] if s != 200 else sid)
if s == 200 and sys.argv[2:] == ["run"]:
    call("POST", f"/scenarios/{sid}/start")  # on-demand scenarios still have to be active to run
    s, r = call("POST", f"/scenarios/{sid}/run", {"responsive": True})
    print("run", s, json.dumps(r)[:600])
    if s in (200, 202):
        while True:
            s, log = call("GET", f"/scenarios/{sid}/logs/{r['executionId']}")
            log = log.get("scenarioLog", {}) if isinstance(log, dict) else {}
            if log.get("eventType") == "EXECUTION_END":
                break
            time.sleep(10)
        print("operations", log.get("operations"), "of", modules, log.get("displayStatus"), log.get("error") or "")
