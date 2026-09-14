#!/usr/bin/env python3
"""
GATE TEST - the shifter holds the gears the car has, and no others.

    .venv/Scripts/python tools/gate-test.py

RLG-069. The gate drew three rails and six slots for every car, and the knob's travel was clamped to
the length of the rail table rather than to the car - so a four-speed could be dragged into slots
labelled 5 and 6, and `gearFactor` returns zero past the end of the ratio table, which means the car
stopped pulling in a gear it does not have.

IT WALKS THE GATE WITH A THUMB, and it did not always. It used to walk with `API.shift(dx, dy)`, a
wrapper on `shiftStep`, and that broke twice without a sound (RLG-244):

  . THE THUMB DOES NOT GO THROUGH `shiftStep` (RLG-220). The knob's drag listener picks its own rail
    and slot, so a walk on `shiftStep` tests the keyboard path, which is out of scope and not what
    ships.
  . `API.shift` IS NOW A DIFFERENT FUNCTION. RLG-203 added the police shift's `API.shift()` later in
    `road.js`, and it overwrites the gearbox one. The walk then moved nothing, every car "reached"
    only the gear it was sitting in, and six checks failed for a reason none of them named.

So the walk holds a real pointer (`page.mouse`) on the knob, sweeps the cross rail from far left to
far right, and on every new rail it pulls hard up and hard down. It reads `API.gate()` - the
engine's own report - after each move. No rail position is computed here: the sweep finds the rails.

WHAT THIS FILE NO LONGER CHECKS, AND WHO DOES. The one-car-per-box rail and slot checks are in
`gate-rails-test.py`, by thumb, with falsifiers. The black knob's car list is in `knob-test.py`,
which reads `BODY_CLASS` as the oracle in both games; the list here was six cars and went stale when
the fleet had eight. This file keeps what neither covers: every gear of seven cars reached by thumb,
the gearbox bands, the plate sizes, and the white text on the working knob.

AND IT NEEDS A TOUCH CONTEXT. The shell adds `no-touch` to the body when the device reports no touch
and the whole thumb cluster is `display:none` under it - a desktop context measures a plate 0 pixels
wide and reports success.

`--falsify` serves one defect back, and names the checks that must fail:
  rails   the drag loop on `RAIL_X.length` (RLG-220): the rails-and-slots check.
  slots   `gateSlots` unfiltered, so every car has six slots: the gears check, on the five-speeds.
  lose    the drag loop one rail short: the gears check, on every car.
  below   the drag path without its slot check (RLG-236): the rails-and-slots check.
  white   the working knob's text rule deleted: the white-text check.
A check that cannot be made to fail is not evidence.

Exit code 0 if every check passed, 1 otherwise.
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

MID_Y = 33   # the cross rail's knob top, as `MID_Y` in road.js

# `--falsify` only: (file, text that must be there, what replaces it). `white` is not a file edit;
# see WHITE_RULE.
FALSIFY = {
    'rails': ('road.js', 'for(let i2=0;i2<railCount();i2++){',
              'for(let i2=0;i2<RAIL_X.length;i2++){'),
    'slots': ('road.js', 'function gateSlots(){ return SLOTS.filter(s => s.g <= gearCount()); }',
              'function gateSlots(){ return SLOTS; }'),
    'lose': ('road.js', 'for(let i2=0;i2<railCount();i2++){',
             'for(let i2=0;i2<railCount()-1;i2++){'),
    'below': ('road.js', '  if(wantY === BOT_Y && !gateSlots().some(s => s.rail === knobRail'
                         ' && s.y === BOT_Y)) wantY = MID_Y;', ''),
}

# `--falsify white` only. Deletes the working knob's text rule from the live document and returns
# how many rules it removed, so a falsifier that matched nothing cannot pass for a defect.
WHITE_RULE = r"""() => {
  let n = 0;
  for (const sh of Array.from(document.styleSheets)) {
    let rules;
    try { rules = sh.cssRules; } catch (e) { continue; }
    for (let i = rules.length - 1; i >= 0; i--) {
      if ((rules[i].selectorText || '').replace(/\s+/g, ' ') === 'body.workknob #knob b') {
        sh.deleteRule(i); n++;
      }
    }
  }
  return n;
}"""

GATE = '() => window.__probe.road.gate()'
PLATE = """() => {
  const k = document.getElementById('knob'), p = document.getElementById('shifter');
  if (!k || !p) return null;
  const a = k.getBoundingClientRect(), b = p.getBoundingClientRect();
  return { kx: a.left + a.width / 2, ky: a.top + a.height / 2,
           l: b.left, t: b.top, r: b.right, b: b.bottom };
}"""


def walk(page):
    """Walk the whole gate with a real pointer and report both ends of every rail it finds.

    NOT SYNTHESISED EVENTS. A `PointerEvent` with an invented `pointerId` makes the knob's
    `setPointerCapture` throw, the drag never arms, and every reading is the knob's resting place
    (RLG-220). `page.mouse` raises pointer events with a live id.

    The knob only changes rail on the cross rail, and it never skips the centre on the way up or
    down, so every vertical move goes in small steps and every sideways move happens at MID_Y.
    Returns a list of {rail, up, down, upY, downY}, or a string saying why no walk happened.
    """
    # THE DRAG HAS TO ARM, AND THAT IS PROVED, NOT ASSUMED. With five browsers running, a press
    # stopped reaching the knob. No drag armed, the knob rested on the cross rail through the
    # whole walk, and the readings looked like a gate with no bottom. The cause that was found is
    # the veil over the plate at the end of the run (see main); the knob's 90ms slide and the
    # cluster's slide when the plate widens are the other things a press can miss. So: wait until
    # nothing that moves the knob is animating, press, require the listener's own `grab`, and name
    # what is under the pointer if it never comes.
    for attempt in range(4):
        until(page, """() => { const k = document.getElementById('knob');
          return !!k && document.getAnimations().every(a =>
            a.playState !== 'running' || !a.effect || !a.effect.target
            || !a.effect.target.contains(k)); }""", timeout=5000, required=False)
        box = page.evaluate(PLATE)
        if not box or box['r'] - box['l'] <= 10:
            return 'the shifter has no box yet'
        page.mouse.move(box['kx'], box['ky'])
        page.mouse.down()
        if page.evaluate("() => document.getElementById('knob').classList.contains('grab')"):
            break
        page.mouse.up()
    else:
        hit = page.evaluate("""([x, y]) => { const e = document.elementFromPoint(x, y);
          return e ? (e.id || e.tagName) + '.' + e.className + ' "'
                     + (e.innerText || '').replace(/\\s+/g, ' ').slice(0, 60) + '"' : 'nothing'; }""",
                            [box['kx'], box['ky']])
        return 'the drag never armed (under the pointer: %s)' % hit
    top, bottom = box['t'] - 60, box['b'] + 80

    # FIND THE CROSS RAIL, do not assume it. Sweep down from above the plate and keep the rows
    # where the engine says the knob is on it. Its middle row is where every sideways move goes.
    #
    # TWICE, AND THE SECOND ON THE FIRST RAIL. On a rail with no slot below - a five-speed's
    # third - a pull down leaves the knob on the cross rail, so the rows run to the bottom of the
    # sweep and their middle is in the bottom zone. The first row found is always on the cross
    # rail, so the knob goes hard left along it, and the first rail has a bottom slot on every car.
    def cross_rows(x):
        rows, y = [], top
        while y <= bottom:
            page.mouse.move(x, y)
            if page.evaluate(GATE)['y'] == MID_Y:
                rows.append(y)
            y += 3
        return rows

    rows = cross_rows(box['kx'])
    if not rows:
        page.mouse.up()
        return 'the knob never reached the cross rail'
    x = box['l'] - 80
    page.mouse.move(box['kx'], rows[0], steps=6)
    page.mouse.move(x, rows[0], steps=10)
    rows = cross_rows(x)
    if not rows or rows[-1] + 3 > bottom:
        page.mouse.up()
        return 'the cross rail has no bottom edge on the first rail: %s' % rows[-1:]
    mid = rows[len(rows) // 2]

    seen, last = [], None
    page.mouse.move(x, mid, steps=10)
    while x <= box['r'] + 80:
        page.mouse.move(x, mid)
        g = page.evaluate(GATE)
        if g['y'] == MID_Y and g['rail'] != last:
            last = g['rail']
            page.mouse.move(x, top, steps=12)
            up = page.evaluate(GATE)
            page.mouse.move(x, mid, steps=8)
            page.mouse.move(x, bottom, steps=12)
            dn = page.evaluate(GATE)
            page.mouse.move(x, mid, steps=8)
            seen.append({'rail': up['rail'], 'up': up['gear'], 'upY': up['y'],
                         'down': dn['gear'], 'downY': dn['y'], 'downRail': dn['rail']})
        x += 3
    page.mouse.up()
    return seen


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
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + str(detail) + ']'))
        if not ok:
            self.fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--cars', default='SEMI,VAN,MUSCLE,ROADSTER,TUNER,CRUISER,SUPERCRUISER')
    ap.add_argument('--falsify', choices=sorted(FALSIFY) + ['white'],
                    help='serve one defect back; see the docstring for what must fail')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('gate-test  .  the gate holds the gears the car has')
    if args.falsify:
        print('  FALSIFY %s: one defect is served back.' % args.falsify)
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed, args=['--mute-audio'])
        ctx = browser.new_context(viewport={'width': 480, 'height': 900},
                                  has_touch=True, is_mobile=True)
        if args.falsify in FALSIFY:
            name, need, put = FALSIFY[args.falsify]
            src = (ROOT / name).read_text(encoding='utf-8')
            if need not in src:
                raise SystemExit('[gate-test] --falsify %s cannot find %r in %s'
                                 % (args.falsify, need, name))
            src = src.replace(need, put, 1)

            def fulfil(route):
                route.fulfill(status=200, content_type='application/javascript', body=src)
            ctx.route('**/' + name, fulfil)
        page = ctx.new_page()
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        for _ in range(4):
            if page.eval_on_selector('[data-act="box"] b',
                                     'el => el.textContent').strip().startswith('MANUAL'):
                break
            page.click('[data-act="box"]')
            page.wait_for_timeout(80)
        res.check(page.eval_on_selector('[data-act="box"] b',
                                        'el => el.textContent').strip().startswith('MANUAL'),
                  'the manual gearbox can be selected')
        page.click('[data-act="drive"]')
        # WAIT FOR THE PLATE TO HAVE A BOX, do not sleep and hope (RLG-220). A drag at a plate
        # with no layout yet lands on nothing, and every reading is the knob's resting place.
        until(page, "() => { const p = document.getElementById('shifter');"
                    " return !!p && p.getBoundingClientRect().width > 10; }", timeout=10000)

        # THE RUN MUST NOT END UNDER THE WALK. On a loaded machine seven thumb walks outlast the
        # run, the veil comes up over the plate, and every press after that lands on the veil and
        # reads as a gate that will not arm. The clock is turned off and the car held still:
        # neither touches the gate, and a car standing still cannot crash out either.
        page.evaluate('() => { const R = window.__probe.road; R.setTimed(false); R.holdSpd(0); }')

        g0 = page.evaluate(GATE)
        res.check(g0['manual'] and g0['plateW'] > 0,
                  'the gate is drawn on a touch device', str(g0))

        worst, stray, broken, widths, boxes = [], [], [], {}, {}
        for key in args.cars.split(','):
            page.evaluate('(k) => window.__probe.road.setBody(k)', key)
            page.wait_for_timeout(140)
            g = page.evaluate(GATE)
            # the plate follows the rails, and the comparison is between plates rather than
            # against a number: the element carries the UI scale, so its measured width is
            # not the width in the stylesheet.
            widths.setdefault(g['rails'], []).append((key, g['plateW']))
            boxes[key] = page.evaluate('(k) => window.__probe.road.gearBox(k)', key)
            seen = walk(page)
            if isinstance(seen, str) or not seen:
                broken.append('%s: %s' % (key, seen or 'the walk found no rail'))
                worst.append(broken[-1])
                continue
            gears = g['gears']
            reach = sorted({s['up'] for s in seen} | {s['down'] for s in seen})
            print('      %-13s %d-speed  %d rails  plate %.0fpx  rails %s  reaches %s'
                  % (key, gears, g['rails'], g['plateW'], [s['rail'] for s in seen], reach))
            # 0 is neutral; no gear above what the car has may be reached
            if max(reach) > gears:
                worst.append('%s (%d-speed) reaches %d' % (key, gears, max(reach)))
            # and every gear the car HAS must be reachable, or the gate has lost one
            missing = [n for n in range(1, gears + 1) if n not in reach]
            if missing:
                worst.append('%s (%d-speed) cannot reach %s' % (key, gears, missing))
            # THE KNOB RESTS ONLY WHERE THE GATE HAS A PLACE. A rail the car has not got, or a
            # slot the gate does not draw, reads as neutral - so the gears check above cannot see
            # it, and this one asks where the knob IS. The cross rail is always a place.
            slots = {(s['rail'], s['y']) for s in g['slots']}
            for s in seen:
                if s['rail'] >= g['rails']:
                    stray.append('%s on rail %d of %d' % (key, s['rail'], g['rails']))
                for rail, y in ((s['rail'], s['upY']), (s['downRail'], s['downY'])):
                    if y != MID_Y and (rail, y) not in slots:
                        stray.append('%s rests at rail %d y %d, which is no slot' % (key, rail, y))

        res.check(not worst, 'by thumb, no car reaches a gear it does not have, and none loses one',
                  '; '.join(worst))
        res.check(not broken and not stray,
                  'and the knob rests only on a rail the car has, in a slot or on the cross rail',
                  '; '.join(stray + broken))

        # ---- AND A SHORT BOX IS DESIGNED, NOT A LONG ONE CUT OFF (RLG-069) ----
        # Owner, 2026-08-30: the muscle car's first three gears are good and its fourth is
        # one long tedious grind. The table was the six-speed's first n gears with the last
        # one's ceiling forced to the top, so a four-speed's fourth ran from 0.41 to 1.00 -
        # fifty-nine per cent of the range in one gear, against 0.17 in first.
        #
        # THE CHECK IS THE RATIO BETWEEN THE LONGEST AND THE SHORTEST GEAR, not that the
        # bands grow. They grew on the broken table too - 0.17, 0.18, 0.21, 0.59 is
        # non-decreasing - so an assertion about growth would have agreed with the build
        # being complained about. What was wrong was HOW MUCH the top one grew by.
        spreads = []
        for key, box in sorted(boxes.items()):
            if not box:
                continue
            bands = [round(g['to'] - g['from'], 3) for g in box]
            ratio = max(bands) / min(bands)
            spreads.append((key, len(box), bands, ratio))
        for key, n, bands, ratio in spreads:
            print('      %-13s %d-speed bands %s  longest/shortest %.2f'
                  % (key, n, bands, ratio))
        bad = [(k, r) for k, n, b, r in spreads if r > 1.6]
        res.check(not bad,
                  'no gearbox has one gear carrying the road while the others sprint',
                  '; '.join('%s at %.2f' % (k, r) for k, r in bad))
        # and the box still covers everything, with somewhere for each shift to happen
        holes = []
        for key, n, bands, _ in spreads:
            box = boxes[key]
            if abs(box[0]['from']) > 1e-6 or abs(box[-1]['to'] - 1) > 1e-6:
                holes.append('%s does not span 0 to 1' % key)
            for a, b in zip(box, box[1:]):
                if b['from'] >= a['to']:
                    holes.append('%s has a gap between %d and %d' % (key, a['g'], b['g']))
        res.check(not holes, 'and every box covers the whole range, with the gears overlapping',
                  '; '.join(holes))
        two = [w for _, w in widths.get(2, [])]
        three = [w for _, w in widths.get(3, [])]
        res.check(len(set(two)) <= 1 and len(set(three)) <= 1,
                  'every plate with the same rails is the same size', str(widths))
        res.check(bool(two) and bool(three) and max(two) < min(three),
                  'a two-rail plate is smaller than a three-rail one',
                  '%s against %s' % (two, three))

        # ---- THE WORKING KNOB'S TEXT IS WHITE ----
        # WHICH cars carry the working knob is `knob-test.py`'s question, against BODY_CLASS in
        # both games. This asks only what that file does not: that the number on it is white.
        # The set is the engine's own - every body that puts `workknob` on the page - and it
        # must not be empty, or the check passes on a cabinet with no working knob at all.
        if args.falsify == 'white':
            if not page.evaluate(WHITE_RULE):
                raise SystemExit('[gate-test] --falsify white found no text rule to remove')
        whites = page.evaluate("""() => {
          const R = window.__probe.road, was = R.bodyKey(), out = {};
          const keys = [...new Set(R.fleet().map(v => v.key).filter(k => /^[A-Z]+$/.test(k)))];
          for (const k of keys) {
            R.setBody(k);
            if (document.body.classList.contains('workknob'))
              out[k] = getComputedStyle(document.querySelector('#knob b')).color;
          }
          R.setBody(was);
          return out;
        }""")
        print('      working knob: %s' % ', '.join(sorted(whites)))
        res.check(bool(whites) and all('255, 255, 255' in c or '242, 244, 248' in c
                                       for c in whites.values()),
                  'the working knob\'s text is white', str(whites))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(res.fails)) if res.fails else '\nall checks passed')
    return 1 if res.fails else 0


if __name__ == '__main__':
    sys.exit(main())
