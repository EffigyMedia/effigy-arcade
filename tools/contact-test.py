#!/usr/bin/env python3
"""CONTACT TEST - a car you have hit is still solid, and contact is one event.

    .venv/Scripts/python tools/contact-test.py

RLG-277. Owner, 2026-09-16: "When you collide with a car you are then allowed to just drive
through them. We can't allow that to happen but I also don't want it to machine gun fire
collisions."

TWO REQUIREMENTS THAT PULL AGAINST EACH OTHER, so a check for either one alone can be passed
by breaking the other. Delete the mercy window and nothing is drivable-through, and every rub
fires sixty crashes a second. Widen the window and the machine gun stops, and you drive through
cars. Both are asserted here, or neither means anything.

SO THERE ARE TWO RUNS, because one contact cannot show both. A car struck head-on is shoved
aside within a few frames - which is correct, and is why "did the player end up past it" is
NOT the test for driving through: being deflected clear and then passing is what a body does.
Sustained contact has to be MADE, by holding the wheel into the other car, and that is the
second run.

  RUN ONE, SOLID          a stationary car dead ahead, driven into at speed. The player's
                          centre must never end up deep inside the other body, and the car in
                          front must cap the speed rather than be passed through at full pace.
  RUN TWO, ONE EVENT      a car alongside, with the wheel held into it for two seconds. Many
                          frames of contact, and a handful of crash responses at most.

A CRASH RESPONSE IS COUNTED AS A STEP IN DAMAGE rather than as a call to anything. Counting
calls means trusting a counter written for this check; counting what the PLAYER feels cannot
be gamed by the thing under test.

WHAT IT CANNOT SEE. Whether the shove FEELS right, whether being held against a car reads as
contact or as a wall, and whether one hit is the right cost for a long grind. Owner's call on
a device.
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


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


# ---- BOTH RUNS SAMPLE ON THE ENGINE'S OWN rAF ------------------------------------------
# Polling from Python samples at whatever rate the round trip allows, and the whole question
# is what happens BETWEEN frames: a car passed through in three frames is invisible to a
# poller that sees one frame in ten.
RUN = r"""
([mode, dx, ahead, seconds, speed]) => new Promise(resolve => {
  const R = window.__probe.road;
  R.setTimed(false);              /* the run clock freezes every number when it expires */
  R.clearTraffic();
  R.setSpd(R.MAX_SPD * speed);
  if(!R.parkTraffic(dx, ahead)){ resolve({ error: 'no car parked' }); return; }
  /* AIM THE PLAYER AT IT. The road bends and the car drifts, so a driver left alone meets
     the parked car on some runs and sails past it on others - which reads as the engine
     being inconsistent when it is the harness that never steered. */
  R.steerOver(dx, 0.01);

  const log = [], t0 = performance.now();
  let hits = 0, lastDmg = R.damage();
  const tick = () => {
    const now = performance.now(), t = (now - t0) / 1000;
    const st = R.contactState(0);
    if(!st){ resolve({ error: 'the car left the array' }); return; }
    /* HOLD THE WHEEL INTO IT. Re-issued every frame so the separation cannot simply win:
       that is what MAKES sustained contact, which a head-on hit never produces. */
    if(mode === 'drive') R.steerOver(st.x, 0.05);
    if(mode === 'lean'){
      /* HOLD THE WHEEL INTO IT, and keep it ALONGSIDE. A parked car is left behind in a
         fraction of a second at road speed, so there is nothing to lean on - matching its
         speed to the player's is what makes the contact last, which is the case the
         owner's "machine gun" lives in. */
      /* PRESS INTO IT, not past it. Steering to the road edge crosses the other car in a
         single frame and parks the player beyond it with nothing to lean on; a target just
         the far side of its centre is a driver holding the wheel over. */
      R.steerOver(st.x + (dx > 0 ? 0.12 : -0.12), 0.05);
      R.trafficSpeed(0, R.spdNow());
    }
    const dmg = R.damage();
    if(dmg > lastDmg + 0.01) hits++;
    lastDmg = dmg;
    log.push({ t: t, gap: st.gap, wide: st.wide, dz: st.dz, square: st.square,
               within: st.within, dmg: dmg, spd: R.spdNow() });
    if(t > seconds){ resolve({ log: log, hits: hits }); return; }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
})
"""


def main():
    console_utf8()
    fails = []

    def check(ok, label, detail=''):
        print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label,
                              '   ' + detail if detail else ''))
        if not ok:
            fails.append(label)

    httpd, port = serve(ROOT)
    print('contact-test  .  a car you have hit is still solid')
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
        page.wait_for_timeout(1800)
        for _ in range(40):
            st = page.evaluate("() => window.__probe.road.startLine()")
            if st['left'] <= 0 and st['go'] <= 0:
                break
            page.wait_for_timeout(90)

        # ---- RUN ONE: SOLID ----------------------------------------------------------
        print('  RUN ONE - a stationary car dead ahead, driven into at speed')
        res = page.evaluate(RUN, ['drive', 0.0, 3000, 3.0, 0.45])
        if res.get('error'):
            print('  the run could not be staged: %s' % res['error'])
            browser.close(); httpd.shutdown(); return 1
        log = res['log']
        # DEEP INSIDE IS THE TEST FOR DRIVING THROUGH. Being deflected clear and then passing
        # is what a body does; being at the same POINT as one is not.
        # ASKED AFTER THE FIRST RESPONSE. The frame of impact is the impact; the defect is
        # what happens in the mercy window AFTERWARDS, which is where the pass-through was.
        firstHit = next((i for i, s in enumerate(log) if s['dmg'] > log[0]['dmg'] + 0.01), 0)
        after = log[firstHit:]
        inside = [s for s in after
                  if s['within'] and s['square'] > 0.5 and s['gap'] < s['wide'] * 0.10]
        met = [s for s in log if s['within']]
        deepest = min((s['gap'] / s['wide']) for s in after if s['within'])             if any(s['within'] for s in after) else 1.0
        print('      %d frames, %d of them nose-to-tail with the car' % (len(log), len(met)))
        print('      closest the two centres came: %.2f of the overlap width' % deepest)
        check(len(met) > 3, 'the player actually reached the car', '%d frames' % len(met))
        check(not inside, 'the player never occupies the same point as the car it hit',
              '%d frame(s) at under a tenth of the overlap while square to it' % len(inside))
        # AND THE CAR IN FRONT CAPS THE SPEED. Driving through shows as the player holding
        # pace through a stationary body.
        squareMet = [s for s in log if s['within'] and s['square'] > 0.35]
        if squareMet:
            slowest = min(s['spd'] for s in squareMet)
            start = log[0]['spd']
            print('      speed on meeting it: %.0f, slowest while square to it: %.0f'
                  % (start, slowest))
            check(slowest < start * 0.75, 'a car in front takes your speed rather than being '
                                          'driven through', '%.0f down from %.0f'
                  % (slowest, start))
        else:
            check(False, 'the player met the car squarely at all')
        check(res['hits'] >= 1, 'and it costs a hit', '%d' % res['hits'])

        # ---- RUN TWO: ONE EVENT ------------------------------------------------------
        print()
        print('  RUN TWO - a car alongside, with the wheel held into it for two seconds')
        res2 = page.evaluate(RUN, ['lean', 0.34, 120, 2.0, 0.30])
        if res2.get('error'):
            print('  the run could not be staged: %s' % res2['error'])
            browser.close(); httpd.shutdown(); return 1
        log2 = res2['log']
        touch = [s for s in log2 if s['within'] and s['gap'] < s['wide']]
        print('      %d frames, %d of them with the two bodies overlapping'
              % (len(log2), len(touch)))
        print('      %d crash response(s)' % res2['hits'])
        check(len(touch) > 20, 'the wheel held into it really does hold them together',
              '%d frames of contact' % len(touch))
        check(res2['hits'] >= 1, 'leaning on a car costs a hit at all', '%d' % res2['hits'])
        # A MACHINE GUN IS ONE PER FRAME. A handful is contact broken and remade, which IS
        # several events; sixty a second is the thing the owner reported.
        check(res2['hits'] <= 5, 'but it is not one a frame',
              '%d responses over %d frames of contact' % (res2['hits'], len(touch)))

        errs = page.evaluate("() => window.__probe.errors")
        check(not errs, 'no page errors', '; '.join(errs[:2]))
        browser.close()
    httpd.shutdown()

    print()
    if fails:
        print('  %d check(s) FAILED' % len(fails))
        return 1
    print('  the car is solid and the crash fires once')
    print('  whether the shove FEELS right, and whether one hit is the right cost for a long')
    print('  grind, is the owner call on a device.')
    return 0


sys.exit(main())
