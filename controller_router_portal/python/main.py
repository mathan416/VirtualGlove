"""Port-80 App Lab entry page for the active UNO Q controller."""
from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


HTML = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Choose a controller</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#081625;color:#e9f7ff}*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(circle at 70% 10%,#18445a,#081625 60%)}
main{max-width:850px;margin:auto;padding:clamp(24px,6vw,70px)}header{display:flex;gap:14px;align-items:center;border-bottom:1px solid #477388;padding-bottom:22px}
.icon{font-size:33px;display:grid;place-items:center;width:60px;height:60px;border:2px solid #5ce2ee;border-radius:18px}h1{font-size:clamp(32px,6vw,56px);margin:28px 0 8px;line-height:1}p{color:#b1ccda;line-height:1.5}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:18px;margin-top:28px}.card{background:#102b3b;border:1px solid #3d667b;border-radius:17px;padding:25px;min-height:205px}
.card h2{font-size:27px;margin:4px 0}.card p{min-height:45px}.badge{display:inline-block;font-size:12px;letter-spacing:.13em;text-transform:uppercase;color:#75e6ed}button{font:700 16px system-ui;width:100%;padding:13px;border:0;border-radius:8px;background:#f7795f;color:#12222b;cursor:pointer}button:disabled{opacity:.5;cursor:wait}
#message{min-height:32px;margin-top:24px;color:#87e9ed}.error{color:#ffaca1!important}a{color:#87e9ed}
</style><main><header><span class="icon">🎮</span><div><strong>CONTROLLER ROUTER</strong><div style="color:#9bc1d1">UNO Q controller selection</div></div></header>
<h1>Choose your controller.</h1><p>Pick the companion you want to use on this UNO Q. An active game must finish before you can switch.</p>
<div class="cards" id="cards"></div><p id="message" role="status" aria-live="polite"></p></main>
<script>
const names={virtualglove:['VirtualGlove','Play with hand gestures.','✋'],rob_vision:['R.O.B. Vision','Play alongside Buddy.','🤖']};
const cards=document.getElementById('cards'),message=document.getElementById('message');let requested=false,selected=null,singleAutoAttempted=false;
async function request(path,body){const options=body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{};const response=await fetch(path,options);return response.json()}
function destination(port){location.assign(location.protocol+'//'+location.hostname+':'+port+'/')}
async function select(key){requested=true;selected=key;try{const value=await request('/api/select',{app:key});if(value.error){requested=false;selected=null;message.className='error';message.textContent=value.error}else{message.className='';message.textContent='Starting '+names[key][0]+'…'}}catch(error){requested=false;selected=null;message.className='error';message.textContent='The launcher is unavailable. Please retry.'}}
async function tick(){try{const state=await request('/api/state');if(state.error)throw Error(state.error);const installed=Object.keys(names).filter(k=>state.apps[k]?.installed);
 if(!installed.length){cards.innerHTML='';message.textContent='No controller app is installed yet.';return}
 if(installed.length===1&&!requested&&!state.error){const key=installed[0];if(state.apps[key].selected&&state.apps[key].ready){destination(state.apps[key].port);return}if(!singleAutoAttempted&&!state.busy&&state.apps[key].ready){singleAutoAttempted=true;select(key);return}}
 if(selected&&state.apps[selected]?.ready&&!state.busy&&(state.selected===undefined||state.selected===selected)){destination(state.apps[selected].port);return}
 cards.innerHTML=installed.map(k=>{const a=state.apps[k],n=names[k];return `<section class="card"><span class="badge">${a.selected?'SELECTED':a.ready?'READY':a.running?'STARTING':'AVAILABLE'}</span><h2>${n[2]} ${n[0]}</h2><p>${n[1]}</p><button data-app="${k}" ${state.busy||a.game_active?'disabled':''}>${a.selected?'Open '+n[0]:'Use '+n[0]}</button></section>`}).join('');
 cards.querySelectorAll('button').forEach(b=>b.onclick=()=>select(b.dataset.app));
 if(state.error){message.className='error';message.textContent=state.error;requested=false}else if(state.busy){message.className='';message.textContent='Starting '+names[state.target]?.[0]+'…'}else if(!requested){message.textContent=''}
 }catch(error){message.className='error';message.textContent=error.message||'The launcher is unavailable. Please retry.'}setTimeout(tick,1200)}tick();
</script></html>"""


def broker(message: dict) -> dict:
    connection = HTTPConnection("portal-host-bridge", 8122, timeout=10)
    try:
        connection.request("POST", "/request", json.dumps(message), {"Content-Type": "application/json"})
        response = connection.getresponse()
        return json.load(response)
    finally:
        connection.close()


class Handler(BaseHTTPRequestHandler):
    def app_origin(self):
        origin = self.headers.get("Origin", "")
        try:
            source = urlsplit(origin)
            host = self.headers.get("Host", "").split(":", 1)[0].lower()
            return (source.scheme == "http" and source.hostname == host and
                    source.port in (8100, 8101))
        except ValueError:
            return False

    def do_OPTIONS(self):
        if urlsplit(self.path).path != "/api/select" or not self.app_origin():
            self.send_error(403)
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
        self.send_header("Access-Control-Allow-Methods", "POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def send_json(self, code: int, value: dict) -> None:
        body = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        if self.app_origin():
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/state":
            try:
                self.send_json(200, broker({"action": "state"}))
            except (OSError, ValueError):
                self.send_json(503, {"error": "The UNO Q launcher is unavailable."})
        elif path == "/":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/select":
            self.send_error(404)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self.send_json(415, {"error": "JSON required."})
            return
        if self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "same-site", "none"):
            self.send_json(403, {"error": "Cross-site requests are blocked."})
            return
        origin = self.headers.get("Origin")
        if origin and not self.app_origin() and (urlsplit(origin).scheme != "http" or
                       urlsplit(origin).netloc.lower() != self.headers.get("Host", "").lower()):
            self.send_json(403, {"error": "Cross-site requests are blocked."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 128:
                raise ValueError("Invalid request size.")
            app = json.loads(self.rfile.read(size)).get("app")
            self.send_json(202, broker({"action": "select", "app": app}))
        except (OSError, ValueError, AttributeError, TypeError):
            self.send_json(400, {"error": "Invalid controller choice."})

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
