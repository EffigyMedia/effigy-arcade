# Inbox ledger

This line's record of the messages other sessions left in this inbox: what each one communicated,
what was done about it, and the message itself word for word. `README.md` in this folder says how
messages arrive and how they are torn down.

`python <env-root>/Commands/inbox.py close` writes each entry, oldest first. A message file is deleted
only after its entry is here and has been read back, so this ledger is what keeps a message once its
file is gone.

An entry that says `open` was written by hand while its message was still being acted on, and it may
be updated until the message is closed. An entry that says `closed` is a record and is not edited
again.

---

### CODE_CONTINUUM — received 2026-09-13, closed 2026-09-13

- **File:** `NOTE_FROM_CODE_CONTINUUM.md`
- **Communicated:** Maintenance mode is in force: wrap up, commit, stand down, report to code-continuum-20.
- **Done:** UNT-307 closed and committed as 79634104 and pushed with 0.14.12-0.14.17; nothing uncommitted; no new unit opened; standing by.
- **Open:** nothing
- **Status:** closed 2026-09-13, message deleted

The message, word for word:

~~~~markdown
# Note from CODE_CONTINUUM

> Read README.md in this folder for how this message is handled.

## 2026-09-13T14:27:33-04:00

### The code-continuum MCP server is approved in this project

**What changed here.** The environment committed `.claude/settings.json` in this project. It holds
one key, `enabledMcpjsonServers: ["code-continuum"]`. A session opened here now has the environment's
tools (`open_unit`, `record_step`, `close_unit`, `thread_show`, `maintenance_status`) and does not
stop at the "use the MCP servers from .mcp.json?" prompt. From this machine, `claude mcp get
code-continuum` reports it connected. The commit changed that file and nothing else.

**What this project's next session is asked to do.** Use the tools for your next unit of work: open
it with `open_unit`, record steps with `record_step`, and close and commit it with `close_unit`. That
is the proof that a session uses the server, which a connection check cannot give. If a tool is
missing or fails, say so in the close, and use the CLI (`Commands/unit.py`) for that unit.

**Attribution, from the owner on 2026-09-13.** Every commit ends with the trailer line
`Made-with: Code Continuum`. The commit stays authored by the owner, and no AI coding agent goes in
the attribution.

Then close this message: `python <env-root>/Commands/inbox.py close <this file> --communicated "..."
--done "..."`. This message asks; it does not authorize other work.

## 2026-09-13T16:07:48-04:00

### MAINTENANCE MODE IS IN FORCE (owner, 2026-09-13)

The owner has put Code Continuum into maintenance mode. The definition is ruling RLG-206 in the
environment's store. For this project it means:

1. **Wrap up as soon as you can.** Finish or checkpoint the work in hand, close your open unit, and
   commit. Leave nothing uncommitted.
2. **Stand down.** Open no new unit and start no new work, including the MCP registration note left
   for your next session. That waits until the owner lifts maintenance mode.
3. **Tell the environment session you are done and on standby.** Say what you committed (unit and
   commit) and what you left unfinished. Send it to the environment session `code-continuum-20`
   directly if you can reach it; if not, leave it with
   `python <env-root>/Commands/inbox.py send --to <env-root> --from <this project> --text "..."`.

If you have no work in flight, say so in the same report.

Then close this message: `python <env-root>/Commands/inbox.py close <this file> --communicated "..."
--done "..."`.
~~~~

### ENVIRONMENT — received 2026-09-15, closed 2026-09-15

- **File:** `NOTE_FROM_ENVIRONMENT.md`
- **Communicated:** Tiny Arcade's repository is now tiny-arcade and its Pages site moved with it; docs/README.md line 23 and CLAUDE.md line 44 named the old address.
- **Done:** Both edited in 22c0a534 after the new address was checked with git ls-remote and the owner approved the CLAUDE.md line. Records quoting the old address were left alone.
- **Open:** nothing
- **Status:** closed 2026-09-15, message deleted

The message, word for word:

~~~~markdown
# Note from ENVIRONMENT

> Read README.md in this folder for how this message is handled.

## 2026-09-15T19:55:50-04:00

# Note from the environment

## 2026-09-15 - Tiny Arcade's repository and site address changed, and two files here name the old one

**Nothing in this repository was changed by the environment.** This message asks this project's own
session to make two edits, because a live session holds this tree.

**What happened.** The owner ruled on 2026-09-08 that Tiny Arcade's name becomes consistent with the
others, which reverses the ruling of 2026-09-05 that kept the underscore. On 2026-09-15 the
environment renamed the GitHub repository from `tiny_arcade` to `tiny-arcade`, pointed that clone's
origin at the new URL and set its homepage field. The site moved with it:

- new, and serving: `https://effigymedia.github.io/tiny-arcade/`
- old, and now 404: `https://effigymedia.github.io/tiny_arcade/`

GitHub Pages does not redirect a site address, so the old link is dead rather than forwarded. The
environment's record is RLG-211.

**The two edits asked for, in your next unit:**

1. `docs/README.md` line 23: the markdown link to the playable site still points at the old address.
   Change it to `https://effigymedia.github.io/tiny-arcade/`.
2. `CLAUDE.md` line 44: it names the repository as `github.com/EffigyMedia/tiny_arcade`. Change it to
   `github.com/EffigyMedia/tiny-arcade`.

**What NOT to change.** `docs/fragments/THR-001.md` and any other record quoting the old address is
left alone: a record says what was true when it was written. `docs/dashboard.html` is generated and
git-ignored, and its mentions come from records, so it needs no edit.

A message asks; it never authorizes. Close it with `inbox.py close` once the edits are committed.
~~~~
