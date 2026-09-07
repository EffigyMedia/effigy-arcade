"""DAMAGE IS A FACTOR OF WHICH END TOOK THE HIT.

    .venv/Scripts/python tools/impact-test.py

Owner, 2026-09-06: "I think damage earned should be a factor of the direction damage is from.
If you have a front impact it's the worst, followed by side impacts. Then finally impact to
your rear is the least damaging."

THE ORDERING IS THE RULING; the three numbers are tuning. So this asserts the ORDER and the
shape, and prints the numbers rather than pinning them - a check that fixed them at 1.00, 0.55
and 0.30 would fail the first time the owner asked for a different balance, which is not a
defect.

  1. FRONT > SIDE > REAR, which is the ruling stated directly.
  2. IT BLENDS. A car sliding from alongside to in line must not step: half-square must sit
     between the side value and the end value, at both ends.
  3. ONE COLLISION SCORES THE TWO CARS DIFFERENTLY. This is the part that is easy to get
     wrong and easy to fake. If you run into the back of a rival, that is YOUR FRONT and
     THEIR REAR - the worst hit on the road for you and the cheapest for them, out of one
     impact. The two numbers must not be equal, and yours must be the larger.

CHECK 3 GOES THROUGH THE REAL `impactWith`. It cannot be tested by calling the function twice
and comparing, because `impactWith` MOVES BOTH CARS as well as scoring the hit - the second
call would read speeds the first had already changed. `API.probeImpact` runs it once against a
throwaway car, reads both severities from that one call, and restores the player afterwards.

WHAT THIS CANNOT SAY: whether the balance is right. Whether a rear-ending should cost 30% of
what a head-on does is a judgement about how the game plays, and only a device can answer it.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, threading, http.server, socketserver, functools

from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
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


with sync_playwright() as p:
    b = launch_chromium(p, headless=True, args=['--mute-audio'])
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(f'http://127.0.0.1:{PORT}/games/sw/interstate.html', wait_until='load')
    pg.wait_for_function("() => window.__road && window.__road.hitFactor", timeout=15000)

    f = lambda sq, nose: pg.evaluate(
        "([s, n]) => window.__road.hitFactor(s, n)", [sq, nose])
    front, side, rear = f(1, True), f(0, True), f(1, False)
    tun = pg.evaluate("() => window.__road.impactTunables()")

    print()
    check(front > side > rear, 'front hurts most, then side, then rear',
          f'front {front}, side {side}, rear {rear}')

    hf, hr = f(0.5, True), f(0.5, False)
    check(side < hf < front and rear < hr < side,
          'and it blends rather than stepping',
          f'half-square front {hf} sits between {side} and {front}; '
          f'half-square rear {hr} between {rear} and {side}')

    check(abs(f(0, True) - f(0, False)) < 1e-9,
          'a fully sideways hit has no end at all',
          f'front-on-side {f(0, True)} equals rear-on-side {f(0, False)}')

    # ---- one collision, two different answers -------------------------------
    # dz > 0: the other car is AHEAD, so this is the player's front and its rear
    ahead = pg.evaluate("() => window.__road.probeImpact(300, 0)")
    behind = pg.evaluate("() => window.__road.probeImpact(-300, 9000)")

    check(ahead and ahead['mine'] > ahead['theirs'],
          'running into a car costs you more than it',
          f"you {ahead['mine']}, them {ahead['theirs']}" if ahead else 'no reading')
    check(behind and behind['theirs'] > behind['mine'],
          'and being run into costs you less than them',
          f"you {behind['mine']}, them {behind['theirs']}" if behind else 'no reading')

    check(not errs, 'no page errors', errs[0] if errs else 'clean')
    pg.close()
    b.close()
srv.shutdown()
print()
print(f'  tunables: front {tun["front"]}, side {tun["side"]}, rear {tun["rear"]} '
      '- the ORDER is the ruling, the numbers are the owner\'s to tune')
print('  ' + ('damage knows which end took it'
              if not bad[0] else f'{bad[0]} FAILURES'))
sys.exit(1 if bad[0] else 0)
