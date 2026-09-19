#!/usr/bin/env python3
"""SQUEAL TEST - a loaded corner makes the tyres squeal, and an ordinary one does not.

    .venv/Scripts/python tools/squeal-test.py

RLG-099. Owner, 2026-08-31: "I also feel like the tire should screech if the car is slid across the
ground because of the centripetal forces of a turn."

IT LISTENS TO THE SOUND. The squeal's level is read off the audio layer's own gain node
(`API.squealLevel`), not off `cornerLoad`, which is the number meant to cause it. A check on the cause
would pass with the wire to the sound cut.

WHAT IT ASSERTS, each with the throttle released, nothing braking, and the car HELD ON ITS LINE - so
the corner's load is the only cause (a car carried sideways squeals by the older path):
  . a straight road at speed is silent - the control;
  . a gentle bend at moderate speed is silent;
  . the hardest bend at speed squeals;
  . the same bend in the wet loads the tyres harder than in the dry.

WHAT IT CANNOT HEAR: whether the squeal sounds right, and whether it comes in at the right corner.
The thresholds are tunables (CORNER_SQUEAL). That is the owner's call by ear, on a device.

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

fails = []
# the level the squeal voices sit at when they are shut is 0; anything a player could hear is well
# above this - the smallest open level the engine sets is 0.018
HEARD = 0.01


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
print('squeal-test  .  a loaded corner squeals, an ordinary one does not')
with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]')
    pg.click('[data-act="drive"]')
    until(pg, "() => window.__probe.road.startLine().left <= 0", timeout=10000, required=False)
    pg.evaluate("() => { const R = window.__probe.road; R.setTimed(false); R.setSnow(0); }")

    def corner(k, frac, wet=0.0):
        """hold a bend of curvature `k` at `frac` of top speed, and read the load and the sound"""
        # THE CAR HOLDS ITS LINE, as a driver countering the corner does. Left free, the corner
        # carries it across the road and the OLD squeal - a car moving sideways - fires on its
        # own: with the corner load cut from the sound, the hardest bend still read 0.0293. Pinned,
        # the car barely moves sideways, so the corner's load is the only thing left to squeal.
        pg.evaluate("([k, f, w]) => { const R = window.__probe.road; R.setWet(w); R.holdCurve(k);"
                    " R.holdSpd(R.MAX_SPD * f); R.clearTraffic(); clearInterval(window.__line);"
                    " window.__line = setInterval(() => R.setLane(0), 4); }", [k, frac, wet])
        pg.wait_for_timeout(1600)
        load = pg.evaluate("() => window.__probe.road.cornerLoad()")
        levels = []
        for _ in range(6):
            pg.evaluate("() => window.__probe.road.clearTraffic()")
            pg.wait_for_timeout(80)
            levels.append(pg.evaluate("() => window.__probe.road.squealLevel()") or 0)
        pg.evaluate("() => clearInterval(window.__line)")
        return load, max(levels)

    straight = corner(0, 0.7)
    gentle = corner(1.4, 0.5)
    hard = corner(6.5, 0.7)
    wet = corner(3.3, 0.6, 1.0)
    dry = corner(3.3, 0.6, 0.0)
    for name, (load, lvl) in (('straight, 70%', straight), ('gentle bend, 50%', gentle),
                              ('hardest bend, 70%', hard), ('hard bend 60%, dry', dry),
                              ('hard bend 60%, wet', wet)):
        print('      %-20s load %.3f   squeal level %.4f' % (name, load, lvl))
    check(straight[1] < HEARD, 'a straight road at speed is silent', 'level %.4f' % straight[1])
    check(gentle[1] < HEARD, 'a gentle bend is silent', 'level %.4f' % gentle[1])
    check(hard[1] > HEARD, 'the hardest bend at speed squeals', 'level %.4f' % hard[1])
    check(wet[0] > dry[0] * 1.05, 'and a wet road loads the tyres harder than a dry one',
          'load %.3f wet against %.3f dry' % (wet[0], dry[0]))

    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
