#!/usr/bin/env python3
"""SCRUB SQUEAL TEST - a snatch at the wheel on a straight road squeals.

    .venv/Scripts/python tools/scrub-squeal-test.py

THIS CHECK EXISTS BECAUSE THE PATH IT COVERS WAS ALMOST DELETED IN SILENCE.

There are two ways to make the tyres sing. `squeal-test.py` covers one: a loaded
CORNER, held on its line, where the car barely moves sideways and `cornerLoad`
is the cause. It says so itself - "a car carried sideways squeals by the older
path" - and nothing covered that older path.

The older path is `scrubOf`, which measures how fast the car is moving ACROSS
the road. Every one of its callers fed a tyre mark, so when the marks were
deleted under RLG-327 it looked like part of the rubber and went with them. It
is not: `step()` reads the player's scrub 2,300 lines below where it is
computed, inside the same 2,800-line function, and hands it to the squeal. The
engine still parsed, the build was still green, and a hard steer had gone quiet.

IT LISTENS TO THE SOUND, like squeal-test does, reading the audio layer's own
gain through `API.squealLevel`. A check on `scrubOf`'s return value would pass
with the wire to the sound cut, which is the whole failure it is written for.

WHAT IT ASSERTS, on a straight road so no corner load can be the cause:
  . a straight road held steady at speed is silent - the control;
  . the same road with the wheel sawed hard squeals.

WHAT IT CANNOT HEAR: whether the squeal sounds right, or comes in at the right
amount of steering. Those are tunables and the owner's call, by ear, on a device.

Exit code 0 if every check passed, 1 otherwise.
"""
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
INIT = (ROOT / 'tools' / 'collide-test.py').read_text(encoding='utf-8').split('INIT = r"""')[1].split('"""')[0]
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright                  # noqa: E402
console_utf8()

fails = []
# the level the squeal voices sit at when they are shut is 0; the smallest open
# level the engine sets is 0.018. The same floor squeal-test uses.
HEARD = 0.01


def check(ok, label, detail=''):
    print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label, '   ' + detail if detail else ''))
    if not ok:
        fails.append(label)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
print('scrub-squeal-test  .  a snatch at the wheel squeals, a steady straight does not')

with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]')
    pg.click('[data-act="drive"]')
    until(pg, "() => window.__probe.road.startLine().left <= 0", timeout=10000, required=False)
    # no weather, no traffic to hit, no timer, and a STRAIGHT road - so the
    # corner load that squeal-test measures cannot be the cause of anything here
    pg.evaluate("() => { const R = window.__probe.road; R.setTimed(false); R.setSnow(0);"
                " R.setWet(0); R.holdCurve(0); R.clearTraffic(); }")
    pg.evaluate("() => window.__probe.road.holdSpd(window.__probe.road.MAX_SPD * 0.7)")

    def listen(ms):
        levels = []
        for _ in range(int(ms / 80)):
            pg.evaluate("() => window.__probe.road.clearTraffic()")
            pg.wait_for_timeout(80)
            levels.append(pg.evaluate("() => window.__probe.road.squealLevel()") or 0)
        return max(levels)

    # ---- the control: straight, steady, pinned to the centre --------------
    pg.evaluate("() => { clearInterval(window.__line);"
                " window.__line = setInterval(() => window.__probe.road.setLane(0), 4); }")
    pg.wait_for_timeout(1200)
    steady = listen(640)
    pg.evaluate("() => clearInterval(window.__line)")

    # ---- and the claim: the same road, with the wheel sawed --------------
    # Driven through the keyboard rather than by setting a lane, because the
    # squeal is caused by the RATE the car crosses the road and setting a
    # position each frame is not the same thing.
    sawed = 0
    for _ in range(5):
        pg.keyboard.down('ArrowLeft')
        pg.wait_for_timeout(120)
        sawed = max(sawed, pg.evaluate("() => window.__probe.road.squealLevel()") or 0)
        pg.keyboard.up('ArrowLeft')
        pg.keyboard.down('ArrowRight')
        pg.wait_for_timeout(120)
        sawed = max(sawed, pg.evaluate("() => window.__probe.road.squealLevel()") or 0)
        pg.keyboard.up('ArrowRight')

    print()
    check(steady < HEARD, 'a straight road held steady is silent', 'level %.4f' % steady)
    check(sawed > HEARD, 'a snatch at the wheel squeals', 'level %.4f' % sawed)
    check(sawed > steady * 2 or (steady < HEARD and sawed > HEARD),
          'and it is the steering that did it', 'steady %.4f -> sawed %.4f' % (steady, sawed))
    b.close()
srv.shutdown()

print()
print('  %d failure(s)%s' % (len(fails), (': ' + ', '.join(fails)) if fails else ''))
sys.exit(1 if fails else 0)
