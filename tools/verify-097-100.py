#!/usr/bin/env python3
"""VERIFY - two owner claims, checked rather than taken on trust.

    .venv/Scripts/python tools/verify-097-100.py

Owner, 2026-08-31: "ruling 100 is probably unnecessary now because adding earning +10 seconds
to each pick up solved that issue. Also, RLG-097 has been fixed. Let's move both of these to
the end and just do a quick analysis to verify these facts."

TWO CLAIMS, TWO DIFFERENT KINDS OF EVIDENCE, and the difference matters.

RLG-097, THE POP ON GO, IS A DEVICE REPORT AND THE OWNER IS THE ONLY WITNESS THAT COUNTS.
This project has RLG-041's lesson written down: five real mechanisms were found and fixed
for that defect and none was the one the owner was seeing. So what this measures is NOT
"is the pop gone" - it cannot see that - but the narrower thing a harness can settle:
whether anything the picture is drawn through still STEPS across the count-in boundary. If
something does, the owner's report is at risk. If nothing does, the fix is consistent with
what they saw.

RLG-100, THE CHECKPOINT BUDGET, IS ARITHMETIC AND A HARNESS CAN SETTLE IT. The claim is
that the crate award closed the margin. That is measurable: drive at full throttle and
watch the clock.

Exit code 0 if both claims survive, 1 otherwise.
"""

import argparse
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


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class Results:
    def __init__(self):
        self.fails = []

    def check(self, ok, label, detail=''):
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + detail + ']'))
        if not ok:
            self.fails.append(label)


# Every field the picture is drawn through, sampled EVERY FRAME across the count-in and into
# driving. The question RLG-121 had to ask was not "did this one field move" but "was
# ANYTHING saved up until the first driving frame", so the probe reports all of them at once.
WATCH_GO = """(secs) => {
  const R = window.__probe.road;
  return new Promise((done) => {
    const rows = [];
    const t0 = performance.now();
    const tick = () => {
      const v = R.viewState();
      rows.push({ t: performance.now() - t0, viewShift: v.viewShift, camX: v.camX,
                  playerX: v.playerX, pushK: v.pushK, bendT: v.bendT, horizon: v.horizon });
      if(performance.now() - t0 < secs * 1000) requestAnimationFrame(tick);
      else done(rows);
    };
    requestAnimationFrame(tick);
  });
}"""

# THE CLOCK, SAMPLED WHILE DRIVING FLAT OUT. `clock` is what the run lives on: it starts at
# 60, gains 20 at every checkpoint two miles apart, and gains 10 for every crate taken. If
# the owner is right, a fast car holds station or drifts down slowly rather than falling off.
WATCH_CLOCK = """(secs) => {
  const R = window.__probe.road;
  return new Promise((done) => {
    const rows = [];
    const t0 = performance.now();
    const tick = () => {
      const st = R.startLine();
      rows.push({ t: (performance.now() - t0) / 1000, clock: st.clock,
                  pos: st.pos, spd: st.spd,
                  crates: R.cratesTaken ? R.cratesTaken() : null });
      if(performance.now() - t0 < secs * 1000) requestAnimationFrame(tick);
      else done(rows);
    };
    requestAnimationFrame(tick);
  });
}"""


def open_game(page, port):
    boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
    try:
        until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
        page.wait_for_timeout(1000)
    except Exception:
        pass
    until(page, '!!window.__probe.road', timeout=10000)
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--seconds', type=float, default=95.0,
                    help='how long to drive when measuring the clock')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('verify  .  two owner claims, checked rather than taken on trust')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)

        # ============================================ RLG-097, the pop on GO
        print()
        print('  RLG-097 - DOES ANYTHING STILL STEP AT GO')
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        open_game(page, port)
        page.click('[data-act="drive"]')
        rows = page.evaluate(WATCH_GO, 6.0)
        fields = ['viewShift', 'camX', 'playerX', 'pushK', 'bendT', 'horizon']
        worst = {}
        for f in fields:
            biggest, at = 0.0, 0.0
            for a, b in zip(rows, rows[1:]):
                if a[f] is None or b[f] is None:
                    continue
                d = abs(b[f] - a[f])
                if d > biggest:
                    biggest, at = d, b['t']
            worst[f] = (biggest, at)
        print('      %d frames sampled across the count-in and into driving' % len(rows))
        for f in fields:
            print('        %-10s largest single-frame step %8.4f  at %.0f ms'
                  % (f, worst[f][0], worst[f][1]))
        # viewShift IS THE ONE RLG-121 NAMED. On a touch layout it goes to -8.5% of the screen
        # width, which at 480 wide is -40.8 pixels - the entire picture moving sideways in one
        # frame. It is set in `step()`, so if `step()` ever returns early during the count
        # again, this is where it shows.
        res.check(worst['viewShift'][0] < 1.0,
                  'the whole forward view does not jump sideways at GO, which is what RLG-121 fixed',
                  'viewShift stepped %.3f px in one frame' % worst['viewShift'][0])
        res.check(worst['camX'][0] < 0.05 and worst['playerX'][0] < 0.05,
                  'and the camera and the car do not jump either',
                  'camX %.4f, playerX %.4f' % (worst['camX'][0], worst['playerX'][0]))
        res.check(worst['horizon'][0] < 30,
                  'and the horizon does not snap',
                  'horizon stepped %.2f' % worst['horizon'][0])
        # WHAT THIS CANNOT SAY, stated in the output rather than left to the reader.
        print('      NOTE: this cannot see the owner pop. It says only that nothing the')
        print('            picture is drawn through steps across the boundary - which is')
        print('            consistent with the report being answered, not proof of it.')
        page.close()

        # ============================================ RLG-100, the checkpoint budget
        print()
        print('  RLG-100 - CAN A CAR HOLD ITS CLOCK AT FULL THROTTLE')
        print('      checkpoints are 2 miles apart and pay 20s; a crate pays 10s;')
        print('      the run starts with 60s on the clock')
        top_of = {'TUNER': int(0.73 * 200), 'ROADSTER': int(0.765 * 200),
                  'MUSCLE': int(0.8 * 200)}
        for body in ('TUNER', 'ROADSTER', 'MUSCLE'):
            page = browser.new_page(viewport={'width': 480, 'height': 900})
            page.add_init_script(INIT)
            open_game(page, port)
            page.evaluate("(b) => window.__probe.road.setBody(b)", body)
            page.click('[data-act="drive"]')
            page.wait_for_timeout(400)
            page.dispatch_event('#gas', 'pointerdown')
            rows = page.evaluate(WATCH_CLOCK, args.seconds)
            page.dispatch_event('#gas', 'pointerup')
            clocks = [r['clock'] for r in rows if r['clock'] is not None]
            if not clocks:
                print('      %-9s the clock could not be read' % body)
                page.close()
                continue
            start, end, low = clocks[0], clocks[-1], min(clocks)
            crates = rows[-1]['crates']
            mi = rows[-1]['pos'] / 128700.0
            print('      %-9s clock %5.1f -> %5.1f  (lowest %5.1f)   %s miles, %s crate(s)'
                  % (body, start, end, low, ('%.2f' % mi) if mi is not None else '?',
                     crates if crates is not None else '?'))
            # THE SPEED IS PRINTED TOO, because a clock that holds up because the car never
            # got going is not the claim being tested.
            # BOTH IN MPH. The engine carries speed in world units and 15,333 of them is
            # 200mph; the first version of this line printed the raw number against a figure
            # in mph and read as though the car had done 11,193 miles an hour.
            peak_mph = max(r['spd'] for r in rows) / 15333.0 * 200
            print('                reached %d mph of the %d this car declares'
                  % (round(peak_mph), top_of.get(body, 0)))
            res.check(low > 2.0,
                      '%s does not run the clock out at full throttle' % body,
                      'the clock reached %.1f seconds' % low)
            page.close()

        # ---- DOES A PICKUP ACTUALLY PAY ITS TEN SECONDS -------------------------------
        # NOT ASKED HERE, BECAUSE IT IS ALREADY ASKED PROPERLY ELSEWHERE. `crate-test`
        # centres the car, parks a crate in its path and reads the clock either side, for
        # every case including a car with nothing else to gain. It reports the ROADSTER
        # going 59.3 -> 65.7 and the LORRY 65.7 -> 72.2 across a drive of a few seconds.
        # A second, worse copy of that check was written here first and failed - it did not
        # centre the car, so the crate was parked at a drifted lateral position and never
        # collected. Duplicating a check badly is how a project ends up believing a
        # working feature is broken.
        print()
        print('  THE TEN SECONDS THEMSELVES ARE PROVEN BY crate-test, NOT HERE')
        print('      it centres the car, parks a crate in its path and reads the clock')
        print('      either side, for every case including a car with nothing else to gain')

        print()
        browser.close()
    httpd.shutdown()

    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('both claims survive the checks a harness can make')
    return 0


sys.exit(main())
