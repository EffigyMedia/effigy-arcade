#!/usr/bin/env python3
"""SEE-THROUGH SHOT - captures of traffic standing in a biome full of scenery.

    .venv/Scripts/python tools/seethru-shot.py
    .venv/Scripts/python tools/seethru-shot.py --biomes FOREST --frames 8

Owner, 2026-09-12, from the device: "Cars (and pickup crates) can be seen through the scenery
again! Also weird rendering in the mirror."

AGAIN, because this is the second report of it. The first was 2026-09-07 - "cars are rendering
through scenery and the checkpoint signs" - and the fix was a far-to-near sort INSIDE a sprite
bucket, recorded in `paintBucket`. That sort orders the things in one bucket against each
other; the roadside goes out through `drawScenery`, which is a different pass entirely.

IT ASSERTS NOTHING. It is an instrument. A picture is the only thing that can settle whether a
car is in front of a tree it should be behind, and this project has already been told once that
a green run is not evidence about anything the tooling cannot see.

WHAT IT HOLDS STILL so two frames can be compared: the hour, the weather and the biome on both
ends of the blend. What it does NOT hold still is the traffic - the whole point is to have cars
on the road among the scenery, so the road is left to fill and the car is driven into it.
"""
import argparse
import base64
import functools
import http.server
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

GAME = 'games/sw/interstate.html'
# the biomes that actually STAND something beside the road. A desert with nothing in it cannot
# show a car drawn through scenery, because there is no scenery for it to be drawn through.
DEFAULT_BIOMES = 'FOREST,CITY'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--biomes', default=DEFAULT_BIOMES)
    ap.add_argument('--frames', type=int, default=6)
    ap.add_argument('--hour', type=float, default=0.5, help='0.5 is midday')
    ap.add_argument('--speed', type=float, default=0.45)
    ap.add_argument('--out', default='')
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()

    out = Path(args.out) if args.out else (ROOT / 'docs' / 'fleet' / '_seethru')
    out.mkdir(parents=True, exist_ok=True)

    dt_path = ROOT / 'tools' / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('dt', dt_path)
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print('seethru-shot  .  traffic among the scenery, %d frame(s) per biome' % args.frames)
    made = []
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=not args.headed, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg.wait_for_timeout(1600)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1500)

            for bio in [x.strip() for x in args.biomes.split(',') if x.strip()]:
                for i in range(args.frames):
                    pg.evaluate(
                        "([k, hour, spd]) => { const R = window.__probe.road;"
                        " R.setBiomePair(k, k); R.setPhase(hour);"
                        " R.setWet(0); R.setSnow(0); R.setPool(0);"
                        " R.setSpd(R.MAX_SPD * spd); }", [bio, args.hour, args.speed])
                    # let the road fill with traffic and carry it past the scenery
                    pg.wait_for_timeout(1400)
                    stats = pg.evaluate(
                        "() => { const R = window.__probe.road;"
                        " return R.spriteStats ? R.spriteStats() : null; }")
                    f = out / ('%s-%d.png' % (bio.lower(), i))
                    f.write_bytes(pg.screenshot())
                    made.append(f)
                    print('  %-8s frame %d  %s' % (bio, i, stats if stats else ''))
            if errs:
                print('  page errors: %s' % errs[0][:160])
            b.close()
    finally:
        srv.shutdown()
    print('  wrote %d file(s) to %s' % (len(made), out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
