"""WHERE A LIGHT BAR ACTUALLY SITS ON A SPRITE, measured rather than guessed.

    .venv/Scripts/python tools/bar-row.py

`barY` is the fraction down the sprite where the bar's lenses are, and the glow heads that
`drawPlayer` throws are placed from it. The note beside it in `road.js` says the two existing
values were SAMPLED from the built sprites - CRUISER rows 18-22 of 164, mid 0.122;
SUPERCRUISER rows 49-53 of 168, mid 0.304 - and that "any future force car declares its own".
A guessed value puts the glow off the bar, which is the exact defect that note records fixing.

HOW IT MEASURES, and the first draft did it wrong. Sniffing the built sprite for strong blue
and red pixels found nothing, because the sprite table is built lazily and because a colour
test has to know what colour to look for - which fails the moment a bar is not blue-and-red,
and an ambulance's is not. So it asks the LAMP DECLARATION instead: RLG-053 made every lamp a
named function that draws itself into any context, so `bar.rl` and `bar.rr` can be rendered
into a blank canvas and their rows read off. No colour knowledge, and it works for a scheme
nobody has invented yet.

IT PRINTS THE TWO KNOWN CARS AS A CONTROL. If CRUISER does not come back at about 0.122 and
SUPERCRUISER at about 0.304, the measurement is wrong and the new number it reports must not
be trusted either. The control is what makes this more than a number generator - it caught the
lazy-build fault above rather than reporting "no bar found" for a car that plainly has one.

Exit code 0 if the controls agree, 1 otherwise.
"""
import sys, threading, http.server, socketserver, functools

from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot, until
from playwright.sync_api import sync_playwright
console_utf8()

h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

MEASURE = """() => {
  const R = window.__road, out = {};
  const f = R.fleet();
  for (const v of f) {
    const spr = v.spr || v.sprite;
    if (!spr || !spr.lamps) continue;
    const ids = Object.keys(spr.lamps).filter(id => id.indexOf('bar.') === 0);
    if (!ids.length) continue;
    let lo = 1e9, hi = -1;
    for (const id of ids) {
      const c = document.createElement('canvas');
      c.width = spr.width; c.height = spr.height;
      const g = c.getContext('2d');
      const fn = spr.lamps[id];
      (fn.plain || fn)(g, 0);                      /* the UNLIT bulb: the lens itself */
      const d = g.getImageData(0, 0, c.width, c.height).data;
      for (let y = 0; y < c.height; y++) {
        for (let x = 0; x < c.width; x++) {
          if (d[(y * c.width + x) * 4 + 3] >= 40) {
            if (y < lo) lo = y;
            if (y > hi) hi = y;
            break;
          }
        }
      }
    }
    if (hi < 0) continue;
    const key = v.key || v.name;
    const face = (v.face || v.side || '');
    const rec = out[key] || (out[key] = []);
    rec.push({ face: face, first: lo, last: hi, h: spr.height,
               mid: +(((lo + hi) / 2) / spr.height).toFixed(3), ids: ids.length });
  }
  return out;
}"""

with sync_playwright() as p:
    b = launch_chromium(p, headless=True, args=['--mute-audio'])
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    boot(pg, f'http://127.0.0.1:{PORT}/games/sw/interstate.html')
    until(pg, '() => window.__road && window.__road.fleet', timeout=15000)
    pg.wait_for_timeout(1500)

    res = pg.evaluate(MEASURE)
    if errs:
        print('  page error:', errs[0])

    EXPECT = {'CRUISER': 0.122, 'SUPERCRUISER': 0.304}
    print()
    if not res:
        print('  no vehicle declared a bar lamp at all - the measurement is broken,')
        print('  not the sprites. Do not read this as "the ambulance has no bar".')
        okc = False
    else:
        okc = True
        for k in sorted(res):
            for r in res[k]:
                tag = f'{k} {r["face"]}'.strip()
                line = (f'  ..    {tag:<20} rows {r["first"]}-{r["last"]} of {r["h"]}'
                        f'   mid {r["mid"]}   ({r["ids"]} lens)')
                if k in EXPECT:
                    near = abs(r['mid'] - EXPECT[k]) <= 0.03
                    okc = okc and near
                    line = ('  ok  ' if near else '  FAIL') + line[6:] + \
                           f'   control, expected ~{EXPECT[k]}'
                print(line)
        for k in EXPECT:
            if k not in res:
                print(f'  FAIL  {k:<20} not measured at all - control missing')
                okc = False
    # ---- THE RED CROSS, IN THE THREE PLACES THE OWNER ASKED FOR IT ----------
    # Owner, 2026-09-05: on the nose, across the back doors "split down the middle
    # as if it's printed at the seam", and as the badge on the steering wheel.
    #
    # EACH CHECK COMPARES AGAINST THE PLAIN VAN, which is the same vehicle without
    # the livery. A check that only counted red pixels on the ambulance would pass
    # on any vehicle with a tail light in frame - the van is what makes the count
    # mean "cross" rather than "red".
    CROSS = """(k) => {
      const R = window.__road, out = {};
      const red = (c, x0f, x1f, y0f, y1f) => {
        if (!c) return -1;
        const g = c.getContext('2d');
        const d = g.getImageData(0, 0, c.width, c.height).data;
        const x0 = (c.width*x0f)|0, x1 = (c.width*x1f)|0;
        const y0 = (c.height*y0f)|0, y1 = (c.height*y1f)|0;
        let n = 0;
        for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
          const i = (y*c.width + x)*4;
          if (d[i+3] < 40) continue;
          if (d[i] > 150 && d[i+1] < 90 && d[i+2] < 90) n++;
        }
        return n;
      };
      const w = R.wheelOf(k);
      out.boss = red(w, 0.40, 0.60, 0.40, 0.60);
      for (const v of R.fleet()) {
        if ((v.key || v.name) !== k) continue;
        /* THE WINDOW IS THE PANEL, NOT THE CROSS. It is bounded in X to 0.30-0.70,
           which excludes the lamps at 0.07 and 0.855 outright - so Y can cover the
           whole body without letting a tail light count as livery. An earlier and
           tighter Y window (0.20-0.55) under-counted the rear cross by a third the
           moment it was lowered onto the handles, and would eventually have read
           zero for a cross that was drawn perfectly well. A check whose window has
           to be re-tuned every time the thing it measures moves is a check that
           will one day be re-tuned wrongly. */
        if (v.spr)   out.rear  = red(v.spr,   0.30, 0.70, 0.15, 0.85);
        if (v.front) out.front = red(v.front, 0.30, 0.70, 0.15, 0.85);
      }
      return out;
    }"""
    amb = pg.evaluate(CROSS, 'AMBULANCE')
    van = pg.evaluate(CROSS, 'VAN')

    def cross(label, key):
        a, v = amb.get(key, -1), van.get(key, -1)
        good = a > 20 and v == 0
        print(f'  {"ok  " if good else "FAIL"}  {label:<20} '
              f'ambulance {a} red px, plain van {v}')
        return good

    print()
    okx = cross('a cross on the nose', 'front')
    okx = cross('and across the doors', 'rear') and okx
    okx = cross('and on the wheel boss', 'boss') and okx

    print()
    print('  ' + ('the controls agree, so the measured numbers can be trusted'
                  if okc else 'A CONTROL IS WRONG - do not trust the numbers above'))
    if not okx:
        print('  the red cross is not where the owner asked for it')
    pg.close()
    b.close()
srv.shutdown()
sys.exit(0 if (okc and okx) else 1)
