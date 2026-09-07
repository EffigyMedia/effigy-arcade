"""INTERSTATE OCCLUSION - are cars hidden, or are they missing?

Crest occlusion in this engine has been wrong twice, and both times it was
invisible to every gate: the road still drove, the console stayed clean, and the
only symptom was that things stopped being on it. One of those attempts culled
EVERY distant sprite and the note left in the source records the result - "23
cars in range, 0 drawn".

A screenshot cannot settle it either, because an empty road and a road whose
cars are all behind a hill look the same in one frame.

So this drives for a while and reads `API.spriteStats()`, which counts what the
sprite pass did rather than what it was asked to do:

  drawn    fully visible
  clipped  straddling a crest - drawn, cut off at the silhouette
  culled   entirely under a crest

What it asserts:
  * sprites are being drawn at all, in quantity          (the 0-drawn failure)
  * culling is not swallowing most of them               (the over-cull failure)
  * over a run with hills, at least some get CLIPPED     (partial occlusion
    actually happening, rather than the test being disabled again)
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

# IT SERVES ITS OWN FOLDER, NOT THE CALLER'S. Both of these were relative to the working
# directory, so the harness only ran from the project root - and `step.py`, which records a
# run as evidence, runs from the environment root. The failure looked like the game never
# reaching its title card, which is a long way from "the server is serving the wrong place".
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
from playwright.sync_api import sync_playwright

console_utf8()

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{PORT}'

SECONDS = 12
STINTS = 3
# ---- ONE STINT IS NOT A MEASUREMENT --------------------------------------
# The terrain is generated fresh on every load and a short stint either meets hills or does not.
# Three runs on ONE unchanged build gave culled = 0, 40 and 147, and the 0 run also failed the
# `drawn > 200` assertion - so this harness was both a flaky gate and an unrepeatable number, and a
# before-and-after comparison made from single runs of it was worth nothing. Measured while fixing
# RLG-041, where exactly that mistake was made and had to be withdrawn from the record.
#
# So: several short stints, each from a fresh page and therefore a fresh road, summed. The per-stint
# figures are printed as well, because the SPREAD is the thing a reader needs to see before quoting
# any of it.


def stint(browser, secs):
    """Drive one fresh road and return what the sprite pass did."""
    ctx = browser.new_context(viewport={'width': 480, 'height': 900})
    page = ctx.new_page()
    errs = []
    page.on('pageerror', lambda e: errs.append(str(e)))
    try:
        page.goto(f'{BASE}/games/sw/interstate.html', wait_until='load')
        # THE FIRST VISIT RELOADS ITSELF. sw.js claims the client on activate, arcade.js reloads on
        # controllerchange, and anything clicked before that lands on a document that is about to be
        # thrown away - which is why the first version of this test reached the title and no further.
        try:
            page.wait_for_function(
                '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1200)
        if not page.evaluate("() => !!(window.__road && window.__road.spriteStats)"):
            return None, 0, errs
        # PINNED TO CITY, which is the only place that now has BOTH kinds. The biome is
        # picked fresh per load and the crest ledger can only report what was drawn, so
        # a stint that landed somewhere without the subject reads as a failure of the
        # gate rather than an absence of lamps.
        #
        # It was pinned to FOREST until the lamps became city scenery (RLG-059), at
        # which point the lamp assertions went red at asked=0 - the harness measuring a
        # thing the ruling had just moved. Recorded rather than quietly repinned,
        # because "the check went red and the fix was to change the check" is the
        # shape that hides a real regression.
        page.evaluate("() => { window.__road.setBiomePair && window.__road.setBiomePair('CITY','CITY'); }")
        page.evaluate("() => { window.__road.setSpd && window.__road.setSpd(9000); }")
        page.evaluate("() => { window.__road.resetCrestStats && window.__road.resetCrestStats(); }")
        page.evaluate("() => { window.__road.watchDraw && window.__road.watchDraw(true); }")
        tot = {'drawn': 0, 'clipped': 0, 'culled': 0}
        # ---- AND WHAT THE WALK DID WITH THE ROADSIDE (owner report, 2026-09-07) ----
        # `invFrames` counts frames where the inversion guard took at least one slice;
        # `invLost` counts slices it took that then drew NO roadside. Before the fix
        # invLost equalled every inverted slice - 70 to 94 of 151 in a jungle frame -
        # and the trees on the whole far half of the draw were simply absent while the
        # cars standing among them were painted. That is the owner's report.
        walk = {'invFrames': 0, 'invSlices': 0, 'invLost': 0, 'noScen': set()}
        frames = 0
        for _ in range(int(secs * 4)):
            page.wait_for_timeout(250)
            st = page.evaluate("() => window.__road.spriteStats()")
            w = page.evaluate("() => window.__road.walkTrace"
                              " ? JSON.parse(JSON.stringify(window.__road.walkTrace())) : null")
            if w:
                drew = set(w['scen'])
                invn = [a[0] for a in w['inv']]
                if invn:
                    walk['invFrames'] += 1
                    walk['invSlices'] += len(invn)
                    walk['invLost'] += sum(1 for n in invn if n not in drew)
                walk['noScen'].update(w['noScen'])
            if st and (st['drawn'] or st['clipped'] or st['culled']):
                frames += 1
                for k in tot:
                    tot[k] += st[k]
        # WHAT THE SHARED CREST GATE DID, per kind of thing that asked it (RLG-073). It
        # accumulates over the whole stint rather than being reset per frame, so it is read
        # once at the end.
        crest = page.evaluate("() => window.__road.crestStats ? window.__road.crestStats() : null")
        return tot, frames, errs, crest, walk
    finally:
        ctx.close()


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
        tot = {'drawn': 0, 'clipped': 0, 'culled': 0}
        frames, errs, per = 0, [], []
        crest_tot = {}
        walk_tot = {'invFrames': 0, 'invSlices': 0, 'invLost': 0, 'noScen': set()}
        for i in range(STINTS):
            st, f, e, crest, w = stint(b, SECONDS)
            errs += e
            for k in ('invFrames', 'invSlices', 'invLost'):
                walk_tot[k] += w[k]
            walk_tot['noScen'].update(w['noScen'])
            for who, row in (crest or {}).items():
                acc = crest_tot.setdefault(who, {'asked': 0, 'hidden': 0, 'clipped': 0})
                for k in acc:
                    acc[k] += row.get(k, 0)
            if st is None:
                ok(False, 'could reach the drive', f'stint {i + 1} never started')
                b.close(); srv.shutdown(); return 1
            per.append(st)
            frames += f
            for k in tot:
                tot[k] += st[k]
            print(f"  ..    stint {i + 1}: drawn={st['drawn']} clipped={st['clipped']} "
                  f"culled={st['culled']}   (a fresh road each time)")

        ok(frames > 0, 'the sprite pass ran', f'{frames} sampled frames over {STINTS} roads')
        ok(tot['drawn'] > 200, 'sprites are drawn, in quantity',
           f"drawn={tot['drawn']} clipped={tot['clipped']} culled={tot['culled']}")
        seen = tot['drawn'] + tot['clipped']
        ok(seen > 0 and tot['culled'] < seen,
           'culling is not swallowing the road',
           f"visible={seen} culled={tot['culled']}")
        ok(tot['clipped'] > 0,
           'some cars are CUT OFF by a crest rather than deleted',
           f"clipped={tot['clipped']}")
        # THE SPREAD, SAID OUT LOUD. Anyone comparing this run with another needs to know how much
        # of the difference is the road rather than the code.
        cul = [x['culled'] for x in per]
        print(f"  ..    culled per stint: {', '.join(str(c) for c in cul)} - "
              f"the road, not the code. Do not compare single runs")
        # ---- THE LAMPS GO THROUGH THE CARS' GATE (RLG-073) -----------------------
        # The owner asked for the lamps and every scenery object to use "the same system
        # that clips and culls vehicles", not one that behaves like it. So the assertion
        # is about the gate itself: both kinds must appear in ITS ledger. Two separate
        # implementations that each happened to work would fail this and should.
        for who, row in sorted(crest_tot.items()):
            print(f"  ..    crest gate, {who}: asked={row['asked']} hidden={row['hidden']} "
                  f"clipped={row['clipped']}")
        ok('car' in crest_tot and 'lamp' in crest_tot and 'scenery' in crest_tot,
           'the cars, the lamps AND the roadside scenery go through one crest gate',
           f"kinds that asked: {sorted(crest_tot) or 'none'}")
        scn = crest_tot.get('scenery', {})
        ok(scn.get('clipped', 0) > 0,
           'a tree coming over a brow is CUT OFF rather than popped in',
           f"clipped={scn.get('clipped', 0)} of {scn.get('asked', 0)}")
        lamp = crest_tot.get('lamp', {})
        ok(lamp.get('asked', 0) > 0, 'the lamps ask it at all',
           f"asked={lamp.get('asked', 0)}")
        # Before this, the lamps' test was `!overBrow(...)`, and `overBrow` returns false on
        # its first line - dead since crestY was re-enabled. A post behind a hill drew
        # straight through it and one coming over a brow arrived whole, so a non-zero clip
        # count here is not a tuning result, it is a thing that could not happen at all.
        ok(lamp.get('clipped', 0) > 0, 'a lamp coming over a brow is CUT OFF rather than popped in',
           f"clipped={lamp.get('clipped', 0)} of {lamp.get('asked', 0)}")
        # HIDDEN IS REPORTED AND NOT ASSERTED, for the same reason this file already refuses
        # to quote a single run: the cull count is the road rather than the code. The cars'
        # own `culled` came back 0, 40 and 147 on one unchanged build, and it is 0 for both
        # kinds on plenty of honest roads. An assertion on it would fail at random and get
        # this harness switched off, which is the failure mode the file was written against.
        print(f"  ..    hidden this run: car={crest_tot.get('car', {}).get('hidden', 0)} "
              f"lamp={lamp.get('hidden', 0)} - the road, not the code. Not asserted on")
        # ---- A SLICE THE WALK DROPPED STILL OWES ITS ROADSIDE --------------------
        # Owner report, 2026-09-07: traffic "behind the scenery, but rendered on top".
        # The traffic was not painted over the trees; the trees were never painted. The
        # three guards at the top of `drawRoad` also skipped `drawScenery`, and the
        # inversion guard alone took 70 to 94 slices of 151 in a jungle frame - every one
        # of them inverted by UNDER ONE PIXEL, which is the road flattening toward the
        # horizon and not a hill.
        #
        # THE CHECK IS NOT VACUOUS AND IT SAYS SO WHEN IT IS. It can only speak about a
        # road that actually inverted, and about half of the roads generated here do not.
        # The frame count is printed for exactly that reason: at zero this run proved
        # nothing, and it is still not turned into a failure, because a gate that goes red
        # on the terrain is a gate that gets switched off.
        print(f"  ..    the walk: {walk_tot['invFrames']} frame(s) had an inverted slice, "
              f"{walk_tot['invSlices']} slices in all")
        ok(walk_tot['invLost'] == 0,
           'a slice the inversion guard dropped still drew its roadside',
           f"{walk_tot['invLost']} of {walk_tot['invSlices']} drew none"
           if walk_tot['invSlices'] else
           'NO ROAD INVERTED THIS RUN - this check proved nothing')
        # The only slice allowed to draw no roadside is one with no valid near end, which
        # is where the camera itself is. Anything further out is a thing gone missing.
        far = sorted(n for n in walk_tot['noScen'] if n > 2)
        ok(not far, 'only the slices under the camera draw no roadside at all',
           f"also missing on {far[:12]}" if far else f"none beyond {sorted(walk_tot['noScen'])}")
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        b.close()

    srv.shutdown()
    print(f"\n  {'occlusion hides, it does not delete' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
