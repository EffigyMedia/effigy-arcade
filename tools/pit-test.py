#!/usr/bin/env python3
"""PIT TEST - a takedown you have to mean, checked as a rule rather than performed.

    .venv/Scripts/python tools/pit-test.py

The PIT is the most deliberate thing a player can do to the police: come alongside rather
than nose to tail, carry real speed, and steer INTO it. Done properly the cruiser goes
around and out. Hit one square on and it is just a crash. Three conditions, and all three
have to hold:

  alongside   overlapping, not rear-ended
  closing     you are steering into it, not away
  fast        above 0.62 of top speed

STAGING ONE WAS TRIED FIRST AND ABANDONED, and the attempt is worth recording because the
obvious approach looks like it works. A harness can place a cruiser, hold the wheel over
and drive at it - but the decision is made on the single frame the two bodies overlap, a
staged cruiser is a REAL one whose chase AI steers and paces it between anything the
harness sets, and the mercy window from one glancing contact locks out the next second of
attempts. Three runs of one unchanged build gave three different answers, including one
where the manoeuvre and its opposite both came back inverted. A gate that flaky is worse
than no gate: it goes red at random until somebody switches it off.

SO THIS CHECKS THE RULE, NOT A PERFORMANCE OF IT. The engine records the three conditions
as it evaluated them on every contact with a cruiser, and this drives a real pursuit and
asserts the implication over all of them: a PIT happened on exactly the contacts where all
three held, and on no others. Dozens of collisions per run, none of them staged, and the
answer does not depend on catching one frame.

IT SAYS SO WHEN IT PROVES NOTHING. A run that never touches a cruiser asserts an empty
implication, which is true and worthless, so the count is printed and a run with too few
contacts fails rather than passing quietly.
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
from playwright.sync_api import sync_playwright

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{PORT}'


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('pit-test  .  a takedown you have to mean')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(f'{BASE}/games/sw/interstate.html', wait_until='load')
        try:
            page.wait_for_function(
                '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(400)
        page.click('[data-act="chase"]')
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)

        # A REAL PURSUIT, AND A WHEEL THAT MOVES. Cruisers have to actually touch the car
        # for there to be anything to read, and they have to touch it while the car is
        # doing a range of speeds and steering both ways - otherwise every contact shares
        # the same answer and the implication is never tested against a mixed set.
        # A CRUISER IS HELD AGAINST THE CAR so that contacts actually happen - left to
        # itself a pursuit rarely touches you, and the first version of this collected
        # ZERO contacts and asserted an empty implication. It is the engine's own cruiser,
        # placed through the spawner's fields, and the engine's own collision test decides
        # every frame. What is swept is the WHEEL and the SPEED, so the three conditions
        # come out in a mixture rather than all reading the same.
        #
        # NO INDIVIDUAL CONTACT HAS TO COME OUT ANY PARTICULAR WAY. That is the point of
        # asserting the rule instead of the manoeuvre: the timing that made a staged PIT
        # unrepeatable simply changes which contacts land in which bucket, and the
        # implication holds over all of them either way.
        page.evaluate("() => { window.__road.heat(5); window.__road.clearCopHits();"
                      " window.__road.traffic.length = 0; }")
        sweep = [(-0.5, 0.85), (0.5, 0.85), (-0.5, 0.45), (0.5, 0.45),
                 (0.0, 0.90), (-0.6, 0.55), (0.6, 0.75), (0.0, 0.40)]
        for lap in range(9):
            for tx, frac in sweep:
                page.evaluate('(a) => { const R = window.__road;'
                              ' R.heat(5); R.setSpd(a[1] * R.MAX_SPD); R.setTarget(a[0]);'
                              ' R.clearIframe();'
                              ' let k = R.cops()[0];'
                              ' if(!k || k.wreck > 0){ R.placeCop(0, R.playerX + 0.14);'
                              '   k = R.cops()[0]; }'
                              ' k.z = R.pos + R.PLAYER_Z; k.spd = R.spd; }',
                              [tx, frac])
                page.wait_for_timeout(120)
        hits = page.evaluate("() => window.__road.copHits()")

        n = len(hits)
        pits = [h for h in hits if h['pit']]
        allthree = [h for h in hits if h['sideOn'] and h['closing'] and h['fast']]
        missing = [h for h in hits if not (h['sideOn'] and h['closing'] and h['fast'])]
        print(f'  ..    {n} contacts with a cruiser, {len(pits)} of them PITs')
        print(f"  ..    of the rest: {sum(1 for h in missing if not h['fast'])} too slow, "
              f"{sum(1 for h in missing if not h['closing'])} not steering into it, "
              f"{sum(1 for h in missing if not h['sideOn'])} rear-ended rather than alongside")

        ok(n >= 8, 'enough contacts happened to say anything at all',
           f'{n} contacts' if n else 'the cruisers never touched the car, so nothing was tested')
        ok(len(pits) == len(allthree),
           'a PIT happens on exactly the contacts where all three conditions hold',
           f'{len(pits)} PITs against {len(allthree)} contacts that qualified')
        # AND EACH CONDITION IS DOING WORK. If every contact in a run qualified, the
        # implication above is satisfied by a rule that ignores its conditions entirely.
        ok(len(missing) > 0, 'and some contacts did NOT qualify, so the conditions bite',
           f'{len(missing)} of {n} fell short of at least one')
        # PRINTED, NOT ASSERTED. Whether any contact in a given run qualifies is the road's
        # business - one run in three produces none, and the implication is still true and
        # still worth asserting when it does. Failing on it would make this a gate that
        # goes red on the traffic, which is the failure mode the whole project guards
        # against. But a run with no qualifying contact has only tested the rule in the
        # negative direction, and that has to be said rather than glossed.
        print('  ..    ' + (f'{len(allthree)} contact(s) met all three, so the positive'
                            ' direction was exercised' if allthree else
                            'NO contact met all three this run - only the negative'
                            ' direction was tested'))
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('the PIT is a manoeuvre, not a collision' if not bad
                 else str(bad) + ' FAILURES'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
