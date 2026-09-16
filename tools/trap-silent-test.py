#!/usr/bin/env python3
"""TRAP SILENT - a parked speed trap makes no siren; an engaged cruiser does.

    .venv/Scripts/python tools/trap-silent-test.py
    .venv/Scripts/python tools/trap-silent-test.py --root <an older checkout> --expect-fail

RLG-269. Owner, 2026-09-16: "Speed traps have their sirens on. They should be silent with no
emergency lights unless they engage somebody."

THE LIGHTS WERE FIXED AND THE SOUND WAS NOT. RLG-253 made a parked trap dark in both views. The
siren's loudness comes from one loop over `cops` that asks only how far away the nearest car is, so a
trap on the verge wailed as the player drove past it.

IT READS THE VOICE, NOT THE CODE. `API.sirenNow()` returns the live oscillator, filter and gain of the
held siren voice, so what is measured is what the ear would get (RLG-065).

  PARKED   a trap from the road's own spawner, held 1,200 ahead - inside the 7,000 the siren
           listens over - and the siren gain must stay at nothing.
  ENGAGED  the same car with `trap` cleared, at the same distance: the gain must rise. Without this
           arm a build with the siren broken altogether would pass the first.

WHAT THIS CANNOT SAY. Whether the mix is right on a phone, and whether a siren that fades in at
7,000 units reads as approaching, are the owner's verdict on the device.

Exit code 0 if every check passed (or, with --expect-fail, if one failed), 1 otherwise.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from harness import console_utf8, launch_chromium, boot, until  # noqa: E402

ARM = """async (a) => {
  const R = window.__road;
  R.holdSpd(null); R.copsClear(); R.parkTraffic(9, 60000); R.heat(2);
  R.holdSpd(0.5 * R.MAX_SPD);
  R.spawnTrap();
  const cs = R.cops(); const k = cs[cs.length - 1];
  let peak = 0, frames = 0, sawTrap = null;
  const t0 = performance.now();
  await new Promise((done) => {
    const tick = () => {
      k.z = R.startLine().pos + R.PLAYER_Z + 1200;
      if(!a.parked){ k.trap = false; k.armed = false; k.spd = R.pursuit().mph / 200 * R.MAX_SPD; }
      sawTrap = !!k.trap;
      const s = R.sirenNow();
      if(s && typeof s.gain === 'number'){ peak = Math.max(peak, s.gain); frames++; }
      if(performance.now() - t0 < a.secs * 1000) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  R.holdSpd(null);
  return { peak: +peak.toFixed(4), frames, trap: sawTrap, voice: !!R.sirenNow() };
}"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--expect-fail', action='store_true')
    args = ap.parse_args()
    console_utf8()
    root = Path(args.root)
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(root)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('trap-silent  .  a parked trap makes no siren')
    print('      serving %s' % root)
    with sync_playwright() as p:
        # the siren is a held Web Audio voice, so the page needs audio to exist at all
        b = launch_chromium(p, headless=True, args=['--autoplay-policy=no-user-gesture-required'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        pg.click('[data-act="chase"]')      # HOT PURSUIT on
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => window.__road.setTimed(false)')

        parked = pg.evaluate(ARM, {'parked': True, 'secs': 3})
        engaged = pg.evaluate(ARM, {'parked': False, 'secs': 3})
        print('      PARKED   siren gain peaked at %s over %d frames (still a trap: %s)'
              % (parked['peak'], parked['frames'], parked['trap']))
        print('      ENGAGED  siren gain peaked at %s over %d frames'
              % (engaged['peak'], engaged['frames']))

        ok(parked['voice'] and parked['frames'] > 30, 'the siren voice exists to be measured',
           '%d frames read, voice %s' % (parked['frames'], parked['voice']))
        ok(engaged['peak'] > 0.0005, 'an engaged cruiser 1,200 ahead sounds its siren',
           'the gain peaked at %s' % engaged['peak'])
        ok(parked['peak'] <= engaged['peak'] * 0.1, 'and a parked trap at the same distance is silent',
           'parked %s against engaged %s' % (parked['peak'], engaged['peak']))

        ok(not errs, 'no page errors', errs[0][:120] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if args.expect_fail:
        print('expected at least one failure: %s' % ('got %d' % len(fails) if fails else 'got NONE'))
        return 0 if fails else 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('a parked trap makes no siren, and an engaged cruiser does')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
