"""Upload the local Make app source (makecomapp.json layout) to a Make custom app via the SDK API.

Usage: python3 -I tools/upload.py . APP_NAME [only=part,...]
Env: MAKE_API_TOKEN, MAKE_API_BASE. Writes the remote ids into makecomapp.json `origins`.
"""
import json
import os
import sys
import urllib.error
import urllib.request

REPO, APP = sys.argv[1], sys.argv[2]
ONLY = set(sys.argv[3].split("=", 1)[1].split(",")) if len(sys.argv) > 3 else None
BASE = os.environ["MAKE_API_BASE"]
TOKEN = os.environ["MAKE_API_TOKEN"]
VER = 1
TYPE_IDS = {"trigger": 1, "action": 4, "search": 9, "instant_trigger": 10, "responder": 11, "universal": 12}
MODULE_SECTIONS = {"communication": "api", "staticParams": "parameters", "mappableParams": "expect",
                   "interface": "interface", "samples": "samples", "scope": "scope"}


def call(method, path, body=None, ctype="application/json"):
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", f"Token {TOKEN}")
    req.add_header("User-Agent", "make-app-lazybird-upload/1.0")
    if data is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:600]


def read(rel):
    with open(os.path.join(REPO, rel), "rb") as f:
        return f.read()


def put_text(method, path, rel, ctype="application/jsonc"):
    status, resp = call(method, path, read(rel), ctype)
    print(f"{status} {method} {path}" + ("" if status < 300 else f"  {resp}"))
    return status


def want(part):
    return ONLY is None or part in ONLY


manifest = json.loads(read("makecomapp.json"))
comp = manifest["components"]
gen = manifest["generalCodeFiles"]
ids = {"connection": {}, "module": {}, "rpc": {}}

status, resp = call("GET", f"/sdk/apps/{APP}/connections")
existing_conns = {c["label"]: c["name"] for c in resp.get("appConnections", [])} if status == 200 else {}

if want("base"):
    put_text("PUT", f"/sdk/apps/{APP}/{VER}/base", gen["base"])
    put_text("PUT", f"/sdk/apps/{APP}/{VER}/common", gen["common"], "application/json")

for local, c in comp["connection"].items():
    remote = existing_conns.get(c["label"])
    if not remote:
        status, resp = call("POST", f"/sdk/apps/{APP}/connections", {"type": c["connectionType"], "label": c["label"]})
        print(status, "create connection", resp)
        remote = resp["appConnection"]["name"]
    ids["connection"][local] = remote
    if want("connection"):
        put_text("PUT", f"/sdk/apps/connections/{remote}/api", c["codeFiles"]["communication"])
        put_text("PUT", f"/sdk/apps/connections/{remote}/parameters", c["codeFiles"]["params"])
        put_text("PUT", f"/sdk/apps/connections/{remote}/common", c["codeFiles"]["common"], "application/json")

status, resp = call("GET", f"/sdk/apps/{APP}/{VER}/rpcs")
existing_rpcs = {r["name"] for r in resp.get("appRpcs", [])} if status == 200 else set()
for name, r in comp["rpc"].items():
    ids["rpc"][name] = name
    if not want("rpc") and not (ONLY and name in ONLY):
        continue
    if name not in existing_rpcs:
        status, resp = call("POST", f"/sdk/apps/{APP}/{VER}/rpcs",
                            {"name": name, "label": r["label"], "connection": ids["connection"][r["connection"]]})
        print(status, "create rpc", name, "" if status < 300 else resp)
    put_text("PUT", f"/sdk/apps/{APP}/{VER}/rpcs/{name}/api", r["codeFiles"]["communication"])
    put_text("PUT", f"/sdk/apps/{APP}/{VER}/rpcs/{name}/parameters", r["codeFiles"]["params"])

status, resp = call("GET", f"/sdk/apps/{APP}/{VER}/modules")
existing_mods = {m["name"] for m in resp.get("appModules", [])} if status == 200 else set()
for name, m in comp["module"].items():
    ids["module"][name] = name
    if not want("module") and not (ONLY and name in ONLY):
        continue
    if name not in existing_mods:
        body = {"name": name, "typeId": TYPE_IDS[m["moduleType"]], "label": m["label"],
                "description": m["description"], "moduleInitMode": "blank",
                "connection": ids["connection"].get(m["connection"])}
        if m.get("actionCrud"):
            body["crud"] = m["actionCrud"]
        status, resp = call("POST", f"/sdk/apps/{APP}/{VER}/modules", body)
        print(status, "create module", name, "" if status < 300 else resp)
    else:
        status, resp = call("PATCH", f"/sdk/apps/{APP}/{VER}/modules/{name}",
                            {"label": m["label"], "description": m["description"]})
        print(status, "patch module", name, "" if status < 300 else resp)
    for key, section in MODULE_SECTIONS.items():
        if key in m["codeFiles"]:
            put_text("PUT", f"/sdk/apps/{APP}/{VER}/modules/{name}/{section}", m["codeFiles"][key])

if want("groups"):
    put_text("PUT", f"/sdk/apps/{APP}/{VER}/groups", gen["groups"])
if want("readme") and os.path.exists(os.path.join(REPO, gen["readme"])):
    put_text("PUT", f"/sdk/apps/{APP}/{VER}/readme", gen["readme"], "text/markdown")
if want("icon") and os.path.exists(os.path.join(REPO, "assets/icon.png")):
    put_text("PUT", f"/sdk/apps/{APP}/{VER}/icon", "assets/icon.png", "image/png")

origin = {"label": "Make US2", "baseUrl": BASE.removesuffix("/api/v2"), "appId": APP, "appVersion": VER,
          "apikeyFile": ".secrets/apikey", "idMapping": {
              kind: [{"local": k, "remote": v} for k, v in ids[kind].items()] for kind in ids}}
manifest["origins"] = [origin]
with open(os.path.join(REPO, "makecomapp.json"), "w") as f:
    json.dump(manifest, f, indent="\t")
    f.write("\n")
print("origins written")
