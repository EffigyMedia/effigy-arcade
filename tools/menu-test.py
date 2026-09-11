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
h=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT))
srv=socketserver.TCPServer(('127.0.0.1',0),h); P=srv.server_address[1]
threading.Thread(target=srv.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{P}'
G={'quietus':'games/em/quietus.html','hardpoint':'games/em/hardpoint.html',
   'interstate':'games/sw/interstate.html','motorsport':'games/sw/motorsport.html'}
bad=0
with sync_playwright() as p:
    b=launch_chromium(p,headless=True,args=['--mute-audio','--autoplay-policy=no-user-gesture-required'])
    ctx=b.new_context(viewport={'width':390,'height':844})
    for gid,path in G.items():
        pg=ctx.new_page(); errs=[]
        pg.on('pageerror',lambda e: errs.append(str(e)))
        pg.on('console',lambda m: errs.append('console: '+m.text) if m.type=='error' else None)
        boot(pg, f'{base}/{path}'); pg.wait_for_timeout(2600)
        btns=[t.strip() for t in pg.locator('#veilBody button, #veil button').all_inner_texts() if t.strip()]
        # NO CONTROLS SCREEN. These are touch games, so a page listing gestures
        # is a page describing what the interface already shows. This check
        # asserted the opposite for about an hour; it asserts the ruling now.
        has_ctrl = any('CONTROLS' in t for t in btns)
        # OPTIONS must still open and come back, which is the path that broke
        # when the controls screen was lifted out from between them
        roundtrip = None
        if any('OPTIONS' in t for t in btns):
            pg.get_by_text('OPTIONS',exact=False).first.click(); pg.wait_for_timeout(600)
            pg.get_by_text('BACK',exact=False).first.click(); pg.wait_for_timeout(600)
            after=[t.strip() for t in pg.locator('#veilBody button, #veil button').all_inner_texts() if t.strip()]
            roundtrip = any('OPTIONS' in t for t in after)
        ok = (not has_ctrl) and roundtrip and not errs
        print(f'  {"ok  " if ok else "FAIL"}  {gid:<11} {" / ".join(btns)}'
              + ('   CONTROLS should be gone' if has_ctrl else '')
              + ('' if roundtrip else '   OPTIONS did not return to the title')
              + (f'   errors={errs}' if errs else ''))
        if not ok: bad+=1
        pg.close()
    b.close()
srv.shutdown()
print(f'\n  {len(G)-bad}/{len(G)} titles complete')
sys.exit(1 if bad else 0)
