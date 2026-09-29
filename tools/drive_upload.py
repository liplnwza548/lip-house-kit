#!/usr/bin/env python3
"""Upload batch6 subtitled MP4s to Lip's Drive folder via Muse Chrome (CDP 9225).

Raw-socket WS client (no Origin header). Flow: new tab -> verify login+folder ->
intercept file chooser -> click New/File-upload -> set 6 files -> poll until done.
"""
import base64
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

CDP = "http://127.0.0.1:9225"
FOLDER_ID = "1B7G-y-3P1cp4a3N-9omtOP8lUWFfSIyi"
FOLDER_URL = f"https://drive.google.com/drive/folders/{FOLDER_ID}"
OUT_DIR = "/home/box/subtitle-work/output/batch6"
EVIDENCE = "/home/box/subtitle-work/output/batch6/upload_evidence"
ALL6 = [f"c{i}_subtitled.mp4" for i in range(1, 7)]
FILES = [a for a in sys.argv[1:] if not a.startswith("--")]


def parse_flags():
    """Optional overrides (defaults preserve batch6 CLI behavior):
    --folder ID --outdir DIR --evidence DIR. Returns None (sets globals)."""
    global FOLDER_ID, FOLDER_URL, OUT_DIR, EVIDENCE, FILES
    args = [a for a in sys.argv[1:] if a.startswith("--")]
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in ("--folder", "--outdir", "--evidence") and i + 1 < len(args):
            if flag == "--folder":
                FOLDER_ID = args[i + 1]
                FOLDER_URL = ("https://drive.google.com/drive/folders/"
                              + FOLDER_ID)
            elif flag == "--outdir":
                OUT_DIR = args[i + 1]
            else:
                EVIDENCE = args[i + 1]
            i += 2
        else:
            raise SystemExit(f"unknown flag {flag} "
                             f"(use --folder/--outdir/--evidence)")
    FILES = [a for a in sys.argv[1:] if not a.startswith("--")] or ALL6
    os.makedirs(EVIDENCE, exist_ok=True)
    for f in FILES:
        p = os.path.join(OUT_DIR, f)
        assert os.path.isfile(p) and os.path.getsize(p) > 10_000_000, f"missing/small: {p}"


def http(path, method="GET"):
    req = urllib.request.Request(CDP + path, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


class WS:
    def __init__(self, ws_url):
        u = urllib.parse.urlparse(ws_url)
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=70)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {u.path or '/'} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("handshake failed")
            resp += chunk
        if b"101" not in resp.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"WS handshake rejected: {resp[:200]}")
        self.buf = b""
        self.mid = 0

    def send(self, method, params=None):
        self.mid += 1
        payload = json.dumps({"id": self.mid, "method": method,
                              "params": params or {}}).encode()
        mask = os.urandom(4)
        if len(payload) < 126:
            hdr = b"\x81" + bytes([0x80 | len(payload)])
        elif len(payload) < 65536:
            hdr = b"\x81\xFE" + len(payload).to_bytes(2, "big")
        else:
            hdr = b"\x81\xFF" + len(payload).to_bytes(8, "big")
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(hdr + mask + masked)
        return self.mid

    def _fill(self, n, deadline):
        while len(self.buf) < n:
            if time.time() > deadline:
                raise TimeoutError("ws recv timeout")
            self.sock.settimeout(max(0.5, deadline - time.time()))
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                raise TimeoutError("ws recv timeout")
            if not chunk:
                raise RuntimeError("ws closed")
            self.buf += chunk

    def recv_frame(self, timeout=60):
        deadline = time.time() + timeout
        self._fill(2, deadline)
        b1, b2 = self.buf[0], self.buf[1]
        ln = b2 & 0x7F
        off = 2
        if ln == 126:
            self._fill(4, deadline)
            ln = int.from_bytes(self.buf[2:4], "big")
            off = 4
        elif ln == 127:
            self._fill(10, deadline)
            ln = int.from_bytes(self.buf[2:10], "big")
            off = 10
        self._fill(off + ln, deadline)
        data = self.buf[off:off + ln]
        self.buf = self.buf[off + ln:]
        if b1 == 0x89:  # ping -> pong
            self.sock.sendall(b"\x8A\x80" + os.urandom(4))
            return self.recv_frame(max(1, deadline - time.time()))
        return json.loads(data.decode())

    def call(self, method, params=None, timeout=60):
        mid = self.send(method, params)
        deadline = time.time() + timeout
        while True:
            msg = self.recv_frame(max(1, deadline - time.time()))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            # stash events for later
            getattr(self, "_events", []).append(msg) if False else None
            (self._evts if hasattr(self, "_evts") else []).append(msg)

    def drain_events(self):
        evts = getattr(self, "_evts", [])
        self._evts = []
        return evts


def ev(ws, js, timeout=30):
    r = ws.call("Runtime.evaluate",
                {"expression": js, "returnByValue": True}, timeout=timeout)
    return r.get("result", {}).get("value")


def precheck_audio(path):
    """P3 upload gate: refuse files with no audio stream or off-spec
    loudness (Lip-locked 2026-09-29 — no bad-audio file may reach Drive)."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    if not (probe.stdout or "").strip():
        raise SystemExit(f"UPLOAD_BLOCKED {path}: no audio stream")
    meas = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    text = meas.stdout + meas.stderr
    try:
        data = json.loads(text[text.find("{"):text.rfind("}") + 1])
        lufs = float(data["input_i"])
    except (ValueError, KeyError):
        raise SystemExit(f"UPLOAD_BLOCKED {path}: loudness unreadable")
    if not (-16.0 <= lufs <= -14.0):
        raise SystemExit(f"UPLOAD_BLOCKED {path}: {lufs} LUFS outside "
                         f"-15+/-1 — remix before delivery")
    print(f"AUDIO_OK {os.path.basename(path)}: {lufs} LUFS", flush=True)


def main():
    parse_flags()
    for f in FILES:
        precheck_audio(os.path.join(OUT_DIR, f))
    # cleanup: close any leftover tabs of ours on this folder (never touch Lip's other tabs)
    for t in http("/json/list"):
        if FOLDER_ID in (t.get("url") or "") and t.get("type") == "page":
            try:
                http(f"/json/close/{t['id']}")
                print(f"CLOSED_LEFTOVER {t['id']}", flush=True)
            except Exception:
                pass
    tab = http("/json/new?" + urllib.parse.quote(FOLDER_URL, safe=""), method="PUT")
    tab_id = tab["id"]
    print(f"TAB {tab_id} {tab.get('url')}", flush=True)
    ws = WS(tab["webSocketDebuggerUrl"])
    ws._evts = []
    ws.call("Page.enable")
    ws.call("Runtime.enable")
    ws.call("DOM.enable")
    ws.call("Page.navigate", {"url": FOLDER_URL})
    print("NAVIGATED", flush=True)

    # 1) verify login + folder (poll 45s)
    ok = False
    for _ in range(15):
        time.sleep(3)
        st = ev(ws, """(() => ({
            href: location.href,
            loginWall: !!document.querySelector('input[type=email]'),
            body: (document.body ? document.body.innerText.slice(0,4000) : '')
        }))()""")
        if not st:
            continue
        if st.get("loginWall"):
            raise SystemExit("BLOCKED: Google login wall — need Lip to log in")
        body = st.get("body", "")
        if FOLDER_ID in st.get("href", "") and ("copy_" in body or "ไดรฟ์" in body or "Drive" in body):
            print("LOGIN_OK FOLDER_OK (sees original copy_*.mov files)", flush=True)
            ok = True
            break
    if not ok:
        raise SystemExit("BLOCKED: folder did not load recognizably")
    shot = ws.call("Page.captureScreenshot", {"format": "jpeg", "quality": 60})
    open(f"{EVIDENCE}/pre.png", "wb").write(base64.b64decode(shot["data"]))
    print("PRE_SHOT saved", flush=True)

    # 2) drag-and-drop upload: drop the 6 files onto the file grid
    # (avoids the native file-chooser dialog entirely)
    paths = [os.path.join(OUT_DIR, f) for f in FILES]
    pt = ev(ws, """(() => {
        const els = [...document.querySelectorAll('div[role=grid], div[role=rowgroup], c-wiz div')];
        let box = null;
        for (const el of els) {
            const r = el.getBoundingClientRect();
            if (r.width > 400 && r.height > 200) { box = {x: r.x + r.width/2, y: r.y + r.height/2}; break; }
        }
        if (!box) box = {x: window.innerWidth/2, y: window.innerHeight*0.6};
        return {x: Math.round(box.x), y: Math.round(box.y), w: window.innerWidth, h: window.innerHeight};
    })()""")
    print(f"DROP_AT {pt}", flush=True)
    drag = {"items": [], "files": paths, "dragOperationsMask": 1}
    ws.call("Input.dispatchDragEvent",
            {"type": "dragEnter", "x": pt["x"], "y": pt["y"], "data": drag})
    time.sleep(1)
    ws.call("Input.dispatchDragEvent",
            {"type": "dragOver", "x": pt["x"], "y": pt["y"], "data": drag})
    time.sleep(1)
    ws.call("Input.dispatchDragEvent",
            {"type": "drop", "x": pt["x"], "y": pt["y"], "data": drag})
    print(f"DROPPED {len(paths)} files", flush=True)
    time.sleep(5)

    # 4) poll upload completion (up to 15 min)
    t0 = time.time()
    final = False
    want = json.dumps(FILES)
    while time.time() - t0 < 900:
        time.sleep(10)
        st = ev(ws, f"""(() => {{
            const t = document.body ? document.body.innerText : '';
            const want = {want};
            return {{
                done: /อัปโหลดเสร็จสมบูรณ์|Upload complete/i.test(t),
                uploading: /กำลังอัปโหลด|Uploading/i.test(t),
                found: want.filter(n => t.includes(n))
            }};
        }})()""", timeout=30) or {}
        el = int(time.time() - t0)
        print(f"[{el}s] done={st.get('done')} uploading={st.get('uploading')} found={len(st.get('found', []))}/{len(FILES)}", flush=True)
        if len(st.get("found", [])) == len(FILES) and not st.get("uploading"):
            final = True
            break
    shot = ws.call("Page.captureScreenshot", {"format": "jpeg", "quality": 60})
    open(f"{EVIDENCE}/post.png", "wb").write(base64.b64decode(shot["data"]))
    print("POST_SHOT saved", flush=True)
    try:
        http(f"/json/close/{tab_id}")
        print("TAB_CLOSED", flush=True)
    except Exception as e:
        print(f"close tab: {e}", flush=True)
    if not final:
        raise SystemExit("BLOCKED: upload did not confirm within 15 min")
    print(f"UPLOAD_OK {len(FILES)}/{len(FILES)} files in folder", flush=True)


if __name__ == "__main__":
    main()
