#!/usr/bin/env python
"""Renderizador quadro a quadro: Chrome sem janela + Chrome DevTools Protocol, só biblioteca padrão.

Cada peça gera uma composição HTML com uma timeline GSAP pausada e a registra em
`window.__timelines[<id>]`. O `#root` traz `data-composition-id`, `data-duration` e `data-fps`.
O renderizador abre a página, posiciona a timeline no instante exato de cada quadro (seek, nunca
relógio real) e captura a tela. Mesmo HTML + mesmo instante = mesmo quadro, sempre.

API usada pelos builders:
    W, H                         tamanho da composição em px (o builder define antes de abrir)
    s = Session(pasta, escala, caminho_do_chrome_ou_None)
    s.cdp.call(metodo, params)   chamada CDP crua (ex.: fundo transparente)
    info = s.open("comp.html")   -> {"id", "dur", "fps"}
    png = s.frame(info["id"], t, "png" | "jpeg")
    s.close()
"""
import base64, json, os, shutil, socket, struct, subprocess, tempfile, time, urllib.parse, urllib.request

W, H = 1080, 1920

CHROME_CANDIDATES = [
    os.environ.get("CHROME_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
]


def find_browser(explicit=None):
    for c in ([explicit] if explicit else []) + CHROME_CANDIDATES:
        if not c:
            continue
        if os.path.isfile(c):
            return c
        w = shutil.which(c)
        if w:
            return w
    raise SystemExit("Chrome/Chromium não encontrado: passe --browser CAMINHO ou defina CHROME_PATH")


class WebSocket:
    """Cliente WebSocket mínimo (RFC 6455): texto, mascarado, com fragmentação e payload longo."""

    def __init__(self, url):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=120)
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (u.path, u.hostname, u.port, key))
        self.sock.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("handshake WebSocket falhou")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.buf = head.split(b"\r\n\r\n", 1)[1]

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise ConnectionError("conexão com o Chrome caiu")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        data = text.encode()
        n = len(data)
        if n < 126:
            hdr = struct.pack("!BB", 0x81, 0x80 | n)
        elif n < 65536:
            hdr = struct.pack("!BBH", 0x81, 0x80 | 126, n)
        else:
            hdr = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(hdr + mask + masked)

    def recv(self):
        parts = []
        while True:
            b0, b1 = self._read(2)
            fin, op, n = b0 & 0x80, b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x8:
                raise ConnectionError("Chrome fechou a conexão")
            if op == 0x9:          # ping -> pong
                continue
            parts.append(data)
            if fin:
                return b"".join(parts).decode()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class CDP:
    def __init__(self, ws_url):
        self.ws = WebSocket(ws_url)
        self.next_id = 0

    def call(self, method, params=None):
        self.next_id += 1
        mid = self.next_id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:          # eventos (sem id) são ignorados
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"]))
                return msg.get("result", {})

    def eval(self, expr, await_promise=False):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": await_promise})
        if "exceptionDetails" in r:
            raise RuntimeError("JS: %s" % r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
        return r.get("result", {}).get("value")


class Session:
    def __init__(self, folder, scale=1, browser=None):
        self.folder = os.path.abspath(folder)
        self.scale = float(scale or 1)
        self.profile = tempfile.mkdtemp(prefix="motion-render-")
        args = [find_browser(browser), "--headless=new", "--remote-debugging-port=0",
                "--user-data-dir=" + self.profile, "--no-first-run", "--no-default-browser-check",
                "--hide-scrollbars", "--mute-audio", "--allow-file-access-from-files",
                "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                "--font-render-hinting=none", "about:blank"]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = os.path.join(self.profile, "DevToolsActivePort")
        t0 = time.time()
        while not (os.path.isfile(port_file) and open(port_file).read().strip()):
            if time.time() - t0 > 30 or self.proc.poll() is not None:
                self.close()
                raise SystemExit("o Chrome não abriu a porta de depuração")
            time.sleep(0.1)
        port = int(open(port_file).read().split()[0])
        pages = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port))
        page = next(p for p in pages if p.get("type") == "page")
        self.cdp = CDP(page["webSocketDebuggerUrl"])
        self.cdp.call("Page.enable")
        self.cdp.call("Runtime.enable")

    def open(self, comp):
        self.cdp.call("Emulation.setDeviceMetricsOverride",
                      {"width": W, "height": H, "deviceScaleFactor": self.scale, "mobile": False})
        url = "file:///" + os.path.join(self.folder, comp).replace("\\", "/").lstrip("/")
        self.cdp.call("Page.navigate", {"url": urllib.parse.quote(url, safe=":/")})
        t0 = time.time()
        while True:
            ok = self.cdp.eval("document.readyState==='complete' && !!window.__timelines "
                               "&& Object.keys(window.__timelines).length>0")
            if ok:
                break
            if time.time() - t0 > 30:
                raise SystemExit("a composição não registrou window.__timelines: " + comp)
            time.sleep(0.05)
        self.cdp.eval("document.fonts.ready.then(()=>true)", await_promise=True)
        info = self.cdp.eval("(()=>{const r=document.querySelector('[data-composition-id]');"
                             "return {id:r.dataset.compositionId,dur:parseFloat(r.dataset.duration),"
                             "fps:parseFloat(r.dataset.fps||'30')}})()")
        if info["id"] not in (self.cdp.eval("Object.keys(window.__timelines)") or []):
            raise SystemExit("timeline '%s' não registrada" % info["id"])
        return info

    def frame(self, comp_id, t, fmt="png"):
        # seek determinístico e espera dois quadros de pintura antes de capturar
        self.cdp.eval("(()=>{const tl=window.__timelines[%s];tl.pause();tl.seek(%f,false);"
                      "return new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))})()"
                      % (json.dumps(comp_id), t), await_promise=True)
        params = {"format": "png" if fmt == "png" else "jpeg", "fromSurface": True,
                  "clip": {"x": 0, "y": 0, "width": W, "height": H, "scale": 1}}
        if fmt != "png":
            params["quality"] = 95
        return base64.b64decode(self.cdp.call("Page.captureScreenshot", params)["data"])

    def close(self):
        try:
            self.cdp.ws.close()
        except Exception:
            pass
        if getattr(self, "proc", None) and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)
