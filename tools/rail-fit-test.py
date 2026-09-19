#!/usr/bin/env python3
"""RAIL FIT TEST - every car meets the rail the same way.

    .venv/Scripts/python tools/rail-fit-test.py

RLG-279. Owner, 2026-09-16: "For the cars to consistently hit the edge physics objects we need
their collider to be perfectly correct."

WHAT IT MEASURED BEFORE. Driven hard into a city barrier, every body stopped short of the rail:
the formula cars by 0.016-0.035 of a road half-width, the production and sports cars by up to
0.072. The rail was drawn for the WIDEST body, so a narrower car never reached it.

WHAT IT ASSERTS. Each car is driven into the barrier on both sides, and `API.railFit` reports the
gap between its flank and the rail every frame while it presses there:
  . never below zero - the car does not pass through the rail;
  . at most `MEETS` - the car actually reaches it;
  . the same for the narrowest and the widest car - "consistently" is the ruling's word.
The narrowest and widest bodies are the two that matter: a rail placed for one of them is wrong
for the other, which is the defect.

WHAT IT CANNOT SEE: whether the car looks like it is touching the rail at speed on a phone. The
gap is in road half-widths, not pixels. That is the owner's call on a device.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, functools, http.server, socketserver, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
INIT = (ROOT / 'tools' / 'collide-test.py').read_text(encoding='utf-8').split('INIT = r"""')[1].split('"""')[0]
from harness import console_utf8, launch_chromium, boot, until
from playwright.sync_api import sync_playwright
console_utf8()

# the most daylight that still counts as meeting the rail: the skin plus the wall's own
# 0.02 of resting jitter, and a hair over. Before the fix the narrowest car read 0.072.
MEETS = 0.03
BODIES = ('ROADSTER', 'COUPE', 'MUSCLE', 'STALLION', 'VECTOR')   # narrowest to widest

fails = []


def check(ok, label, detail=''):
    print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label, '   ' + detail if detail else ''))
    if not ok:
        fails.append(label)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


s = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = s.server_address[1]
threading.Thread(target=s.serve_forever, daemon=True).start()
print('rail-fit-test  .  every car meets the rail the same way')
with sync_playwright() as p:
    b = launch_chromium(p, headless=True)
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]')
    pg.click('[data-act="drive"]')
    pg.wait_for_timeout(4500)
    # A CITY, because it has a barrier on BOTH sides, so both sides are measured in one place
    pg.evaluate("() => { const R = window.__probe.road; R.setTimed(false);"
                " R.setBiomePair('CITY', 'CITY'); R.holdCurve(0); }")
    worst = {}
    for k in BODIES:
        pg.evaluate("(k) => window.__probe.road.setBody(k)", k)
        # after a body swap the browser delivers no frames for about a second (RLG-279)
        t0 = pg.evaluate("() => window.__probe.road.simTime()")
        until(pg, "(t) => window.__probe.road.simTime() > t + 0.1", arg=t0, timeout=10000,
              required=False)
        gaps = []
        for side in (1, -1):
            for _ in range(40):
                pg.evaluate("(s) => { const R = window.__probe.road; R.clearTraffic();"
                            " R.setSpd(R.MAX_SPD * 0.3); R.setTarget(s * 2); }", side)
                pg.wait_for_timeout(40)
            for _ in range(12):
                pg.evaluate("(s) => { const R = window.__probe.road; R.clearTraffic();"
                            " R.setSpd(R.MAX_SPD * 0.3); R.setTarget(s * 2); }", side)
                pg.wait_for_timeout(30)
                gaps.append(pg.evaluate("() => window.__probe.road.railFit().gap"))
        half = pg.evaluate("() => window.__probe.road.railFit().half")
        worst[k] = (min(gaps), max(gaps))
        print('      %-9s half-width %.4f   flank to rail %+.4f .. %+.4f' % (k, half, min(gaps), max(gaps)))
        check(min(gaps) >= 0, '%s does not pass through the rail' % k.lower(), '%+.4f' % min(gaps))
        check(max(gaps) <= MEETS, '%s reaches the rail' % k.lower(),
              'up to %.4f of daylight against %.2f' % (max(gaps), MEETS))
    spread = max(w[1] for w in worst.values()) - min(w[1] for w in worst.values())
    check(spread < 0.005, 'and the narrowest and widest cars meet it the same way',
          'the largest gap differs by %.4f across the bodies' % spread)
    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
