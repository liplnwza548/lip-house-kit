#!/usr/bin/env python3
"""Move old batch6 files to Drive trash via Muse Chrome (CDP 9225).

Lip-approved: delete ONLY the filenames passed as argv (old wrong versions)
before re-uploading fixed ones. Verifies selection + confirm dialog + disappearance.
Usage: drive_delete.py <name1> [name2 ...]
"""
import base64
import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive_upload import WS, http, ev  # noqa: E402

CDP = "http://127.0.0.1:9225"
FOLDER_ID = "1B7G-y-3P1cp4a3N-9omtOP8lUWFfSIyi"
FOLDER_URL = f"https://drive.google.com/drive/folders/{FOLDER_ID}"
EVIDENCE = "/home/box/subtitle-work/output/batch6/upload_evidence"

TARGETS = [a for a in sys.argv[1:] if not a.startswith("--")]


def parse_flags():
    """Optional overrides (defaults preserve batch6 CLI behavior):
    --folder ID --evidence DIR. Returns (folder_id, evidence)."""
    global FOLDER_ID, FOLDER_URL, EVIDENCE
    args = [a for a in sys.argv[1:] if a.startswith("--")]
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in ("--folder", "--evidence") and i + 1 < len(args):
            if flag == "--folder":
                FOLDER_ID = args[i + 1]
                FOLDER_URL = ("https://drive.google.com/drive/folders/"
                              + FOLDER_ID)
            else:
                EVIDENCE = args[i + 1]
            i += 2
        else:
            raise SystemExit(f"unknown flag {flag} "
                             f"(use --folder ID --evidence DIR)")
    os.makedirs(EVIDENCE, exist_ok=True)
    assert TARGETS, "usage: drive_delete.py [--folder ID] <name> [...]"
    assert all(t.endswith(".mp4") and "/" not in t for t in TARGETS), \
        "mp4 names only"


def main():
    parse_flags()
    tab = http("/json/new?" + urllib.parse.quote(FOLDER_URL, safe=""), method="PUT")
    tab_id = tab["id"]
    print(f"TAB {tab_id}", flush=True)
    ws = WS(tab["webSocketDebuggerUrl"])
    ws._evts = []
    ws.call("Page.enable")
    ws.call("Runtime.enable")
    ws.call("Page.navigate", {"url": FOLDER_URL})

    ok = False
    for _ in range(15):
        time.sleep(3)
        st = ev(ws, """(() => ({
            loginWall: !!document.querySelector('input[type=email]'),
            body: (document.body ? document.body.innerText.slice(0,2000) : '')
        }))()""")
        if st and not st.get("loginWall") and "copy_" in st.get("body", ""):
            ok = True
            break
    if not ok:
        raise SystemExit("BLOCKED: folder not loaded")
    print("FOLDER_OK", flush=True)

    for name in TARGETS:
        # 1) scope the grid with Drive search ("/" focuses it) so ONLY our
        # file is listed. Abort unless exactly 1 match (no mis-targeting).
        for kd in ({"type": "rawKeyDown"}, {"type": "keyUp"}):
            ws.call("Input.dispatchKeyEvent",
                    {"type": kd["type"], "text": "/", "key": "/",
                     "code": "Slash", "windowsVirtualKeyCode": 191})
        time.sleep(2)
        prep = ev(ws, """(() => {
            const a = document.activeElement;
            if (!a || !/INPUT|TEXTAREA/.test(a.tagName)) return 'FOCUS:' + (a ? a.tagName : 'none');
            return 'IN_INPUT:' + (a.getAttribute('aria-label') || '-').slice(0, 30);
        })()""")
        print(f"SEARCHFOCUS {name}: {prep}", flush=True)
        if not str(prep).startswith("IN_INPUT"):
            raise SystemExit(f"BLOCKED: / did not focus search ({prep})")
        # clear previous search text (Ctrl+A, Backspace)
        for kd in ({"type": "keyDown"}, {"type": "keyUp"}):
            ws.call("Input.dispatchKeyEvent",
                    {"type": kd["type"], "modifiers": 2, "key": "a",
                     "code": "KeyA", "windowsVirtualKeyCode": 65})
        for kd in ({"type": "rawKeyDown"}, {"type": "keyUp"}):
            ws.call("Input.dispatchKeyEvent",
                    {"type": kd["type"], "key": "Backspace",
                     "code": "Backspace", "windowsVirtualKeyCode": 8})
        time.sleep(1)
        ws.call("Input.insertText", {"text": name})
        time.sleep(1)
        back = ev(ws, """(() => {
            const a = document.activeElement;
            return (a && /INPUT|TEXTAREA/.test(a.tagName)) ? a.value : 'LOST';
        })()""")
        if back != name:
            raise SystemExit(f"BLOCKED: search text did not land ({back!r})")
        for k in ("rawKeyDown", "keyUp"):
            ws.call("Input.dispatchKeyEvent",
                    {"type": k, "windowsVirtualKeyCode": 13, "key": "Enter",
                     "code": "Enter", "nativeVirtualKeyCode": 13})
        time.sleep(4)
        n0 = ev(ws, f"""(() => {{
            return [...document.querySelectorAll('body *')].filter(e =>
                e.children.length === 0 && (e.innerText||'').trim() === {json.dumps(name)}).length;
        }})()""")
        print(f"SEARCH {name}: leaf matches = {n0}", flush=True)
        if n0 != 1:
            raise SystemExit(f"BLOCKED: expected exactly 1 match for {name}, saw {n0} — abort, no delete")
        # 1b) hover the single row and open its More-actions menu
        opened = ev(ws, f"""(() => {{
            const want = {json.dumps(name)};
            const leafs = [...document.querySelectorAll('body *')].filter(e =>
                e.children.length === 0 && (e.innerText||'').trim() === want);
            if (leafs.length !== 1) return 'NOT_SINGLE:' + leafs.length;
            let el = leafs[0], row = null;
            for (let i=0;i<8 && el && el.tagName!=='BODY';i++) {{
                const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {{}};
                if ((r.width||0) > 300 && (r.height||0) > 30 && (r.height||0) < 120) {{ row = el; break; }}
                el = el.parentElement;
            }}
            if (!row) return 'NO_ROW';
            const r = row.getBoundingClientRect();
            return 'ROW_AT:' + Math.round(r.x + r.width - 40) + ',' + Math.round(r.y + r.height/2);
        }})()""")
        print(f"HOVER {name}: {opened}", flush=True)
        if not str(opened).startswith("ROW_AT"):
            raise SystemExit(f"BLOCKED: no single row for {name}")
        _x, _y = [int(v) for v in str(opened).split(":")[1].split(",")]
        ws.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": _x, "y": _y})
        time.sleep(1)
        opened2 = ev(ws, """(() => {
            const more = [...document.querySelectorAll('button')].filter(b =>
                /การดำเนินการเพิ่มเติม|More actions/i.test(b.getAttribute('aria-label')||''));
            if (!more.length) return 'NO_BTN';
            more[0].click();
            return 'MENU_OPENED';
        })()""")
        print(f"MENU {name}: {opened2}", flush=True)
        if str(opened2) != "MENU_OPENED":
            raise SystemExit(f"BLOCKED: menu did not open for {name}")
        time.sleep(2)
        # 2) click Remove / Move-to-trash menu item
        removed = ev(ws, """(() => {
            const cands = [...document.querySelectorAll('body *')].filter(e =>
                e.children.length === 0 && /^\\s*(นำออก|Remove|ย้ายไปที่ถังขยะ|Move to trash)\\s*$/.test(e.innerText || ''));
            if (!cands.length) {
                const all = [...document.querySelectorAll('body *')].filter(e =>
                    e.children.length === 0 && (e.innerText||'').trim().length < 40 && (e.innerText||'').trim().length > 0)
                    .map(e => e.innerText.trim()).join('|').slice(-400);
                return 'NO_ITEM, visible:' + all;
            }
            cands[0].click();
            return 'CLICKED_REMOVE';
        })()""")
        print(f"REMOVE {name}: {removed}", flush=True)
        if str(removed) != "CLICKED_REMOVE":
            raise SystemExit(f"BLOCKED: no remove item ({removed})")
        time.sleep(2)
        conf = ev(ws, """(() => {
            const t = document.body ? document.body.innerText : '';
            const m = /ย้ายไปที่ถังขยะ|Move to trash/i.test(t);
            if (!m) return 'NO_DIALOG:' + t.slice(-200);
            const btns = [...document.querySelectorAll('button')];
            const ok = btns.find(b => /ย้ายไปที่ถังขยะ|Move to trash|^ย้าย$|^Move$/i.test(b.innerText.trim()));
            if (!ok) return 'NO_CONFIRM_BTN';
            ok.click();
            return 'CONFIRMED';
        })()""")
        print(f"TRASH {name}: {conf}", flush=True)

        # 3) verify disappearance: wait out the toast, then NO leaf may carry the name
        time.sleep(12)
        gone = False
        for _ in range(6):
            n = ev(ws, f"""(() => {{
                const want = {json.dumps(name)};
                return [...document.querySelectorAll('body *')].filter(e =>
                    e.children.length === 0 && (e.innerText||'').trim() === want).length;
            }})()""")
            if n == 0:
                gone = True
                break
            time.sleep(5)
        print(f"VERIFY {name}: {'TRASHED' if gone else 'STILL THERE: ' + str(n)}", flush=True)
        if not gone:
            raise SystemExit(f"BLOCKED: {name} still visible after delete")

    shot = ws.call("Page.captureScreenshot", {"format": "jpeg", "quality": 60})
    open(f"{EVIDENCE}/delete_post.png", "wb").write(base64.b64decode(shot["data"]))
    try:
        http(f"/json/close/{tab_id}")
    except Exception:
        pass
    print(f"DELETE_OK {len(TARGETS)} file(s) trashed", flush=True)


if __name__ == "__main__":
    main()
