#!/usr/bin/env python3
"""TRAP GAP - speed traps are laid a random 30 to 60 seconds apart, a little closer at high heat.

    .venv/Scripts/python tools/trap-gap-test.py
    .venv/Scripts/python tools/trap-gap-test.py --root <an older checkout> --expect-fail

RLG-261. Owner, 2026-09-15: "We need to make the interval between speed traps much longer. They have
way too frequently. It would never allow you to cool down. So let's make the interval way longer but
also a random range so it's not consistently a specific interval." The range is 30 to 60 seconds, and
a star takes a tenth off it, to half the range at five stars.

IT WATCHES THE ROAD LAY THEM. The player is held at 60 % of top speed, every frame is read for a trap,
and the police are then cleared - so what is measured is the timer rather than the road's stock of
traps. The gap between one arrival and the next is the measurement.

  CLEAN    at no heat, 150 seconds: every gap is 28 to 62 seconds.
  HOT      at five stars, 100 seconds: every gap is 13 to 32 seconds - the range halved, which is what
           five stars take off it, with the same slack the CLEAN arm gets.
  RANDOM   the gaps are not all the same length: the longest and the shortest differ by over 3
           seconds across the run. A fixed interval would pass the two above and fail this.

The heat is pinned every 250 ms, because driving over the limit earns more of it.

WHAT THIS CANNOT SAY. Whether a road with this many traps on it feels right, and whether the player
can now cool down in play, are the owner's verdict on the device.

Exit code 0 if every check passed (or, with --expect-fail, if one failed), 1 otherwise.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from harness import console_utf8, launch_chromium, boot, until, garage_screen  # noqa: E402

# when a trap arrives, in seconds from the start of the watch
WATCH = """(a) => {
  const R = window.__road;
  return new Promise((done) => {
    const at = [];
    const t0 = performance.now();
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      R.heat(a.heat);
      /* THE ROAD IS EMPTIED EVERY FRAME, and that is what makes this the TIMER's
         measurement. Left alone, two other things land in the cops array and read as
         a trap being laid: a cruiser that gives up parks and becomes a trap again,
         and the road stops laying them once its cap is parked - which skips a tick
         and doubles the gap. Measured with neither: gaps of 0.1 and 10.6 seconds. */
      for(const k of R.cops()) if(k.trap) at.push(+t.toFixed(2));
      R.copsClear();
      if(t < a.secs) requestAnimationFrame(tick); else done(at);
    };
    requestAnimationFrame(tick);
  });
}"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--expect-fail', action='store_true')
    args = ap.parse_args()
    console_utf8()
    root = Path(args.root)
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(root)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('trap-gap  .  speed traps are laid far apart, on a random interval')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        # the drive's settings are on the SETTINGS screen (RLG-071)
        garage_screen(pg, 'settings')
        pg.click('[data-act="chase"]')      # HOT PURSUIT on
        garage_screen(pg, 'main')
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => { const R = window.__road; R.setTimed(false); R.holdSpd(0.6 * R.MAX_SPD); }')

        every = []

        def arm(name, heat, secs, lo, hi):
            pg.evaluate('() => { const R = window.__road; R.copsClear(); }')
            at = pg.evaluate(WATCH, {'heat': heat, 'secs': secs})
            gaps = [round(b - a, 1) for a, b in zip(at, at[1:])]
            print('      %-6s traps laid at %s; gaps %s' % (name, at, gaps))
            every.extend(gaps)
            ok(len(gaps) >= 2, '%s: the road laid enough traps to measure a gap' % name,
               '%d laid in %ds' % (len(at), secs))
            ok(gaps and all(lo <= g <= hi for g in gaps), '%s: every gap is %d to %d seconds' % (name, lo, hi),
               'gaps %s' % gaps)

        arm('CLEAN', 0, 150, 28, 62)
        arm('HOT', 5, 100, 13, 32)

        ok(len(every) >= 2 and max(every) - min(every) > 3, 'the interval is random, not fixed',
           'the gaps ran %s' % sorted(every))
        pg.evaluate('() => window.__road.holdSpd(null)')
        ok(not errs, 'no page errors', errs[0][:120] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if args.expect_fail:
        print('expected at least one failure: %s' % ('got %d' % len(fails) if fails else 'got NONE'))
        return 0 if fails else 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('speed traps are laid far apart, on a random interval')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
