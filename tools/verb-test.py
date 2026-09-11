#!/usr/bin/env python3
"""
VERB TEST - muting a bus mutes its reverb, and does not mute anyone else's.

    .venv/Scripts/python tools/verb-test.py

RLG-078. The owner: "if I was to mute the music, the reverb bus still plays so we want to make sure
muting the music also mutes that bus." There was one convolver and its return went straight to
master, so a voice was connected twice and only the dry copy rode the mute.

WHY THIS LISTENS RATHER THAN READS. A check that reads a gain value off the Web Audio graph is not
reading the graph - RLG-065 cost three attempts on exactly that, and a GainNode on a closed context
reports a healthy value quite happily. A ROUTING fault is worse still: it changes no gain anywhere,
so there is no value to read that could be wrong. The only thing that answers "did the tail come out
of the speaker" is the signal, so this hangs an analyser off master and measures it.

AND THE SECOND HALF IS WHY THE OBVIOUS FIX IS WRONG. Muting the single shared return would have
silenced the report and taken the sound effects' reverb with it, because one return carried both. So
this asserts BOTH directions: music muted leaves nothing of a music tail, and leaves an effects tail
alone.

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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot

GAME = 'games/sw/interstate.html'

# A VOICE WITH ALMOST NOTHING DRY AND A LOT OF TAIL. The dry copy is what the mute was already
# silencing correctly; the wet copy is what this is about, so the send is loud and the voice
# short - by the time the measurement is taken the note is over and only the tail is left.
PLAY = """(bus) => {
  const A = window.Arcade;
  A.sfx.tone({ bus:bus, verb:0.95, freq:520, to:520, dur:0.10, peak:0.9, type:'sine' });
  return A.audio.verbBuses();
}"""

# RMS off the analyser, which is the real output of the graph rather than anyone's opinion of it
READ = """() => {
  const an = window.Arcade.audio.tap();
  if (!an) return null;
  const d = new Float32Array(an.fftSize);
  an.getFloatTimeDomainData(d);
  let s = 0, pk = 0;
  for (let i = 0; i < d.length; i++){ s += d[i]*d[i]; if (Math.abs(d[i]) > pk) pk = Math.abs(d[i]); }
  return { rms: +Math.sqrt(s/d.length).toFixed(6), peak: +pk.toFixed(6) };
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class Results:
    def __init__(self):
        self.fails = []

    def check(self, ok, label, detail=''):
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + str(detail) + ']'))
        if not ok:
            self.fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('verb-test  .  a tail rides the gain its dry copy rides')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed,
                                  args=['--autoplay-policy=no-user-gesture-required'])
        page = browser.new_context(viewport={'width': 480, 'height': 900},
                                   has_touch=True, is_mobile=True).new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        page.wait_for_timeout(1500)
        # a gesture, because a context that never started measures silence and passes everything
        page.mouse.click(240, 700)
        page.wait_for_timeout(600)
        state = page.evaluate("() => { Arcade.audio.init();"
                              " return Arcade.audio.ctx && Arcade.audio.ctx.state; }")
        page.wait_for_timeout(400)
        state = page.evaluate("() => Arcade.audio.ctx && Arcade.audio.ctx.state")
        print('      audio context: %s' % state)
        res.check(state == 'running', 'the audio context is running', str(state))
        res.check(page.evaluate('() => !!window.Arcade.audio.tap()'), 'the output can be tapped')
        # AND THE ROOM HAS TO BE EMPTY FIRST. The title screen plays a music bed, and the first
        # version of this measured that rather than its own voices: the floor read 0.21 with
        # music on and 0.00 with music muted, which is a difference the check would have read
        # as proof of the very thing it was testing. The bed is paused, so the only thing on
        # either bus is the voice this harness puts there.
        page.evaluate('() => window.Arcade.music && window.Arcade.music.pause()')
        page.wait_for_timeout(300)

        # THE IMPULSE IS 1.9 SECONDS LONG, AND THAT IS THE WHOLE DIFFICULTY. The first version
        # measured one phase 520ms after the last and every reading carried the previous tail
        # into it - a muted bus read 0.0009 where it should have read zero, and an UNMUTED one
        # read high because un-muting a bus brings back whatever is still ringing inside its
        # convolver. So every measurement waits for silence first and is checked for it.
        def settle(ms=2400):
            page.wait_for_timeout(ms)
            return page.evaluate(READ)

        def tail(bus, before=None):
            """silence, then one short reverb-heavy voice, then the loudest of the tail"""
            base = settle()
            page.evaluate(PLAY, bus)
            # A DECAYING TAIL THROUGH A 2048-SAMPLE WINDOW IS A LOTTERY. One read landed at
            # 0.00024 and the same condition read 0.00066 a moment later, purely on where the
            # window fell. Five reads across the tail, and the loudest is the answer.
            got = {'rms': 0.0, 'peak': 0.0}
            for _ in range(5):
                page.wait_for_timeout(150)
                r = page.evaluate(READ)
                if r['rms'] > got['rms']:
                    got = r
            got['floor'] = base['rms']
            return got

        def measure(bus, ms=520):
            return tail(bus)

        def prefs(sfx, music):
            page.evaluate('([s, m]) => { Arcade.audio.set("sfx", s);'
                          ' Arcade.audio.set("music", m); }', [sfx, music])
            page.wait_for_timeout(300)

        # ---------------------------------------------- everything on, so there is a tail at all
        prefs(True, True)
        base_m = tail('music')
        base_s = tail('sfx')
        res.check(base_m['floor'] < 0.0005 and base_s['floor'] < 0.0005,
                  'the room is silent before each measurement',
                  'floors %s and %s' % (base_m['floor'], base_s['floor']))
        print('      tails with nothing muted:  music %s   sfx %s' % (base_m, base_s))
        # a hundred times the measured silence floor, which reads 0 to 2e-06
        res.check(base_m and base_m['rms'] > 0.0002,
                  'a music voice leaves a tail when nothing is muted', str(base_m))
        res.check(base_s and base_s['rms'] > 0.0002,
                  'and so does an effect', str(base_s))

        # ---------------------------------------------- music muted: no music tail
        prefs(True, False)
        quiet_m = tail('music')
        print('      music muted, music tail:   %s' % quiet_m)
        res.check(quiet_m['rms'] < base_m['rms'] * 0.05,
                  'muting the music mutes its reverb',
                  '%s against %s unmuted' % (quiet_m, base_m))

        # ---------------------------------------------- and the effects keep theirs
        still_s = tail('sfx')
        print('      music muted, sfx tail:     %s' % still_s)
        res.check(still_s['rms'] > base_s['rms'] * 0.30,
                  'and does not take the effects reverb with it',
                  '%s against %s with nothing muted' % (still_s, base_s))

        # ---------------------------------------------- the other way round
        prefs(False, True)
        quiet_s = tail('sfx')
        still_m = tail('music')
        print('      sfx muted:  sfx tail %s   music tail %s' % (quiet_s, still_m))
        res.check(quiet_s['rms'] < base_s['rms'] * 0.05,
                  'muting the effects mutes their reverb', str(quiet_s))
        res.check(still_m['rms'] > base_m['rms'] * 0.30,
                  'and leaves the music tail alone', str(still_m))

        prefs(True, True)
        print('      reverbs built: %s' % page.evaluate('() => Arcade.audio.verbBuses()'))
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(res.fails)) if res.fails else '\nall checks passed')
    return 1 if res.fails else 0


if __name__ == '__main__':
    sys.exit(main())
