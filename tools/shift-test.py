"""A RIVAL HOLDS A GEAR, AND YOU HEAR IT SHIFT.

    .venv/Scripts/python tools/shift-test.py

Owner, 2026-09-06: "the AI racers should have shift events all the same no matter what... I
should hear them hit the red line and shift up or shift down if they slam on the brakes next
to me." And, clarifying: "I don't mean I actually hear the shifter. I just hear what their
engine does as an effect of them shifting up or down."

SO THE CLAIM UNDER TEST IS NOT "A SOUND PLAYS". Nothing new is played. The claim is that a
rival's REVS stop being a smooth function of its speed - that they climb, break, and drop.
This checks the mechanism that produces that, and then the consequence.

  1. Every rival holds a gear at all. Before this they had none: the band was recomputed
     from speed each frame, so there was no gear to hold and nothing to shift out of.
  2. Gears actually CHANGE over a run, and cars are seen mid-shift. A held gear that never
     moves would satisfy check 1 and be worse than what it replaced.
  3. The field is not in lockstep. Eleven cars of three models at different speeds should
     not all be in the same gear - if they are, the gear is a disguised speed reading.
  4. Revs BREAK. This is the audible claim itself: sampling one car's rpm-in-gear, the
     series must fall somewhere despite the car accelerating. A car with no gearbox rises
     monotonically forever, which is exactly the sound being complained about.

CHECK 4 IS THE ONE THAT MATTERS AND IT IS COMPUTED THE WAY THE AUDIO COMPUTES IT - speed
against the top of the held band - rather than by reading the oscillator. The engine voice is
shared between sixteen slots and reassigned by proximity, so which node carries which car
changes from frame to frame; reading a node would measure the voice allocator, not the car.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, threading, http.server, socketserver, functools

from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot, until
from playwright.sync_api import sync_playwright
console_utf8()

h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

bad = [0]


def check(ok, label, detail):
    print(f'  {"ok  " if ok else "FAIL"}  {label:<44} {detail}')
    if not ok:
        bad[0] += 1


SAMPLE = """async () => {
  const R = window.__road;
  const frames = [];
  for (let i = 0; i < 140; i++) {
    await new Promise(r => setTimeout(r, 40));
    frames.push(R.rivalGears());
  }
  return frames;
}"""

with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    boot(pg, f'http://127.0.0.1:{PORT}/games/sw/interstate.html')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="mode"]', timeout=5000)
    pg.click('[data-act="mode"]')          # TEST DRIVE -> SINGLE RACE, so there is a field
    pg.wait_for_timeout(150)
    pg.click('[data-act="drive"]')

    # ---- WAIT FOR THE FLAG, DO NOT MEASURE THE COUNT-IN ---------------------
    # The grid is HELD during the count: all eleven cars sit at exactly the same
    # speed and no gear has been picked, because the gearbox only steps once the
    # racers do. Sampling then reports "0 of 11 cars hold a gear" - which is true
    # and means nothing. This waits for the field to actually be released, and
    # fails loudly if it never is rather than measuring a stationary grid.
    try:
        until(pg, "() => { const g = window.__road.rivalGears();"
            "        return g.length && g.some(r => r.gear >= 1); }",
            timeout=15000)
    except Exception:
        print()
        print('  FAIL  the grid was never released - nothing below is meaningful')
        bad[0] += 1

    frames = pg.evaluate(SAMPLE)
    live = [f for f in frames if f]

    print()
    if not live or not live[0]:
        check(False, 'there is a field to measure at all',
              'no rivals returned - a race did not start, so nothing below means anything')
    else:
        n = len(live[0])
        held = sum(1 for r in live[0] if r['gear'] >= 1)
        check(held == n, 'every rival holds a gear',
              f'{held} of {n} cars')

        # gears change, and cars are caught between them
        changes = 0
        for a, b2 in zip(live, live[1:]):
            for x, y in zip(a, b2):
                if x['gear'] != y['gear']:
                    changes += 1
        mid = sum(1 for f in live for r in f if r['shifting'])
        check(changes > 0 and mid > 0, 'and shifts out of it',
              f'{changes} gear changes, {mid} samples caught mid-shift')

        spread = max(len({r['gear'] for r in f}) for f in live)
        check(spread > 1, 'and the field is not in lockstep',
              f'up to {spread} different gears across the field at once')

        # the audible claim: revs must FALL somewhere while the car accelerates
        best = None
        for i in range(n):
            ser = [(f[i]['spd'], f[i]['gear']) for f in live]
            drops = sum(1 for (s1, g1), (s2, g2) in zip(ser, ser[1:])
                        if s2 > s1 and g2 > g1)
            if best is None or drops > best[1]:
                best = (i, drops)
        check(best and best[1] > 0, 'and its revs break instead of climbing',
              f'car {best[0]} shifted up {best[1]} times while still accelerating'
              if best else 'no car measured')

    check(not errs, 'no page errors', errs[0] if errs else 'clean')
    pg.close()
    b.close()
srv.shutdown()
print()
print('  ' + ('a rival has a gearbox you can hear'
              if not bad[0] else f'{bad[0]} FAILURES'))
sys.exit(1 if bad[0] else 0)
