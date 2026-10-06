"""A small web control panel: on/off, trigger level, vibe steering, manual buttons, mute,
the live log and what it has cost so far. Protected by a random token in state/panel-token.
"""

from __future__ import annotations

import html
import json
import secrets
from pathlib import Path

from aiohttp import web

from .sidekick import TRIGGER, Sidekick

PAGE = """<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Jev Soundboard</title>
<style>
:root{--bg:#f6f6f4;--fg:#1d1d1b;--card:#fff;--muted:#6b6b66;--btn:#e8e8e4;--on:#1f8a5b;--warn:#c0392b}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--card:#1c1c1c;--muted:#9a9a94;--btn:#2c2c2c}}
body{font:16px system-ui,sans-serif;margin:0 auto;max-width:720px;padding:16px;background:var(--bg);color:var(--fg)}
h1{font-size:22px;margin:0 0 4px} .muted{color:var(--muted);font-size:14px}
section{background:var(--card);border-radius:12px;padding:12px;margin:12px 0}
button{font:inherit;margin:3px;padding:9px 12px;border-radius:10px;border:0;background:var(--btn);color:var(--fg);cursor:pointer}
button.active{background:var(--on);color:#fff} button.off{background:var(--warn);color:#fff}
input{font:inherit;width:100%;box-sizing:border-box;padding:9px;border-radius:8px;border:1px solid var(--btn);background:var(--bg);color:var(--fg)}
pre{white-space:pre-wrap;font-size:13px;max-height:45vh;overflow:auto;margin:0}
</style>
<h1>🥁 Jev Soundboard</h1>
<div class=muted id=status>connecting…</div>
<section>
  <button id=toggle></button> <button id=mute></button>
  <div id=levels></div>
</section>
<section>
  <form id=vibe><input name=vibe placeholder="Steer the vibe, e.g. only hype people up, no roasting"></form>
  <div class=muted>Vibe: <span id=vibetext></span></div>
</section>
<section><div class=muted>Fire manually</div><div id=clips></div></section>
<section><pre id=log></pre></section>
<script>
const t = new URLSearchParams(location.search).get("t");
const post = (path, data) => fetch(`api/${path}?t=${t}`, {method: "POST", body: data ? new URLSearchParams(data) : undefined}).then(refresh);
function el(tag, text, cls, onclick) { const e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; if (onclick) e.onclick = onclick; return e; }
let built = false;
async function refresh() {
  const s = await (await fetch(`api/state?t=${t}`)).json();
  document.getElementById("status").textContent =
    `${s.enabled ? s.trigger.replace("_", "-") : "OFF"} · ${s.transport} · ${s.listening ? "listening" : "not listening"} · ${s.decisions} decisions · $${s.cost.toFixed(3)} so far (Jev $${s.jev_cost.toFixed(3)} + speech-to-text $${s.transcribe_cost.toFixed(3)})`;
  const toggle = document.getElementById("toggle");
  toggle.textContent = s.enabled ? "On" : "Off"; toggle.className = s.enabled ? "active" : "off";
  toggle.onclick = () => post("toggle");
  const mute = document.getElementById("mute");
  mute.textContent = s.muted ? "Unmute" : "Mute"; mute.className = s.muted ? "off" : "";
  mute.onclick = () => post("mute");
  const levels = document.getElementById("levels"); levels.replaceChildren();
  for (const level of s.levels) levels.append(el("button", level.replace("_", "-"), level === s.trigger ? "active" : "", () => post("trigger", {level})));
  document.getElementById("vibetext").textContent = s.vibe;
  if (!built) {
    const clips = document.getElementById("clips");
    for (const name of s.clips) clips.append(el("button", name, "", () => post("fire", {name})));
    built = true;
  }
  document.getElementById("log").textContent = s.log.slice().reverse().join("\\n");
}
document.getElementById("vibe").onsubmit = (e) => { e.preventDefault(); const v = e.target.vibe.value.trim(); if (v) post("vibe", {vibe: v}); e.target.reset(); };
refresh(); setInterval(refresh, 1500);
</script></html>"""


def panel_token(state_dir: Path) -> str:
    state_dir.mkdir(parents=True, exist_ok=True)
    token_file = state_dir / "panel-token"
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(12))
        token_file.chmod(0o600)
    return token_file.read_text().strip()


def make_app(sidekick: Sidekick, token: str, transport=None, transcriber=None) -> web.Application:
    @web.middleware
    async def auth(request, handler):
        if not secrets.compare_digest(request.query.get("t", ""), token):
            raise web.HTTPForbidden(text="Missing or wrong token: use the URL jevboard printed at startup.")
        return await handler(request)

    async def index(_):
        return web.Response(content_type="text/html", text=PAGE)

    async def state(_):
        return web.json_response({
            "enabled": sidekick.enabled,
            "trigger": sidekick.trigger,
            "levels": list(TRIGGER),
            "vibe": sidekick.vibe,
            "muted": bool(transport and transport.muted),
            "listening": bool(transcriber and transcriber.connected),
            "transport": getattr(transport, "name", ""),
            "decisions": sidekick.cost.decisions,
            "cost": sidekick.cost.usd(sidekick.config),
            "jev_cost": sidekick.cost.jev_usd(sidekick.config),
            "transcribe_cost": sidekick.cost.transcribe_usd(sidekick.config),
            "clips": sidekick.board.names(),
            "log": list(sidekick.events)[-80:],
        }, dumps=lambda value: json.dumps(value, ensure_ascii=False))

    async def toggle(_):
        sidekick.enabled = not sidekick.enabled
        sidekick.log("🎛️ turned " + ("on" if sidekick.enabled else "off"))
        return web.json_response({"ok": True})

    async def mute(_):
        if transport is not None:
            transport.muted = not transport.muted
        return web.json_response({"ok": True})

    async def trigger(request):
        level = (await request.post()).get("level", "")
        if level not in TRIGGER:
            raise web.HTTPBadRequest(text="unknown level")
        sidekick.trigger = level
        sidekick.log(f"🎛️ trigger: {level}")
        return web.json_response({"ok": True})

    async def vibe(request):
        text = str((await request.post()).get("vibe", "")).strip()[:300]
        if text:
            sidekick.vibe = text
            sidekick.log(f"🎛️ vibe: {html.escape(text)}")
        return web.json_response({"ok": True})

    async def fire(request):
        name = (await request.post()).get("name", "")
        if not sidekick.fire(str(name), manual=True):
            raise web.HTTPNotFound(text="no such clip")
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[auth])
    app.add_routes([
        web.get("/", index), web.get("/api/state", state),
        web.post("/api/toggle", toggle), web.post("/api/mute", mute), web.post("/api/trigger", trigger),
        web.post("/api/vibe", vibe), web.post("/api/fire", fire),
    ])
    return app
