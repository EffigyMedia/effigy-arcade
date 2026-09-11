"""Does traffic actually change lane, or does it move a fraction of one?

RLG-040. The owner reported it from a phone: "when traffic merges, they don't go fully to a new
lane. It's like a fraction of a lane." RLG-033 part 1 measured the same fault from the rivals' side
and put a number on it - rivals spent 59-61% of their time off a lane centre - so this harness asks
the same question of the other code path.

WHAT IS MEASURED, and all of it from OUTSIDE the merge logic
------------------------------------------------------------
The engine's own merge state is not read. A car's lateral position over time is, at 20Hz, and every
number below is derived from that alone - so this instrument cannot be fooled by a merge that is
recorded as made and never carried out, which is the exact failure being investigated.

  moves        a completed lateral move: a car that was standing still across the road, moved, and
               came to rest again. Counted per car, so a car that is culled mid-move contributes
               nothing rather than half a move.
  size         how far that move went, in LANE WIDTHS. One lane is the whole point of the ruling.
               The lane width comes from the engine (`API.laneX()`), never from a copy kept here,
               because RLG-024 is going to widen the road and a harness with its own LANE_X would
               keep reporting on the old one without being able to say so.
  landed       the share of completed moves that came to rest within 0.15 lanes of a lane centre.
               A move that ends between two lanes is the fault, whatever its size.
  off-centre   the share of ALL samples more than 0.12 lanes from the nearest lane centre. The same
               definition racer-test uses for rivals, so the two code paths can be read together.

YIELDERS ARE COUNTED SEPARATELY, AND ON PURPOSE
-----------------------------------------------
`keepLaneOpen` deliberately leans a car toward the verge, past the outermost lane, to hold a
corridor open (RLG-037). That is not a merge and it is not meant to end on a lane centre. A car
that has ever yielded is reported on its own line and excluded from the assertions - the only
place this harness looks at engine state, and it looks at it to CLASSIFY, never to judge.

THE VACUITY GUARD
-----------------
"No fractional merges" is also what a road with no merges at all reports. The run fails if it
observes fewer than `--need-moves` completed moves, and it cross-checks its own count against
`API.mergesMade()` - if the engine says it decided on merges and this sampler saw none of them
carried out, the sampler is what is wrong.

Math.random is seeded before any game script runs, so two invocations meet the same grid and the
same traffic. Read the lesson in RLG-033 first: a number from a harness like this one is not
established until two separate invocations agree, because a session fixes its seeded grid at the
start and between-session variance is the larger kind.
"""

import argparse
import functools
import http.server
import importlib.util
import socketserver
import statistics
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME = 'games/sw/interstate.html'


# --- find the interpreter that has Playwright --------------------------------
# The same handover as racer-test.py, and see RLG-039 for why it is needed: step.py runs with the
# environment root as cwd, and on Windows CreateProcess resolves a relative EXECUTABLE against the
# calling process's directory, so the project .venv cannot be named by any relative path from there.

def _handover():
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        pass
    for candidate in (ROOT / '.venv' / 'Scripts' / 'python.exe', ROOT / '.venv' / 'bin' / 'python'):
        if candidate.exists() and candidate.resolve() != Path(sys.executable).resolve():
            sys.exit(subprocess.run([str(candidate), str(Path(__file__).resolve())]
                                    + sys.argv[1:]).returncode)
    raise SystemExit(
        '[merge-test] playwright is not importable and there is no project .venv to hand over to.\n'
        '             Build one: uv venv .venv, then uv pip install --python .venv playwright')


_handover()

from playwright.sync_api import sync_playwright   # noqa: E402

from harness import console_utf8, launch_chromium, boot, until  # noqa: E402


def serve(root):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


def drive_test_module():
    path = Path(__file__).resolve().parent / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('drive_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SEED_RNG = r"""
(function(){
  var s = 0x9E3779B9;
  Math.random = function(){
    s |= 0; s = (s + 0x6D2B79F5) | 0;
    var t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
})();
"""


# A completed move, defined without reference to anything inside the engine:
#   at rest        lateral speed under REST lanes/second
#   moving         lateral speed over GO lanes/second at least once
#   completed      moving, then at rest again for HOLD consecutive samples
# A lane change runs at about 2.2 lanes/second and the idle drift at about 0.02, so the two
# thresholds are three orders of magnitude apart and nothing sits between them.
SAMPLER = r"""
(function(){
  var P = window.__probe, R = P.road;
  var LX = R.laneX();
  var LW = Math.abs(LX[1] - LX[0]);
  var REST = 0.10, GO = 0.60, HOLD = 3;
  var nextId = 1, cars = {};
  var lanes = function(x){ return x / LW; };
  var offLane = function(x){
    var best = 1e9;
    for(var i = 0; i < LX.length; i++) best = Math.min(best, Math.abs(LX[i] - x));
    return best / LW;                       /* distance to the nearest lane centre, IN LANES */
  };

  P.merge = { moves: [], samples: 0, off: 0, parked: 0, restN: 0,
              t0: performance.now(), cars: 0 };

  P.merge.timer = setInterval(function(){
    var dt = 0.05;
    var seen = {};
    (R.traffic || []).forEach(function(c){
      if(!c.__mtid){ c.__mtid = nextId++; }
      seen[c.__mtid] = 1;
      var s = cars[c.__mtid];
      if(!s){
        cars[c.__mtid] = { x: c.x, anchor: c.x, moving: false, still: 0, yielded: !!c.yielding };
        P.merge.cars++;
        return;
      }
      if(c.yielding) s.yielded = true;
      var v = Math.abs(lanes(c.x - s.x)) / dt;
      s.x = c.x;

      P.merge.samples++;
      if(offLane(c.x) > 0.12) P.merge.off++;

      /* PARKED BETWEEN LANES - the measurement that discriminates, and it reads
         no engine state at all.

         "Where is a car once it has given way" cannot be asked of the engine as
         it was, because `yielding` was set and never cleared: there was no
         afterwards to look at, and a check written that way ABSTAINS on the
         defect instead of failing on it. Measured that way round the defect is
         plain - a car that is standing still across the road and is not on a
         lane centre is in neither lane, whatever put it there. */
      if(v <= REST && offLane(c.x) > 0.12) P.merge.parked++;
      if(v <= REST) P.merge.restN++;

      if(v > GO){ s.moving = true; s.still = 0; return; }
      if(v > REST){ s.still = 0; return; }
      s.still++;
      if(s.moving && s.still >= HOLD){
        P.merge.moves.push({ size: Math.abs(lanes(c.x - s.anchor)),
                             landed: offLane(c.x), yielded: s.yielded });
        s.moving = false;
      }
      if(!s.moving) s.anchor = c.x;         /* at rest: this is where the next move starts from */
    });
    /* a culled car takes its half-finished move with it, which is what we want */
    for(var k in cars) if(!seen[k]) delete cars[k];
  }, 50);

  P.merge.collect = function(){
    return { moves: P.merge.moves, samples: P.merge.samples, off: P.merge.off,
             parked: P.merge.parked, restN: P.merge.restN,
             cars: P.merge.cars, secs: (performance.now() - P.merge.t0) / 1000,
             laneW: LW, lanes: LX.length };
  };
  return true;
})
"""


def run(browser, base_url, seconds, settle, pace):
    dt = drive_test_module()
    ctx = browser.new_context(viewport={'width': 480, 'height': 900})
    ctx.add_init_script(SEED_RNG)
    ctx.add_init_script(dt.INIT)
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    try:
        boot(page, base_url + '/' + GAME)
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5_000)
            page.wait_for_timeout(1_200)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10_000)
        if not page.evaluate('() => typeof window.__probe.road.laneX === "function"'):
            raise SystemExit('[merge-test] the engine does not expose laneX(). This harness reads '
                             'the lane geometry from road.js rather than keeping a copy, so it '
                             'stops here rather than measuring against a road that may have moved.')

        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10_000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5_000)
        page.click('[data-act="drive"]')            # TEST DRIVE: the road, no race
        page.wait_for_timeout(int(settle * 1000))

        before = page.evaluate('() => window.__probe.road.mergesMade()')
        beforeSig = page.evaluate(
            '() => window.__probe.road.signalledMerges ? window.__probe.road.signalledMerges() : 0')
        beforeStart = page.evaluate(
            '() => window.__probe.road.signalsStarted ? window.__probe.road.signalsStarted() : 0')
        page.evaluate(SAMPLER + '()')
        # Hold a real pace, the way traffic-test does: waves keep arriving, the field keeps
        # bunching, and cars keep finding reasons to go round each other.
        for _ in range(int(seconds * 4)):
            page.evaluate('(v) => window.__probe.road.setSpd(v)',
                          pace * page.evaluate('() => window.__probe.road.MAX_SPD'))
            page.wait_for_timeout(250)
        out = page.evaluate('() => window.__probe.merge.collect()')
        out['decided'] = page.evaluate('() => window.__probe.road.mergesMade()') - before
        out['signalled'] = page.evaluate(
            '() => window.__probe.road.signalledMerges ? window.__probe.road.signalledMerges() : 0'
        ) - beforeSig
        out['started'] = page.evaluate(
            '() => window.__probe.road.signalsStarted ? window.__probe.road.signalsStarted() : 0'
        ) - beforeStart
        page.evaluate('() => { clearInterval(window.__probe.merge.timer); }')
        out['errors'] = errors + page.evaluate('() => window.__probe.errors')
        return out
    finally:
        ctx.close()


def main():
    console_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=60.0)
    ap.add_argument('--settle', type=float, default=4.0)
    ap.add_argument('--pace', type=float, default=0.55,
                    help='player speed as a fraction of MAX_SPD, held through the run')
    ap.add_argument('--need-moves', type=int, default=12,
                    help='fewer completed moves than this and the run proves nothing')
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()

    print('merge-test  -  RLG-040  -  does traffic change a whole lane?  (%gs)' % args.seconds)

    httpd, port = serve(ROOT)
    try:
        with sync_playwright() as p:
            browser = launch_chromium(
                p, headless=not args.headed,
                args=['--autoplay-policy=no-user-gesture-required', '--mute-audio'])
            out = run(browser, 'http://127.0.0.1:%d' % port, args.seconds, args.settle, args.pace)
            browser.close()
    finally:
        httpd.shutdown()

    moves = [m for m in out['moves'] if not m['yielded']]
    yielders = [m for m in out['moves'] if m['yielded']]
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label, '   ' + detail if detail else ''))

    print()
    print('  %d lanes, %.3f lane width, %d cars seen, %d samples over %.0fs'
          % (out['lanes'], out['laneW'], out['cars'], out['samples'], out['secs']))
    print('  the engine decided on %d merges; this sampler saw %d completed moves '
          '(%d of them by a yielding car)' % (out['decided'], len(out['moves']), len(yielders)))
    print()

    # --- the vacuity guard, before any finding -------------------------------
    ok(out['samples'] > 200, 'the run was long enough to matter', '%d samples' % out['samples'])
    ok(len(moves) >= args.need_moves,
       'traffic moved often enough to be measured',
       '%d completed moves, need %d' % (len(moves), args.need_moves))
    if out['decided'] > 0 and not out['moves']:
        ok(False, 'the sampler saw the merges the engine says it made',
           'engine %d, sampler 0 - the sampler is what is wrong here'
           % out['decided'])

    if moves:
        sizes = [m['size'] for m in moves]
        landed = [m for m in moves if m['landed'] <= 0.15]
        full = [s for s in sizes if s >= 0.85]
        frac = [s for s in sizes if s < 0.5]
        print('    move size, in lanes   mean %.2f   median %.2f   min %.2f   max %.2f'
              % (statistics.fmean(sizes), statistics.median(sizes), min(sizes), max(sizes)))
        print('    a whole lane or more  %d of %d (%.0f%%)'
              % (len(full), len(sizes), 100 * len(full) / len(sizes)))
        print('    under half a lane     %d of %d (%.0f%%)'
              % (len(frac), len(sizes), 100 * len(frac) / len(sizes)))
        print('    came to rest on a lane centre  %d of %d (%.0f%%)'
              % (len(landed), len(moves), 100 * len(landed) / len(moves)))
        print()
        ok(statistics.median(sizes) >= 0.85,
           'a lane change is a whole lane',
           'median %.2f lanes' % statistics.median(sizes))
        ok(len(landed) / len(moves) >= 0.90,
           'and it ends on a lane centre',
           '%.0f%% landed' % (100 * len(landed) / len(moves)))

    if yielders:
        ys = [m['size'] for m in yielders]
        yl = [m for m in yielders if m['landed'] <= 0.15]
        print('    YIELDERS, reported and not judged: %d moves, mean %.2f lanes, '
              'median %.2f, %d of %d ended on a lane centre'
              % (len(ys), statistics.fmean(ys), statistics.median(ys), len(yl), len(ys)))
        print('    %.0f%% of every lateral move on the road was a yield, not a merge.'
              % (100 * len(yielders) / max(1, len(out['moves']))))
        print()

    off = out['off'] / max(1, out['samples'])
    print('    off a lane centre     %.0f%% of all samples' % (100 * off))
    ok(off <= 0.25, 'traffic is in a lane, not between two',
       '%.0f%% of samples off centre' % (100 * off))

    # THE LINE THAT DISCRIMINATES. A car standing still across the road and not on a lane
    # centre is in neither lane. Measured on the engine before this was fixed: 8%. After: under
    # 1%. It reads position over time and nothing else, so no change inside the merge logic can
    # make it report success by moving a flag.
    parked = out['parked'] / max(1, out['restN'])
    print('    standing still BETWEEN two lanes  %.1f%% of the samples where a car was at rest'
          % (100 * parked))
    ok(out['restN'] > 500, 'cars were seen at rest often enough to say', '%d samples' % out['restN'])
    ok(parked <= 0.03, 'no car is left parked between two lanes',
       '%.1f%% of at-rest samples' % (100 * parked))
    # ---- AND THE ANNOUNCED ONES COMPLETE (owner report, 2026-09-07) ------------
    # A car either moves at once - `signals` false, about one driver in five - or puts its
    # indicator on, waits, and then moves. THE SECOND PATH WAS DEAD. The merge decision
    # re-ran on every frame the car was held up, including the frames where it was already
    # waiting out its own indicator, and rewrote the wait with a fresh 1.1 to 1.8 seconds.
    # The countdown then took one frame off a number that had just been reset, so it could
    # never reach zero and four fifths of the traffic could not change lane at all.
    #
    # THIS FILE PASSED THE WHOLE TIME. The total merely fell from 30 completed moves to 18,
    # comfortably over the 12 this harness asks for, because both kinds of merge landed in
    # one counter. Splitting them out is what makes the defect visible: with it present this
    # number is EXACTLY ZERO, and no amount of ordinary traffic changes that.
    # COMPLETIONS ALONE DO NOT DISCRIMINATE. With the defect present the decision is only
    # re-entered on frames where `mergeCool` happens to be zero, so some waits survive by
    # luck: measured, 28 completions became 9 rather than 0, which two runs of ordinary
    # traffic could produce between them. The number of indicators STARTED is what separates
    # the two states absolutely - a working engine announces a move once, a broken one
    # announces the same move on every frame the car is held up.
    started, done = out['started'], out['signalled']
    rate = done / max(1, started)
    print('    indicators started  %d      of those, moves completed  %d   (%.0f%%)'
          % (started, done, 100 * rate))
    ok(done > 0 and rate > 0.25,
       'an announced lane change is announced ONCE and then made',
       '%d of %d signals completed (%.0f%%)' % (done, started, 100 * rate))
    ok(out['errors'] == [], 'no page errors', out['errors'][0][:100] if out['errors'] else '')

    print()
    print('  %s' % ('traffic changes lane properly' if not bad else '%d FAILURES' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
