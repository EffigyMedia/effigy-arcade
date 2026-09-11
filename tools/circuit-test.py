"""A CIRCUIT IS NOT A HIGHWAY - and it must stay that way when you stop.

`CFG.circuitOnly` switches off civilian traffic, police, roadblocks and crates,
because a closed track with a lorry on it is not a race. Four of the five
spawners are grouped together behind that gate where it is obvious. The fifth -
the one that drops a car in BEHIND you once you have been slower than the flow
for two seconds - sits up with the speed logic and was outside it, so slowing
down on the circuit conjured civilian traffic out of nothing.

That was reported from play, not caught by a gate, and no existing harness could
have seen it: the drive test holds the throttle down, and this only happens when
you stop.

So this stops. Both games, twelve seconds at a standstill, and then counts the
civilian cars. The circuit must be empty; the highway must not be, because
traffic arriving behind a stopped player is what makes stopping feel exposed.
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
from harness import launch_chromium, console_utf8, boot, until
from playwright.sync_api import sync_playwright
console_utf8()
h=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT))
srv=socketserver.TCPServer(('127.0.0.1',0),h); P=srv.server_address[1]
threading.Thread(target=srv.serve_forever,daemon=True).start()
bad = [0]
with sync_playwright() as p:
    b=launch_chromium(p,headless=True,args=['--mute-audio','--autoplay-policy=no-user-gesture-required'])
    for gid,path in [('motorsport','games/sw/motorsport.html'),('interstate','games/sw/interstate.html')]:
        pg=b.new_context(viewport={'width':480,'height':900}).new_page()
        boot(pg, f'http://127.0.0.1:{P}/{path}')
        try:
            until(pg, '() => navigator.serviceWorker && navigator.serviceWorker.controller',timeout=5000)
            pg.wait_for_timeout(1200)
        except Exception: pass
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]',timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]',timeout=5000)
        pg.click('[data-act="drive"]'); pg.wait_for_timeout(1500)
        # sit still for 12 seconds - the condition that conjures traffic
        for _ in range(48):
            pg.evaluate("() => window.__road.setSpd && window.__road.setSpd(0)")
            pg.wait_for_timeout(250)
        n = pg.evaluate("() => (window.__road.trafficCount ? window.__road.trafficCount() : null)")
        # THE HORN AND THE SIREN ARE HIGHWAY FURNITURE TOO. A horn asks traffic
        # to move over and a siren tells it to; a circuit has neither traffic
        # nor police, so both answer a question it does not ask. The BUTTON has
        # to go, not just its effect - a control that is present and does
        # nothing costs the player a lap of wondering what they are missing.
        horn = pg.evaluate("() => !!document.getElementById('horn')")
        siren_off = pg.evaluate("() => !!(window.__road.snd && window.__road.snd.noSiren)")
        want_horn = (gid != 'motorsport')
        hg = (horn == want_horn) and (siren_off == (gid == 'motorsport'))
        print(f'  {"ok  " if hg else "FAIL"}  {gid:<11} '
              f'horn control present: {horn}, siren muted: {siren_off}'
              f'  ({"a circuit needs neither" if gid == "motorsport" else "a highway needs both"})')
        if not hg:
            bad[0] += 1

        want_empty = (gid == 'motorsport')
        good = (n == 0) if want_empty else (n > 0)
        print(f'  {"ok  " if good else "FAIL"}  {gid:<11} '
              f'civilian traffic after 12s stopped: {n}'
              f'  ({"a circuit must be empty" if want_empty else "a highway must not be"})')
        if not good:
            bad[0] += 1
        pg.close()
    b.close()
srv.shutdown()
print()
print('  ' + ('the gate holds at a standstill' if not bad[0] else str(bad[0]) + ' FAILURES'))
sys.exit(1 if bad[0] else 0)
