#!/usr/bin/env python3
"""RAGE TEST - a driver you anger comes after you, and what it tries depends on where it is.

    .venv/Scripts/python tools/rage-test.py

RLG-241. Owner, 2026-09-13: "if you piss off another driver they may try to run you down and
hit you." Answered 2026-09-16 on who rages, what angers them, what they do and how it ends.

RAGE IS A STATE OF THE DRIVER AND CANNOT BE SEEN. A car closing on you looks exactly the same
whether it is angry or merely faster, so every claim here is read off `API.ragers` rather than
inferred from a crash. That is the same reason RLG-252's spans are asserted as numbers.

  WHO RAGES      the odds follow the personality scale and a COMMUTER never does. Asserted on
                 the table AND by provoking a thousand drivers of each mind, because a table
                 nothing reads is the failure this engine has receipts on.

  WHAT THEY DO   the owner's own answer, and more than any option offered: they reach for the
                 overtake first, and "if they're not faster than you, they quickly give up on
                 that and do one of the others based position instead". So the move must
                 follow the POSITION - ahead is a brake-check, alongside is a swipe, behind is
                 a ram - and a driver that cannot get past must stop trying.

  HOW IT ENDS    it cools off, or you outrun it.

WHAT IT CANNOT SEE: whether being hunted is frightening or merely annoying, whether a
brake-check reads as malice or as traffic being bad, and whether the odds put one on you too
often. Owner's call on a device.
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
from harness import console_utf8, launch_chromium, boot, until

GAME = 'games/sw/interstate.html'

INIT = r"""
window.__probe = { errors: [], road: null };
(function(){
  var real = null, wrapped = null;
  Object.defineProperty(window, 'ROAD', {
    configurable: true,
    get: function(){ return real ? wrapped : undefined; },
    set: function(fn){
      real = fn;
      wrapped = function(CFG){
        var api = real(CFG);
        window.__probe.road = api || (CFG && CFG.api) || null;
        return api;
      };
    }
  });
})();
window.addEventListener('error', function(e){ window.__probe.errors.push(String(e.message)); });
"""

MINDS = {'COMMUTER': 0, 'SPEEDER': 1, 'OUTLAW': 2, 'RACER': 3}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


def main():
    console_utf8()
    fails = []

    def check(ok, label, detail=''):
        print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label,
                              '   ' + detail if detail else ''))
        if not ok:
            fails.append(label)

    httpd, port = serve(ROOT)
    print('rage-test  .  a driver you anger comes after you')
    print()
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=15000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1600)
        for _ in range(40):
            st = page.evaluate("() => window.__probe.road.startLine()")
            if st['left'] <= 0 and st['go'] <= 0:
                break
            page.wait_for_timeout(90)
        page.evaluate("() => window.__probe.road.setTimed(false)")

        # ---- WHO RAGES -----------------------------------------------------------
        print('  WHO RAGES, OVER 400 PROVOKED DRIVERS OF EACH MIND')
        odds = page.evaluate('() => window.__probe.road.ragers().odds')
        print('      the table: %s' % odds)
        # PROVOKED THROUGH THE ENGINE'S OWN ROLL, not by reading the table back. A check
        # that asked for the odds and then asserted the odds would agree with itself.
        got = page.evaluate("""(minds) => {
          const R = window.__probe.road, out = {};
          for(const name in minds){
            let raged = 0;
            for(let i = 0; i < 400; i++){
              R.clearTraffic();
              R.parkTraffic(0.5, 3000, 'sedan', minds[name]);
              R.angerFirst();
              if(R.ragers().raging.length) raged++;
            }
            out[name] = raged;
          }
          R.clearTraffic();
          return out;
        }""", MINDS)
        for name in ('COMMUTER', 'SPEEDER', 'OUTLAW', 'RACER'):
            print('      %-9s raged %3d of 400   (table says %.2f)'
                  % (name, got[name], odds[str(MINDS[name])]))
        check(got['COMMUTER'] == 0, 'a COMMUTER never rages',
              '%d of 400 did' % got['COMMUTER'])
        check(got['OUTLAW'] > got['SPEEDER'] > 0,
              'and the chance rises with lawlessness',
              'speeder %d, outlaw %d of 400' % (got['SPEEDER'], got['OUTLAW']))

        # ---- WHAT THEY DO, BY POSITION -------------------------------------------
        print()
        print('  AND WHAT THEY TRY FOLLOWS WHERE THEY ARE')

        def staged(dz, kind, secs=5.0):
            """park one car at a known offset, enrage it, and read the move it settles on

            THE VEHICLE IS WHAT MAKES IT SLOW, not a speed the harness sets. A rager
            drives at its own capability by design - RLG-241 caps it at TYPE_VMAX and
            nothing else - so `trafficSpeed` is overridden on the very next frame and a
            'slow' sedan passed the player exactly as a fast one did. A TRUCK tops out
            at 0.34 of MAX against a player doing 0.45, so it genuinely cannot get by.

            AND IT WATCHES LONG ENOUGH. The give-up timer is 3.2 seconds; a two-second
            observation ended while the driver was still legitimately trying.
            """
            page.evaluate("""([dz, kind]) => {
              const R = window.__probe.road;
              R.clearTraffic(); R.clearRacers();
              /* PINNED, NOT SET. `setSpd` is a value the engine moves on from - it
                 coasts down between the harness's pokes - so the player ended up
                 slower than a car doing a fifth of top speed and every staged
                 position inverted: a rager parked 2,200 behind finished 1,100 ahead
                 and every case read BLOCK. `holdSpd` pins it. */
              R.holdSpd(R.MAX_SPD * 0.45);
              R.parkTraffic(0, dz, kind, 2);
              R.enrage(0, 'test');
            }""", [dz, kind])
            seen = []
            last = []
            for _ in range(int(secs / 0.05)):
                page.evaluate("() => { const R = window.__probe.road;"
                              " R.holdSpd(R.MAX_SPD * 0.45); }")
                page.wait_for_timeout(50)
                r = page.evaluate('() => window.__probe.road.ragers().raging')
                if r:
                    seen.append(r[0])
                    last[:] = [r[0]]
            return seen, (last[0] if last else None)

        # ---- THE INVARIANT, NOT THE ENDING -------------------------------------
        # The first version asserted what a rager "settles on" after five seconds, and
        # it was asserting the wrong thing: an encounter MOVES. A truck alongside a
        # faster player cannot stay alongside, so it correctly becomes a RAM; a sedan
        # that gets in front and brake-checks pulls the player level with it, so it
        # correctly becomes a SWIPE. Both were the code being right and the check being
        # written against a snapshot.
        #
        # WHAT IS ACTUALLY RULED is that the move follows the POSITION at the time, so
        # that is what is asserted - every sampled frame, against the offset on that
        # frame. The bands are generous by RAGE_LOOK's worth of travel, because the move
        # is re-picked a couple of times a second and a car crossing a boundary carries
        # the old choice until it is asked again.
        def band(dz):
            if dz > 900:
                return {'BLOCK', 'CUT'}
            if dz > -900:
                return {'SWIPE', 'BLOCK', 'RAM', 'CUT'}
            return {'RAM', 'CUT'}

        for label, dz0, kind in (('behind, in a truck', -2200, 'truck'),
                                 ('alongside, in a truck', 0, 'truck'),
                                 ('ahead of you', 2600, 'sedan')):
            seen, last1 = staged(dz0, kind)
            wrong = [f for f in seen if f['move'] not in band(f['dz'])]
            moves = sorted({f['move'] for f in seen})
            print('      %-22s moves %-28s %d of %d frames out of place'
                  % (label, str(moves), len(wrong), len(seen)))
            check(seen, 'a rager staged %s is on the road at all' % label,
                  '%d frames' % len(seen))
            check(not wrong,
                  'and every move it makes %s fits where it was' % label,
                  '%s' % (wrong[:2] if wrong else ''))

        # AND A DRIVER THAT CANNOT GET PAST STOPS TRYING, which is the half of the
        # owner's answer that stops every rager hanging off the bumper mid-overtake.
        seen, _ = staged(-2200, 'truck')
        cuts = sum(1 for f in seen if f['move'] == 'CUT')
        print('      a slower rager spent %d of %d frames still trying to pass'
              % (cuts, len(seen)))
        check(cuts < len(seen) * 0.5,
              'and one that cannot out-run you gives up on the overtake',
              '%d of %d frames still CUT' % (cuts, len(seen)))

        # ---- AND IT ENDS ---------------------------------------------------------
        print()
        print('  AND IT ENDS')
        page.evaluate("""() => { const R = window.__probe.road;
          R.clearTraffic(); R.holdSpd(R.MAX_SPD * 0.45);
          R.parkTraffic(0, -2000, 'sedan', 2);
          R.trafficSpeed(0, 0); R.enrage(0, 'test'); }""")
        # OUTRUN: the player drives off and the car is left standing.
        left = None
        for _ in range(90):
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.holdSpd(R.MAX_SPD * 0.95); R.trafficSpeed(0, 0); }")
            page.wait_for_timeout(50)
            r = page.evaluate('() => window.__probe.road.ragers()')
            if not r['raging']:
                left = True
                break
        check(left is True, 'outrunning a rager ends it',
              'it was still on the player after 4.5s of full throttle')

        errs = page.evaluate("() => window.__probe.errors")
        check(not errs, 'no page errors', '; '.join(errs[:2]))
        browser.close()
    httpd.shutdown()

    print()
    if fails:
        print('  %d check(s) FAILED' % len(fails))
        return 1
    print('  the angry drive at you, and what they try depends on where they are')
    print('  whether being hunted is frightening or merely annoying, and whether the')
    print('  odds put one on you too often, is the owner call on a device.')
    return 0


sys.exit(main())
