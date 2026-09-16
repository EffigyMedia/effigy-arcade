#!/usr/bin/env python3
"""RUN SILENCE - leaving a run by any door stops every sound the run was making.

    .venv/Scripts/python tools/run-silence-test.py
    .venv/Scripts/python tools/run-silence-test.py --selftest

RLG-272. Owner, 2026-09-16: "When you get to the game over screen essentially they're still looping
engine sounds that make it sound ugly. We need to cut the run sounds when we leave a run."

▶ A SOUND TEST CANNOT LISTEN, BUT IT CAN READ THE WEB AUDIO GRAPH. Every layer a run holds open is a
GainNode with a live value on it, published through `API.snd`, so "is the engine still sounding under
the end card" has a number behind it. The defect was exactly that: `snd.quiet()` took every held
layer to a gain of zero EXCEPT the engine, which it took to 0.01 and left there — measured 0.0100 on
the end card and again in the garage, against 0.0899 while driving. A held oscillator sounds until
something tells it to stop.

▶ A GAIN IS NOT EVIDENCE ON ITS OWN. A GainNode on a CLOSED context reports its value perfectly
happily; a broken audio build once read a healthy 0.13 that way. So this asserts the context is
RUNNING first. A silent graph on a dead context would otherwise pass this file while proving nothing,
and the failure it is meant to catch is a voice that is audible rather than one that is missing.

  DRIVING          the engine is actually sounding, or nothing below means anything.
  END CARD         the run has ended on the clock and every held layer is at zero.
  STILL, LATER     and it is still at zero four seconds on, not passing through zero on a ramp.
  GARAGE           and CHANGE CAR back to the garage has not started anything up again.

`--selftest` puts the defect back — it writes the old 0.01 idle onto the engine after the run has
ended — and asserts this file reports it. Watched failing that way, which is what separates a check
from a hopeful one.

Exit code 0 if every check passed, 1 otherwise.
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

# every layer a run holds open. `quiet()` is the one function that is supposed to close all of them.
HELD = ['eng', 'eng2', 'wind', 'siren', 'thrust', 'sqA', 'sqB', 'sqC', 'screechLow',
        'horn1', 'horn2']

# ---- WHY THIS IS A FLOOR AND NOT ZERO -------------------------------------------------------
# `set()` ramps with `setTargetAtTime`, which is exponential: a layer told to go to zero APPROACHES
# zero and never arrives. Two seconds after the end card the engine reads 0.00008 and it is still
# falling; four seconds later it reads a true zero. An equality test would fail on a working build
# for the shape of the ramp rather than for anything audible.
#
# THE NUMBER IS NOT CHOSEN TO MAKE THE CHECK PASS. 0.0005 is a thousandth of the way up from
# silence, about 180 times below the 0.0899 the engine sits at while driving, and 20 times below the
# 0.01 idle that IS the defect - so the floor separates the two cases by a wide margin rather than
# splitting the difference between them. `--selftest` writes 0.01 back and watches this fail.
INAUDIBLE = 0.0005

READ = """(keys) => {
  const R = window.__road, S = R && R.snd, A = window.Arcade;
  if(!S) return { err: 'the engine does not publish its sound layers' };
  const out = { ctx: (A && A.audio && A.audio.ctx) ? A.audio.ctx.state : 'none', gains: {} };
  for(const k of keys){
    const l = S[k];
    out.gains[k] = (l && l.gain) ? +l.gain.gain.value.toFixed(5) : null;
  }
  return out;
}"""

# THE DEFECT, PUT BACK. This is the value `quiet()` used to leave on the engine.
RE_BREAK = """() => { const S = window.__road.snd;
                      if(S && S.eng) S.eng.set(60, 0.01, 300, 0.05); }"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def loudest(sample, floor=0.0):
    """the layer sounding most above `floor`, and how loudly - so a failure names the voice"""
    live = {k: v for k, v in sample['gains'].items() if v and v > floor}
    if not live:
        return None, 0.0
    k = max(live, key=lambda n: live[n])
    return k, live[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--selftest', action='store_true',
                    help='put the old engine idle back and prove this file reports it')
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
    print('run-silence  .  leaving a run stops every sound the run was making')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)

        def tap(act, wait=250):
            sel = '#veil:not(.hidden) [data-act="%s"]' % act
            if not pg.query_selector(sel):
                raise RuntimeError('no %s button on the screen' % act.upper())
            pg.click(sel)
            pg.wait_for_timeout(wait)

        def sample():
            s = pg.evaluate(READ, HELD)
            if s.get('err'):
                raise RuntimeError(s['err'])
            return s

        def show(where, s):
            live = {k: v for k, v in s['gains'].items() if v}
            print('      %-16s ctx %-8s %s'
                  % (where, s['ctx'], ('sounding ' + ', '.join('%s %.4f' % (k, v)
                                                               for k, v in sorted(live.items()))
                                       ) if live else 'silent'))

        # ---- the run ---------------------------------------------------------------------
        tap('play', 600)
        tap('drive', 1800)
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => window.__road.setSpd(0.6 * window.__road.MAX_SPD)')
        pg.wait_for_timeout(1200)
        driving = sample()
        show('DRIVING', driving)
        ok(driving['ctx'] == 'running', 'the audio context is live', driving['ctx'])
        _, loud = loudest(driving)
        ok(loud > 0.01, 'the engine is actually sounding while you drive, so silence means '
                        'something', 'loudest layer %.5f' % loud)

        # ---- out of time -----------------------------------------------------------------
        # BOTH HALVES ARE NEEDED. `setClock` does nothing on a run that does not count seconds
        # (RLG-125), and an empty clock is not the end either: the engine waits for the car to come
        # to REST as well, so a car left rolling sits on an expired clock forever.
        pg.evaluate('() => { window.__road.setTimed(true); window.__road.setClock(0.2); }')
        ended = False
        for _ in range(60):
            pg.evaluate('() => window.__road.setSpd(0)')
            if pg.evaluate('() => { const el = document.getElementById("veil");'
                           ' return !!el && !el.classList.contains("hidden")'
                           ' && !!el.querySelector(\'[data-act="again"]\'); }'):
                ended = True
                break
            pg.wait_for_timeout(250)
        ok(ended, 'the run ends on the clock and the end card comes up')
        if not ended:
            print('\n  the run never ended - nothing below could be measured')
            b.close()
            httpd.shutdown()
            return 1

        if args.selftest:
            print('      selftest  .  the old engine idle is written back onto the run')
            pg.evaluate(RE_BREAK)

        pg.wait_for_timeout(2000)
        card = sample()
        show('END CARD', card)
        ok(card['ctx'] == 'running', 'the context is still live under the end card', card['ctx'])
        k, v = loudest(card, INAUDIBLE)
        ok(k is None, 'every sound the run was making has stopped under the end card',
           'None' if k is None else '%s is still at %.5f' % (k, v))

        # ---- and it stays stopped --------------------------------------------------------
        # A RAMP PASSES THROUGH ZERO. Reading once, two seconds in, cannot tell a layer that has
        # been turned off from one that is on its way somewhere else.
        pg.wait_for_timeout(4000)
        later = sample()
        show('STILL, LATER', later)
        k, v = loudest(later, INAUDIBLE)
        ok(k is None, 'and it is still silent four seconds on',
           'None' if k is None else '%s is at %.5f' % (k, v))

        # ---- and the garage does not start it up again -----------------------------------
        tap('garage', 1200)
        pg.wait_for_timeout(1200)
        garage = sample()
        show('GARAGE', garage)
        k, v = loudest(garage, INAUDIBLE)
        ok(k is None, 'and going back to the garage does not start it up again',
           'None' if k is None else '%s is at %.5f' % (k, v))

        ok(not errs, 'no page errors', errs[0][:120] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if args.selftest:
        if fails:
            print('the defect was put back and this file reported it: %s' % '; '.join(fails))
            return 0
        print('SELFTEST FAILED: the old engine idle was written back and nothing noticed')
        return 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('leaving a run stops every sound the run was making')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
