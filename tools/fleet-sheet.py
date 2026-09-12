"""Draw the whole fleet - back, front, lamps and wipers - and save it as a picture.

RLG-053 made every lamp a DECLARATION: one drawing, run unlit into the sprite and again lit on top
of it. This renders that, and it is the check a person can make in a second - if a lit lamp is not
exactly on top of the bulb in the dark cell beside it, the declaration has drifted, which is the
fault the whole ruling exists to make impossible. `tools/lamp-test.py` asserts the same thing in
numbers; this is the version you can look at.

Each vehicle gets TWO rows, back then front, and the sheet ends with the steering wheels - one per
car, which nothing outside the cockpit has ever shown side by side.

  back    dark, braking, indicating right, indicating left, bar, all, striped
  front   dark, headlights, indicating right, indicating left, wipers parked, wipers swept, striped

A car is drawn in the paint it is ALLOWED to wear, which is white for almost all of them: a cab is
yellow, and each patrol car appears twice, once in each of the force's two liveries. The striped cell
is empty where a car already wears a livery of its own.

ONE ROW PER VEHICLE, NOT PER LIVERY. The garage car and the traffic car are the same painter with
different paint - there is no garage version of anything - so rows are grouped by painter and each
is named once.

Everything comes from the engine through `API.fleet()` and `API.wheelOf()`, so nothing here knows how
a car is painted and a body added later appears without this file being touched.
"""
import base64
import functools
import http.server
import importlib.util
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# ONE SHEET PER CLASS. A single picture of everything came out unreadable at any
# size that fits on a screen - the owner asked for them split, and a class is the
# grouping the fleet actually has rather than one invented for the page.
# THE LAST NAME HERE WAS `utility` AND NO SUCH CLASS EXISTS. The fleet resort made the non-racing
# vehicles one class called `traffic`, and this list was never moved with it - so every run printed
# "utility no vehicles in this class" and the VAN, the SEMI, the CAB, the PICKUP and the AMBULANCE
# have had no sheet at all since. A name that silently matches nothing is the worst kind of stale.
CLASSES = ['formula', 'super', 'sport', 'police', 'production', 'traffic']


def _handover():
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        pass
    for c in (ROOT / '.venv' / 'Scripts' / 'python.exe', ROOT / '.venv' / 'bin' / 'python'):
        if c.exists() and c.resolve() != Path(sys.executable).resolve():
            sys.exit(subprocess.run([str(c), str(Path(__file__).resolve())] + sys.argv[1:]).returncode)
    raise SystemExit('[fleet-sheet] playwright is not importable and there is no project .venv')


_handover()

from playwright.sync_api import sync_playwright   # noqa: E402
from harness import console_utf8, launch_chromium, boot  # noqa: E402


SHEET = r"""(cls) => {
  const R = window.__probe.road;
  const fleet = R.fleet().filter(v => v.cls === cls);
  if (!fleet.length) return null;

  const rows = [], by = {};
  for (const v of fleet) {
    if (by[v.sig] === undefined) { by[v.sig] = rows.length; rows.push(v); }
    else if (!rows[by[v.sig]].front && v.front) rows[by[v.sig]].front = v.front;
  }

  const CELL = 300, PAD = 18, LABEL = 240;
  const cols = 8;
  const W = LABEL + cols*CELL + PAD*2;
  const H = PAD*3 + 52 + rows.length*(CELL*2 + PAD*2) + CELL + PAD*4;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');

  g.fillStyle = '#0b0c10'; g.fillRect(0, 0, W, H);
  g.fillStyle = '#f0f2f6';
  g.font = '700 22px system-ui, sans-serif';
  g.fillText('EFFIGY ARCADE - ' + cls.toUpperCase(), PAD, PAD + 22);
  g.fillStyle = '#7c8199';
  g.font = '500 13px system-ui, sans-serif';
  g.fillText('every lamp is one drawing, run unlit into the sprite and again lit on top of it',
             PAD, PAD + 40);

  const cell = (spr, x, y, ids, wipeT, label, lvl) => {
    g.fillStyle = '#15171e';
    g.fillRect(x + 3, y + 3, CELL - 6, CELL - 6);
    if (label) {
      g.fillStyle = '#5f6579';
      g.font = '500 10px system-ui, sans-serif';
      g.fillText(label, x + 8, y + 15);
    }
    if (!spr) {
      g.fillStyle = '#2a2e39';
      g.font = '500 12px system-ui, sans-serif';
      g.fillText('none', x + CELL/2 - 14, y + CELL/2);
      return;
    }
    const s = Math.min((CELL - 22) / spr.width, (CELL - 22) / spr.height);
    const dw = spr.width*s, dh = spr.height*s;
    const dx = x + (CELL - dw)/2, dy = y + (CELL - dh)/2 + 6;
    g.drawImage(spr, dx, dy, dw, dh);
    g.save();
    g.translate(dx, dy); g.scale(dw/spr.width, dh/spr.height);
    if (ids && ids.length && spr.lamps) {
      /* NOT `lighter`. A lamp carries its own baked halo and paints its own
         lens opaquely (RLG-053), so adding the whole thing to the picture
         underneath is what turned a bright red brake light white. */
      g.save();
      for (const id of ids) if (spr.lamps[id]) spr.lamps[id](g, lvl === undefined ? 2 : lvl);
      g.restore();
    }
    /* the wipers are not a lamp: they are the same drawing at a different point
       in its sweep, so they are drawn normally rather than added */
    if (wipeT !== null && wipeT !== undefined && spr.wipers) {
      spr.wipers(g, wipeT);
      /* and whatever stands in FRONT of them goes back on top - the muscle
         car's blower is bodywork over the bottom of the screen, and without
         this the blades sweep across the front of a supercharger */
      if (spr.overWipers) spr.overWipers(g);
    }
    g.restore();
  };

  let y = PAD*2 + 46;
  for (const r of rows) {
    const back = r.spr, front = r.front;
    const bL = back.lamps || {}, fL = (front && front.lamps) || {};
    const bar = Object.keys(bL).filter(k => k.indexOf('bar.') === 0);
    const fbar = Object.keys(fL).filter(k => k.indexOf('bar.') === 0);

    g.fillStyle = '#e6e9f0';
    g.font = '600 16px system-ui, sans-serif';
    g.fillText(r.name, PAD, y + CELL - 6);
    g.fillStyle = '#5f6579';
    g.font = '500 10px system-ui, sans-serif';
    g.fillText(r.sig, PAD, y + CELL + 12);

    cell(back, LABEL + 0*CELL, y, [], null, 'back - dark');
    /* the three states of a rear lamp: off, the running light, the brake */
    cell(back, LABEL + 1*CELL, y, ['tail'], null, 'running (dim)', 1);
    cell(back, LABEL + 2*CELL, y, ['tail'], null, 'braking (bright)');
    cell(back, LABEL + 3*CELL, y, ['turn.r'], null, 'right');
    cell(back, LABEL + 4*CELL, y, ['turn.l'], null, 'left');
    cell(back, LABEL + 5*CELL, y, bar, null, bar.length ? 'bar' : '');
    cell(back, LABEL + 6*CELL, y, Object.keys(bL), null, 'all');
    /* stripes are paint rather than a body, and a car already wearing a livery
       does not take them - so this cell is empty for the formula car and for
       both patrol cars, which is the answer rather than a missing frame */
    cell(r.sprS, LABEL + 7*CELL, y, [], null, 'stripes');

    const y2 = y + CELL + PAD;
    cell(front, LABEL + 0*CELL, y2, [], 0, 'front - dark');
    cell(front, LABEL + 1*CELL, y2, ['head'], 0, 'headlights');
    cell(front, LABEL + 2*CELL, y2, ['turn.r'], 0, 'right');
    cell(front, LABEL + 3*CELL, y2, ['turn.l'], 0, 'left');
    cell(front, LABEL + 4*CELL, y2, fbar, 0, 'wipers parked');
    cell(front, LABEL + 5*CELL, y2, fbar, 1, 'wipers swept');
    cell(front, LABEL + 6*CELL, y2, Object.keys(fL), 0, 'all');
    cell(r.frontS, LABEL + 7*CELL, y2, [], 0, 'stripes');

    y += CELL*2 + PAD*2;
  }

  /* ---- and the wheel each of them is driven with ------------------------ */
  g.fillStyle = '#e6e9f0';
  g.font = '600 16px system-ui, sans-serif';
  g.fillText('THE WHEELS', PAD, y + 22);
  let wx = LABEL, wy = y;
  const shown = {};
  for (const v of rows) {
    /* two liveries of one patrol car are one car, and it has one wheel */
    if (shown[v.key || v.name]) continue;
    shown[v.key || v.name] = 1;
    const wheel = R.wheelOf(v.key || v.name);
    if (!wheel) continue;
    g.fillStyle = '#15171e';
    g.fillRect(wx + 3, wy + 3, CELL - 6, CELL - 6);
    const s = Math.min((CELL - 26) / wheel.width, (CELL - 26) / wheel.height);
    g.drawImage(wheel, wx + (CELL - wheel.width*s)/2, wy + (CELL - wheel.height*s)/2 + 6,
                wheel.width*s, wheel.height*s);
    g.fillStyle = '#8d93a8';
    g.font = '500 10px system-ui, sans-serif';
    g.fillText(v.key || v.name, wx + 8, wy + 15);
    wx += CELL;
    if (wx + CELL > W - PAD) { wx = LABEL; wy += CELL + PAD; }
  }
  return c.toDataURL('image/png');
}"""


def main():
    console_utf8()
    dt_path = Path(__file__).resolve().parent / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('dt', dt_path)
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            pg.wait_for_timeout(1600)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1500)
            made = []
            for cls in CLASSES:
                url = pg.evaluate(SHEET, cls)
                if not url:
                    print('  %-11s no vehicles in this class' % cls)
                    continue
                # they live in their own folder: six pictures beside the prose
                # is a folder you have to read past to find a document 
                out = ROOT / 'docs' / 'fleet' / ('%s.png' % cls)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(base64.b64decode(url.split(',', 1)[1]))
                made.append(out)
                print('  wrote %s (%d KB)' % (out.relative_to(ROOT), out.stat().st_size // 1024))
            if errs:
                print('  page errors: ' + errs[0][:140])
            b.close()
    finally:
        srv.shutdown()
    return 0 if made else 1


if __name__ == '__main__':
    sys.exit(main())
