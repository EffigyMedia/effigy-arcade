"""What the two test harnesses need from the machine they run on.

Playwright normally drives a browser build it downloads itself - about 130 MB per engine, kept
outside this repository. That build is the right thing when it is there: it is pinned, so a number
measured today can be compared with a number measured in six months.

It is not always there. A fresh environment has the `playwright` package and no browsers, and
downloading one is a decision about somebody's disk rather than a thing a test script should do on
its own. Most machines that run this already have Chrome or Edge installed, and for what these
harnesses ask - does the cabinet boot, is there paint on the canvas, does the car reach 150mph -
an installed Chrome answers exactly as well.

▶ THE BROWSER THAT WAS USED IS PRINTED, ALWAYS. A harness that silently changed which engine it
measured would be a harness whose numbers cannot be compared between two runs, and the first
symptom would be a performance figure that moved for no reason anybody could find.

To pin the browser instead: `python -m playwright install chromium`.
"""

CHANNELS = ("chrome", "msedge")


def launch_chromium(p, **kw):
    """Playwright's own build first, then an installed Chrome or Edge. Says which it got."""
    try:
        browser = p.chromium.launch(**kw)
        print("  browser: playwright bundled chromium (pinned)")
        return browser
    except Exception as bundled_failed:
        for channel in CHANNELS:
            try:
                browser = p.chromium.launch(channel=channel, **kw)
                print(f"  browser: installed {channel} - no bundled chromium, so the engine "
                      f"version is whatever this machine has")
                return browser
            except Exception:
                continue
        raise bundled_failed


def node_exe():
    """The node executable, by whatever name this machine has it under.

    THE HARNESSES SHELL OUT TO NODE to read `games.js`, because the catalogue is JavaScript and
    the alternative is a second parser that can disagree with the launcher. On Windows the name
    is the problem: `subprocess` calls CreateProcess directly, which does not apply PATHEXT, so a
    bare "node" misses `node.cmd` and `node.exe` and fails with "The system cannot find the file
    specified" - a message that names neither node nor PATH.
    """
    import shutil
    for name in ("node", "node.exe", "node.cmd", "node.bat"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit(
        "[harness] node is not on PATH, and the catalogue is read with it.\n"
        "          Install Node, or run the environment's shim installer.")


def console_utf8():
    """Make this console take the characters the harnesses print.

    THE REPORTS ARE FULL OF THEM - a middle dot between fields, an arrow between HUD states, an
    approximation sign in front of a measured average. On Windows the console is cp1252 by default,
    and printing one of those raises `UnicodeEncodeError` INSIDE the report, AFTER every check has
    already run and passed. The result is a harness that does the work, throws the answer away, and
    exits non-zero - which reads as a failing test suite rather than as a broken printer.
    """
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Booting a cabinet: wait for the ENGINE, never for the document.
# ─────────────────────────────────────────────────────────────────────────────

READY = {
    # The shell. Present on every cabinet AND on the launcher, so it is the
    # default: `Arcade.save` rather than bare `Arcade`, because the object is
    # created early and filled in afterwards.
    'arcade': '() => !!(window.Arcade && window.Arcade.save)',
    # The driving engine. Only the two driving cabinets have it.
    'road': '() => typeof window.__road === "object" && window.__road !== null',
}

DRIVING = ('interstate', 'motorsport')


def ready_for(url):
    """Which engine a URL's readiness is, so a call site needs no second argument."""
    return 'road' if any(name in url for name in DRIVING) else 'arcade'


def boot(page, url, ready=None, timeout=30_000, settle=0, required=True):
    """Navigate to a cabinet and wait for its ENGINE. Returns True if it came up.

    ▶ WHY THIS EXISTS, AND WHY IT IS NOT `wait_until="load"` (RLG-208). On 2026-09-09 and again
    on 2026-09-10 this machine stopped firing `load` for the two driving cabinets. A direct probe
    found `window.__road` present, a canvas on the page, zero page errors - and
    `document.readyState` stuck at `interactive`. The engine had booted and was answering, while
    every harness in the suite sat waiting for a document event that was never going to arrive and
    reported a timeout that reads exactly like a broken build. It failed identically on the last
    known-good commit, which is the test that proved it environmental.

    NO HARNESS HERE CARES WHETHER THE DOCUMENT FINISHED. Every one of them cares whether the
    engine is up, and that is what this waits for. On a healthy machine nothing behaves
    differently - the engine is up before `load` would have fired either way.

    ▶ A FIXED WAIT AND A DIRECT READ, NOT `wait_for_function`. Measured on the wedged machine: the
    polling form timed out after 20 seconds while a single `evaluate` after a plain wait answered
    immediately. The page's own animation loop starves the in-page poller. The loop below polls
    from Python, one round trip at a time, and is not starved by it.

    `ready` is a key of READY, or a raw JavaScript expression for a cabinet that needs something
    more specific. Omitted, the URL decides. `settle` is a pause after the engine answers, for a
    caller that needs a few frames drawn before it reads anything.

    ▶ IT RAISES BY DEFAULT, AND THAT IS THE POINT OF `required`. `goto` raised when the page did
    not arrive, so every call site it replaces was written expecting a loud stop. A helper that
    quietly returned False in its place would let a harness run its whole battery against a dead
    page and report the damage as a dozen unrelated failures. What it raises with is a READING of
    the page rather than a timeout, so the next person can tell a broken build from a wedged
    machine without writing a probe first. Pass `required=False` to be told rather than stopped.
    """
    expr = READY.get(ready or ready_for(url), ready)
    page.goto(url, wait_until='commit', timeout=timeout)
    if until(page, expr, timeout=timeout, required=False):
        if settle:
            page.wait_for_timeout(settle)
        return True
    if not required:
        return False
    raise RuntimeError('[harness] the engine never came up: %s\n%s' % (url, _diagnose(page)))


def until(page, expression, timeout=10_000, arg=None, required=True, poll=100):
    """Wait for a JavaScript expression to go truthy. Returns True if it did.

    ▶ THE REPLACEMENT FOR `page.wait_for_function`, AND THE REASON IS MEASURED (RLG-208). The
    Playwright form injects a poller into the page and drives it from the page's own animation
    frames. On the wedged machine of 2026-09-10 that poller timed out after 20 seconds while a
    single `evaluate` immediately afterwards answered at once - the game's own rAF loop starves
    it. This polls from PYTHON, one round trip at a time, so nothing in the page can starve it.

    It raises by default, the way `wait_for_function` did, and for the same reason `boot` does:
    the call sites it replaces were written expecting a loud stop. `required=False` returns a bool
    instead. `poll` is the gap between reads in milliseconds.
    """
    waited = 0
    while True:
        try:
            if page.evaluate(expression, arg) if arg is not None else page.evaluate(expression):
                return True
        except Exception as e:
            # ▶ A DEAD PAGE IS AN ANSWER, AND SWALLOWING IT COST TEN MINUTES.
            # The context going away MID-NAVIGATION is not a failure - the
            # document is being replaced under us and the next read will
            # succeed. A page that has CRASHED or been CLOSED will never answer,
            # and waiting the full timeout out turns a browser crash into a
            # hang: shift-stop-test sat for ten minutes on a tab that died
            # during boot, and reported a timeout rather than the crash.
            if page.is_closed() or 'TargetClosed' in type(e).__name__                or 'crash' in str(e).lower():
                raise
        if waited >= timeout:
            break
        page.wait_for_timeout(poll)
        waited += poll
    if not required:
        return False
    raise RuntimeError('[harness] never became true within %dms: %s\n%s'
                       % (timeout, expression, _diagnose(page)))


def reboot(page, ready=None, timeout=30_000, settle=0, required=True):
    """`page.reload()` that waits for the ENGINE rather than for the document. See `boot`."""
    page.reload(wait_until='commit', timeout=timeout)
    expr = READY.get(ready or ready_for(page.url), ready)
    if until(page, expr, timeout=timeout, required=False):
        if settle:
            page.wait_for_timeout(settle)
        return True
    if not required:
        return False
    raise RuntimeError('[harness] the engine never came back after a reload: %s\n%s'
                       % (page.url, _diagnose(page)))


def _diagnose(page):
    """What the page actually looked like when it would not boot.

    A TIMEOUT NAMES NOTHING. These four lines separate the cases that matter: a build that threw,
    a shell that never attached, an engine that never started, and a document that is running
    fine and simply will not finish - which is the wedge this helper exists for.
    """
    try:
        seen = page.evaluate("""() => ({
            state:  document.readyState,
            arcade: !!(window.Arcade && window.Arcade.save),
            road:   typeof window.__road,
            canvas: document.querySelectorAll('canvas').length })""")
    except Exception as e:
        return '          the page could not even be read: %s' % e
    return ('          document.readyState = %s\n'
            '          window.Arcade       = %s\n'
            '          window.__road       = %s\n'
            '          canvases on the page= %d\n'
            '          If the shell is attached and readyState is `interactive`, this is the\n'
            '          document-never-finishes wedge and the readiness expression is wrong,\n'
            '          not the build.' % (seen['state'], seen['arcade'], seen['road'],
                                          seen['canvas']))
