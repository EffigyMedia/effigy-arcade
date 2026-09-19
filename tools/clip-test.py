#!/usr/bin/env python3
"""CLIP TEST - a car close to the player is not clipped along its bottom by the road.

    .venv/Scripts/python tools/clip-test.py

RLG-068. Owner, 2026-08-29, from the device: "a vehicle close to the player has the very bottom of
its sprite clipped by a slice of road."

MEASURED, AS THE RULING ASKED, BEFORE BELIEVING ANY FIX. A car is parked at a known distance on a
straight, still road, and the frame is taken with it and without it. The pixels that change ARE the
car, whatever colour it is - so the count of them, and the lowest row they reach, say how much of the
car the road left visible. The same car, the same place, is measured twice: in the OLD paint order
(`emitLag(0)`) and in the new one, where a car waits for the slice in front of it. The old order is
the defect put back, in the same run.

WHAT IT ASSERTS: at every distance, the new order shows at least as much of the car as the old one,
and at the distances where the old one lost rows, it shows them.

WHAT IT CANNOT SEE: whether the result looks right in motion on a phone. That is the owner's call.

Exit code 0 if every check passed, 1 otherwise.
"""
import io, sys, functools, http.server, socketserver, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
INIT = (ROOT / 'tools' / 'collide-test.py').read_text(encoding='utf-8').split('INIT = r"""')[1].split('"""')[0]
from harness import console_utf8, launch_chromium, boot, until
from playwright.sync_api import sync_playwright
console_utf8()

fails = []
DISTANCES = (700, 900, 1200, 1600, 2400)


def check(ok, label, detail=''):
    print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label, '   ' + detail if detail else ''))
    if not ok:
        fails.append(label)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def car_pixels(a, b):
    """how many pixels differ between two frames, and the lowest row that differs"""
    from PIL import Image
    ia = Image.open(io.BytesIO(a)).convert('RGB')
    ib = Image.open(io.BytesIO(b)).convert('RGB')
    w, h = ia.size
    pa, pb = ia.load(), ib.load()
    n, low = 0, -1
    # the lower 55% of the frame: the road ahead, not the mirror
    for y in range(int(h * 0.45), h):
        for x in range(0, w):
            ca, cb = pa[x, y], pb[x, y]
            if abs(ca[0]-cb[0]) + abs(ca[1]-cb[1]) + abs(ca[2]-cb[2]) > 30:
                n += 1
                if y > low:
                    low = y
    return n, low


s = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = s.server_address[1]
threading.Thread(target=s.serve_forever, daemon=True).start()
print('clip-test  .  a car close to the player keeps its bottom edge')
with sync_playwright() as p:
    b = launch_chromium(p, headless=True)
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]')
    pg.click('[data-act="drive"]')
    until(pg, "() => window.__probe.road.startLine().left <= 0", timeout=10000, required=False)
    # a still, straight, dry road at midday, so the only thing that changes is the car
    pg.evaluate("() => { const R = window.__probe.road; R.setTimed(false); R.holdCurve(0);"
                " R.setBiomePair('DESERT', 'DESERT'); R.setWet(0); R.setSnow(0); R.setPool(0);"
                " R.setPhase(0.75); R.clearTraffic(); R.holdSpd(0); }")
    pg.wait_for_timeout(1500)

    def measure(lag, dz):
        pg.evaluate("(l) => window.__probe.road.emitLag(l)", lag)
        pg.evaluate("() => { const R = window.__probe.road; R.clearTraffic(); R.holdSpd(0);"
                    " R.setPhase(0.75); }")
        pg.wait_for_timeout(150)
        empty = pg.screenshot()
        pg.evaluate("(d) => { const R = window.__probe.road; R.parkTraffic(0, d, 'sedan');"
                    " R.holdSpd(0); R.setPhase(0.75); }", dz)
        pg.wait_for_timeout(150)
        with_car = pg.screenshot()
        pg.evaluate("() => window.__probe.road.clearTraffic()")
        return car_pixels(empty, with_car)

    lost_any = False
    for dz in DISTANCES:
        old = measure(0, dz)
        new = measure(1, dz)
        print('      %5d ahead   old order %5d px, lowest row %d   |   new order %5d px, lowest row %d'
              % (dz, old[0], old[1], new[0], new[1]))
        check(new[0] >= old[0] - 5 and new[1] >= old[1],
              'at %d ahead the new order shows at least as much of the car' % dz,
              'old %d px to row %d, new %d px to row %d' % (old[0], old[1], new[0], new[1]))
        if new[1] > old[1]:
            lost_any = True
    check(lost_any, 'and at some distance the old order lost rows the new one shows',
          '' if lost_any else 'no distance differed - the defect was not reproduced here')
    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
