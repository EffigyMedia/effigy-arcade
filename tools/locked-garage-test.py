#!/usr/bin/env python3
"""LOCKED GARAGE - a car you do not own offers the arrows to another car and the way out, and nothing else.

    .venv/Scripts/python tools/locked-garage-test.py

RLG-223. Owner, 2026-09-12: "If you don't have a car unlocked we don't wanna show any options in the
garage other than changing car."

OWNERSHIP IS ASKED OF `playableBodies`, NOT OF THE CARD. RLG-223 records that two earlier harnesses
asked the wrong instrument: one read the card's `???` name and passed with the unlock migration
deleted, and one read garage MEMBERSHIP and passed with the sports cars open. A locked car here is
one `garageBodies` lists and `playableBodies` does not.

WHAT EACH CHECK WOULD CATCH

    only the picker   the controls on screen for a locked car are exactly prev, next and back. A
                      build that greys the controls instead of removing them still has their
                      `data-act` in the page, so it fails.
    card still there  paired with the above: a garage that failed to render would also have
                      "no options", so the silhouette's `???` name must be present.
    arrows work       pressing next leaves the locked car. The picker must not be decoration.
    arrows share row  with the gearbox button gone, the two arrows fill the row between them
                      rather than standing as two 46 px squares.
    arrows stay put   the arrows on a locked car are at the height an owned car put them, so
                      tapping through the fleet does not move the button under the thumb.
    owned car full    an owned car still has DRIVE, CUSTOMISE CAR, SETTINGS and MODE, so the rule
                      has not removed the garage for everybody. The paint and the gearbox are one
                      screen further in since RLG-071 (owner, 2026-09-19), behind those two.

Both driving cabinets are walked, because Motorsport adds its own QUALIFY button through
`CFG.garageButtons` and that must go too.

Exit code 0 if every check passes, 1 otherwise.
"""

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot  # noqa: E402

ACTS = """() => Array.from(document.querySelectorAll('#veil:not(.hidden) [data-act]'))
  .map(b => b.dataset.act.indexOf('paint:') === 0 ? 'paint' : b.dataset.act)"""

WIDTHS = """() => {
  const r = s => { const b = document.querySelector('#veil:not(.hidden) [data-act="' + s + '"]');
                   return b ? b.getBoundingClientRect() : { width: 0, top: -1 }; };
  return { prev: r('prev').width, next: r('next').width, top: r('prev').top };
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    console_utf8()
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d' % httpd.socket.getsockname()[1]
    fails = []

    def ok(good, label, detail=''):
        print(('  ok    ' if good else '  FAIL  ') + label + ('' if good else '   [' + detail + ']'))
        if not good:
            fails.append(label)

    print('locked-garage  .  a car you do not own shows only the way to another car')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        for cab in ('interstate', 'motorsport'):
            print('  -- %s' % cab)
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            page = ctx.new_page()
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)))
            boot(page, '%s/games/sw/%s.html' % (base, cab))
            page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            page.click('[data-act="play"]')
            page.wait_for_selector('#veil:not(.hidden) [data-act="back"]', timeout=5000)
            page.wait_for_timeout(250)

            cars = page.evaluate("() => { const R = window.__road;"
                                 " const own = R.playableBodies();"
                                 " return { own: own,"
                                 "   locked: R.garageBodies().filter(k => own.indexOf(k) < 0) }; }")
            if not cars['locked'] or not cars['own']:
                ok(False, 'a fresh save has both a locked and an owned car',
                   'locked %d, owned %d' % (len(cars['locked']), len(cars['own'])))
                ctx.close()
                continue

            # the garage opens on an owned car; this is where its arrows are
            owned_top = page.evaluate(WIDTHS)['top']
            k = cars['locked'][0]
            page.evaluate("(k) => { const R = window.__road; R.setBody(k); R.showGarage(); }", k)
            page.wait_for_timeout(200)
            acts = page.evaluate(ACTS)
            ok(sorted(acts) == ['back', 'next', 'prev'],
               'locked %s offers only prev, next and back' % k,
               'on screen: %s' % ', '.join(acts))
            name = page.evaluate("() => { const n = document.querySelector('.gname');"
                                 " return n ? n.textContent.trim() : null; }")
            ok(name == '???', 'and its card is still drawn, as a locked card',
               'card name %r - with no card, "no options" proves nothing' % name)
            wd = page.evaluate(WIDTHS)
            ok(wd['prev'] > 100 and abs(wd['prev'] - wd['next']) <= 2,
               'and the two arrows share the row',
               'prev %.0f px, next %.0f px' % (wd['prev'], wd['next']))
            # THE OWNER CHOSE TO KEEP THE ARROWS STILL. Without the padding they sat about
            # 100 px lower on a locked car, so tapping through the fleet moved the button.
            ok(owned_top > 0 and abs(wd['top'] - owned_top) <= 2,
               'and they sit where an owned car puts them',
               'owned %.0f px, locked %.0f px from the top' % (owned_top, wd['top']))

            page.click('#veil:not(.hidden) [data-act="next"]')
            page.wait_for_timeout(250)
            now = page.evaluate("() => window.__road.body()")
            ok(now != k, 'pressing next leaves the locked car', 'still on %s' % now)

            own = cars['own'][0]
            page.evaluate("(k) => { const R = window.__road; R.setBody(k); R.showGarage(); }", own)
            page.wait_for_timeout(200)
            acts = page.evaluate(ACTS)
            missing = [a for a in ('drive', 'custom', 'settings', 'mode', 'prev', 'next', 'back') if a not in acts]
            ok(not missing, 'owned %s keeps the whole garage' % own,
               'missing: %s' % ', '.join(missing))
            if cab == 'motorsport':
                ok('qualify' in acts, 'and Motorsport keeps QUALIFY on an owned car',
                   'on screen: %s' % ', '.join(acts))

            ok(not errs, 'no page errors', errs[0][:120] if errs else '')
            ctx.close()
        b.close()
    httpd.shutdown()
    print()
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('a locked car offers the way to another car, and nothing else')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
