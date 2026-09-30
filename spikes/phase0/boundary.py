"""Fixture-only servers and explicit deny-by-default proxy for the feasibility spike."""

from __future__ import annotations

import http.client
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class LocalServer:
    def __init__(self, handler):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self):
        return self.server.server_address[1]

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def sentinel_handler(requests):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({"method": "GET", "path": self.path})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Sentinel: this request should never arrive")

        def do_POST(self):
            requests.append({"method": "POST", "path": self.path})
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


def fixture_handler(sentinel_origin):
    # No third-party dependencies, real accounts, or external endpoints exist in this fixture.
    page = """<!doctype html><html lang="en"><head><meta charset="utf-8">
    <title>FrictionLab local storefront</title><style>
    body{font:18px system-ui;margin:48px;max-width:720px;background:#f5f7fb;color:#17233b}
    button{padding:14px 22px;margin:12px 12px 12px 0;border:0;border-radius:9px;
    background:#2455c4;color:white;font:inherit} section{background:white;padding:28px}
    </style></head><body><main><h1>Backpack checkout</h1><section id="panel">
    <p>Trail backpack: $65. Delivery in 3 days. Total including shipping: $70.</p>
    <button onclick="startCheckout()">Start checkout</button>
    <button onclick="showPolicy()">Read delivery policy</button>
    <p id="status" role="status">Choose the next step.</p></section></main><script>
    function startCheckout(){document.querySelector('#panel').innerHTML=
    '<h2>Order review</h2><p>Backpack $65 + shipping $5 = $70.</p>'+
    '<p role="status">Checkout started. No order has been placed.</p>';}
    function showPolicy(){document.querySelector('#status').textContent='Delivery takes 3 days.';}
    window.runProtectionProbes = async function(){
      const forbidden = 'SENTINEL';
      const image = new Image(); image.src = forbidden + '/image';
      const frame = document.createElement('iframe'); frame.src = forbidden + '/frame';
      frame.hidden = true; document.body.appendChild(frame);
      fetch(forbidden + '/api', {method:'POST',body:'synthetic'}).catch(()=>{});
      navigator.sendBeacon(forbidden + '/beacon', 'synthetic');
      const socket = new WebSocket(forbidden.replace('http:', 'ws:') + '/socket');
      socket.onerror = ()=>{};
      try {await navigator.serviceWorker.register('/sw.js');} catch(e) {}
      await new Promise(r=>setTimeout(r,500));
      image.src=''; frame.remove(); socket.close();
      return (await navigator.serviceWorker.getRegistrations()).length;
    };
    </script></body></html>""".replace("SENTINEL", sentinel_origin)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body, content_type = page.encode(), "text/html; charset=utf-8"
            elif self.path == "/sw.js":
                body, content_type = b"self.addEventListener('fetch',()=>{});", "text/javascript"
            elif self.path == "/favicon.ico":
                body, content_type = b"", "image/x-icon"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def proxy_handler(fixture_origin, events):
    allowed = urlsplit(fixture_origin)

    class Handler(BaseHTTPRequestHandler):
        def reject(self, reason):
            events.append({"method": self.command, "url": self.path, "decision": "blocked", "reason": reason})
            self.send_error(403, "Replica-only policy")

        def do_CONNECT(self):
            self.reject("HTTPS tunnels are not permitted in the local HTTP spike")

        def do_GET(self):
            target = urlsplit(self.path)
            if (
                target.scheme != "http"
                or target.hostname != "127.0.0.1"
                or target.port != allowed.port
                or target.username is not None
                or target.password is not None
                or target.path not in {"/", "/sw.js", "/favicon.ico"}
                or target.query
            ):
                self.reject("Origin/path is not the declared local replica")
                return
            events.append({"method": "GET", "url": self.path, "decision": "allowed"})
            # Never connect to the caller-selected hostname: the upstream is fixed.
            upstream = http.client.HTTPConnection("127.0.0.1", allowed.port, timeout=10)
            try:
                upstream.request("GET", target.path)
                response = upstream.getresponse()
                body = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "text/plain"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                upstream.close()

        def do_POST(self):
            self.reject("Mutating methods are not permitted in Phase 0")

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST
        do_OPTIONS = do_POST
        do_HEAD = do_POST

        def log_message(self, *args):
            pass

    return Handler
