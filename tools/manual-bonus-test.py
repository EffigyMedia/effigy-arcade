#!/usr/bin/env python3
"""MANUAL BONUS TEST - working the gate is worth a little pull and a little top end.

    .venv/Scripts/python tools/manual-bonus-test.py

RLG-294. Owner, 2026-09-20: "I think we should slightly bump the acceleration and top speed of every
car when manual transmission is being used." The bonus belongs to the CHOICE, not to any body, so it
is measured as the same car driven twice - once on the automatic and once through the gate.

MEASURED AGAINST THE SAME RUN WITH THE BONUS OFF, not against the automatic. In manual the speed is
capped by the gear the car is in, and a car with fewer gears tops out below its declared figure
whatever the bonus is - the HATCH reaches 0.966 of its own top end in fourth. So comparing the two
gearboxes measures the gear table, not the bonus. `API.manualBonus` sets the two numbers live, and
each run is driven twice: once at 1.0 and 1.0, once at the committed defaults.

WHAT IT ASSERTS:
  . on the manual, the bonus lifts the speed the car settles at, by about what it says;
  . and it gets there sooner, which is the pull half of it;
  . on the AUTOMATIC nothing moves, because the bonus belongs to the choice.
The manual run is driven from inside the page - throttle held, a change up at the top of each gear's
band through the gate's own `placeKnob` - because a car left in first reaches nothing.

WHAT IT CANNOT SEE: whether the bonus feels like enough. The owner's, and the numbers are tunable.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, functools, http.server, socketserver, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
INIT = (ROOT / 'tools' / 'collide-test.py').read_text(encoding='utf-8').split('INIT = r"""')[1].split('"""')[0]
from harness import console_utf8, launch_chromium, boot, until, garage_screen
from playwright.sync_api import sync_playwright
console_utf8()

fails = []


def check(ok, label, detail=''):
    print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label, '   ' + detail if detail else ''))
    if not ok:
        fails.append(label)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


# hold the throttle, and on the manual change up at the top of each band
RUN = """(manual) => {
  const R = window.__probe.road;
  if (window.__mb) cancelAnimationFrame(window.__mb);
  window.__mbTop = 0; window.__mbTo90 = null;
  const t0 = R.simTime ? R.simTime() : null;
  /* four fifths of THIS car's own top end: a mark it reaches on any gearbox */
  const mark = R.MAX_SPD * R.BODY[R.bodyKey()].vmax * 0.80;
  const tick = () => {
    R.gas(true);
    R.clearTraffic();               /* an empty road, so a run is not timing a queue */
    if (manual) { const g = R.gate().gear; if (g === 0) R.putGear(1); else if (R.shiftDue()) R.putGear(g + 1); }
    const v = R.spdNow();
    if (v > window.__mbTop) window.__mbTop = v;
    if (window.__mbTo90 === null && v >= mark && t0 !== null && R.simTime)
      window.__mbTo90 = +(R.simTime() - t0).toFixed(3);
    window.__mb = requestAnimationFrame(tick);
  };
  window.__mb = requestAnimationFrame(tick);
}"""


def run_of(pg, body, manual, seconds, bonus):
    """Drive `body` for `seconds`, with the bonus set to `bonus`, and report what it did."""
    pg.evaluate("(b) => window.__probe.road.manualBonus(b[0], b[1])", bonus)
    pg.evaluate("() => { const R = window.__probe.road; R.showGarage(); }")
    pg.wait_for_timeout(200)
    garage_screen(pg, 'settings')
    for _ in range(3):
        lab = pg.evaluate("() => (document.querySelector('#veil [data-act=\"box\"] b') || {}).textContent")
        if (lab or '').strip() == ('MANUAL' if manual else 'AUTO'):
            break
        pg.click('#veil [data-act="box"]')
        pg.wait_for_timeout(150)
    garage_screen(pg, 'main')
    pg.evaluate("(k) => { const R = window.__probe.road; R.setBody(k); R.showGarage(); }", body)
    pg.wait_for_timeout(200)
    garage_screen(pg, 'main')
    pg.click('#veil [data-act="drive"]')
    pg.wait_for_timeout(600)
    pg.evaluate(RUN, manual)
    t0 = time.time()
    while time.time() - t0 < seconds:
        pg.wait_for_timeout(1000)
    out = pg.evaluate("""() => { const R = window.__probe.road;
        return { top: window.__mbTop, to90: window.__mbTo90,
                 vmax: R.MAX_SPD * R.BODY[R.bodyKey()].vmax,
                 gear: R.gate().gear, manual: R.gate().manual }; }""")
    pg.evaluate("() => { if (window.__mb) cancelAnimationFrame(window.__mb); window.__mb = null; }")
    return out


s = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = s.server_address[1]
threading.Thread(target=s.serve_forever, daemon=True).start()
print('manual-bonus-test  .  the gate is worth a little pull and a little top end')
with sync_playwright() as p:
    b = launch_chromium(p, headless=True, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]')
    pg.evaluate("() => window.Arcade.save.merge('interstate-opts', { super:true })")
    OFF, ON = [1.0, 1.0], None
    ON = pg.evaluate("() => { const b = window.__probe.road.manualBonus(); return [b.accel, b.top]; }")
    print('      the committed bonus is %.2f of pull and %.2f of top end' % (ON[0], ON[1]))
    # A RUN THAT NEVER REACHED ITS CEILING IS NOT EVIDENCE. A car that meets something, or
    # goes off the road, settles low and says nothing about the gearbox - measured, one run
    # in several reads a few per cent under while the rest agree to four decimals. So a run
    # short of what that gearbox can do is DRIVEN AGAIN, and the best of them is taken.
    def best_run(body, manual, bonus, want):
        best = None
        for _ in range(3):
            r = run_of(pg, body, manual, 60, bonus)
            if best is None or r['top'] > best['top']:
                best = r
            if r['top'] / r['vmax'] >= want - 0.004:
                break
        return best

    man_off = best_run('HATCH', True, OFF, 1.0)
    man_on = best_run('HATCH', True, ON, ON[1])
    auto_off = best_run('HATCH', False, OFF, 1.0)
    auto_on = best_run('HATCH', False, ON, 1.0)
    for n, r in (('manual, no bonus', man_off), ('manual, bonus', man_on),
                 ('auto, no bonus', auto_off), ('auto, bonus', auto_on)):
        print('      %-18s settled at %.4f of its top end, reached the mark in %s s'
              % (n, r['top'] / r['vmax'], r['to90']))
    check(man_on['manual'] and man_on['gear'] > 1, 'the manual runs really worked the gate',
          'gear %s' % man_on['gear'])
    lift = man_on['top'] / man_off['top']
    check(abs(lift - ON[1]) < 0.004, 'the bonus lifts the speed a manual car settles at, by what it says',
          '%.4f against %.2f' % (lift, ON[1]))
    # BY A MARGIN, not merely sooner. With the bonus removed the two runs came out 0.06 s
    # apart and this passed on the noise; the real gain measured 0.55 s.
    check(man_off['to90'] and man_on['to90'] and man_on['to90'] < man_off['to90'] - 0.25,
          'and it gets there sooner, which is the pull half of it',
          '%s s with it, %s s without' % (man_on['to90'], man_off['to90']))
    # THE AUTOMATIC IS COMPARED ON ITS TIME TO THE MARK, not on where it settled: a run that
    # meets something and never reaches its top end reads low, and that is the road rather than
    # the gearbox. The mark is passed in the first dozen seconds, before anything is met.
    check(abs(auto_on['to90'] - auto_off['to90']) < 0.25,
          'and the automatic is untouched by it, because the bonus is the choice',
          '%s s with it, %s s without' % (auto_on['to90'], auto_off['to90']))
    check(abs(auto_on['top'] / auto_on['vmax'] - 1) < 0.004,
          'and an automatic run still settles at its declared top end',
          '%.4f' % (auto_on['top'] / auto_on['vmax']))
    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
