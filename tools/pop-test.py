"""RLG-041 - vehicles disappear and reappear. This is the MEASUREMENT, and it changes nothing.

The owner reported it from play on a real device. Nothing here has ever reproduced it, and the
fragment is explicit that the first unit is an instrument rather than a fix, for a reason the
project has already paid for once: "occasional" and "disappear and reappear" fit at least four
mechanisms present in this engine, and a plausible-sounding rendering cause has produced a wrong
plan in this codebase before.

THE QUESTION THE RULING ASKS, IN ONE LINE
-----------------------------------------
Is the vehicle still in `traffic` or `racers` at the moment it is not drawn?

  still in the array   a DRAW fault. The object exists, the painter declined to paint it.
  gone from the array  a SPAWN or CULL fault. Nothing was asked to paint it, correctly.

Those are different bugs with different fixes, and a harness that cannot separate them is worth
nothing here. So every event below is stamped with both.

WHAT IT READS
-------------
`road.js` carries a ledger behind `API.watchDraw()`. Every vehicle offered to the painter records
the reason it did or did not appear, and the reasons are the painter's own exits rather than this
file's idea of them:

  drawn / clipped   painted; `clipped` is a car across a crest, which is deliberate (RLG-021)
  behind            nearer than 430 units - behind the camera
  noproj            the projection refused the point
  tiny / huge       too small to see, or so close it fills the screen. NEITHER counts a stat
                    today, so both are invisible to `spriteStats`
  offscreen         off the top or the bottom of the frame
  crest             entirely under a hill silhouette
  unbucketed        outside the drawn road, so the painter was never offered it
  unemitted         bucketed, but the road never painted that slice. This IS the occlusion
                    mechanism, not a fault by itself
  nosprite          no painter entry for that body

A POP, DEFINED WITHOUT REFERENCE TO A CAUSE
-------------------------------------------
A vehicle that was painted, then was not painted, then was painted again, while never leaving the
array. That is what "disappears and reappears" means from the seat, and it is measured as such: the
reason is recorded but no reason is assumed. A car that leaves the array and comes back is a
different event and is counted separately - it cannot be the same car, but it can look like one.

WHAT THIS CANNOT TELL YOU
-------------------------
It runs at desktop frame rates in a headless browser at 480x900. The owner's report is from a phone.
A pop that only happens under a frame-time spike, or at a device pixel ratio this never sees, will
not appear here - and a clean run is therefore NOT evidence that the reported fault does not exist.
Say so in the record rather than closing the fragment on it.
"""

import argparse
import collections
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
GAMES = {'interstate': 'games/sw/interstate.html',
         'motorsport': 'games/sw/motorsport.html'}


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
        '[pop-test] playwright is not importable and there is no project .venv to hand over to.\n'
        '           Build one: uv venv .venv, then uv pip install --python .venv playwright')


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


# The collector runs on rAF so it sees EVERY frame the engine paints. A sample taken on a timer
# cannot tell a vehicle that was skipped for one frame from one the sampler happened to miss, and
# one frame is exactly the length of the event being hunted. The frame number the engine returns is
# what proves the difference: a gap in it is the collector's fault and is counted as one.
COLLECTOR = r"""
(function(){
  var P = window.__probe, R = P.road;
  var PAINTED = { drawn:1, clipped:1 };
  var last = {}, frames = 0, gaps = 0, lastN = null;
  var pops = [], vanish = [], reasons = {}, offered = 0, inArrayNotOffered = 0;
  var browAt = {}, browJump = [], bigAt = [], cutAt = {}, cutJump = [], cutDir = {}, reversals = [];

  P.pop = { on:true };
  R.watchDraw(true);

  var inWorld = function(){
    var live = {};
    var add = function(list){ if(list) for(var i=0;i<list.length;i++){
      var o = list[i]; if(o.__vid) live[o.__vid] = o; } };
    add(R.traffic); add(R.racers); add(R.cops && R.cops());
    return live;
  };

  var tick = function(){
    if(!P.pop.on) return;
    window.requestAnimationFrame(tick);
    var f = R.drawFrame();
    if(f.n === lastN) return;                 /* the engine has not painted since we last looked */
    if(lastN !== null && f.n !== lastN + 1) gaps += (f.n - lastN - 1);
    lastN = f.n;
    frames++;

    var live = inWorld(), now = {};
    for(var i = 0; i < f.seen.length; i++){
      var e = f.seen[i];
      now[e.id] = e;
      offered++;
      reasons[e.why] = (reasons[e.why] || 0) + 1;
      /* HOW FAR THE BROW MOVED since this car's last frame. The crest silhouette is what
         decides whether a car is hidden, so a step in it IS a car appearing or vanishing at
         the brow of a hill - which is what the owner reports seeing. */
      if(e.brow !== null && e.brow !== undefined){
        var pc = cutAt[e.id];
        if(pc !== undefined && e.cut !== undefined){
          var dc = Math.abs(e.cut - pc);
          if(dc > 0.25) cutJump.push({ dz:e.dz, px:e.px, from:+pc.toFixed(2), to:e.cut });
          /* ---- IS IT GOING, OR IS IT FLICKERING? -------------------------
             A car sliding behind a hill loses itself in ONE direction. A car
             that flickers loses and regains. Only the second is a fault, and
             the two are indistinguishable in a count of jumps. */
          if(dc > 0.10){
            var dir = e.cut > pc ? 1 : -1;
            if(cutDir[e.id] !== undefined && cutDir[e.id] !== dir)
              reversals.push({ dz:e.dz, px:e.px, at:+e.cut.toFixed(2) });
            cutDir[e.id] = dir;
          }
        }
        cutAt[e.id] = e.cut;
        var prev = browAt[e.id];
        if(prev !== undefined){
          var d = Math.abs(e.brow - prev);
          browJump.push(d);
          /* WHERE a big step happens. The owner reports the survivors in valleys, at a
             particular place, so the distribution of distances is the question. */
          if(d > 10) bigAt.push({ dz: e.dz, from: +prev.toFixed(1), to: e.brow });
        }
        browAt[e.id] = e.brow;
      } else { delete browAt[e.id]; }
    }

    /* every vehicle the engine knows about, whether or not the painter saw it */
    for(var id in live){
      var e = now[id], was = last[id];
      var why = e ? e.why : 'not-offered';
      if(!e) inArrayNotOffered++;
      var painted = !!(e && PAINTED[e.why]);
      if(was && was.painted && !painted){
        /* it stopped being painted and it is STILL IN THE ARRAY: a draw fault by definition,
           whatever the reason turns out to be */
        was.goneAt = frames; was.goneWhy = why; was.goneDz = e ? e.dz : null;
        was.goneMiss = (e && e.miss !== undefined) ? e.miss : null;
      }
      if(was && was.goneAt && painted){
        pops.push({ why: was.goneWhy, dz: was.goneDz, frames: frames - was.goneAt,
                    miss: was.goneMiss, kind: 'in-array' });
        was.goneAt = 0;
      }
      last[id] = last[id] || {};
      last[id].painted = painted;
      last[id].goneAt = was ? was.goneAt : 0;
      last[id].goneWhy = was ? was.goneWhy : '';
      last[id].goneDz = was ? was.goneDz : null;
      last[id].dz = e ? e.dz : (was ? was.dz : null);
    }

    /* and the other half of the ruling's question: a vehicle that was being painted and has left
       the arrays altogether. Not a draw fault - a cull or a spawn one - and it has to be counted
       apart or the two will be added together and called one number. */
    for(var k in last){
      if(live[k]) continue;
      if(last[k].painted) vanish.push({ dz: last[k].dz });
      delete last[k];
    }
  };
  window.requestAnimationFrame(tick);

  P.pop.collect = function(){
    P.pop.on = false;
    R.watchDraw(false);
    return { frames:frames, gaps:gaps, pops:pops, vanish:vanish, reasons:reasons,
             browJump:browJump, bigAt:bigAt, cutJump:cutJump, reversals:reversals,
             offered:offered, notOffered:inArrayNotOffered };
  };
  return true;
})
"""


def run(browser, base_url, game, seconds, settle):
    dt = drive_test_module()
    ctx = browser.new_context(viewport={'width': 480, 'height': 900})
    ctx.add_init_script(dt.INIT)
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    try:
        boot(page, base_url + '/' + GAMES[game])
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5_000)
            page.wait_for_timeout(1_200)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10_000)
        if not page.evaluate('() => typeof window.__probe.road.watchDraw === "function"'):
            raise SystemExit('[pop-test] the engine has no draw ledger (API.watchDraw). This '
                             'harness reads the painter\'s own exits and cannot infer them from '
                             'outside, so it stops rather than reporting on nothing.')

        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10_000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5_000)
        if game == 'interstate':
            page.click('[data-act="mode"]')        # TEST DRIVE -> SINGLE RACE: rivals as well
            page.wait_for_timeout(150)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(400)
        page.evaluate('() => window.__probe.drive()')
        page.wait_for_timeout(int(settle * 1000))
        page.evaluate(COLLECTOR + '()')
        page.wait_for_timeout(int(seconds * 1000))
        out = page.evaluate('() => window.__probe.pop.collect()')
        page.evaluate('() => window.__probe.stop()')
        out['errors'] = errors + page.evaluate('() => window.__probe.errors')
        return out
    finally:
        ctx.close()


def report(game, out, seconds):
    print()
    print('  %s   %d frames, %d vehicle-frames offered to the painter'
          % (game.upper(), out['frames'], out['offered']))
    if out['gaps']:
        print('    %d engine frames were missed by the collector - every number below is a '
              'LOWER BOUND' % out['gaps'])
    if out['notOffered']:
        print('    %d vehicle-frames were in an array and never offered to the painter at all'
              % out['notOffered'])

    order = sorted(out['reasons'].items(), key=lambda kv: -kv[1])
    total = max(1, sum(out['reasons'].values()))
    print('    what the painter did, per vehicle-frame:')
    for why, n in order:
        print('      %-11s %8d  %5.1f%%' % (why, n, 100.0 * n / total))

    # THE BROW, FRAME TO FRAME. It is sampled once per road segment, so it steps as a car crosses
    # a boundary - and a step in the silhouette is a car appearing or vanishing at the brow of a
    # hill. Reported as the distribution of jumps, in screen pixels.
    mins = max(seconds, 1) / 60.0
    rv = out['reversals']
    print('    REVERSALS - a car losing a tenth of itself to the crest and then getting it back: '
          '%d  (%.1f/min)' % (len(rv), len(rv) / mins))
    if rv:
        farr = [r for r in rv if r['dz'] >= 8000]
        print('      beyond 8,000 units: %d, median %d units, median height %.1f px'
              % (len(farr), statistics.median([r['dz'] for r in farr]) if farr else 0,
                 statistics.median([r['px'] for r in farr]) if farr else 0))

    cj = out['cutJump']
    if cj:
        near = [c for c in cj if c['dz'] < 8000]
        far  = [c for c in cj if c['dz'] >= 8000]
        print('    a car LOST OR REGAINED over a quarter of itself between two frames: %d times'
              % len(cj))
        print('      within 8,000 units: %-4d   beyond: %-4d' % (len(near), len(far)))
        if far:
            print('      the far ones: median %d units out, median sprite height %.1f px'
                  % (statistics.median([c['dz'] for c in far]),
                     statistics.median([c['px'] for c in far])))
    else:
        print('    no car lost a quarter of itself between two frames')

    big = out['bigAt']
    if big:
        ds = sorted(b['dz'] for b in big)
        print('    steps over 10 px in the silhouette: %d, at distances %d to %d (median %d)'
              % (len(ds), ds[0], ds[-1], statistics.median(ds)))
        buckets = {}
        for b in big:
            k = (b['dz'] // 4000) * 4000
            buckets[k] = buckets.get(k, 0) + 1
        for k in sorted(buckets):
            print('      %6d - %6d units: %-3d %s'
                  % (k, k + 3999, buckets[k], '#' * min(50, buckets[k])))

    bj = [j for j in out['browJump'] if j > 0.05]
    if bj:
        big = [j for j in bj if j > 2.0]
        print('    the crest silhouette moved between frames: %d times, median %.2f px, '
              'max %.1f px' % (len(bj), statistics.median(bj), max(bj)))
        print('      of those, jumps over 2 px:  %d  (%.1f%% of moves)  - a step, not a slide'
              % (len(big), 100.0 * len(big) / len(bj)))
    else:
        print('    the crest silhouette never moved - no hills were met, so this run says nothing')

    pops = out['pops']
    mins = max(seconds, 1) / 60.0
    print('    POPS - painted, not painted, painted again, never leaving the array:  %d  (%.1f/min)'
          % (len(pops), len(pops) / mins))
    if pops:
        by = collections.Counter(p['why'] for p in pops)
        for why, n in by.most_common():
            dzs = [p['dz'] for p in pops if p['why'] == why and p['dz'] is not None]
            gap = [p['frames'] for p in pops if p['why'] == why]
            print('      %-11s %5d   median %s units ahead, out for a median of %d frames'
                  % (why, n,
                     ('%d' % statistics.median(dzs)) if dzs else 'n/a',
                     statistics.median(gap)))
    # A FLICKER IS NOT AN OCCLUSION, AND THE DIFFERENCE IS THE WHOLE REPORT.
    # A car that is gone for two seconds while you drive over a rise is the hill doing its job and
    # reads as one. A car gone for three frames at 17,000 units reads as a glitch, which is the
    # word the owner used. Same event by the definition above; different bug, and possibly not a
    # bug at all in the first case.
    flick = [p for p in pops if p['frames'] <= 5]
    print('      of those, gone for 5 frames or fewer - a FLICKER, not an occlusion:  %d  (%.1f/min)'
          % (len(flick), len(flick) / mins))
    if flick:
        by = collections.Counter(p['why'] for p in flick)
        for why, n in by.most_common():
            dzs = [p['dz'] for p in flick if p['why'] == why and p['dz'] is not None]
            print('        %-11s %5d   median %s units ahead'
                  % (why, n, ('%d' % statistics.median(dzs)) if dzs else 'n/a'))
        # HOW NEARLY THE SLICE WAS PAINTED. A car behind a hill and a car on a crest tangent are
        # the same `unemitted` event and are not the same thing. The engine records the smaller of
        # the two misses that would have emitted the bucket, in screen pixels.
        miss = [p['miss'] for p in flick if p['why'] == 'unemitted' and p['miss'] is not None]
        if miss:
            tight = [m for m in miss if m <= 4]
            print('        the slice missed being painted by: median %.1f px, min %.1f, max %.1f'
                  % (statistics.median(miss), min(miss), max(miss)))
            print('        %d of %d missed by 4 pixels or fewer - a crest tangent, not a hill'
                  % (len(tight), len(miss)))
    print('    LEFT THE ARRAY while being painted (a cull or a spawn, not a draw):  %d'
          % len(out['vanish']))
    if out['vanish']:
        dzs = [v['dz'] for v in out['vanish'] if v['dz'] is not None]
        if dzs:
            print('      median %d units ahead, range %d to %d'
                  % (statistics.median(dzs), min(dzs), max(dzs)))
    if out['errors']:
        print('    page errors: ' + out['errors'][0][:110])


def main():
    console_utf8()
    ap = argparse.ArgumentParser()
    # Interstate by default. MOTORSPORT'S `DRIVE` IS A SOLO PRACTICE SESSION - no traffic, no
    # grid, nothing on the track but you - and QUALIFY is solo as well, so neither reaches a
    # vehicle for this to measure. Getting to a circuit grid needs a flow this harness does not
    # have. Ask for it explicitly and the run will tell you it saw nothing rather than print zeros.
    ap.add_argument('games', nargs='*', choices=list(GAMES), default=None)
    ap.add_argument('--seconds', type=float, default=45.0)
    ap.add_argument('--settle', type=float, default=5.0)
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    games = args.games or ['interstate']

    print('pop-test  -  RLG-041  -  which vehicle was not drawn, and why  (%gs each)'
          % args.seconds)

    httpd, port = serve(ROOT)
    outs = {}
    try:
        with sync_playwright() as p:
            browser = launch_chromium(
                p, headless=not args.headed,
                args=['--autoplay-policy=no-user-gesture-required', '--mute-audio'])
            for g in games:
                outs[g] = run(browser, 'http://127.0.0.1:%d' % port, g, args.seconds, args.settle)
            browser.close()
    finally:
        httpd.shutdown()

    empty = [g for g in games if not outs[g]['offered']]
    for g in games:
        report(g, outs[g], args.seconds)

    if empty:
        print()
        raise SystemExit(
            "[pop-test] %s put NO vehicle in front of the painter for the whole run, so the "
            "numbers above are the absence of a measurement rather than a clean result. "
            "Motorsport's DRIVE is a solo practice session and QUALIFY is a solo lap; reaching a "
            "grid needs a flow this harness does not have." % ", ".join(empty))

    print()
    print('  A DRAW fault and a CULL fault are the two lines above and they are not the same bug.')
    print('  This run says nothing about a phone: it is a headless desktop browser at 480x900, and')
    print('  a pop that needs a frame-time spike or another pixel ratio will not appear in it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
