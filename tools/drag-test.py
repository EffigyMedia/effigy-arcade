#!/usr/bin/env python3
"""DRAG TEST - one mile, one rival in the same car, forced manual, a best time per car.

    .venv/Scripts/python tools/drag-test.py

RLG-156. The owner's shape (2026-09-05 and 2026-09-19): an empty straight highway, one mile, two of
the same car, forced manual, open from the start on every car, a rival driver drawn at random each
race, and the player's best time kept per car.

WHAT IT ASSERTS:
  . the MODE control ends on DRAG RACE for a production car, a supercar and a police car - every
    car the garage lists (a work vehicle cannot be picked, RLG-249);
  . a drag race starts from rest, with the gearbox MANUAL although the player's setting is AUTO;
  . the road is straight and flat for the whole mile, and holds no traffic, no police and no clock;
  . there is one rival, in the same body and a different paint, level with the player;
  . the race ends at the mile on its own card, with both times; the best is saved per car, and the
    launcher's best-distance label is left alone;
  . back in the garage the player's own gearbox setting is back;
  . the driver decides: the same car with a SHARP driver beats it with a SLOPPY one.
The player is driven from inside the page: throttle held, and a change up at the top of each gear's
band, placed through the gate's own `placeKnob` (API.putGear). Shifting well is not what is tested.

WHAT IT CANNOT SEE: how a drag race feels, and whether the rival's misses read as a driver. The
owner's call.

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


# THE PLAYER, DRIVEN IN THE PAGE. One round trip a frame from Python is slower than the engine, so a
# mile took minutes; this runs on the page's own frames and Python only reads the result.
DRIVER = """() => {
  const R = window.__probe.road;
  if (window.__dragDrive) cancelAnimationFrame(window.__dragDrive);
  const tick = () => {
    const d = R.drag();
    if (d.finished) { window.__dragDrive = null; return; }
    R.gas(true);
    const g = R.gate().gear;
    if (g === 0) R.putGear(1); else if (R.shiftDue()) R.putGear(g + 1);
    window.__dragDrive = requestAnimationFrame(tick);
  };
  window.__dragDrive = requestAnimationFrame(tick);
}"""


def mode_walk(pg, body, n=6):
    # from TEST DRIVE, so a walk is not started wherever the last one left the shared setting
    set_mode(pg, body, 'TEST DRIVE')
    seen = []
    for i in range(n):
        lab = pg.evaluate("() => (document.querySelector('#veil [data-act=\"mode\"] b') || {}).textContent || null")
        seen.append(lab)
        if lab is None or i == n - 1:
            break
        pg.click('#veil [data-act="mode"]')
        pg.wait_for_timeout(120)
    return seen


def set_mode(pg, body, want):
    pg.evaluate("(k) => { const R = window.__probe.road; R.setBody(k); R.showGarage(); }", body)
    pg.wait_for_timeout(250)
    garage_screen(pg, 'main')
    for _ in range(6):
        lab = pg.evaluate("() => (document.querySelector('#veil [data-act=\"mode\"] b') || {}).textContent || null")
        if lab == want:
            return True
        pg.click('#veil [data-act="mode"]')
        pg.wait_for_timeout(120)
    return False


def wait_for(pg, expr, limit_s):
    t0 = time.time()
    while time.time() - t0 < limit_s:
        v = pg.evaluate(expr)
        if v:
            return v
        pg.wait_for_timeout(400)
    return None


s = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = s.server_address[1]
threading.Thread(target=s.serve_forever, daemon=True).start()
print('drag-test  .  one mile, one rival in the same car, forced manual')
with sync_playwright() as p:
    b = launch_chromium(p, headless=True, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]')
    # the supercar and the police car are won in a real save; a fresh one has only production cars
    pg.evaluate("() => window.Arcade.save.merge('interstate-opts', { super:true, cruiser:true, manual:false })")
    label_before = pg.evaluate("() => (window.Arcade.save.get('interstate') || {}).label || null")

    # ---- THE MODE CONTROL --------------------------------------------------------------------
    print('  the mode control')
    for body, want in (('HATCH', ['TEST DRIVE', 'SINGLE RACE', 'TOURNAMENT', 'DRAG RACE', 'TEST DRIVE']),
                       ('MATADOR', ['TEST DRIVE', 'SINGLE RACE', 'TOURNAMENT', 'DRAG RACE', 'TEST DRIVE']),
                       ('CRUISER', ['TEST DRIVE', 'INTERCEPT', 'INTERCEPT TOURNAMENT', 'DRAG RACE', 'TEST DRIVE'])):
        got = mode_walk(pg, body, len(want))
        print('      %-8s %s' % (body, ' -> '.join(map(str, got))))
        check(got == want, '%s: MODE walks round to DRAG RACE and back' % body, repr(got))

    # ---- A RACE --------------------------------------------------------------------------------
    print('  a race')
    check(set_mode(pg, 'HATCH', 'DRAG RACE'), 'DRAG RACE can be chosen on the HATCH')
    pg.click('#veil [data-act="drive"]')
    pg.wait_for_timeout(250)
    d0 = pg.evaluate("() => window.__probe.road.drag()")
    bends = pg.evaluate("() => window.__probe.road.dragBends()")
    check(d0['on'] and d0['racers'] == 1, 'the race has one rival', '%d' % d0['racers'])
    r0 = d0['rival'] or {}
    print('      rival: %s in %s, driver %s' % (r0.get('body'), r0.get('paint'), r0.get('driver')))
    mine = pg.evaluate("() => window.__probe.road.paint()")
    check(r0.get('body') == 'HATCH' and r0.get('paint') not in (None, mine),
          'and it is the same car in another paint', '%s in %s, the player in %s'
          % (r0.get('body'), r0.get('paint'), mine))
    check(abs(r0.get('z', 0) - d0['playerZ']) < 1 and abs(r0.get('x', 0) - d0['playerX']) > 0.3,
          'level with the player, in the next lane', 'z %.0f vs %.0f, x %.2f vs %.2f'
          % (r0.get('z', 0), d0['playerZ'], r0.get('x', 0), d0['playerX']))
    check(d0['pos'] == 0 and r0.get('spd') == 0, 'from rest', 'pos %s, rival speed %s' % (d0['pos'], r0.get('spd')))
    check(d0['manual'] and d0['kept'] is False,
          'with the gearbox MANUAL, though the player\'s own setting is AUTO', 'manual %s, kept %s' % (d0['manual'], d0['kept']))
    check(bends['maxCurve'] == 0 and bends['maxGrade'] == 0, 'on a road straight and flat for the whole mile',
          repr(bends))
    check(not d0['clock'] and d0['wet'] == 0, 'with no clock and a dry road', 'clock %s, wet %s' % (d0['clock'], d0['wet']))

    pg.evaluate(DRIVER)
    busiest = {'traffic': 0, 'cops': 0}
    t0 = time.time()
    while time.time() - t0 < 360:
        d = pg.evaluate("() => window.__probe.road.drag()")
        busiest['traffic'] = max(busiest['traffic'], d['traffic'])
        busiest['cops'] = max(busiest['cops'], d['cops'])
        if d['finished']:
            break
        pg.wait_for_timeout(500)
    check(busiest['traffic'] == 0 and busiest['cops'] == 0, 'and nothing else on the road all the way',
          repr(busiest))
    check(d['finished'], 'the race ends', 't %.1f s' % d['t'])
    over = d['pos'] - d['finishZ']
    check(0 <= over < 1500, 'at the mile', 'the car stopped being raced %.0f units past the line' % over)
    card = wait_for(pg, "() => { const v = document.querySelector('#veil:not(.hidden)');"
                        " return v && /DRAG RACE/.test(v.innerText) ? v.innerText : null; }", 10) or ''
    res = pg.evaluate("() => window.__probe.road.drag().result") or {}
    print('      you %.3f s, rival %s%.3f s (%s), best %.3f s'
          % (res.get('mine', -1), '~' if res.get('est') else '', res.get('theirs') or -1,
             res.get('driver'), res.get('best', -1)))
    check(('YOU WIN' in card or 'YOU LOSE' in card) and 'YOUR TIME' in card and 'RIVAL' in card,
          'on its own card, with the result and both times', card.replace('\n', ' / ')[:120])
    check(abs(res.get('mine', 0) - d['t']) < 0.05 and res.get('theirs'),
          'and the times are the race\'s own', '%s against %s' % (res.get('mine'), d['t']))
    best = pg.evaluate("() => window.Arcade.save.get('interstate-drag') || {}")
    check(abs(best.get('HATCH', 0) - res.get('mine', -1)) < 0.002, 'the best is kept for the HATCH', repr(best))
    label_after = pg.evaluate("() => (window.Arcade.save.get('interstate') || {}).label || null")
    check(label_after == label_before, 'and the launcher\'s best-distance label is left alone',
          '%r then %r' % (label_before, label_after))
    pg.click('#veil [data-act="garage"]')
    pg.wait_for_timeout(300)
    after = pg.evaluate("() => window.__probe.road.drag()")
    check(after['manual'] is False and after['kept'] is None,
          'back in the garage the player\'s own gearbox is back', 'manual %s' % after['manual'])

    # ---- THE DRIVER DECIDES ------------------------------------------------------------------
    # The player sits on the line and the rival runs alone, so its time is its own - once with the
    # best driver in the table and once with the worst.
    print('  the driver decides')
    times = {}
    for name in ('SHARP', 'SLOPPY'):
        pg.evaluate("(n) => window.__probe.road.dragDriver(n)", name)
        set_mode(pg, 'HATCH', 'DRAG RACE')
        pg.click('#veil [data-act="drive"]')
        t = wait_for(pg, "() => { const d = window.__probe.road.drag(); return d.rival && d.rival.time; }", 360)
        rv = pg.evaluate("() => window.__probe.road.drag().rival") or {}
        times[name] = t
        print('      %-6s rival ran the mile in %s s, changing at %.2f of each band, %d changes'
              % (name, t and '%.3f' % t, rv.get('shiftAt') or 0, rv.get('shifts') or 0))
        pg.evaluate("() => { const R = window.__probe.road; R.dragDriver(null); R.showGarage(); }")
        pg.wait_for_timeout(300)
    check(times['SHARP'] and times['SLOPPY'] and times['SLOPPY'] > times['SHARP'] + 0.2,
          'the same car is slower with a sloppy driver than a sharp one',
          '%s against %s' % (times['SLOPPY'], times['SHARP']))

    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
