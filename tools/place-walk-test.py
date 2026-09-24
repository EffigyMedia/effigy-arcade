#!/usr/bin/env python3
"""PLACE WALK TEST - the road never repeats a place, and never ping-pongs between two.

    .venv/Scripts/python tools/place-walk-test.py

OWNER, 2026-09-23, from the device: "for some reason, I kept getting mountain to
city to mountain to city to mountain to city to mountain to city. We also need to
make sure that we don't ever roll the same biome back to back."

TWO FAULTS, AND THEY ARE NOT THE SAME ONE. The rule asked for is that a place
never follows itself. The fault reported is an A-B-A-B PING-PONG, which that rule
does not prevent: a picker that only refuses the place you are standing in can
alternate between two forever and never break its own rule.

WHY IT HAPPENS HERE IS THE CLIMATE. Each place may only be entered at a
temperature within its own range, and the run's temperature may only move a step
at a time. A MOUNTAIN reaches 0.00 to 0.30 and a CITY reaches 0.00 to 0.90, so a
run that settles cold has essentially two places it can reach - TUNDRA's window
is 0.01 to 0.09 and everything else starts at 0.30. Refuse only the current
place and the walk has nowhere to go but back.

IT WALKS THE CHOICE WITHOUT DRIVING. `API.walkPlaces` asks the picker for a long
run of places from a given start, so a thousand crossings can be read in a second
- which matters, because a crossing takes about a mile of road and the fault only
shows over a dozen of them.

WHAT IT ASSERTS, from several cold starts and several warm ones:
  . no place ever follows itself - the owner's rule;
  . no place is back within two - the ping-pong;
  . and the walk reaches more than two places, which is the report itself.

WHAT IT DOES NOT CHECK: whether the ORDER is pleasing, or how long each place
runs for. It reads the picker, not the road.

Exit code 0 if every check passed, 1 otherwise.
"""
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright                  # noqa: E402
console_utf8()

fails = []
WALK = 300


def check(ok, label, detail=''):
    print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label, '   ' + detail if detail else ''))
    if not ok:
        fails.append(label)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
print('place-walk-test  .  no place follows itself, and no two places take turns')

with sync_playwright() as p:
    br = launch_chromium(p, headless=True)
    pg = br.new_page(viewport={'width': 480, 'height': 900})
    boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
    until(pg, '() => !!window.__road', timeout=15000)
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
    pg.click('[data-act="drive"]')
    pg.wait_for_timeout(1500)

    # THE STARTS ARE CHOSEN TO BE AWKWARD. A cold start is where the reachable
    # set is smallest, which is where the ping-pong was reported; a warm one is
    # the control, and should not have been able to produce it in the first
    # place.
    starts = [('MOUNTAIN', 0.15), ('TUNDRA', 0.05), ('CITY', 0.10),
              ('DESERT', 0.95), ('FOREST', 0.45)]
    worstRepeat = worstPing = 0
    fewest = 99
    for key, temp in starts:
        walk = pg.evaluate("([n, k, t]) => window.__road.walkPlaces(n, k, t)",
                           [WALK, key, temp])
        seq = [w['key'] for w in walk if w['key']]
        repeats = sum(1 for i in range(1, len(seq)) if seq[i] == seq[i-1])
        pings = sum(1 for i in range(2, len(seq)) if seq[i] == seq[i-2])
        distinct = len(set(seq))
        worstRepeat = max(worstRepeat, repeats)
        worstPing = max(worstPing, pings)
        fewest = min(fewest, distinct)
        # ---- AND WHERE THE TEMPERATURE WENT, WHICH IS THE CAUSE ------
        # A place may only be entered inside its own range, so the set of
        # places the road can reach IS the temperature. A walk that loops is a
        # walk whose temperature never left the corner it started in.
        ts = [w['temp'] for w in walk if w['temp'] is not None]
        print('  from %-9s at %.2f   %3d places, %2d distinct, %3d repeats, %3d ping-pongs'
              % (key, temp, len(seq), distinct, repeats, pings))
        print('        temperature %.2f to %.2f  (%d to %d F)'
              % (min(ts), max(ts), round(-10 + min(ts)*130), round(-10 + max(ts)*130)))
        print('        %s' % ' '.join(s[:3] for s in seq[:22]))

    print()
    check(worstRepeat == 0, 'no place ever follows itself',
          '%d times across every walk' % worstRepeat)
    check(worstPing == 0, 'no place comes back within two',
          '%d times across every walk' % worstPing)
    check(fewest > 2, 'every walk reaches more than two places',
          'the narrowest walk saw %d' % fewest)
    br.close()
srv.shutdown()

print()
print('  %d failure(s)%s' % (len(fails), (': ' + ', '.join(fails)) if fails else ''))
sys.exit(1 if fails else 0)
