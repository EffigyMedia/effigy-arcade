"""HARDPOINT AUDIO - does the sound actually follow the ship?

A sound test cannot listen. What it CAN do is read the Web Audio graph: every
held layer is a GainNode and an OscillatorNode with live values on them, so the
question "does the engine get louder when you open the throttle" has a number
behind it.

This exists because the whole point of the audio pass is that the layers are
CONTINUOUS and STATE-DRIVEN. A one-shot either fires or it does not, and a
missing one is obvious the first time you play. A held layer that has quietly
stopped tracking the throttle sounds like a game with an engine drone, and
nobody notices for a month.

What it asserts, in order:
  * the four held layers exist once the run has begun
  * engine level RISES with the throttle
  * engine pitch RISES with speed
  * burn is silent below 100% and audible above it
  * ENGINES DARK takes the engine to silence and leaves the air behind, which
    is the mechanic the game is built on
  * the alarm appears with heat and is silent without it
"""
import sys, threading, http.server, socketserver, functools

# ---- IT FINDS ITS OWN ROOT (RLG-039) --------------------------------------------------
# This served the folder from '.' and imported from 'tools', so it only ran from the project
# directory. `step.py` runs a command with the ENVIRONMENT's root as its working directory, so
# every one of these harnesses 404'd or raised there and recorded a FALSE FAILURE as evidence -
# twice in one session before it was worth fixing. The root is the file's own parent.
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot
from playwright.sync_api import sync_playwright

console_utf8()

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{PORT}'

# PUSH THE STATE, THEN WAIT REAL TIME, THEN READ.
#
# The first version of this file looped snd.step forty times and read the graph
# immediately, and every measurement came back frozen at its starting value. The
# code was fine; the test was wrong. `setTargetAtTime` ramps from the AUDIO
# clock, so forty calls in one instant all re-target from the same moment and
# nothing has moved yet. The clock has to actually advance before a held layer
# is anywhere near where it was sent.
#
# So: one push, a real wait, then read. It costs about half a second per
# measurement and it is the only way the numbers mean anything.
PUSH = """(st) => {
  const s = Object.assign({thr:0, spd:0, heat:0, cut:0, hull:100}, st);
  snd.step(0.05, s, false);
}"""

READ = """() => {
  const g = l => (l && l.gain ? l.gain.gain.value : null);
  return {
    eng:  g(snd.eng),  engHz: snd.eng ? snd.eng.osc.frequency.value : null,
    burn: g(snd.burn), air: g(snd.air), alarm: g(snd.alarm)
  };
}"""

SETTLE = 520          # ms - long enough for the ramps to arrive


# Backgrounding, as the browser reports it. `document.hidden` is a getter, so it is redefined
# rather than assigned - assigning to it silently does nothing and the test would pass on a
# teardown that never happened.
HIDE = """() => { Object.defineProperty(document, 'hidden', {configurable:true, get:()=>true});
  Object.defineProperty(document, 'visibilityState', {configurable:true, get:()=>'hidden'});
  document.dispatchEvent(new Event('visibilitychange')); }"""
SHOW = """() => { Object.defineProperty(document, 'hidden', {configurable:true, get:()=>false});
  Object.defineProperty(document, 'visibilityState', {configurable:true, get:()=>'visible'});
  document.dispatchEvent(new Event('visibilitychange'));
  document.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true})); }"""
# counts how many times a game is asked to rebuild its held voices
COUNT_REBUILDS = """window.__rebuilds = 0;
document.addEventListener('DOMContentLoaded', function(){
  var A = window.Arcade; if (!A || !A.audio) return;
  var real = A.audio.onReset;
  A.audio.onReset = function(fn){ real.call(A.audio, function(){ window.__rebuilds++; fn(); }); };
});"""


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        bctx = b.new_context(viewport={'width': 390, 'height': 844})
        bctx.add_init_script(COUNT_REBUILDS)
        page = bctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, f'{BASE}/games/em/hardpoint.html')
        page.wait_for_timeout(2000)

        started = page.evaluate("() => { snd.begin(); return !!(snd.eng && snd.burn && snd.air && snd.alarm); }")
        ok(started, 'the four held layers exist once a run begins')
        if not started:
            print('\n  the audio context never opened - nothing else can be measured')
            b.close(); srv.shutdown(); return 1

        def sample(st, settle=SETTLE):
            page.evaluate(PUSH, st)
            page.wait_for_timeout(settle)
            return page.evaluate(READ)

        idle = sample({'thr': 0, 'spd': 0})
        half = sample({'thr': 50, 'spd': 160})
        full = sample({'thr': 100, 'spd': 320})
        burn = sample({'thr': 110, 'spd': 320})
        # THE SPIN-DOWN IS SLOW ON PURPOSE, so this one is given the time it
        # was designed to take. Engines do not stop like a switch, and the
        # 0.55s time constant means 520ms only gets a third of the way there -
        # which the first run of this test reported as a failure of the code
        # rather than of its own patience.
        dark = sample({'thr': 0, 'spd': 200, 'cut': 2.5}, settle=2200)
        hot  = sample({'thr': 105, 'spd': 300, 'heat': 95})
        hurt = sample({'thr': 60, 'spd': 200, 'hull': 12})

        ok(idle['eng'] < half['eng'] < full['eng'],
           'engine level rises with the throttle',
           f"{idle['eng']:.3f} -> {half['eng']:.3f} -> {full['eng']:.3f}")
        ok(idle['engHz'] < half['engHz'] < full['engHz'],
           'engine pitch rises with speed',
           f"{idle['engHz']:.0f}Hz -> {half['engHz']:.0f}Hz -> {full['engHz']:.0f}Hz")
        ok(full['burn'] < 0.002 and burn['burn'] > 0.02,
           'the burn is silent below 100% and audible above it',
           f"100%={full['burn']:.4f}  110%={burn['burn']:.4f}")

        # the mechanic the game is built on
        ok(dark['eng'] < 0.006,
           'ENGINES DARK spins the engine down to silence within ~2s',
           f"{dark['eng']:.4f} from {full['eng']:.3f}")
        ok(dark['air'] > full['air'],
           'and leaves the air louder than it was under power',
           f"under power {full['air']:.3f}, dark {dark['air']:.3f}")

        # A PULSE HAS TO BE MEASURED AS A PEAK, NOT AS A SNAPSHOT. Both alarms
        # are square pulses, so a single reading lands wherever the phase
        # happens to be - the first run of this check reported the heat alarm
        # as silent because it sampled during an off-beat, and passed anyway on
        # the hull alarm beside it. That is a check that would have missed a
        # genuinely dead alarm.
        def peak(st, ms=700):
            # SETTLE FIRST, THEN MEASURE. Without this the peak catches the tail
            # of the PREVIOUS state decaying, which reported an alarm on a
            # healthy ship purely because the sample before it had a failing
            # hull. A peak over a transition is not a peak of anything.
            for _ in range(6):
                page.evaluate(PUSH, st)
                page.wait_for_timeout(50)
            hi = 0
            for _ in range(14):
                page.evaluate(PUSH, st)
                page.wait_for_timeout(ms // 14)
                hi = max(hi, page.evaluate(READ)['alarm'])
            return hi

        quiet_alarm = peak({'thr': 100, 'spd': 320})
        heat_alarm  = peak({'thr': 105, 'spd': 300, 'heat': 95})
        hull_alarm  = peak({'thr': 60,  'spd': 200, 'hull': 12})

        ok(quiet_alarm < 0.002, 'no alarm when nothing is wrong', f"peak {quiet_alarm:.4f}")
        ok(heat_alarm > 0.004, 'the heat alarm sounds at redline', f"peak {heat_alarm:.4f}")
        ok(hull_alarm > 0.004, 'and a separate one for a failing hull', f"peak {hull_alarm:.4f}")

        # ---- A HELD VOICE MUST SURVIVE THE APP BEING PUT AWAY ---------------
        # Reported from the device: after the app has been in the background, looping sounds
        # never come back while one-shots still work. Four seconds hidden calls `teardown`,
        # which CLOSES the audio context on purpose - a merely suspended iOS session can wake
        # after a force-quit. Every held voice dies with it, and a one-shot builds fresh nodes
        # every time it plays, which is exactly that split.
        #
        # The check counts how many times the games are ASKED to rebuild. It cannot listen, and
        # a context that is 'running' again proves nothing on its own: the whole defect was a
        # live context with no held voices on it.
        before = sample({'thr': 100, 'spd': 320})
        page.evaluate(HIDE)
        page.wait_for_timeout(6000)
        gone = page.evaluate("() => Arcade.audio.ctx && Arcade.audio.ctx.state")
        page.evaluate(SHOW)
        page.wait_for_timeout(2500)
        back = page.evaluate("() => Arcade.audio.ctx && Arcade.audio.ctx.state")
        after = sample({'thr': 100, 'spd': 320})
        # WHICH ENGINE DOES THE LAYER BELONG TO? This is the one question that can be asked of a
        # graph without listening to it, and two weaker versions were tried first.
        #
        # Counting calls to `audio.onReset` read zero on a fixed build, because the game subscribes
        # while the page parses and a harness can only wrap the hook afterwards - it was measuring
        # the harness's own timing.
        #
        # Reading the layer's gain read a HEALTHY 0.13 on a broken build, because a GainNode on a
        # CLOSED context still reports its value quite happily. It is silent and it does not know it.
        #
        # A node carries the context it was made on. If the layer's context is not the one the
        # arcade is playing through, the sound is gone whatever its gain says.
        live = page.evaluate("""() => {
            const A = window.Arcade, l = window.snd && window.snd.eng;
            if (!A.audio.ctx) return 'no context';
            if (!l || !l.gain) return 'no layer';
            return l.gain.context === A.audio.ctx ? 'live' : 'orphaned on a closed context';
        }""")
        ok(gone is None, 'the engine is torn down while the app is away', f'ctx {gone!r}')
        ok(back == 'running', 'and a fresh one is built on the way back', f'ctx {back!r}')
        ok(live == 'live',
           'the held layers belong to the engine that is now playing', live)
        ok(after['eng'] > before['eng'] * 0.5,
           'and they are still being driven',
           f"engine {before['eng']:.4f} before, {after['eng']:.4f} after")

        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        b.close()

    srv.shutdown()
    print(f"\n  {'audio follows the ship' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
