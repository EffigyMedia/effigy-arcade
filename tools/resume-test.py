#!/usr/bin/env python3
"""RESUME TEST - coming back from a pause mid-run counts you in, with the world frozen.

    .venv/Scripts/python tools/resume-test.py

RLG-147. Owner, 2026-09-01: "Whenever you pause the game and you return during a run, we need a
new countdown." Decided 2026-09-19: the world stays FROZEN until GO, then the car carries on at the
speed it paused at; the count is three seconds, like the start line.

IT DRIVES THE REAL PAUSE BUTTON. The shell holds the game's animation frame back while paused and
tells the game through `Arcade.onResume` when it is handed back, so a check that set the engine's
count directly would skip the one link that can break - the shell's signal.

WHAT IT ASSERTS:
  . right after resuming, a three-second count is running;
  . while it runs, the car has not moved and its speed has not changed - the world is frozen;
  . after GO the count is over, the car is moving, and at about the speed it paused at.
AND THE CONTROL: pausing and resuming on the title screen, where there is no run, starts no count.
Without it, a count that fired on every resume - or at every frame - would pass the checks above.

WHAT IT CANNOT SEE: whether three seconds feels right. That is the owner's call on a device.

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


def check(ok, label, detail=''):
    print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label, '   ' + detail if detail else ''))
    if not ok:
        fails.append(label)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def line(pg):
    return pg.evaluate("() => { const R = window.__probe.road, s = R.startLine();"
                       " return { left: s.left, resuming: s.resuming, pos: s.pos, spd: s.spd }; }")


def press_pause(pg):
    """Pause with the title bar's button."""
    pg.click('.ark-btn')
    pg.wait_for_timeout(250)


def press_resume(pg):
    """Resume with the pause menu's RESUME - the menu covers the pause button while it is up."""
    pg.click('.ark-veil.on [data-a="resume"]')
    pg.wait_for_timeout(250)


s = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = s.server_address[1]
threading.Thread(target=s.serve_forever, daemon=True).start()
print('resume-test  .  a resume counts you back in, with the world frozen')
with sync_playwright() as p:
    b = launch_chromium(p, headless=True)
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)

    # ---- THE CONTROL FIRST: no run, no count --------------------------------------
    press_pause(pg)
    press_resume(pg)
    ctl = line(pg)
    check(not ctl['resuming'] and ctl['left'] <= 0,
          'resuming on the title screen starts no count', '%s' % ctl)

    # ---- A RUN AT SPEED -----------------------------------------------------------
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]')
    pg.click('[data-act="drive"]')
    until(pg, "() => window.__probe.road.startLine().left <= 0", timeout=10000, required=False)
    pg.evaluate("() => { const R = window.__probe.road; R.setTimed(false); R.clearTraffic();"
                " R.setSpd(R.MAX_SPD * 0.5); }")
    pg.wait_for_timeout(300)

    press_pause(pg)
    paused = line(pg)
    pg.wait_for_timeout(700)
    press_resume(pg)
    first = line(pg)
    print('      paused at pos %d, speed %d; resumed: count %.2f, holding %s'
          % (paused['pos'], paused['spd'], first['left'], first['resuming']))
    check(first['resuming'] and 2.4 < first['left'] <= 3.0,
          'resuming mid-run starts a three-second count', 'count %.2f' % first['left'])

    # ---- FROZEN WHILE IT COUNTS ---------------------------------------------------
    pg.wait_for_timeout(1500)
    mid = line(pg)
    check(abs(mid['pos'] - first['pos']) < 1 and abs(mid['spd'] - first['spd']) < 1,
          'while it counts, the car does not move and keeps its speed',
          'pos %d -> %d, speed %d -> %d' % (first['pos'], mid['pos'], first['spd'], mid['spd']))
    check(mid['resuming'] and mid['left'] < first['left'] - 1.0,
          'and the count is running down', '%.2f -> %.2f' % (first['left'], mid['left']))

    # ---- AND THEN IT CARRIES ON ---------------------------------------------------
    until(pg, "() => !window.__probe.road.startLine().resuming", timeout=6000, required=False)
    go = line(pg)
    pg.wait_for_timeout(400)
    after = line(pg)
    check(not go['resuming'], 'the count ends', '%s' % go)
    check(after['pos'] > go['pos'] + 100, 'and the car is moving again',
          'pos %d -> %d' % (go['pos'], after['pos']))
    check(abs(go['spd'] - paused['spd']) < paused['spd'] * 0.08,
          'at about the speed it paused at', 'paused %d, at GO %d' % (paused['spd'], go['spd']))

    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
