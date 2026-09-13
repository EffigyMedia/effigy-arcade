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


# `--falsify floor` only. Deletes the garage floor out of the live stylesheet, which is the
# state the card was in before RLG-182's second half. Returns how many rules it removed, so a
# falsifier that quietly matched nothing cannot be mistaken for a defect that failed to reproduce.
DROP_FLOOR = """() => {
  let n = 0;
  for (const sh of Array.from(document.styleSheets)) {
    let rules;
    try { rules = sh.cssRules; } catch (e) { continue; }
    if (!rules) continue;
    for (let i = rules.length - 1; i >= 0; i--) {
      const sel = rules[i].selectorText || '';
      if (sel.indexOf('.gwrap') >= 0 && sel.indexOf('before') >= 0) { sh.deleteRule(i); n++; }
    }
  }
  return n;
}"""

# where the floor line is, in the card's own pixels, and how wide the car is there
WHERE = """() => {
  const w = document.querySelector('.gwrap');
  const cv = document.getElementById('gcar');
  if (!w || !cv) return null;
  const f = parseFloat(getComputedStyle(w).getPropertyValue('--gfloor'));
  if (!isFinite(f)) return null;
  const r = w.getBoundingClientRect();
  return { floor: f, w: r.width, h: r.height };
}"""


def read_band(page):
    """Photograph the composed card and measure the band just above the floor line.

    Three numbers come back. `card_lum` is the plain card well above the car, which is the
    control - it says what "unlit" looks like on this build. `floor_lum` is the lit floor
    beside the car at the floor line. `spread` is that floor against the darkest pixel under
    the car in the same rows, which is the tyre: it is the contrast a player actually sees.
    """
    import base64, io as _io
    try:
        from PIL import Image
    except ImportError:
        return None
    w = page.evaluate(WHERE)
    if not w:
        return None
    png = page.locator('.gwrap').screenshot()
    im = Image.open(_io.BytesIO(png)).convert('RGB')
    k = im.width / w['w']                      # device pixels per CSS pixel
    lum = lambda px: 0.2126*px[0] + 0.7152*px[1] + 0.0722*px[2]
    row = lambda y, x0, x1: [lum(im.getpixel((x, int(y)))) for x in range(int(x0), int(x1))]
    floor_y = w['floor'] * k
    band = [floor_y - 6*k, floor_y - 2*k]
    mid = im.width / 2
    # the car occupies the middle of the card; the floor is lit either side of it and the
    # tyres are the darkest thing inside it
    inner = []
    outer = []
    y = band[0]
    while y < band[1]:
        inner += row(y, mid - 90*k, mid + 90*k)
        outer += row(y, mid - 118*k, mid - 96*k) + row(y, mid + 96*k, mid + 118*k)
        y += 1
    if not inner or not outer:
        return None
    # THE CONTROL IS THE SAME COLUMNS, HIGHER UP, and the first version was not - it read the
    # card's outer edges, which are dark whether a floor is drawn or not, so "there is a lit
    # floor" passed with the floor deleted. Measuring the floor's own columns above its reach
    # isolates the one thing being asked about: same x, same card, no floor.
    ctrl = []
    for yy in (floor_y - 74*k, floor_y - 68*k, floor_y - 62*k):
        if yy > 0:
            ctrl += row(yy, mid - 118*k, mid - 96*k) + row(yy, mid + 96*k, mid + 118*k)
    outer.sort()
    inner.sort()
    floor_lum = outer[int(len(outer)*0.5)]
    dark = inner[int(len(inner)*0.05)]
    return { 'floor_lum': floor_lum, 'card_lum': (sum(ctrl)/len(ctrl)) if ctrl else 0.0,
             'spread': floor_lum - dark }


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
    ap.add_argument('--falsify', choices=['floor'],
                    help='delete the garage floor from the live stylesheet; the tyre check must fail')
    # ---- THE CARS A FRESH SAVE ACTUALLY HAS (RLG-182) ----------------------
    # This was TUNER, MUSCLE, ROADSTER and all three are SPORTS, which RLG-213 locked
    # on a fresh save. So every card this walked was a LOCKED one: the width checks
    # still passed, because a silhouette is fitted exactly like a car, and the three
    # button checks failed on every run because RLG-210's amendment correctly takes
    # the flip button OFF a locked card. The harness had been red for that reason
    # alone, against a product that was right.
    #
    # Production is open from the start, so these three are owned by anybody.
    ap.add_argument('--bodies', default='SALOON,COUPE,HATCH')
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
                      " R.setBody('SALOON'); R.showGarage(); }")
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
                          " R.setBody('SALOON'); R.showGarage(); }")
            page.wait_for_timeout(200)
            res.ok(page.locator('.gflip').count() == 1,
                   'and an owned car gets it back',
                   'the button did not return, so it is gone for everyone')

        # ---- THE TYRES READ, BECAUSE THE CAR STANDS ON SOMETHING (RLG-182) ----
        # Owner: "we need to show a little bit of the tires on the bottom." The wheels
        # were always in the sprite - a SALOON's are three rows of two 36-pixel blocks
        # at luminance 16 to 22 - with `groundShadow`'s full-width black bar directly
        # under them, on a near-black card. Three dark things that could not be told
        # apart.
        #
        # THE FLOOR IS CSS AND IS NOT ON THE CANVAS, so this cannot read `#gcar` the
        # way every check above does. It photographs the composed card and measures
        # what a player's eye gets: in the band just above the floor line, the dark
        # tyre must stand clear of the lit floor around it.
        page.evaluate("() => { const R = window.__road;"
                      " R.setBody('SALOON'); R.showGarage(); }")
        page.wait_for_timeout(220)
        if args.falsify == 'floor':
            gone = page.evaluate(DROP_FLOOR)
            if not gone:
                raise SystemExit('[garage-card] --falsify floor found no floor rule to remove')
            page.wait_for_timeout(120)
        band = read_band(page)
        if not band:
            res.ok(False, 'the floor band could be measured', 'no card to photograph')
        else:
            # 1. there is a floor at all - the band is lighter than the card above it
            print('      floor %.1f  card %.1f  spread %.1f'
                  % (band['floor_lum'], band['card_lum'], band['spread']))
            # THIRTY, AND THE NUMBER WAS MEASURED RATHER THAN CHOSEN. At six this check
            # passed its own falsifier: the card's background is itself brighter at the
            # bottom than 70 pixels higher - 20.2 against 11.6 - so a gradient that was
            # always there cleared the bar with no floor drawn at all. With the floor the
            # same reading is 71.9 against 11.6. Thirty sits between 8.6 and 60.3 with room
            # on both sides.
            res.ok(band['floor_lum'] - band['card_lum'] >= 30,
                   'the card has a lit floor under the car',
                   "floor %.1f against card %.1f - that is the card's own gradient, not a floor"
                   % (band['floor_lum'], band['card_lum']))
            # 2. and the tyre stands clear of it. Without the floor every pixel in
            #    this band is near-black and the spread collapses.
            res.ok(band['spread'] >= 18,
                   'the tyres read against the floor',
                   'only %.1f between the darkest and the lit floor - they are one smear'
                   % band['spread'])

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
