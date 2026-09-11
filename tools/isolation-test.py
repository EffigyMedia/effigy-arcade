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
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h); P = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{P}'
G = {'quietus':'games/em/quietus.html','hardpoint':'games/em/hardpoint.html',
     'interstate':'games/sw/interstate.html','motorsport':'games/sw/motorsport.html'}
bad = 0
with sync_playwright() as p:
    b = launch_chromium(p, headless=True, args=['--mute-audio','--autoplay-policy=no-user-gesture-required'])
    ctx = b.new_context(viewport={'width':390,'height':844})
    pg = ctx.new_page()

    # the launcher sets music OFF; a fresh cabinet should inherit it ONCE
    boot(pg, f'{base}/index.html'); pg.wait_for_timeout(1500)
    print('  launcher scope :', pg.evaluate("() => window.Arcade.scope"))
    pg.evaluate("() => window.Arcade.music.toggle ? window.Arcade.music.toggle() : null")
    pg.evaluate("() => localStorage.setItem('effigyarcade.launcher.audio.v1', JSON.stringify({sfx:true,music:false,vMaster:0.5,vMusic:1,vSfx:1}))")

    for gid, path in G.items():
        boot(pg, f'{base}/{path}'); pg.wait_for_timeout(1600)
        scope = pg.evaluate("() => window.Arcade.scope")
        seeded = pg.evaluate("() => JSON.parse(localStorage.getItem('effigyarcade.'+window.Arcade.scope+'.audio.v1')||'null')")
        ok = scope == gid
        print(f'  {"ok  " if ok else "FAIL"}  {gid:<11} scope={scope}  seeded-from-launcher={seeded}')
        if not ok: bad += 1

    # now diverge one machine and prove the others do not move
    boot(pg, f'{base}/{G["quietus"]}'); pg.wait_for_timeout(1400)
    pg.evaluate("() => localStorage.setItem('effigyarcade.quietus.audio.v1', JSON.stringify({sfx:false,music:false,vMaster:0.1,vMusic:0,vSfx:0}))")
    boot(pg, f'{base}/{G["hardpoint"]}'); pg.wait_for_timeout(1400)
    hp = pg.evaluate("() => JSON.parse(localStorage.getItem('effigyarcade.hardpoint.audio.v1')||'null')")
    q  = pg.evaluate("() => JSON.parse(localStorage.getItem('effigyarcade.quietus.audio.v1')||'null')")
    iso = hp and q and hp.get('vMaster') != q.get('vMaster')
    print(f'  {"ok  " if iso else "FAIL"}  isolation   quietus vMaster={q.get("vMaster")}  hardpoint vMaster={hp.get("vMaster")}')
    if not iso: bad += 1
    b.close()
srv.shutdown()
print(f'\n  {"all isolated" if not bad else str(bad)+" FAILURES"}')
sys.exit(1 if bad else 0)
