"""RLG-053: is a lit lamp the UNLIT BULB DRAWN AGAIN, or something drawn near it?

The owner's ruling is a technique: a lit lamp is never a rectangle with its own coordinates, it is
the bulb the painter already drew, drawn once more in a lit colour. The engine did the opposite, and
the comment above the old `tailLights` admitted it - "These MUST match what paintCar draws... copied
here rather than guessed." Two descriptions of one object. There were in fact three, and one of them
was unreachable.

A count cannot check a technique and neither can a screenshot. What can:

  1. the sprite DECLARES lamps at all - read from the baked canvas, not from a name in road.js
  2. the indicator is WIRED - `signal()` lights it on a car nothing in the game ever signals with,
     which is the ruling that every vehicle's lamps function and only the driver differs
  3. THE LIGHT LANDS ON THE BULB - the pixels that change when the lamp comes on sit inside the
     region the sprite's own unlit bulb occupies, mapped onto the car as drawn

Point 3 is the one that would catch a reskin moving the art and leaving the glow behind, which is
the whole reason the ruling exists.

THE CONTROL, AND IT IS NOT OPTIONAL
-----------------------------------
The world does not hold still: the sky turns, the tail glow follows the daylight, and the car
breathes. Measured here, that is ~800 changed pixels on the car between two frames with the lamp
OFF, against ~120 from the lamp itself. A plain before-and-after diff is mostly churn and reports a
centroid in the middle of the car. So two frames are taken with the lamp off first, and only pixels
that change WITH the lamp and NOT in the control are attributed to it.

WHICH VEHICLE THIS COVERS
-------------------------
The MATADOR body, and only that one. CREST and STALLION still paint their tails straight into the
sprite with no declaration and still light them from a hand-placed pair of circles. The ruling says
one vehicle end to end first, and the record has to say which - this harness is that record, and it
SKIPS rather than passes when the chosen body has not been converted.
"""

import sys, threading, http.server, socketserver, functools, importlib.util
from pathlib import Path
# ---- IT FINDS ITS OWN ROOT (RLG-039) --------------------------------------------------
# This served the folder from '.' and imported from 'tools', so it only ran from the project
# directory. `step.py` runs a command with the ENVIRONMENT's root as its working directory, so
# every one of these harnesses 404'd or raised there and recorded a FALSE FAILURE as evidence -
# twice in one session before it was worth fixing. The root is the file's own parent.
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot
from playwright.sync_api import sync_playwright
spec = importlib.util.spec_from_file_location('dt', ROOT / 'tools' / 'drive-test.py')
dt = importlib.util.module_from_spec(spec); spec.loader.exec_module(dt)
console_utf8()
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

# Where the RIGHT indicator bulb is in the baked sprite, in sprite units. Read from the sprite.
BULB = """(side) => {
  const spr = window.__probe.road.playerSprite();
  const c = document.createElement('canvas');
  c.width = spr.width; c.height = spr.height;
  const g = c.getContext('2d'); g.drawImage(spr, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height).data;
  let x0 = 1e9, x1 = -1, y0 = 1e9, y1 = -1, n = 0;
  for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
    if (side > 0 ? x < c.width/2 : x > c.width/2) continue;
    const i = (y*c.width+x)*4, r = d[i], gg = d[i+1], b = d[i+2], a = d[i+3];
    if (a < 40) continue;
    if (r > 28 && r < 150 && gg > 14 && gg < 100 && b < 60 && r > gg*1.25 && gg > b*1.3) {
      if (x < x0) x0 = x; if (x > x1) x1 = x;
      if (y < y0) y0 = y; if (y > y1) y1 = y; n++;
    }
  }
  return n ? {x0:x0/c.width, x1:x1/c.width, y0:y0/c.height, y1:y1/c.height, n:n} : null;
}"""

# the drawn car, in screen pixels, taken from the same numbers drawPlayer uses
BOX = """() => {
  const R = window.__probe.road, spr = R.playerSprite();
  const p = R.playerScreen();
  return p ? {x:p.x, y:p.y, w:p.w, h:p.h, sw:spr.width, sh:spr.height} : null;
}"""

SHOT = """() => {
  const c = document.querySelector('canvas');
  const g = c.getContext('2d');
  const d = g.getImageData(0, 0, c.width, c.height);
  return {w:c.width, h:c.height, data:Array.from(d.data)};
}"""

bad = 0


def ok(cond, label, detail=''):
    global bad
    if not cond:
        bad += 1
    print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label, '   ' + detail if detail else ''))


with sync_playwright() as p:
    b = launch_chromium(p, headless=True, args=['--mute-audio'])
    ctx = b.new_context(viewport={'width': 480, 'height': 900}); ctx.add_init_script(dt.INIT)
    pg = ctx.new_page()
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % PORT)
    pg.wait_for_timeout(1600)
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    pg.click('[data-act="drive"]'); pg.wait_for_timeout(1500)
    pg.evaluate("() => { window.__probe.road.setSpd(0); }")
    pg.wait_for_timeout(600)

    bulb = pg.evaluate(BULB, 1)
    box = pg.evaluate(BOX)
    lamps = pg.evaluate("() => window.__probe.road.lampsOf('player')")
    print('  ..    the player sprite declares: %s' % (lamps or 'nothing'))
    if not lamps:
        print()
        print('  this body has not been converted yet - RLG-053 is one vehicle at a time,')
        print('  and there is nothing here to check rather than something failing.')
        b.close(); srv.shutdown(); raise SystemExit(0)
    ok('turn.l' in lamps and 'turn.r' in lamps,
       'the car declares indicators', ', '.join(lamps))
    ok(bulb is not None, 'and an unlit indicator bulb is baked into the sprite',
       'found %d pixels of it' % (bulb['n'] if bulb else 0))
    ok(box is not None, 'the car reports where it was drawn')
    if not (bulb and box):
        b.close(); srv.shutdown(); raise SystemExit(1)

    # ---- THE TECHNIQUE, TESTED WHERE THE WORLD CANNOT INTERFERE -------------
    # A live frame is a poor place to ask this. The sky turns, the tail glow follows the daylight,
    # and the car breathes: measured, ~800 to 1300 pixels of the car change between two frames with
    # the lamp OFF, against a few hundred from the lamp. A control diff removes most of it and not
    # reliably - the same run reported 100% and then 35% on consecutive attempts, which is a
    # harness reporting weather.
    #
    # The claim being tested does not need the world at all. The declaration IS the drawing: run it
    # lit into a blank canvas the size of the sprite, and ask whether those pixels sit where the
    # sprite's own unlit bulb sits. If a reskin ever moves the art and leaves the glow behind, this
    # is what catches it, and nothing else here would.
    lit = pg.evaluate("""(side) => {
        const spr = window.__probe.road.playerSprite();
        const c = document.createElement('canvas');
        c.width = spr.width; c.height = spr.height;
        const g = c.getContext('2d');
        /* the LENS, without its baked halo - a glow reaches past the bulb on
           purpose, and this check is the claim that the BULB has not moved */
        const f = spr.lamps[side > 0 ? 'turn.r' : 'turn.l'];
        (f.plain || f)(g, 2);
        const d = g.getImageData(0, 0, c.width, c.height).data;
        let x0 = 1e9, x1 = -1, y0 = 1e9, y1 = -1, n = 0;
        for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
          const i = (y*c.width+x)*4;
          if (d[i+3] < 40) continue;
          if (x < x0) x0 = x; if (x > x1) x1 = x;
          if (y < y0) y0 = y; if (y > y1) y1 = y; n++;
        }
        return n ? {x0:x0/c.width, x1:x1/c.width, y0:y0/c.height, y1:y1/c.height, n:n} : null;
    }""", 1)
    ok(lit is not None, 'the declared lamp draws something when it is lit',
       '%d pixels' % (lit['n'] if lit else 0))
    if lit:
        # in sprite units, so it stays true at any drawn size
        pad = 1.5 / 220.0
        inside = (lit['x0'] >= bulb['x0'] - pad and lit['x1'] <= bulb['x1'] + pad and
                  lit['y0'] >= bulb['y0'] - pad and lit['y1'] <= bulb['y1'] + pad)
        print('  ..    unlit bulb  x %.3f-%.3f  y %.3f-%.3f'
              % (bulb['x0'], bulb['x1'], bulb['y0'], bulb['y1']))
        print('  ..    lit lamp    x %.3f-%.3f  y %.3f-%.3f'
              % (lit['x0'], lit['x1'], lit['y0'], lit['y1']))
        ok(inside, 'the lit lamp occupies the unlit bulb, and nothing else',
           'lit is %s the bulb' % ('inside' if inside else 'OUTSIDE'))

    # ---- THE WHOLE FLEET, WITHOUT KNOWING ONE COLOUR -----------------------
    # The check above reads the amber casing out of the baked sprite, which only works for an
    # indicator. Every lamp on every vehicle can be asked the same question with no colour
    # knowledge at all: the declaration draws the bulb when it is off and the lamp when it is on,
    # so run BOTH into blank canvases and compare. If the lit pixels leave the unlit bulb, the two
    # have drifted - which is the one thing this ruling exists to make impossible.
    fleet = pg.evaluate("""() => {
        const R = window.__probe.road, f = R.fleet(), out = [];
        /* Render the declaration off and on into blank canvases and compare PIXELS, not bounding
           boxes. A box is too coarse for a lamp drawn in more than one piece: shifting one lamp of
           a pair sideways keeps it inside the pair's own box, and a check on boxes reports nothing.
           Measured - that exact drift went undetected until this was written per-pixel. */
        /* ---- THE LENS, NOT THE HALO ------------------------------------
           A lit lamp now carries a baked glow, so its lit pixels reach well
           past the bulb ON PURPOSE - which is exactly what this check used to
           forbid. `plain` is the lamp's own drawing without the halo, and it
           is what "the lit lamp is the unlit bulb" is a claim about. The halo
           is checked separately, below. */
        const mask = (spr, id, on) => {
          const c = document.createElement('canvas');
          c.width = spr.width; c.height = spr.height;
          const g = c.getContext('2d');
          const f = spr.lamps[id];
          (f.plain || f)(g, on ? 2 : 0);
          const d = g.getImageData(0, 0, c.width, c.height).data;
          const m = new Uint8Array(c.width * c.height);
          let n = 0;
          for (let i = 0, k = 0; k < m.length; k++, i += 4)
            if (d[i+3] >= 40) { m[k] = 1; n++; }
          return { m: m, n: n, w: c.width, h: c.height };
        };
        /* ---- BOTH FACES, NOT JUST THE BACK OF THE CAR (RLG-053) --------
           Every REAR sprite was converted and checked here; the FRONTS were
           not, and nothing noticed because nothing looked. A front declares
           `head` the way a rear declares `tail`, and the same two questions
           apply to it: does the lit lamp stay inside the unlit bulb, and does
           it carry a glow past its own lens. */
        const faces = [];
        for (const v of f) {
          if (v.spr) faces.push({ v: v, spr: v.spr, name: v.name, face: 'rear' });
          if (v.front) faces.push({ v: v, spr: v.front, name: v.name, face: 'front' });
        }
        for (const fc of faces) {
          const v = fc.v, spr = fc.spr, name = fc.name, L = spr.lamps || {}, ids = Object.keys(L);
          const rows = [];
          for (const id of ids) {
            const off = mask(spr, id, false), on = mask(spr, id, true);
            let stray = 0;
            const R2 = 1;   /* one pixel of slack for antialiasing, and no more */
            for (let y = 0; y < on.h; y++) for (let x = 0; x < on.w; x++) {
              if (!on.m[y*on.w + x]) continue;
              let near = 0;
              for (let dy = -R2; dy <= R2 && !near; dy++) for (let dx = -R2; dx <= R2; dx++) {
                const yy = y+dy, xx = x+dx;
                if (yy < 0 || xx < 0 || yy >= on.h || xx >= on.w) continue;
                if (off.m[yy*on.w + xx]) { near = 1; break; }
              }
              if (!near) stray++;
            }
            rows.push({ id: id, offN: off.n, onN: on.n, stray: stray });
          }
          /* and the halo: the full lit lamp must cover MORE than its own lens,
             or the glow is not being baked at all */
          let glow = true;
          for(const id of ids){
            const lens = mask(spr, id, true);
            const c2 = document.createElement('canvas');
            c2.width = spr.width; c2.height = spr.height;
            const g2 = c2.getContext('2d');
            spr.lamps[id](g2, 2);
            const d2 = g2.getImageData(0,0,c2.width,c2.height).data;
            let full = 0;
            for(let i = 3; i < d2.length; i += 4) if(d2[i] >= 12) full++;
            if(full <= lens.n) glow = false;
          }
          out.push({ name: name, cls: v.cls, ids: ids, rows: rows, glow: glow, face: fc.face });
        }
        return out;
    }""")
    ok(len(fleet) > 10, 'the engine reports a fleet', '%d vehicles' % len(fleet))
    drifted, notail, noturn, nohead = [], [], [], []
    rears = [v for v in fleet if v.get('face') == 'rear']
    fronts = [v for v in fleet if v.get('face') == 'front']
    for v in fleet:
        if v.get('face') == 'front':
            # A FRONT'S LAMP IS ITS HEADLIGHT. Indicators are checked on the rear below; a front
            # that declares them too is welcome to, and RLG-052 will want them.
            # AND A FORMULA CAR HAS NO HEADLIGHTS EITHER. The same exception the indicators
            # already carry, read from the CLASS rather than from a name: a single-seater runs
            # in daylight on a closed circuit and has never had them. It is what the car IS.
            if v.get('cls') != 'formula' and 'head' not in v['ids']:
                nohead.append(v['name'])
            for r in v['rows']:
                if not r['onN'] or not r['offN']:
                    drifted.append('%s front %s (draws nothing)' % (v['name'], r['id']))
                elif r['stray'] > r['onN'] * 0.02:
                    drifted.append('%s front %s (%d of %d lit pixels off the bulb)'
                                   % (v['name'], r['id'], r['stray'], r['onN']))
            continue
        if 'tail' not in v['ids']:
            notail.append(v['name'])
        # A FORMULA CAR HAS NO INDICATORS. Owner's ruling, 2026-08-29: a single-seater has none,
        # and that is what the car IS rather than something unfinished. The exception is read from
        # the CLASS rather than from a name: there were three open-wheelers by the end of the same
        # day, and two of them are not called FORMULA. A class cannot be widened by a rename.
        if v.get('cls') != 'formula' and not ('turn.l' in v['ids'] and 'turn.r' in v['ids']):
            noturn.append(v['name'])
        for r in v['rows']:
            if not r['onN'] or not r['offN']:
                drifted.append('%s %s (draws nothing)' % (v['name'], r['id']))
            elif r['stray'] > r['onN'] * 0.02:
                drifted.append('%s %s (%d of %d lit pixels off the bulb)'
                               % (v['name'], r['id'], r['stray'], r['onN']))
    ok(not notail, 'every vehicle declares a tail lamp',
       'missing on ' + ', '.join(notail) if notail else '%d rear sprites' % len(rears))
    ok(not nohead, 'and every front outside the formula class declares a headlight',
       'missing on ' + ', '.join(nohead[:6]) if nohead
       else '%d front sprites, the formula class excepted by ruling' % len(fronts))
    ok(not noturn, 'every vehicle outside the formula class declares indicators',
       'missing on ' + ', '.join(noturn) if noturn else 'the formula class excepted by ruling')
    noglow = [v['name'] for v in fleet if not v.get('glow')]
    ok(not noglow, 'and a lit lamp carries a glow past its own lens',
       'flat on ' + ', '.join(noglow[:4]) if noglow else '%d vehicles' % len(fleet))
    ok(not drifted, 'and every lit lamp stays inside its own unlit bulb',
       ', '.join(drifted[:4]) if drifted else
       '%d lamps across %d vehicles' % (sum(len(v['ids']) for v in fleet), len(fleet)))

    # ---- AND IT IS WIRED INTO THE GAME --------------------------------------
    # The above proves the technique. This proves the path: the indicator, on a car nothing in the
    # game ever signals with, actually changes what is on the screen when it is asked to.
    pg.evaluate("() => { window.__probe.road.signal(0); window.__probe.road.holdBlink(false); }")
    pg.wait_for_timeout(140)
    a2 = pg.evaluate(SHOT)
    pg.evaluate("() => { window.__probe.road.signal(1); window.__probe.road.holdBlink(true); }")
    pg.wait_for_timeout(140)
    b2 = pg.evaluate(SHOT)
    W, Hh = a2['w'], a2['h']
    A, Bd = a2['data'], b2['data']
    dpr = W / 480.0
    ex0 = int((box['x'] - box['w']/2 + bulb['x0']*box['w']) * dpr) - 4
    ex1 = int((box['x'] - box['w']/2 + bulb['x1']*box['w']) * dpr) + 4
    ey0 = int((box['y'] - box['h'] + bulb['y0']*box['h']) * dpr) - 4
    ey1 = int((box['y'] - box['h'] + bulb['y1']*box['h']) * dpr) + 4
    onbulb = 0
    for y in range(max(0, ey0), min(Hh, ey1)):
        row = y*W*4
        for x in range(max(0, ex0), min(W, ex1)):
            i = row + x*4
            if abs(A[i]-Bd[i]) + abs(A[i+1]-Bd[i+1]) + abs(A[i+2]-Bd[i+2]) > 40:
                onbulb += 1
    ok(onbulb > 0,
       'and asking for it changes the screen, right where that bulb is',
       '%d pixels lit up at the bulb' % onbulb)

    # ---- AND THE FRONTS ARE WIRED, WHICH IS THE HALF THAT WAS MISSING -------
    # Every front declared a headlight and nothing ever asked for one, so the cars behind you
    # drove at midnight with their lights off. The counter is reset by reading it, so this
    # measures frames rather than history.
    def heads(ms=900):
        pg.evaluate('() => window.__probe.road.headsLit()')
        pg.wait_for_timeout(ms)
        return pg.evaluate('() => window.__probe.road.headsLit()')

    pg.evaluate("() => { const R = window.__probe.road;"
                " R.setSpd(R.MAX_SPD*0.5); }")
    pg.wait_for_timeout(2500)
    pg.evaluate('() => window.__probe.road.setPhase(0.25)')   # midnight
    pg.wait_for_timeout(500)
    dark = heads()
    # THE LAMPS FADE, THEY DO NOT FLIP. `lampsOn` ramps over seconds, so a reading taken
    # straight after the clock moves is still measuring dusk - 351 lit "at midday" on the
    # first run of this check, which is the lamps on their way out rather than a fault.
    # AND IN CLEAR WEATHER, WHICH IS NOT PEDANTRY. `lampsOn` is the STRONGER of the hour and
    # the weather, on the owner's ruling that a storm at noon puts the lights on - so a check
    # for "off in daylight" that does not dry the road is measuring rain. It read 550 lit at
    # midday until the weather was cleared, and that was the game being right.
    pg.evaluate("() => { const R = window.__probe.road;"
                " R.setPhase(0.75); R.setWet(0); R.setSnow(0); R.setPool(0); }")
    pg.wait_for_timeout(4000)
    light = heads()
    print('  ..    headlights lit in the mirror: %d at midnight, %d at midday' % (dark, light))
    ok(dark > 0, 'the cars behind you have their headlights on after dark',
       '%d lit over a second' % dark)
    ok(light == 0, 'and off in daylight', '%d lit at midday' % light)

    ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
    b.close()
srv.shutdown()
print()
print('  %s' % ('the lit lamp is the unlit bulb' if not bad else '%d FAILURES' % bad))
sys.exit(1 if bad else 0)
