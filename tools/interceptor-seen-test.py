#!/usr/bin/env python3
"""INTERCEPTOR SEEN - a dispatched Interceptor comes close enough to be seen.

    .venv/Scripts/python tools/interceptor-seen-test.py

RLG-248. Owner, 2026-09-14: "when an interceptor is dispatched I never see it."

WHAT WAS MEASURED BEFORE THE FIX. At a held 180mph with heat 5 and the trap condition met, the road
dispatched fifteen Interceptors in thirty seconds. Every one entered 9,000 to 16,000 units behind
the player and stayed 8,000 to 33,000 units behind, and most were culled at 34,000 after a second or
two. The car is dispatched only at 150mph or more and it is a 190mph car, so from that far back it
closes slowly or not at all, and traffic makes it lift.

WHAT THIS READS. A car behind the player can only be seen in the mirror, so this reads the mirror's
own record of each Interceptor it drew and how wide it drew it, in canvas pixels. The forward view's
draw ledger cannot answer this: it never draws a car that is behind.

Two arms, run in the same page:

  OLD   the spawn band put back to 9,000-16,000 through `API.superBack`
  NEW   the band the build ships

Each arm holds 170mph for twenty seconds from an empty road. A dispatch counts as SEEN when the
mirror draws that car at least SEEN_PX wide. NEW must see most of its dispatches, and OLD must see
fewer than half of its own. OLD is the falsifier: if OLD also sees its dispatches, the check cannot
tell the defect from the fix, and it fails.

WHAT THE FIX DOES NOT CHANGE. An Interceptor is still a 190mph car. A player holding more than that
still pulls away from it, and at 170 to 180 most of them still drop back after they are seen. That is
the owner's rule for this car, and this file does not assert that one catches the player.

WHAT THIS CANNOT SAY. It reads the canvas, not a phone. Whether a car of this width reads as an
Interceptor at a glance, in the owner's mirror, is the owner's verdict on the device.

Exit code 0 if every check passed, 1 otherwise.
"""
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until, garage_screen  # noqa: E402

GAME = 'games/sw/interstate.html'
MPH = 170
SECS = 20
# THE MIRROR WIDTH AT WHICH A CAR IS CALLED SEEN. The mirror is 340 px wide. On the first
# measured run the old band drew its Interceptors at most 10 to 16 px wide - a smudge about
# 4 % of the glass - and the shipped band drew them 36 to 130 px wide. 24 px, 7 % of the glass,
# sits between the two. It was chosen after that run, so it is stated here rather than implied.
SEEN_PX = 24
OLD_BAND = (9000, 16000)

INIT = r"""
window.__probe = { errors: [], road: null };
(function(){ var real = null, wrapped = null;
  Object.defineProperty(window, 'ROAD', { configurable: true,
    get: function(){ return real ? wrapped : undefined; },
    set: function(fn){ real = fn; wrapped = function(CFG){ var a = real(CFG);
      window.__probe.road = a || (CFG && CFG.api) || null; return a; }; } });
})();
window.addEventListener('error', function(e){ window.__probe.errors.push(String(e.message)); });
"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    console_utf8()
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('interceptor-seen  .  a dispatched Interceptor comes close enough to see')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900},
                           has_touch=True, is_mobile=True).new_page()
        pg.add_init_script(INIT)
        boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(pg, '!!window.__probe.road', timeout=10000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        # the drive's settings are on the SETTINGS screen (RLG-071)
        garage_screen(pg, 'settings')
        pg.click('[data-act="chase"]')      # HOT PURSUIT on, or nothing is dispatched
        garage_screen(pg, 'main')
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__probe.road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => window.__probe.road.setTimed(false)')
        shipped = pg.evaluate('() => window.__probe.road.superBack()')
        print('      the shipped band is %d-%d units behind; the old band was %d-%d'
              % (shipped[0], shipped[1], OLD_BAND[0], OLD_BAND[1]))

        def arm(name, band):
            pg.evaluate('(b) => window.__probe.road.superBack(b[0], b[1])', list(band))
            pg.evaluate('(v) => { const R = window.__probe.road; R.copsClear();'
                        ' R.heat(5); R.earnSupers(true); R.holdSpd(R.MAX_SPD*v);'
                        ' R.watchDraw(1); R.mirrorSupers(true); R.clearCopOrigins(); }', MPH / 200.0)
            widest, mirror = {}, 0
            for _ in range(SECS * 4):
                pg.wait_for_timeout(250)
                # the glass tags each draw with the car it drew, so a width is never
                # credited to a different Interceptor
                for d in pg.evaluate('() => window.__probe.road.mirrorSupers(true)'):
                    widest[d['vid']] = max(widest.get(d['vid'], 0.0), d['w'])
                    mirror = d['mw']
            pg.evaluate('() => window.__probe.road.holdSpd(null)')
            born = [o['dz'] for o in pg.evaluate('() => window.__probe.road.copOrigins()')
                    if o['from'] == 'super']
            # a dispatch the glass never drew at all is in `born` and not in `widest`
            for i in range(len(born) - len(widest)):
                widest['never-%d' % i] = 0.0
            seen = sum(1 for w in widest.values() if w >= SEEN_PX)
            print('      %-3s the mirror is %d px wide' % (name, mirror))
            print('      %-3s %d dispatched, entering %s to %s units back; %d seen at %d px or more;'
                  ' widest %s' % (name, len(widest), min(born) if born else '-',
                                  max(born) if born else '-', seen, SEEN_PX,
                                  sorted(round(w, 1) for w in widest.values())))
            return len(widest), seen

        old_n, old_seen = arm('OLD', OLD_BAND)
        new_n, new_seen = arm('NEW', shipped)
        pg.evaluate('(b) => window.__probe.road.superBack(b[0], b[1])', shipped)

        ok(old_n >= 3 and new_n >= 3, 'both arms dispatched Interceptors',
           'OLD %d, NEW %d' % (old_n, new_n))
        ok(new_seen * 2 > new_n, 'most dispatched Interceptors are seen in the mirror',
           '%d of %d' % (new_seen, new_n))
        ok(old_seen * 2 < old_n,
           'and with the old band put back, fewer than half are seen, so the check can fail',
           'OLD %d of %d seen - the check cannot tell the defect from the fix' % (old_seen, old_n))
        errs = pg.evaluate('() => window.__probe.errors')
        ok(not errs, 'no page errors', str(errs))
        b.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(fails)) if fails else '\na dispatched Interceptor is seen')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
