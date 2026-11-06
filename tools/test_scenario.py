"""Create or update the Lazybird test scenario on Make and run it.

Every module maps outputs of the ones before it, and filters check the rest, so a run where all
operations finish means every module returned what it should. The scenario creates and deletes two
cloned voices.

Usage: python3 -I tools/test_scenario.py [run]
Env: MAKE_API_TOKEN, MAKE_API_BASE, MAKE_TEAM_ID, MAKE_CONNECTION_ID (a Lazybird connection on Make),
     MAKE_SCENARIO_ID (optional; without it a new scenario is created and its ID printed).
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


def mod(i, name, mapper, checks=()):
    """A Lazybird module; `checks` become a filter in front of it, so a missing output stops the run."""
    m = {"id": i, "module": f"{APP}:{name}", "version": 1, "parameters": {"__IMTCONN__": CONN},
         "mapper": mapper, "metadata": {"designer": {"x": 300 * (i - 1), "y": 0}}}
    if checks:
        m["filter"] = {"name": f"check before {name}", "conditions": [[
            {"a": a, "o": o, **({"b": b} if b is not None else {})} for a, o, b in checks]]}
    return m


# Each step maps the previous outputs, and the filters check the rest. All 9 operations = every output worked.
flow = [
    mod(1, "getAccount", {}),
    mod(2, "searchVoices", {"section": "library", "q": "narrator", "limit": 1},
        [("{{1.plan.tier}}", "exist", None), ("{{1.credits.remaining}}", "number:greaterorequal", "0")]),
    mod(3, "getVoice", {"voiceId": "{{2.id}}"}),
    mod(4, "makeApiCall", {"url": "/v2/voices/{{3.id}}", "method": "GET"},
        [("{{3.displayName}}", "exist", None)]),
    mod(5, "generateSpeech", {"voiceId": "{{4.body.voice.id}}", "inputType": "text",
                              "text": "Every great story starts with a single line. This one was made in Make, "
                                      "carried from a spreadsheet row to a finished voiceover without anyone "
                                      "pressing record, and it sounds just as calm and clear as a studio take.",
                              "fileName": "make-test.mp3", "speed": 1},
        [("{{4.statusCode}}", "number:equal", "200")]),
    mod(6, "designVoice", {"description": "Calm middle-aged male narrator, warm and clear",
                           "text": "The river had carried stories down from the mountains for a thousand years, and tonight it carried one more."},
        [("{{5.fileName}}", "text:equal", "make-test.mp3"), ("{{length(5.data)}}", "number:greater", "10000")]),
    mod(7, "cloneVoice", {"name": "Make test file clone", "sampleSource": "file", "fileName": "{{5.fileName}}",
                          "data": "{{5.data}}", "rightsConfirmed": True}),
    mod(8, "deleteVoice", {"voiceId": "{{7.id}}"}),
    mod(9, "cloneVoice", {"name": "Make test URL clone", "sampleSource": "url", "sampleUrl": "{{6.sampleUrl}}",
                          "rightsConfirmed": True}),
    mod(10, "deleteVoice", {"voiceId": "{{9.id}}"}),
    mod(11, "makeApiCall", {"url": "/v2/me", "method": "GET"},
        [("{{8.voiceId}}", "text:equal", "{{7.id}}"), ("{{10.voiceId}}", "text:equal", "{{9.id}}")]),
]
blueprint = {"name": "Lazybird app test", "flow": flow, "metadata": {
    "version": 1, "scenario": {"roundtrips": 1, "maxErrors": 3, "autoCommit": True, "autoCommitTriggerLast": True,
                               "sequential": False, "confidential": False, "dataloss": False, "dlq": False,
                               "freshVariables": False}, "designer": {"orphans": []}}}

sid = os.environ.get("MAKE_SCENARIO_ID")
if sid:
    s, r = call("PATCH", f"/scenarios/{sid}?confirmed=true", {"blueprint": json.dumps(blueprint)})
else:
    s, r = call("POST", "/scenarios?confirmed=true", {"blueprint": json.dumps(blueprint), "teamId": TEAM,
                                                     "scheduling": json.dumps({"type": "on-demand"})})
    if s == 200:
        sid = r["scenario"]["id"]
print("scenario", s, json.dumps(r)[:400] if s != 200 else sid)
if s == 200 and sys.argv[1:] == ["run"]:
    s, r = call("POST", f"/scenarios/{sid}/run", {"responsive": True})
    print("run", s, json.dumps(r)[:600])
    if s in (200, 202):
        while True:
            s, log = call("GET", f"/scenarios/{sid}/logs/{r['executionId']}")
            log = log.get("scenarioLog", {}) if isinstance(log, dict) else {}
            if log.get("eventType") == "EXECUTION_END":
                break
            time.sleep(10)
        print("operations", log.get("operations"), "of", len(flow), log.get("displayStatus"), log.get("error") or "")
