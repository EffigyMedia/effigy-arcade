#!/usr/bin/env python3
"""GARAGE CARD - one end, centred, standing on the floor, and a button that flips it.

    .venv/Scripts/python tools/garage-card-test.py

RLG-210. The card showed BOTH ends side by side, each fitted into half the width.
The owner asked for one end only - the front - so that it can be larger and centred,
for every car to stand on a common floor rather than hang from a ceiling, and for a
button in the corner of the view pane to turn the car round, with the front restored
every time the garage opens.

IT READS THE PAINTED PIXELS, NOT THE CODE. Every check below measures the canvas the
player is looking at: where ink actually starts and stops across the card. A check
that asked `garageEnd` would pass on a build that never drew anything, and a check
that counted `put` calls would pass on one that drew them both on top of each other.

WHAT EACH ONE WOULD CATCH

    one end       two cars side by side leave ink in BOTH outer thirds and a gap
                  down the middle. One centred car is the opposite of that, so
                  the check is on the shape of the ink rather than on a count.
    larger        the drawn car is wider than the old half-width could hold. 126
                  was the widest a car could be drawn under the two-end layout.
    centred       the ink's own midpoint sits within a few pixels of the card's.
    floor         the ink reaches the same bottom line for a tall car and a low
                  one - a ceiling anchor is what the ruling calls the fault, and
                  it shows up as two different bottoms.
    flip          the button changes the picture. Compared as pixels, because a
                  button that toggles a variable and redraws the same car is the
                  exact failure this is for.
    reset         leaving the garage and coming back shows the FRONT again, after
                  a flip to the rear. `showGarage` is called by every control in
                  that screen, so the reset has to be on entry alone - and this
                  also checks the other half of that: a paint change while the
                  rear is showing must NOT flip it back.

Exit code 0 if every check passes, 1 otherwise.
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

# WHERE THE INK IS. Columns and rows that carry any non-transparent pixel, plus a
# cheap signature of the whole card so two draws can be compared.
INK = """() => {
  const cv = document.getElementById('gcar');
  if(!cv) return null;
  const g = cv.getContext('2d');
  const w = cv.width, h = cv.height;
  const d = g.getImageData(0, 0, w, h).data;
  const cols = [], rows = [];
  let sum = 0, n = 0;
  for(let x = 0; x < w; x++) cols.push(0);
  for(let y = 0; y < h; y++) rows.push(0);
  for(let y = 0; y < h; y++){
    for(let x = 0; x < w; x++){
      const a = d[(y*w + x)*4 + 3];
      if(a > 8){ cols[x]++; rows[y]++; n++;
                 sum += d[(y*w+x)*4] + d[(y*w+x)*4+1]*3 + d[(y*w+x)*4+2]*7 + x; }
    }
  }
  const first = a => { for(let i = 0; i < a.length; i++) if(a[i]) return i; return -1; };
  const last  = a => { for(let i = a.length - 1; i >= 0; i--) if(a[i]) return i; return -1; };
  // the device pixel ratio is baked into the canvas, so everything is reported in
  // CSS pixels - the units the layout is written in
  const k = w / 300;
  return { x0: first(cols)/k, x1: last(cols)/k, y0: first(rows)/k, y1: last(rows)/k,
           w: w/k, h: h/k, ink: n, sig: sum };
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class Res:
    def __init__(self):
        self.fails = []

    def ok(self, good, label, detail=''):
        print(('  ok    ' if good else '  FAIL  ') + label
              + ('' if good else '   [' + detail + ']'))
        if not good:
            self.fails.append(label)


def open_garage(page):
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.wait_for_timeout(250)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--bodies', default='TUNER,MUSCLE,ROADSTER')
    args = ap.parse_args()
    console_utf8()
    httpd, port = serve(ROOT)
    base = 'http://127.0.0.1:%d' % port
    res = Res()
    print('garage-card  .  one end, centred, on the floor, with a button to flip it')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio',
                                  '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, base + '/games/sw/interstate.html')
        try:
            until(page, '() => navigator.serviceWorker'
                        ' && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        open_garage(page)

        bottoms = {}
        for body in [x.strip() for x in args.bodies.split(',') if x.strip()]:
            page.evaluate("(k) => { const R = window.__road;"
                          " R.setBody(k); R.showGarage(); }", body)
            page.wait_for_timeout(200)
            m = page.evaluate(INK)
            if not m or m['ink'] == 0:
                res.ok(False, '%s paints something on the card' % body, 'no ink at all')
                continue
            mid = (m['x0'] + m['x1']) / 2
            width = m['x1'] - m['x0']
            bottoms[body] = m['y1']

            # ONE END, MEASURED AGAINST THE ENGINE'S OWN FIT rather than against a
            # threshold. `carEnds` reports each end's ink box and the height it is
            # drawn at, and the scale is drawnH/inkH - so the width ONE car should
            # occupy is arithmetic. Two cars side by side span that plus the 150
            # between their centres, which no tolerance can absorb.
            #
            # THE FIRST VERSION OF THIS CHECK ASKED WHETHER THE MIDDLE COLUMN WAS
            # PAINTED, and it PASSED with both ends drawn. Widening the fit to the
            # whole card made each half-drawn car wide enough to overlap the centre,
            # so the check no longer separated the two layouts - it was watched
            # passing with the defect present, which is the only reason it was found.
            ends = page.evaluate("(k) => window.__road.carEnds()[k]", body)
            want = None
            if ends:
                e = ends['front'] or ends['back']
                if e and e['inkH']:
                    want = e['inkW'] * e['drawnH'] / e['inkH']
            if want:
                res.ok(abs(width - want) <= 8,
                       '%s paints ONE car, at the width the fit asks for' % body,
                       'painted %.0f px against the %.0f one end should take -'
                       ' two ends side by side span about %.0f'
                       % (width, want, want + 150))
                res.ok(width > 126,
                       '%s is drawn wider than the old half allowed' % body,
                       'drawn %.0f px against the old ceiling of 126' % width)
            else:
                print('  BLKD  %s - the engine did not report a fit to measure'
                      ' against' % body)
                res.fails.append('%s could not be measured against the fit' % body)
            res.ok(abs(mid - 150) <= 6, '%s is centred on the card' % body,
                   'ink midpoint at %.1f of 150' % mid)

        # THE FLOOR. Every car's ink must END on the same line. A ceiling anchor
        # shows up here as cars of different heights finishing at different bottoms.
        if len(bottoms) > 1:
            spread = max(bottoms.values()) - min(bottoms.values())
            res.ok(spread <= 2, 'every car stands on the same floor line',
                   'bottoms differ by %.1f px: %s'
                   % (spread, ', '.join('%s %.0f' % kv for kv in bottoms.items())))

        # THE BUTTON. It must exist, and pressing it must change the PICTURE.
        page.evaluate("() => { const R = window.__road;"
                      " R.setBody('TUNER'); R.showGarage(); }")
        page.wait_for_timeout(200)
        before = page.evaluate(INK)
        has = page.locator('.gflip').count()
        res.ok(has == 1, 'there is a flip button on the card',
               'found %d of them' % has)
        if has:
            page.click('.gflip')
            page.wait_for_timeout(250)
            after = page.evaluate(INK)
            res.ok(after and before and after['sig'] != before['sig'],
                   'pressing it turns the car round', 'the card did not change')

            # A PAINT CHANGE MUST NOT UNDO THE FLIP. `showGarage` is what every
            # control calls to redraw, so a reset written at the top of it would
            # snap the card back to the front on any of them.
            sw = page.locator('[data-act^="paint:"]')
            if sw.count() > 1:
                sw.nth(1).click()
                page.wait_for_timeout(250)
                # THE BUTTON CARRIES A GLYPH NOW, so its label is no longer the
                # thing to read. `aria-label` is what says which end is showing,
                # and it is the accessible name a screen reader gets - so reading
                # it checks something the player is actually served rather than a
                # test hook.
                still = page.evaluate(
                    "() => { const b = document.querySelector('.gflip');"
                    " return b ? b.getAttribute('aria-label') : ''; }")
                res.ok(still == 'show the front',
                       'changing the paint leaves the rear showing',
                       'the button offers %r, so the card flipped back' % still)

            # AND THE FRONT COMES BACK WHEN THE GARAGE IS REOPENED.
            page.click('[data-act="back"]')
            page.wait_for_timeout(250)
            open_garage(page)
            label = page.evaluate(
                "() => { const b = document.querySelector('.gflip');"
                " return b ? b.getAttribute('aria-label') : ''; }")
            res.ok(label == 'show the rear',
                   'reopening the garage shows the FRONT again',
                   'the button offers %r, so the rear was still showing' % label)

        # ---- AND A CAR YOU HAVE NOT WON GETS NO BUTTON (owner, 2026-09-12) ----
        # "The functionality to flip the view of a car you don't have unlocked yet
        # is unnecessary." Both ends of a silhouette are the same flat grey, so the
        # control would promise a second look and not deliver one.
        #
        # THE CHECK IS PAIRED, because "no button" passes on a build where the card
        # never renders at all. So it walks to a LOCKED car and asserts the button is
        # gone AND the card still paints a silhouette, then walks back to an owned
        # car and asserts the button returns.
        locked = page.evaluate(
            "() => { const R = window.__road;"
            " return R.garageBodies().filter(k => R.carLocked && R.carLocked(k)); }")
        if not locked:
            # `carLocked` may not be exposed; fall back to the card's own ??? name
            locked = page.evaluate(
                "() => { const R = window.__road; const out = [];"
                " for(const k of R.garageBodies()){ R.setBody(k); R.showGarage();"
                "   const n = document.querySelector('.gname');"
                "   if(n && n.textContent.trim() === '???') out.push(k); }"
                " return out; }")
        if not locked:
            print('  BLKD  no locked car in the garage to test the rule on')
            res.fails.append('no locked car was available')
        else:
            page.evaluate("(k) => { const R = window.__road;"
                          " R.setBody(k); R.showGarage(); }", locked[0])
            page.wait_for_timeout(200)
            n = page.locator('.gflip').count()
            ink = page.evaluate(INK)
            res.ok(n == 0, 'a locked car has NO flip button',
                   '%s still shows %d' % (locked[0], n))
            res.ok(bool(ink and ink['ink'] > 0),
                   'and its card still paints the silhouette',
                   'nothing was drawn, so the check above proves nothing')
            page.evaluate("() => { const R = window.__road;"
                          " R.setBody('TUNER'); R.showGarage(); }")
            page.wait_for_timeout(200)
            res.ok(page.locator('.gflip').count() == 1,
                   'and an owned car gets it back',
                   'the button did not return, so it is gone for everyone')

        if errs:
            res.ok(False, 'the page reported no errors', '; '.join(errs[:3]))
        b.close()
    httpd.shutdown()
    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('the card is one end, centred, on the floor, and the button turns it round')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
