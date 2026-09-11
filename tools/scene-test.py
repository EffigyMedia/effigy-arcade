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
# AND IT HAS SOMEWHERE TO WRITE WITHOUT BEING TOLD. This required its output directory as
# argv[1], so running it with no arguments - which is how every other harness is run, and
# how step.py runs one - raised IndexError before it opened a browser.
out=sys.argv[1] if len(sys.argv) > 1 else str(ROOT / '_scene')
import os; os.makedirs(out, exist_ok=True)
with sync_playwright() as p:
    b=launch_chromium(p,headless=True,args=['--mute-audio','--autoplay-policy=no-user-gesture-required'])
    pg=b.new_context(viewport={'width':390,'height':844},device_scale_factor=2).new_page()
    errs=[]; pg.on('pageerror',lambda e: errs.append(str(e)))
    boot(pg, f'http://127.0.0.1:{P}/games/em/hardpoint.html')
    pg.wait_for_timeout(2200)
    # three frames across the loop so the chase is visibly moving
    for i,ms in enumerate([0,2600,5200]):
        if ms: pg.wait_for_timeout(ms)
        pg.screenshot(path=f'{out}/scene-{i}.png')
    sig = pg.evaluate("""() => {
      const c=document.getElementById('hpArt');
      if(!c) return {err:'no canvas'};
      const g=c.getContext('2d');
      const d=g.getImageData(0,0,c.width,c.height).data;
      let lit=0,sum=0;
      for(let i=0;i<d.length;i+=4){ if(d[i]+d[i+1]+d[i+2]>40) lit++; sum+=d[i]+d[i+1]+d[i+2]; }
      return {w:c.width,h:c.height,litPixels:lit,mean:Math.round(sum/(d.length/4))};
    }""")
    print('  canvas:',sig)
    print('  running on title:', pg.evaluate("() => document.getElementById('veil').classList.contains('art')"))
    # AND IT MUST STOP WHEN A MENU TAKES OVER. This clicked CONTROLS, which is a screen this
    # project ruled out of existence: a controls page exists to tell a player which keys do what,
    # and a thumb does not need telling where it is (RLG-002). menu-test asserts its ABSENCE, so
    # this harness was waiting thirty seconds for a button that must never come back. OPTIONS is
    # the menu every title actually has.
    pg.get_by_text('OPTIONS',exact=False).first.click(); pg.wait_for_timeout(600)
    print('  stops on OPTIONS:', not pg.evaluate("() => document.getElementById('veil').classList.contains('art')"))
    print('  errors:',errs or 'none')
    b.close()
srv.shutdown()
