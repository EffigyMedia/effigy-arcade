"""Proof that `harness.boot()` waits for the ENGINE, and that the check can still fail.

WHAT IS BEING PROVED (RLG-208). Every harness in `tools/` navigated with `wait_until="load"`.
Twice - 2026-09-09 and 2026-09-10 - this machine stopped firing `load` for the two driving
cabinets while the engine booted, drove and answered underneath. The whole suite reported timeouts
that read exactly like a broken build. `boot()` navigates on `commit` and then waits for the
engine, so it survives a state the old shape cannot run in at all.

THE WEDGE IS REPRODUCED HERE, NOT WAITED FOR. The proof's own server holds one request open
forever - an image appended at DOMContentLoaded and never answered - so `load` can never fire
while everything else on the page runs normally. That is the same signature the real wedge left
behind: the engine up, zero page errors, and `document.readyState` stuck at `interactive`. The
hold is done in the SERVER rather than with `page.route`, because a Playwright route left
unresolved is cancelled when the context closes and buries the report in tracebacks.

IT RUNS THE CONTROL AGAINST THE LAUNCHER, DELIBERATELY. The natural wedge only takes the two
DRIVING cabinets, so on a wedged machine a driving cabinet would fail `load` with or without the
fixture and case A would prove nothing about the fixture. The launcher still fires `load` there,
which makes the control real: without the hold `load` arrives, with the hold it does not.

WHAT THIS PROOF CANNOT CHECK. It does not prove the real wedge and this fixture have the same
CAUSE - only that they present the same way to a harness, which is what `boot()` has to survive.
It says nothing about whether any individual harness reads correct numbers after booting; it
proves only that the page is up and running when the harness starts asking. And it runs on one
browser on one machine, so a second engine's `load` behaviour is untested.

Exit code 0 if every check passed, 1 otherwise.
"""
import http.server
import re
import socketserver
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, ready_for   # noqa: E402
from playwright.sync_api import sync_playwright                      # noqa: E402

HOLD_PATH = '/__proof_hold.png'
BLANK_PATH = '/__proof_blank.html'
BLANK_BODY = b'<!doctype html><meta charset="utf-8"><title>blank</title>'

# Appended once the document is parsed, so it is still a pending resource when `load` would
# otherwise fire. An image is the right lever: it delays `load` and nothing else waits on it.
HOLD_SCRIPT = """
document.addEventListener('DOMContentLoaded', function () {
  var i = document.createElement('img');
  i.src = '%s';
  document.documentElement.appendChild(i);
});
""" % HOLD_PATH

CANVAS_SIG = """() => {
  const cvs = [...document.querySelectorAll('canvas')];
  if (!cvs.length) return null;
  const cv = cvs.reduce((a, b) => a.width * a.height >= b.width * b.height ? a : b);
  try {
    const g = cv.getContext('2d');
    if (!g) return 'webgl';
    const d = g.getImageData(0, 0, cv.width, cv.height).data;
    let sum = 0;
    for (let i = 0; i < d.length; i += 4013) sum += d[i];
    return sum;
  } catch (e) { return 'unreadable'; }
}"""

STOP = threading.Event()
fails = []


class Handler(http.server.SimpleHTTPRequestHandler):
    """The site, plus one request that is never answered and one page with nothing on it."""

    def do_GET(self):
        if self.path == HOLD_PATH:
            # No status line, no headers, no body - and the socket stays open. This is the whole
            # fixture: the browser keeps the request pending, so `load` never fires.
            STOP.wait()
            return
        if self.path == BLANK_PATH:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(BLANK_BODY)))
            self.end_headers()
            self.wfile.write(BLANK_BODY)
            return
        return super().do_GET()

    def log_message(self, *a):
        pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True          # a held request must never keep the process alive


def check(label, condition, fact='', why=''):
    """`fact` is printed either way; `why` only when the check FAILS.

    A DETAIL STRING PRINTED ON A PASS IS HOW A CHECK GOES QUIET. This project has already had a
    line reading 'the nitrous button did not take' sitting next to an ok mark for months. A
    measured fact belongs on both; an explanation of a failure belongs on the failure alone.
    """
    bits = ''
    if fact:
        bits += '   ' + fact
    if not condition and why:
        bits += '   <- ' + why
    print('  %s  %s%s' % ('PASS' if condition else 'FAIL', label, bits))
    if not condition:
        fails.append(label)


def main():
    console_utf8()
    srv = Server(('127.0.0.1', 0), lambda *a, **k: Handler(*a, directory=str(ROOT), **k))
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    launcher = base + '/index.html'
    driving = base + '/games/sw/interstate.html'
    blank = base + BLANK_PATH

    print('boot-proof  .  the harness waits for the engine, not for the document')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])

        def fresh(hold=False):
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            if hold:
                ctx.add_init_script(HOLD_SCRIPT)
            return ctx, ctx.new_page()

        def loads(page, url, ms=8000):
            """Seconds `wait_until="load"` took to arrive, or None if it never did."""
            t = time.time()
            try:
                page.goto(url, wait_until='load', timeout=ms)
                return time.time() - t
            except Exception:
                return None

        # -- CONTROL: with nothing held, this machine fires `load` on the launcher. -------
        # If this fails, case A proves nothing, because `load` was already broken here.
        ctx, pg = fresh()
        took = loads(pg, launcher)
        check('control: the launcher fires `load` with nothing held', took is not None,
              'never' if took is None else '%.2fs' % took,
              'load was already broken here, so the fixture below cannot be trusted')
        ctx.close()

        # -- CASE A: the wedge reproduced. `load` never comes; the shell is up anyway. ----
        ctx, pg = fresh(hold=True)
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        took = loads(pg, launcher)
        check('a held subresource stops `load` firing', took is None,
              'never' if took is None else '%.2fs' % took,
              'the wedge was not reproduced')
        state = pg.evaluate('() => document.readyState')
        check('and the page is stuck at readyState `interactive`', state == 'interactive', state)
        check('while the page itself raised no error', not errs, '%d error(s)' % len(errs),
              '; '.join(errs[:2]))
        ctx.close()

        ctx, pg = fresh(hold=True)
        t = time.time()
        up = boot(pg, launcher, timeout=20000)
        check('boot() brings the launcher up through the same wedge', up,
              '%.2fs' % (time.time() - t))
        check('and the shell is genuinely attached, not merely present',
              pg.evaluate('() => !!(window.Arcade && Arcade.save && Arcade.pad)'))
        state = pg.evaluate('() => document.readyState')
        check('the document is still unfinished when boot() returns', state != 'complete', state,
              'the hold leaked, so this case proved nothing')
        ctx.close()

        # -- CASE B: the driving engine, which is what the real wedge takes. --------------
        ctx, pg = fresh(hold=True)
        t = time.time()
        up = boot(pg, driving, timeout=30000)
        check('boot() brings a DRIVING cabinet up through the wedge', up,
              '%.2fs' % (time.time() - t))
        if up:
            # A RUNNING engine, not merely a constructed one. `phase` is the engine's own
            # frame clock and it advances from the first frame, so a second reading that has
            # moved is the animation loop turning - which a global that simply exists would
            # not prove. NOT `simTime`, which is the RUN clock and sits at 0 until a run
            # starts; the cabinet is at its title screen here, and every harness does its own
            # start sequence after booting.
            first = pg.evaluate('() => window.__road.phase()')
            pg.wait_for_timeout(700)
            later = pg.evaluate('() => window.__road.phase()')
            check('and the engine is RUNNING, not merely constructed',
                  isinstance(first, (int, float)) and later > first,
                  'phase %r -> %r' % (first, later))
            # A black screen and a painted screen both have a canvas. Read the pixels.
            sig = pg.evaluate(CANVAS_SIG)
            check('and it has painted a real frame', isinstance(sig, (int, float)) and sig > 0,
                  'canvas %r' % (sig,), 'a canvas with nothing on it')
        else:
            fails.append('BLKD: the driving engine never came up')
            print('  BLKD  the driving engine never came up - the two checks under it are blocked')
        ctx.close()

        # -- CASE C: the check can still fail. Without these it is a ceremony. ------------
        ctx, pg = fresh()
        t = time.time()
        up = boot(pg, blank, timeout=5000, required=False)
        check('boot() returns False for a page with no engine at all', up is False,
              '%.2fs' % (time.time() - t))
        ctx.close()

        ctx, pg = fresh()
        # The launcher HAS `Arcade` and has no `__road`. Asking for the driving engine there must
        # fail, which is what proves the readiness expression is read rather than assumed.
        up = boot(pg, launcher, ready='road', timeout=5000, required=False)
        check("boot(ready='road') returns False on the launcher, which has no driving engine",
              up is False)
        check('though the launcher was reachable - the failure is the ENGINE, not the page',
              pg.evaluate('() => !!(window.Arcade && Arcade.save)'))
        ctx.close()

        # The 105 call sites this replaces all used `goto`, which RAISED when the page did not
        # arrive. A helper that returned False in their place would let a whole battery run
        # against a dead page, so the default has to stop - and say what it saw.
        ctx, pg = fresh()
        raised, said = None, ''
        try:
            boot(pg, blank, timeout=3000)
        except Exception as e:
            raised, said = type(e).__name__, str(e)
        check('boot() RAISES by default, the way the `goto` it replaces did',
              raised == 'RuntimeError', raised or 'nothing was raised')
        check('and it raises with a reading of the page, not a bare timeout',
              'readyState' in said and 'window.__road' in said,
              said.splitlines()[0] if said else '')
        ctx.close()

        # -- CASE D: a call site needs no second argument - the URL decides. --------------
        check('the URL picks the engine',
              ready_for('/games/sw/interstate.html') == 'road'
              and ready_for('/games/sw/motorsport.html') == 'road'
              and ready_for('/games/em/quietus.html') == 'arcade'
              and ready_for('/games/em/hardpoint.html') == 'arcade'
              and ready_for('/index.html') == 'arcade')

        b.close()

    # -- CASE E: nothing in the suite SHADOWS a helper it imported. -----------------------
    # This is not hypothetical. Five harnesses have a wrapper of their own called `boot`, and
    # converting them turned the helper's call into the wrapper calling ITSELF with the wrong
    # arity. drive-test went from 37 checks to a TypeError. The five import it as `engine_boot`
    # now, and this is what stops the sixth from being written the broken way.
    shadowed = []
    for f in sorted((ROOT / 'tools').glob('*.py')):
        if f.name in ('harness.py', 'boot-proof.py'):
            continue
        src = f.read_text(encoding='utf-8')
        m = re.search(r'^from harness import (.+)$', src, re.M)
        if not m:
            continue
        plain = [n.strip() for n in m.group(1).split('#')[0].split(',')
                 if ' as ' not in n]
        for name in plain:
            if re.search(r'^\s*def %s\b' % re.escape(name.strip()), src, re.M):
                shadowed.append('%s defines its own %s' % (f.name, name.strip()))
    check('no harness shadows a name it imports from harness.py', not shadowed,
          '%d file(s)' % len(shadowed), '; '.join(shadowed))

    STOP.set()                      # release the held request so the server can wind down
    print('\n%d failure(s)%s' % (len(fails), (': ' + ', '.join(fails)) if fails else ''))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
