"""Everything that can be behind you has a face.

The mirror draws the FRONT of a car, because a car behind you is coming at you. Three times a vehicle
has been found with no front sprite at all and fallen back to a coloured block: the racers, which are
keyed by body and paint rather than by traffic type; the police, which were excluded by a test in the
mirror itself; and, before both, every car in the game before the front painters existed.

Each one was found by eye, on a phone, weeks after it shipped. This asks the engine the same question
`drawMirrorFull` asks - what would you draw for this vehicle - for EVERY vehicle at once.

It also checks the sprite is a real picture rather than an empty canvas, because a blank sprite and a
missing one look identical in a mirror and only one of them is caught by a null test.
"""
import functools
import http.server
import importlib.util
import json
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _handover():
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        pass
    for c in (ROOT / '.venv' / 'Scripts' / 'python.exe', ROOT / '.venv' / 'bin' / 'python'):
        if c.exists() and c.resolve() != Path(sys.executable).resolve():
            sys.exit(subprocess.run([str(c), str(Path(__file__).resolve())] + sys.argv[1:]).returncode)
    raise SystemExit('[face-test] playwright is not importable and there is no project .venv')


_handover()

from playwright.sync_api import sync_playwright   # noqa: E402
from harness import console_utf8, launch_chromium, boot  # noqa: E402


# every case the mirror can be handed. The traffic types are what a traffic car carries as `type`;
# the body keys are what a racer carries as `body`; the last two are the police.
PROBE = r"""
() => {
  const R = window.__probe.road;
  const TRAFFIC = ['sedan','sedan2','coupe','tuner','muscle','pickup','van','taxi','truck'];
  const out = [];
  const look = (label, kind, paint) => {
    const spr = R.frontOf(kind, paint);
    if (!spr) { out.push({ name: label, ok: false, why: 'no sprite at all' }); return; }
    /* a blank canvas is not a face. Count pixels that are actually painted. */
    let ink = 0;
    try {
      const c = document.createElement('canvas');
      c.width = spr.width; c.height = spr.height;
      const g = c.getContext('2d');
      g.drawImage(spr, 0, 0);
      const d = g.getImageData(0, 0, c.width, c.height).data;
      for (let i = 3; i < d.length; i += 4) if (d[i] > 24) ink++;
    } catch (e) { out.push({ name: label, ok: false, why: 'unreadable: ' + e.message }); return; }
    const frac = ink / (spr.width * spr.height);
    out.push({ name: label, ok: frac > 0.02, why: (frac*100).toFixed(1) + '% painted',
               w: spr.width, h: spr.height });
  };
  for (const t of TRAFFIC) look('traffic ' + t, t);
  for (const v of R.fleet()) if (v.key && R.BODY[v.key] && !R.BODY[v.key].rigOnly) look('body ' + v.key, v.key);
  look('police cruiser', 'cop');
  look('police super cruiser', 'supercop');
  return out;
}
"""


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

    print('face-test  -  everything that can be behind you has a face')
    bad = []
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            pg.wait_for_timeout(1500)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1400)
            rows = pg.evaluate(PROBE)
            for r in rows:
                mark = 'ok  ' if r['ok'] else 'MISS'
                print('    %s  %-28s %s' % (mark, r['name'], r.get('why', '')))
                if not r['ok']:
                    bad.append(r['name'])
            if errs:
                print('    page errors: ' + errs[0][:140])
                bad.append('page error')
            b.close()
    finally:
        srv.shutdown()

    print()
    if bad:
        print('  %d vehicle(s) would be drawn as a block in the mirror: %s' % (len(bad), ', '.join(bad)))
        return 1
    print('  every vehicle in the game has a face  (%d checked)' % len(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
