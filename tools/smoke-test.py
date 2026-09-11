#!/usr/bin/env python3
"""
SMOKE TEST — every cabinet boots, or the build does not ship.

The drive test proves the two driving games PLAY. This proves the other
sixteen at least WAKE UP: page loads, no errors thrown, a canvas is present
and actually painting, the arcade shell attached, and the machine still
renders something ten seconds in. It will not catch a game with broken rules;
it will catch the black screen, which is the failure that has actually
shipped twice.

    python3 tools/smoke-test.py            all 18
    python3 tools/smoke-test.py coil deep  by id

Exit 0 when every cabinet passes.
"""

import argparse
import functools
import http.server
import json
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from harness import console_utf8, launch_chromium, node_exe, boot, until, READY, ready_for

ROOT = Path(__file__).resolve().parent.parent


def catalogue():
    """games.js is the single source of truth; read it, do not restate it."""
    out = subprocess.run(
        [node_exe(), '-e',
         "global.window={};eval(require('fs').readFileSync('games.js','utf8'));"
         "console.log(JSON.stringify(window.EFFIGY_ARCADE))"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    httpd = socketserver.TCPServer(
        ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


CANVAS_SIG = """() => {
  /* a black screen and a painted screen both have a canvas; tell them apart
     by reading pixels. Sample the largest canvas; sum a sparse grid. */
  const cvs = [...document.querySelectorAll('canvas')];
  if (!cvs.length) return null;
  const cv = cvs.reduce((a, b) => a.width * a.height >= b.width * b.height ? a : b);
  try {
    const g = cv.getContext('2d');
    if (!g) return 'webgl';                    /* not readable this way */
    const d = g.getImageData(0, 0, cv.width, cv.height).data;
    let sum = 0;
    for (let i = 0; i < d.length; i += 4013) sum += d[i];
    return sum;
  } catch (e) { return 'unreadable'; }
}"""


def smoke(page, base, game, seconds):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    # CONSOLE ERRORS COUNT TOO. A cabinet that draws a word in its own alphabet
    # loses any letter that alphabet lacks, silently - Quietus shipped as "IET"
    # for a release that way. The shell reports it on the console now, so the
    # console has to be part of what "clean" means.
    page.on('console', lambda m: errors.append('console: ' + m.text)
            if m.type == 'error' else None)
    boot(page, f'{base}/{game["file"]}')
    try:
        until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
            timeout=5_000)
    except Exception:
        pass

    checks = []
    ok = lambda c, l, d='': checks.append((bool(c), l, d))

    ok(page.title().strip() != '', 'has a title', page.title())
    ok(page.query_selector('canvas'), 'has a canvas')
    ok(page.evaluate('() => !!(window.Arcade && Arcade.save && Arcade.pad)'),
       'arcade shell attached')
    meta = page.evaluate(
        '() => (document.querySelector(\'meta[name="arcade-title"]\')||{}).content')
    ok(meta, 'arcade-title meta present', meta or 'missing')

    first = page.evaluate(CANVAS_SIG)
    page.wait_for_timeout(int(seconds * 1000))
    later = page.evaluate(CANVAS_SIG)
    ok(later not in (None, 0), 'the canvas has paint on it', f'signal {later}')

    # ---- EVERY MACHINE CAN ERASE ITSELF, FROM ITS OWN OPTIONS -------------
    # A static check cannot see a button. This drives the real path: seed a
    # save so the label cannot read NO SAVED DATA, walk in through OPTIONS,
    # arm it, confirm it, and look at the store on the far side of the reload.
    gid = game['id']
    try:
        page.evaluate("id => window.Arcade.save.set(id, {best: 7})", gid)
        page.get_by_text('OPTIONS', exact=False).first.click(timeout=4_000)
        page.wait_for_timeout(600)
        body = page.locator('body').inner_text()
        ok('ERASE SAVE' in body, 'options offer ERASE SAVE',
           '' if 'ERASE SAVE' in body else 'not in the options screen')
        if 'ERASE SAVE' in body:
            page.get_by_text('ERASE SAVE', exact=False).first.click()
            page.wait_for_timeout(400)
            armed = 'SURE?' in page.locator('body').inner_text()
            ok(armed, 'one press arms rather than erasing')
            if armed:
                page.get_by_text('SURE?', exact=False).first.click()
                page.wait_for_timeout(1_600)
                left = page.evaluate("id => window.Arcade.save.get(id)", gid)
                ok(left is None, 'the second press erases', f'save is {left}')
    except Exception as e:
        ok(False, 'the erase control is reachable', f'{type(e).__name__}: {e}')

    ok(errors == [], 'no page errors', errors[0][:110] if errors else '')
    return checks, first, later


def launcher(page, base, games):
    """THE LAUNCHER IS A MUST-FLOW AND NOTHING TESTED IT.

    Every check in this file used to `goto` a cabinet URL directly, so the one
    thing every player does first - open the arcade and tap a game - was the
    one path with no coverage. A dead click handler on the rack sent first-time
    visitors to `/null` for weeks behind an 18/18 green run.

    So: open the launcher, click a real cabinet, and assert where the browser
    actually ENDED UP. Not that a handler ran; where it landed.

    THE SHELF STEP IS GONE, AND IT WAS NOT REMOVED FOR TIDINESS. Tiny Arcade
    landed on a picker of three shelves, so reaching a cabinet meant opening one
    first. This arcade lands on the rack. The check that used to open a shelf now
    asserts the opposite invariant - that the cabinets are reachable with NO step
    in between - because a picker reappearing is itself a regression here.
    """
    checks = []

    def ok(cond, label, detail=''):
        checks.append((bool(cond), label, detail))

    boot(page, f'{base}/index.html')
    page.wait_for_timeout(900)                      # the loading panel has a floor

    # ---- HOLD THE CABINET'S FETCH, AND THIS IS THE WHOLE POINT ------------
    # The failure this guards against is a RACE: a stray timer overwrites the
    # real navigation a few tens of milliseconds after it starts. Served from
    # localhost the cabinet arrives instantly, the old page is torn down before
    # the stray timer can run, and the bug CANNOT reproduce - which is exactly
    # why it shipped. The developer's machine always wins the race; a new
    # player's network does not.
    #
    # CDP throttling does not slow a main-frame navigation, so it does not
    # help here (tried, 2026-08-24). Delaying the cabinet's own response does:
    # the launcher stays alive past the moment any late timer would fire, and
    # whatever the page decides to do LAST is what we measure.
    def slow_cabinet(route):
        time.sleep(0.6)
        route.continue_()
    page.route('**/games/**/*.html', slow_cabinet)

    # ---- THE FLOOR IS THE LANDING PAGE ------------------------------------
    # No shelf, no picker, no step. If a cabinet is not visible the moment the
    # loading panel lifts, something has put a screen back in front of the rack.
    visible = page.locator('.cab:visible')
    ok(visible.count() == 4, 'the floor shows its four machines',
       f'{visible.count()} visible')
    ok(page.locator('.shelf:visible').count() == 0,
       'and nothing stands in front of them',
       f'{page.locator(".shelf:visible").count()} shelf buttons visible')
    if not visible.count():
        return checks

    cab = page.locator('.cab:visible').first
    want = cab.get_attribute('data-href')

    # ---- ONE CABINET, ONE LAUNCH PATH -------------------------------------
    # The invariant that broke was not "the link is right" - it was that TWO
    # click handlers answered one tap, a live one and a dead one left over from
    # when a cabinet was an <a href>. The dead one read an attribute a <div>
    # does not have and scheduled a navigation to `null`. Whether that stray
    # navigation WINS depends on whether a service worker is mediating it, so a
    # landing-place check cannot see it reliably. The COUNT can: neuter the
    # timers so the tap goes nowhere, count what one tap schedules, and require
    # exactly one. Then put the clock back and do the tap for real.
    page.evaluate('''() => {
      window.__t = [];
      window.__st = window.setTimeout.bind(window);
      window.setTimeout = function(fn, ms){ window.__t.push(ms); return window.__st(function(){}, 999999); };
    }''')
    cab.click()
    page.wait_for_timeout(200)
    scheduled = page.evaluate('window.__t') or []
    ok(len(scheduled) == 1, 'one tap schedules one launch',
       f'{len(scheduled)} timers: {scheduled}')
    page.evaluate('() => { window.setTimeout = window.__st; }')

    cab = page.locator('.cab:visible').first
    cab.click()
    # the launcher waits ~130ms on purpose, to let the coin land
    try:
        page.wait_for_url(lambda u: 'index.html' not in u and not u.endswith('/'),
                          timeout=9000)
        # The ENGINE of whatever cabinet the tap opened, not the document (RLG-208). The check
        # below only reads the URL, so a cabinet that never finishes loading must not stop it.
        until(page, READY[ready_for(page.url)], timeout=9000, required=False)
    except Exception:
        pass
    page.wait_for_timeout(700)      # let any late timer have its say
    landed = page.url
    ok(want and want.split('/')[-1] in landed,
       'tapping a cabinet opens that cabinet', landed.replace(base, ''))
    ok('null' not in landed.rsplit('/', 1)[-1],
       'and not a dead address', landed.replace(base, ''))
    return checks


def saves(page, base):
    """ERASING ONE MACHINE MUST ERASE ALL OF IT, AND NONE OF ITS NEIGHBOUR.

    `Arcade.save.clear` used to remove the save slot and nothing else, so a
    machine that had been erased still remembered its options, its own stored
    counters, and every intro it had already shown. The call reported success
    the whole time, which is why this is a harness check and not a code review
    note: the only way to know an eraser erased is to put something in front of
    it and look afterwards.

    Seeds all four shapes a machine can store under, plus a NEIGHBOUR whose id
    shares a prefix - the case a naive `startsWith` gets wrong.
    """
    checks = []

    def ok(cond, label, detail=''):
        checks.append((bool(cond), label, detail))

    boot(page, f'{base}/index.html')
    page.wait_for_timeout(900)

    result = page.evaluate("""() => {
      const A = window.Arcade;
      if (!A || !A.save || !A.save.clear) return { fatal: 'Arcade.save.clear missing' };

      localStorage.clear();
      // EVERY SHAPE A MACHINE CAN OWN. If a new store is added and not listed
      // here, this check keeps passing while that store survives an erase -
      // so adding a store means adding it to this list.
      A.save.set('inter', { best: 1 });                                  // the save
      A.save.set('inter-opts', { invertY: true });                       // a second slot
      localStorage.setItem('effigyarcade.inter.tally.v1', '{}');         // its own key
      localStorage.setItem('effigyarcade.inter.opts.v1', '{"mirror":"OFF"}');  // shell options
      localStorage.setItem('effigyarcade.inter.audio.v1', '{"music":false}');  // audio prefs
      localStorage.setItem('effigyarcade.inter.cinema.v1', '{"intro":1}');     // seen intros

      // a neighbour whose id shares a prefix with the one being erased
      A.save.set('interstate', { best: 99 });
      localStorage.setItem('effigyarcade.interstate.audio.v1', '{"music":true}');
      // and the launcher, which is a scope but not a machine
      localStorage.setItem('effigyarcade.launcher.audio.v1', '{"music":true}');

      const before = A.save.has('inter');
      const removed = A.save.clear('inter');

      const left = Object.keys(localStorage).filter(k =>
        k.indexOf('effigyarcade.inter.') === 0
        || k === 'effigyarcade.save.v1.inter'
        || k.indexOf('effigyarcade.save.v1.inter-') === 0);

      const neighbour = A.save.get('interstate');
      const neighbourAudio = localStorage.getItem('effigyarcade.interstate.audio.v1');
      const launcherAudio = localStorage.getItem('effigyarcade.launcher.audio.v1');
      const reserved = A.save.clear('launcher');

      const all = A.save.clearAll();
      const anyLeft = Object.keys(localStorage).filter(k => k.indexOf('effigyarcade.') === 0);

      return { before, removed, left, neighbour, neighbourAudio, launcherAudio,
               reserved, stillSeen: A.save.has('inter'), clearedAll: all, anyLeft,
               scope: A.scope };
    }""")

    if result.get('fatal'):
        ok(False, 'the shell exposes save.clear', result['fatal'])
        return checks

    ok(result['before'] is True, 'save.has sees a machine with data')
    ok(result['left'] == [], 'erasing a machine leaves NONE of its six stores',
       'survived: ' + ', '.join(result['left']))
    ok(result['stillSeen'] is False, 'and save.has agrees it is gone')

    # the precision test: `inter` must not eat `interstate`
    ok(result['neighbour'] is not None and result['neighbour'].get('best') == 99,
       'a machine with a shared prefix survives', str(result['neighbour']))
    ok(result['neighbourAudio'] is not None,
       'including its own audio settings')

    # the launcher is a scope, not a machine, and must be un-erasable by id
    ok(result['reserved'] == 0, 'the launcher scope cannot be erased as a machine',
       f"clear('launcher') removed {result['reserved']}")
    ok(result['launcherAudio'] is not None, 'so its settings stay')

    ok(result['scope'] == 'launcher', 'the launcher resolves its own scope',
       str(result['scope']))
    ok(result['anyLeft'] == [], 'clearAll leaves nothing behind',
       ', '.join(result['anyLeft']))
    return checks


def main():
    console_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument('ids', nargs='*')
    ap.add_argument('--seconds', type=float, default=8.0)
    args = ap.parse_args()

    games = catalogue()
    if args.ids:
        games = [g for g in games if g['id'] in args.ids]

    httpd, port = serve()
    base = f'http://127.0.0.1:{port}'
    failed = 0
    total = len(games)
    print(f'smoke-test  ·  {len(games)} cabinets  ·  {args.seconds:g}s each')
    with sync_playwright() as p:
        browser = launch_chromium(
            p,
            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = browser.new_context(viewport={'width': 480, 'height': 900})

        if not args.ids:
            page = ctx.new_page()
            try:
                lchecks = launcher(page, base, games)
            except Exception as e:
                lchecks = [(False, 'the launcher loads', f'{type(e).__name__}: {e}')]
            lbad = [c for c in lchecks if not c[0]]
            failed += bool(lbad)
            total += 1
            mark = 'ok  ' if not lbad else 'FAIL'
            line = f'  {mark}  {"launcher":<10}'
            if lbad:
                line += '  ·  ' + '; '.join(f'{l} ({d})' if d else l for _, l, d in lbad)
            print(line)
            page.close()

            page = ctx.new_page()
            try:
                schecks = saves(page, base)
            except Exception as e:
                schecks = [(False, 'the save layer answers', f'{type(e).__name__}: {e}')]
            sbad = [c for c in schecks if not c[0]]
            failed += bool(sbad)
            total += 1
            mark = 'ok  ' if not sbad else 'FAIL'
            line = f'  {mark}  {"saves":<10}'
            if sbad:
                line += '  ·  ' + '; '.join(f'{l} ({d})' if d else l for _, l, d in sbad)
            print(line)
            page.close()

        for g in games:
            page = ctx.new_page()
            try:
                checks, _, _ = smoke(page, base, g, args.seconds)
            except Exception as e:
                checks = [(False, 'loads at all', f'{type(e).__name__}: {e}')]
            bad = [c for c in checks if not c[0]]
            failed += bool(bad)
            mark = 'ok  ' if not bad else 'FAIL'
            line = f'  {mark}  {g["id"]:<10}'
            if bad:
                line += '  ·  ' + '; '.join(f'{l} ({d})' if d else l for _, l, d in bad)
            print(line)
            page.close()
        browser.close()
    httpd.shutdown()
    print(f'\n  {total - failed}/{total} checks pass')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
