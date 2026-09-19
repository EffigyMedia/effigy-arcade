#!/usr/bin/env python3
"""LADDER TEST - there is no radio: a wanted level sends no cruiser of its own.

    .venv/Scripts/python tools/ladder-test.py
    .venv/Scripts/python tools/ladder-test.py --root <an older checkout> --expect-fail

RLG-257. Owner, 2026-09-15: "I want to get rid of the radio. Only patrols and speed traps can add to
your engaged cruisers, they all obey the same slot allotment."

WHAT THIS FILE USED TO BE. It proved the opposite: that the radio (`spawnCop`, from 'radio') sent more
cars as heat rose, because for a long time that source was never called and nothing noticed. The
radio is now removed on purpose, and a wanted level buys police through the slots (RLG-256), which
tools/trap-slots-test.py proves. So this file now guards the removal.

THE CONDITIONS ARE THE RADIO'S OWN, so a radio that still existed would fire. At heat 3 and at heat 5
a cruiser is committed to the player 9,000 units back - inside LOST_AT, so it is "on" the player - and
the player is held at 72 % of top speed, faster than a cruiser, so it never catches up and ends the
run. Each level is watched for 25 seconds, longer than the radio's longest wait at those levels.

  NONE     `copCensus().sent` does not rise, and no car from 'radio' is on the road.
  LIVE     control: traps and patrols still put cruisers on the player in the same window, so a road
           that had no police at all would not pass.

WHAT THIS CANNOT SAY. Whether a pursuit without the radio has enough police in it is the owner's
verdict on the device.

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
from harness import console_utf8, launch_chromium, boot, until, garage_screen  # noqa: E402

SECS = 25


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
    print('ladder-test  .  there is no radio')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        # the drive's settings are on the SETTINGS screen (RLG-071)
        garage_screen(pg, 'settings')
        pg.click('[data-act="chase"]')      # HOT PURSUIT on
        garage_screen(pg, 'main')
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => window.__road.setTimed(false)')

        total_radio, total_other = 0, 0
        for level in (3, 5):
            pg.evaluate('(h) => { const R = window.__road; R.copsClear(); R.heat(h);'
                        ' if(R.commitCop) R.commitCop("player", -9000);'
                        ' else R.cops().push({ z: R.startLine().pos + R.PLAYER_Z - 9000, x: 0, spd: 0,'
                        '   wreck:0, ang:0, grace:0, cool:1, side:1, w:0.27, len:400, phase:0, dmg:0,'
                        '   from:"test", engaged:true, onPlayer:true, tgt:null }); }', level)
            sent0 = pg.evaluate('() => window.__road.copCensus().sent')
            radio_seen, other = 0, set()
            for _ in range(SECS * 4):
                pg.evaluate('(h) => { const R = window.__road; R.setSpd(0.72 * R.MAX_SPD); R.heat(h); }', level)
                pg.wait_for_timeout(250)
                got = pg.evaluate("""() => { const cs = window.__road.cops().filter(k => k.wreck <= 0 && !k.trap);
                    cs.forEach(k => { if(k.__id === undefined) k.__id = Math.random(); });
                    return { radio: cs.filter(k => k.from === 'radio').length,
                             other: cs.filter(k => k.from === 'trap' || k.from === 'patrol').map(k => k.__id) }; }""")
                radio_seen = max(radio_seen, got['radio'])
                other.update(got['other'])
            sent = pg.evaluate('() => window.__road.copCensus().sent') - sent0
            print('      heat %d: radio sent %d, at most %d radio cars out; %d cruisers from traps and patrols'
                  % (level, sent, radio_seen, len(other)))
            total_radio += sent + radio_seen
            total_other += len(other)

        ok(total_radio == 0, 'the radio sends nothing at heat 3 or heat 5 with a cruiser on the player',
           '%d radio dispatches or cars seen' % total_radio)
        ok(total_other > 0, 'control: traps and patrols still put cruisers on the player',
           'none in %d seconds' % (SECS * 2))
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
    print('there is no radio')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
