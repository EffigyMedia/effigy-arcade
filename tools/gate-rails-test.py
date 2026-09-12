#!/usr/bin/env python3
"""GATE RAILS TEST - a four-speed's gate has two rails, dragged by a THUMB.

    .venv/Scripts/python tools/gate-rails-test.py
    .venv/Scripts/python tools/gate-rails-test.py --falsify

RLG-220. Owner, 2026-09-12: "You can still change the gear to 5 and 6 on a 4 speed... they act as
neutral but the gates aren't rendered yet you can still put the shifter there." And, on what a
five-speed should keep: "It's fine if it's there for 5 speed... remove it on 4 speed!"

IT MUST BE DRIVEN BY A THUMB AND THAT IS THE WHOLE POINT OF THIS FILE. RLG-069 already fixed this
once, in `shiftStep`, which is what the I/K/J/L keys and the right stick call. The drag listener
never went through it and kept its own loop over `RAIL_X.length`. So a check written against
`shiftStep` - or against `API.shift`, which is a wrapper on it - PASSES ON THE BROKEN BUILD. That is
not a hypothetical: it is what happened, and it is why the defect survived a ruling that names it.

So this synthesises the pointer events the knob itself listens for: `pointerdown` on the knob, then
`pointermove` at an x far to the right of the last rail, which is the gesture the owner made. It
reads `API.gate().rail` afterwards - the engine's own report of where the knob is - and asserts the
knob did not reach a rail the car does not have.

  4-speed   two rails. The knob must not reach rail index 2 however hard it is dragged.
  5-speed   three rails, and the neutral slot on the third one stays. Owner's words above.
  6-speed   three rails, all of them real.

`--falsify` serves the engine with the drag loop back on `RAIL_X.length` - the defect exactly as
reported - and the four-speed check must fail. A check that cannot be made to fail is not evidence.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

GAME = 'games/sw/interstate.html'
# one car per gearbox size, and what its gate should hold. The gear counts are read off the engine
# rather than trusted from here - these names only choose which car to sit in.
CARS = [('SALOON', 4, 2), ('CRUISER', 5, 3), ('MATADOR', 6, 3)]

# THE MANUAL BOX HAS TO BE ON BEFORE BOOT. It is remembered in the shell's save slot and read back
# at start-up, so seeding the slot is how a harness sits in a car with a gate. Setting it afterwards
# would need the pause menu, which is a different thing to test.
SEED = """
try {
  /* TWO STORES, AND BOTH HAVE TO SAY IT. The game keeps the flag in its own save slot and reads it
     at start-up; the SHELL keeps the pause-menu setting separately and applies it afterwards, so
     seeding only the first was silently overwritten back to AUTO and the gate never appeared.
     `effigyarcade.<id>.opts.v1` is the shell's; `effigyarcade.save.v1.<id>-opts` is the game's. */
  localStorage.setItem('effigyarcade.save.v1.interstate-opts', JSON.stringify({ manual: true }));
  localStorage.setItem('effigyarcade.interstate.opts.v1', JSON.stringify({ manual: 'MANUAL' }));
} catch (e) {}
"""


def drag(pg, dx):
    """Drag the knob to NEUTRAL and then hard sideways, with a REAL pointer.

    NOT SYNTHESISED EVENTS, and the first build of this file learned why. Dispatching a
    `PointerEvent` with an invented `pointerId` makes the knob's own `setPointerCapture` throw
    before `knobDrag` is ever set, so the drag listener never arms - and every car reported the
    knob still on rail 0, which READS LIKE A PASS. The four-speed check and the six-speed check
    agreed with each other because neither gesture happened at all.

    `page.mouse` is a real input device to the browser, so the pointer events it raises carry a
    live id and the capture succeeds. The listener does not care that it is a mouse: it is a
    pointer handler, and the thumb raises the same events.
    """
    box = pg.evaluate("""() => {
      const k = document.getElementById('knob'), p = document.getElementById('shifter');
      if (!k || !p) return null;
      const a = k.getBoundingClientRect(), b = p.getBoundingClientRect();
      return { kx: a.left + a.width / 2, ky: a.top + a.height / 2,
               px: b.left + b.width / 2, py: b.top + b.height / 2 };
    }""")
    if not box:
        return 'no shifter'
    # A DEGENERATE BOX IS NOT A SHIFTER. Run under `step.py` on a busier machine, the drag landed
    # on nothing and every car reported rail 0 - which the "does reach the last rail" check caught
    # and a naive version would have called a pass. The plate is hidden until the manual box is on
    # and laid out, so a zero-sized rect means the gesture would go to the corner of the screen.
    if box['px'] <= 1 or box['py'] <= 1 or box['kx'] <= 1:
        return 'the shifter has no box yet'
    pg.mouse.move(box['kx'], box['ky'])
    pg.mouse.down()
    # the rail can only change from the centre row - that is the gate's own rule, not something
    # to route around, so the gesture goes through neutral exactly as a thumb must
    pg.mouse.move(box['kx'], box['py'], steps=4)
    # then hard across. A thumb does not stop politely at the last gate it is allowed into,
    # which is how the owner found this.
    for i in range(1, 7):
        pg.mouse.move(box['px'] + dx * i / 6.0, box['py'], steps=2)
    pg.mouse.up()
    return 'ok'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help='serve the drag loop back on RAIL_X.length; the four-speed check must fail')
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()

    dt_path = ROOT / 'tools' / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('dt', dt_path)
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('gate-rails-test  .  the gate holds the rails the car has, dragged by a thumb')
    if args.falsify:
        print('  FALSIFY: the drag loop is served back on RAIL_X.length. The four-speed must fail.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=not args.headed, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900},
                                has_touch=True, is_mobile=True)
            ctx.add_init_script(dt.INIT)
            ctx.add_init_script(SEED)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8').replace(
                    'for(let i2=0;i2<railCount();i2++){',
                    'for(let i2=0;i2<RAIL_X.length;i2++){')
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg.wait_for_timeout(1600)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            # WAIT FOR THE GATE, do not sleep and hope. A fixed 1200ms was enough on an idle
            # machine and not enough under `step.py`, where the drag then went to a plate that
            # had no layout yet and every car came back on rail 0.
            pg.wait_for_selector('#shifter', state='visible', timeout=10000)
            pg.wait_for_selector('#knob', state='visible', timeout=10000)
            pg.wait_for_function(
                "() => { const p = document.getElementById('shifter');"
                " return p && p.getBoundingClientRect().width > 10; }", timeout=10000)
            pg.wait_for_timeout(300)

            # THE GATE HAS TO BE THERE AT ALL, and this is asserted rather than assumed.
            # Without it every drag below moves nothing and every check passes for the wrong
            # reason - which is what the first build of this file did.
            g0 = pg.evaluate("() => window.__probe.road.gate()")
            ok(bool(g0) and bool(g0.get('manual')), 'the manual gearbox is on',
               'gate says manual=%s' % (g0 or {}).get('manual'))
            if not (g0 and g0.get('manual')):
                print('  every check below would pass vacuously. Stopping.')
                b.close()
                return 1

            for name, want_gears, want_rails in CARS:
                pg.evaluate("(k) => window.__probe.road.setBody(k)", name)
                pg.wait_for_timeout(250)
                g = pg.evaluate("() => window.__probe.road.gate()")
                ok(g['gears'] == want_gears,
                   '%-9s is a %d-speed' % (name, want_gears), 'engine says %d' % g['gears'])
                ok(g['rails'] == want_rails,
                   '%-9s declares %d rail(s)' % (name, want_rails), 'engine says %d' % g['rails'])
                # drag hard right, then hard left, and see where the knob ends up each time
                reached = []
                for dx in (260, -260):
                    r = drag(pg, dx)
                    if r != 'ok':
                        ok(False, '%-9s could not be dragged' % name, str(r))
                        break
                    pg.wait_for_timeout(120)
                    reached.append(pg.evaluate("() => window.__probe.road.gate().rail"))
                if len(reached) == 2:
                    worst = max(reached)
                    ok(worst <= want_rails - 1,
                       '%-9s the thumb cannot reach a rail it has not got' % name,
                       'rail %d of a gate %d wide' % (worst, want_rails))
                    ok(min(reached) == 0,
                       '%-9s and it can still reach the first rail' % name,
                       'lowest rail reached was %d' % min(reached))
                    # AND THE GESTURE HAS TO BE SHOWN TO DO ANYTHING. A car with three real
                    # rails must REACH the third one on a hard drag right. Without this the
                    # four-speed's "cannot reach rail 2" is satisfied by a drag that never
                    # happened, which is exactly how the first build of this file passed.
                    if want_rails == 3:
                        ok(worst == 2,
                           '%-9s and the drag does reach the last rail it has' % name,
                           'furthest rail reached was %d' % worst)

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
