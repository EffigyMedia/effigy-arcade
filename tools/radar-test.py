#!/usr/bin/env python3
"""RADAR TEST - the detector sees what is ahead, and only what is ahead.

    .venv/Scripts/python tools/radar-test.py

Owner, 2026-09-07 (RLG-164): "we could add a radar detector element for upcoming speed
traps and traffic cops, just like it was done in the original Need for Speed games."

THE RULING NAMES BOTH KINDS and they are held in two different places - a speed trap is a
parked entry in `cops` and a patrol is an ordinary car in `traffic` until it engages - so a
detector that swept one list and not the other would be half built and would look finished.
Each kind is measured on its own, alone on the road, so a check for a trap cannot pass on
the strength of the patrol code.

WHAT MAKES THIS EVIDENCE RATHER THAN A READING: the road is emptied and re-measured between
arms, so a gauge that simply returned a number fails the empty one; and the strength is
asserted to RISE as one contact closes, which no constant can satisfy.
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot
from playwright.sync_api import sync_playwright

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d' % PORT

# ONE CONTACT, PUT BACK EVERY TICK, AND NOTHING ELSE ON THE ROAD. The engine keeps
# dispatching and keeps laying traffic down the road, so a measurement of "what is at
# 20,000 units" has to own the road or the number is about whatever else arrived. The
# same rebuild-rather-than-add approach the heat points check needed, for the same reason.
HOLD = """([dz, kind]) => {
  const R = window.__road;
  clearInterval(window.__hold);
  window.__hold = setInterval(() => {
    const pz = R.pos + R.PLAYER_Z;
    R.setSpd(0);
    R.parkTraffic(9, 60000);
    for(const c of R.traffic) c.patrol = false;
    const a = R.cops(); a.length = 0;
    if(kind === 'trap')
      a.push({ z: pz + dz, x: 1.16, spd: 0, wreck: 0, ang: 0, grace: 0, cool: 0,
               side: 1, w: 0.27, len: 400, phase: 0, trap: true, armed: true,
               from: 'trap' });
    if(kind === 'patrol') R.placePatrol(dz);
  }, 8);
}"""


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('radar-test  .  the detector sees what is ahead')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, BASE + '/games/sw/interstate.html')
        page.wait_for_timeout(1200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(400)
        # HOT PURSUIT on, or there are no police for a detector to detect
        page.click('[data-act="chase"]')
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1200)
        # AND THE RUN HAS TO OUTLIVE THE CHECKS. A parked car reaches no checkpoint, so
        # the sixty seconds a run starts with expire and the update stops, freezing every
        # reading where it stood. See RLG-169, where that cost most of an afternoon.
        page.evaluate('() => window.__road.setTimed(false)')

        rng = page.evaluate('() => window.__road.radar().range')
        mile = page.evaluate('() => window.__road.heatPoints().rates.mileUnits')
        print('  ..    the detector reaches %d units, about %.2f of a mile'
              % (rng, rng / mile))

        def read(dz, kind):
            page.evaluate(HOLD, [dz, kind])
            page.wait_for_timeout(700)
            return page.evaluate('() => window.__road.radar()')

        # ---- AN EMPTY ROAD READS NOTHING ----------------------------------------
        empty = read(0, 'none')
        ok(empty['up'] == 0 and empty['bars'] == 0, 'an empty road reads nothing',
           'up %.3f, %d bars' % (empty['up'], empty['bars']))

        # ---- AND SO DOES ONE BEYOND THE RANGE -----------------------------------
        far = read(int(rng * 1.4), 'trap')
        ok(far['up'] == 0, 'a trap beyond the range reads nothing',
           'up %.3f at %d units' % (far['up'], int(rng * 1.4)))

        # ---- A TRAP CLOSING RAISES IT -------------------------------------------
        # THE SEQUENCE IS THE ASSERTION. A single reading proves only that the gauge
        # returns a number; a rising one proves that the number is a distance.
        steps = [0.90, 0.60, 0.35, 0.10]
        trap = [read(int(rng * f), 'trap') for f in steps]
        print('  ..    a trap closing: up %s, bars %s'
              % (['%.2f' % t['up'] for t in trap], [t['bars'] for t in trap]))
        ok(all(trap[i]['up'] < trap[i + 1]['up'] for i in range(len(trap) - 1)),
           'a speed trap closing raises the detector',
           ' -> '.join('%.2f' % t['up'] for t in trap))
        ok(trap[0]['bars'] >= 1 and trap[-1]['bars'] == 4,
           'and it runs from one bar at the edge to four on arrival',
           '%d bars then %d' % (trap[0]['bars'], trap[-1]['bars']))

        # ---- AND SO DOES A PATROL, THE OTHER HALF OF THE RULING -----------------
        pat = [read(int(rng * f), 'patrol') for f in steps]
        print('  ..    a patrol at the same places: up %s, bars %s'
              % (['%.2f' % t['up'] for t in pat], [t['bars'] for t in pat]))
        ok(all(t['up'] > 0 for t in pat),
           'a patrol car in traffic is detected too',
           ' '.join('%.2f' % t['up'] for t in pat))
        ok(all(pat[i]['up'] < pat[i + 1]['up'] for i in range(len(pat) - 1)),
           'and it rises as that one closes as well',
           ' -> '.join('%.2f' % t['up'] for t in pat))

        # ---- AND THE GAUGE IS ON THE SCREEN, NOT ONLY IN THE STATE --------------
        # A number nobody can see is not a detector. This reads the DOM the player is
        # looking at rather than the API that fed it.
        page.evaluate(HOLD, [int(rng * 0.1), 'trap'])
        page.wait_for_timeout(700)
        shown = page.evaluate("""() => {
            const w = document.getElementById('radarWrap');
            return { hidden: w.hidden,
                     lit: document.querySelectorAll('#radar i.on').length,
                     hot: document.querySelectorAll('#radar i.hot').length }; }""")
        ok(not shown['hidden'] and shown['lit'] == 4 and shown['hot'] == 1,
           'the readout is on the screen with the last bar hot', str(shown))

        page.evaluate('() => { clearInterval(window.__hold); window.__road.copsClear(); }')
        page.wait_for_timeout(900)
        gone = page.evaluate("() => document.getElementById('radarWrap').hidden")
        ok(gone, 'and it leaves the row when there is nothing to warn about')

        ok(errs == [], 'no page errors', errs[0][:120] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('the detector sees what is ahead' if not bad else str(bad) + ' FAILURES'))
    return 1 if bad else 0


sys.exit(main())
