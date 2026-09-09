#!/usr/bin/env python3
"""MIRROR BAR TEST - the glass draws the sprite's light bar and no second one.

    .venv/Scripts/python tools/mirror-bar-test.py

RLG-177. Owner, 2026-09-08, from the device: "Why is there something that looks like a health bar
or something only visible on the police cruisers in the rearview mirror? Is this a render defect?
I don't want health bars in either view."

IT WAS A SECOND LIGHT BAR. The mirror painted its own `fillRect` over the cruiser - the whole
width of the car, one bar-height ABOVE the roof - on top of the bar the front sprite already
draws. A solid full-width rectangle floating over a car reads as a health bar, which is what the
owner saw. The fix lights the sprite's declared `bar.fl` / `bar.fr` lamps instead.

HOW THIS IS CHECKED WITHOUT A HUMAN LOOKING, AND THE FIRST WAY DID NOT WORK. The stray bar was
filled with two literal colours, `#3b6bff` and `#ff2b4a`, and the first appears nowhere else in
the game - so counting pixels of exactly that blue looked like a perfect instrument. IT PASSED ON
THE BROKEN BUILD. The bar is painted under the arrival fade, so `globalAlpha` blends it with
whatever is behind and it never lands on its own literal value. A check that reads a colour is
not reading the thing.

WHAT WORKS IS GEOMETRY. The rule is not "that colour must not appear" - it is that **nothing
belonging to a police car may be painted above its own sprite**. So the engine reports where the
glass put the cruiser (`mirrorCopBox`) and the check reads the band directly ABOVE the roof,
across the car's own width, for anything strongly blue or red. The sprite's bar is inside the
sprite and never reaches that band; the stray bar was a full-width run sitting exactly in it.

AND THE PHASE IS WHY IT SAMPLES OVER TIME. The stray bar alternated blue on one beat and red on
the next, so one frame catches one or the other. Sixty samples cover both, and the check keeps
the WORST frame rather than the last.

THE POSITIVE CONTROLS ARE THE OTHER HALF. A check that only looks for something it does not want
passes on an empty mirror, a black frame, or a cruiser that never arrived. So it also asserts
that the glass really drew a cruiser, and that the sprite's own bar really is being painted.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium
from playwright.sync_api import sync_playwright

GAME = 'games/sw/interstate.html'

# Read straight out of the canvas at device pixels. Cropping a screenshot would resample.
COUNT = """() => {
  const R = window.__road;
  const box = R.mirrorCopBox && R.mirrorCopBox();
  if(!box || box.w < 4) return { seen: false, above: 0, own: 0, run: 0, w: 0 };
  const c = document.querySelector('canvas');
  const rect = c.getBoundingClientRect();
  const dpr = c.width / rect.width;
  const g = c.getContext('2d');
  /* SATURATED, and the margin is what the sky forced. A first version asked for
     b - r > 45, which the daylight sky itself satisfies at about (170,190,215) -
     so the check reported twelve stray pixels above every cruiser on a build with
     nothing wrong. A light bar is a saturated colour and the sky is not: 80 clears
     the sky by a wide margin and still catches every lens the scheme declares, the
     palest of which (#8fb6ff) is 112 apart. */
  const barish = (r, gg, b) => (b > 150 && b - r > 80) || (r > 150 && r - b > 80);

  /* the band directly above the roof, the car's own width - where a bar that is not
     part of the sprite has to be, and where no part of the car ever is */
  const bandH = Math.max(2, Math.round(box.h * 0.22));
  const sx = Math.round(box.x * dpr);
  const sy = Math.max(0, Math.round((box.y - bandH) * dpr));
  const sw = Math.max(1, Math.round(box.w * dpr));
  const sh = Math.max(1, Math.round(bandH * dpr));
  const d = g.getImageData(sx, sy, sw, sh).data;
  let above = 0, run = 0;
  for(let y = 0; y < sh; y++){
    let cur = 0;
    for(let x = 0; x < sw; x++){
      const i = (y * sw + x) * 4;
      if(barish(d[i], d[i+1], d[i+2])){ above++; cur++; if(cur > run) run = cur; }
      else cur = 0;
    }
  }

  /* and the sprite's own bar, INSIDE the car, as the positive control */
  const bd = g.getImageData(sx, Math.round(box.y * dpr), sw,
                            Math.max(1, Math.round(box.h * 0.45 * dpr))).data;
  let own = 0;
  for(let i = 0; i < bd.length; i += 4) if(barish(bd[i], bd[i+1], bd[i+2])) own++;

  return { seen: true, above: above, own: own, run: run, w: Math.round(box.w) };
}"""

STAGE = """(dz) => {
  const R = window.__road;
  R.copsClear();
  R.placeCop(dz, 0.0);
  const k = R.cops()[0];
  k.from = 'test';
  k.onPlayer = true; k.engaged = true; k.tgt = null;
  window.__hold = setInterval(() => {
    const kk = R.cops()[0];
    if(!kk) return;
    kk.z = R.pos + R.PLAYER_Z + dz; kk.x = 0; kk.spd = R.MAX_SPD * 0.30;
    kk.onPlayer = true; kk.engaged = true;
  }, 8);
  return true;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print("mirror-bar-test  .  one light bar, and it is the sprite's")
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto('%s/%s' % (base, GAME), wait_until='load')
        try:
            page.wait_for_function(
                '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(300)
        page.click('[data-act="chase"]')
        page.wait_for_timeout(150)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2000)
        page.evaluate('() => window.__road.setSpd(window.__road.MAX_SPD * 0.30)')
        page.wait_for_timeout(800)
        page.evaluate(STAGE, -6000)
        page.wait_for_timeout(600)

        worst_above, worst_run, best_own, seen, width = 0, 0, 0, 0, 0
        for _ in range(60):
            page.wait_for_timeout(70)
            r = page.evaluate(COUNT)
            if not r['seen']:
                continue
            seen += 1
            width = r['w']
            worst_above = max(worst_above, r['above'])
            worst_run = max(worst_run, r['run'])
            best_own = max(best_own, r['own'])

        ok(seen >= 30, 'the glass really drew a cruiser while this was read',
           '%d of 60 samples had one, %dpx wide' % (seen, width))
        ok(best_own > 0, 'and the sprite draws its own light bar',
           '%d bar-coloured pixels inside the car at best' % best_own)
        ok(worst_above == 0, 'and nothing is painted above the roof',
           '%d bar-coloured pixels above it, longest run %dpx of a %dpx car'
           % (worst_above, worst_run, width))
        ok(not errs, 'and the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
