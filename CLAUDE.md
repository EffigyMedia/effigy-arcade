# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this is

**Effigy Arcade** — **four games on one floor**, each meant to be built out into a full
multi-scene game rather than filled in. Vanilla JavaScript, no framework, no dependency, no build
step, and no network call at launch.

**MOBILE ONLY, AND TOUCH IS THE INPUT.** Portrait, phone first, installed to the home screen as a
progressive web app. **Keyboard, mouse and gamepad are out of scope** — not deprecated, not a lower
priority, simply not part of what this product is. Every input question answers itself from that: a
control is designed for a thumb, and a feature that needs a keyboard is not built. Owner ruling,
2026-08-25, recorded in `docs/fragments/RLG-002.md`.

**No machine has a controls screen, and none should get one.** A controls page exists to tell a
player which keys do what; a thumb does not need to be told where it is, and a page listing gestures
only describes what the interface already shows one tap away. **If a gesture needs explaining, teach
it in play the first time it matters.** `tools/menu-test.py` asserts the absence.

The four machines:

| Machine | id | What it is |
|---|---|---|
| **Quietus** | `quietus` | A dead ship. Nothing aboard is alive; plenty of it still moves. |
| **Hardpoint** | `hardpoint` | A small-scope FPS SIMcade RPG. Fly it, leave the chair, board, fight. Pirate or bounty hunter, your choice. |
| **Redline Interstate** | `interstate` | The endless road. |
| **Redline Motorsport** | `motorsport` | The circuit. |

**REDLINE is a marque, not decoration.** Interstate and Motorsport are one engine - `road.js` - with
the same six cars in the same garage, separated by a `CFG` seam. Two disciplines, one parent.

**Quietus supersedes the owner's parked project of that name** (`Projects/Parked/Quietus`) when it
goes standalone. That project is the same fiction as a menu-only terminal game, it is **already
Godot 4.7 targeting iOS and Android**, and it holds the repository `quietus-dev`. See
`docs/fragments/RLG-005.md` before assuming anything about which repository the standalone takes.

**`docs/reference/PRIVATEER.md` is Hardpoint's design document.** It keeps its original filename
because it is a frozen record written before the rename; the in-code citations to it are correct.

**This is not a version of Tiny Arcade.** That project is nineteen small machines sorted onto three
shelves, and it is **parked, complete, and still playable** at
`github.com/EffigyMedia/tiny_arcade`. Nothing here changes it, and a fix made here does not travel
back to it. This project inverts its premise: few machines, each deep.

**Where this is going, and there are two routes.** Each game is intended to leave this arcade when
it is finished, either wrapped as a standalone binary or **converted to Godot**.
`./pack.sh --standalone <id>` performs the first half of the wrapper route — it emits ONE
self-contained HTML file with every script inlined — and the frozen `SHIPPING.md` in Tiny Arcade
assessed the wrappers themselves. **Keep `--standalone` working.**

**The second route changes what this codebase is for.** Under a Godot conversion, the HTML and
JavaScript here are the playable design document that the Godot version is built from, rather than
the thing that ships. **So do not invest in work whose only value is on the web** — a bundle-size
fight, or offline behavior beyond what the owner needs to test on a phone. Gameplay, tuning and the
rules of each machine survive either route; web plumbing does not.

This project runs a documentation-driven **development process**, read in place from the shared
process docs (never copied here, never edited from project work):

Process docs: `<env-root>/Process/`;
starter blanks: `<env-root>/Templates/_Project_Template/`

> **`<env-root>` is the directory that holds `.code-continuum-env-root`.** To find it, go up from
> here, parent by parent, until you find that file. Never write a drive-letter path in this file —
> see `Path_Policy.md`.

- `Development_Process.md` — the operating manual: the feature loop, releases, the trigger phrases
  below. **The source of *how*.**
- `Artifact_Formats.md` — formats for `changelog.md` and technical references.
- `Performance_Testing.md` / `Audit_and_Testing.md` — perf practice; the audit workflow.
- `Path_Policy.md` — how anything names a location. **This file carries no absolute path.**
- `Agent_Scope.md` — how far a session may reach. This is a **project** session.
- `Writing_Standard.md` — the standard itself, stated in full in the standing policy section
  below. **The inherited source uses British spelling; do not rewrite it, and do not copy it into
  new prose.** That sentence is this project's own, and the generated section does not carry it.
- **The work record is the fragment store** in `docs/fragments/`, written with
  `<env-root>/Commands/fragment.py` and never by hand. **This project keeps no `tracker.md`** — the
  view over the store is the dashboard, opened by `Dashboard.bat` / `dashboard.sh` at the root.
- `docs/reference/` — inherited reference, **frozen**. `DESIGN.md` (Tiny Arcade's full decision log,
  newest first, 277 KB — **search it, never read it end to end**), `DRIVING.md` (what is built in
  the two driving games and what is not), `REFACTOR.md` (the state of `road.js` and what is
  load-bearing but invisible), `PRIVATEER.md`. **Read them for reasoning; never add to them.**
  **They are not equally aged**, and that has already cost one wrong plan in the parent project:
  `DESIGN.md` kept being appended after the others were written, so **its top entries are the
  newest**. When they disagree, the top of `DESIGN.md` is newest — **and the code settles it.**
- **Shared Knowledge Base** — `<env-root>/Process/Knowledge_Base/`: consult it for browser, PWA and
  Playwright gotchas before stack-specific work, and **append** new lessons there.
- **Model routing** — `<env-root>/Process/Model_Routing.md`.
- **Routing posture** — `ROUTING_BIAS: 2` (quality). Each of these four is meant to become a
  product, and a defect in the 9,849-line driving engine ships to two of them at once. Drop to
  efficiency only for mechanical churn.

---

<!-- BEGIN standing-policy - generated, do not edit here -->

## Standing policy — set at the environment level

> **Keep this section verbatim. Do not summarize it and do not delete it.** These rules are set at
> the environment level and a project may not repeal them. `check-policy.py` verifies that the
> standard is named and in force in every project. This section is generated:
> `Commands/materialize-projects.py` writes it from the template, and an edit here is overwritten.

**Write all output in Simplified Technical English (ASD-STE100).**
`<env-root>/Process/Writing_Standard.md` is the one owning document. The rules are not repeated here.

The standard covers your chat output, every document, every commit message, and every source-code
comment. **It has one exemption: authored product prose.** That is the text which ships as the
product — game dialogue, item and lore text, book chapters, marketing copy, user-facing narrative.
Write that prose in the voice the project needs. Everything you write *about* the work stays in the
standard.

**A record is exempt from brevity. It is not exempt from the standard.** Keep the full meaning of a
record. Write it in short, active, plain sentences. Cut the words that carry no meaning.

**Chat output is concise. It is not terse.** Brief, and complete. Short full sentences, the
answer first, no preamble and no recap of what was just shown. Tables over prose where a table fits.
Do not drop articles, do not write in fragments, and do not trade grammar for length: the goal is
fewer tokens with the meaning kept whole.

**This has three registers and they are not the same.** Chat is concise. A durable record - a commit
message, a fragment, a design document - is exempt from brevity and keeps deliberate prose, because a
reply is read once and a record is read by every later session. Authored product prose is exempt from
the standard altogether. Collapsing the three is the mistake this rule exists to stop.

**Say what a thing is FOR before you name it.** Lead with the plain-language purpose, then the
detail: "the tool that copies the shared rules into every project" before its filename. One clause
is enough, and only on first mention. Identifiers stay bare - a ticket, a commit or a document ID
needs no title unless it is ambiguous, and the owner wants them terse. The rule is that the sentence
AROUND the reference carries meaning, not that references are removed. The test: could the reader
repeat what was done and why it mattered, from your reply alone? If not, the purpose sentence is
missing. Owner-decided 2026-08-28, after several sessions of reports written entirely in this
codebase's own shorthand.

**Re-entry is the thread.** `python <env-root>/Commands/thread.py show` — read it first in every
session. **Checkpointing is the unit boundary**, which fires the context clear on its own. Do not
write handoff documents and do not create a `docs/milestones/` folder.

**Sessions reach each other through inboxes.** Every line has one: `<env-root>/Environment/docs/inbox/`
for the environment and `docs/inbox/` in each project. To tell another line something, run
`python <env-root>/Commands/inbox.py send --to <a path inside that line> --from <this project> --file
<message.md>`, and do not leave a file at its root. When your arrival banner names a message in this
project's inbox, act on it, then close it with `inbox.py close`, which records it word for word in
the inbox's ledger and deletes it. A message asks; it never authorizes.

<!-- END standing-policy -->

## Trigger phrases

Summaries — the canonical procedures live in `<env-root>/Process/Development_Process.md`.

| Phrase | Meaning |
|---|---|
| *(normal work)* | Feature loop: implement → `test` → fragment → changelog → **patch** bump → commit. One feature = one commit = one patch = one changelog entry = one fragment to built. |
| **Track this: …** | Write a new `RLG-NNN` fragment with status `requested`; do not start it. |
| *(after a clear)* | Read the thread: `python <env-root>/Commands/thread.py show --store docs/fragments`. It carries the focus, the next action **and its origin**, the constraints in force, and what is unfinished. That is the whole of re-entry. Verify the working tree is clean, then act by the origin — `stated`, do it; `asked`, do it; `inferred`, put it to the owner first; `absent`, say so and stop. |
| **Perform audit** | Run `Audit_and_Testing.md`; produce a findings report; change no code. |

**Milestones and handoffs do not exist.** The environment replaced both with the **thread
fragment**, `docs/fragments/THR-001.md`, which is **maintained continuously and never written at
the threshold** — that is what makes a context clear cheap. Write it with `Commands/thread.py`,
never by hand. This project keeps no `docs/milestones/` folder.

## Commands

There is **no toolchain to resolve and nothing to install to run the product**. It is a static site.
Python 3 with Playwright installed runs the two test harnesses; a browser runs everything else.

- `run` — serve the folder and open it: `python -m http.server 8000`, then `http://localhost:8000`.
  `index.html` also opens straight from the file system. **Neither is an on-target check** — a
  desktop browser does not verify phone layout, webview audio, or feel.
- `setup` — build the test environment. Playwright cannot be installed into the environment's
  uv-managed Python (it refuses, by PEP 668), so the harnesses run from a project-local venv:
  `<env-root>/Runtime/bin/uv venv .venv` then
  `<env-root>/Runtime/bin/uv pip install --python .venv playwright`. `.venv/` is git-ignored.
- `test` — four harnesses. `smoke-test.py` is the gate; the other three cover what it cannot see:
  `menu-test.py` (every title has the same set and OPTIONS returns to it), `isolation-test.py`
  (each machine owns its own settings), and `audio-test.py` (Hardpoint's held sound layers still
  follow the ship — **a sound test cannot listen, but it can read the Web Audio graph**).
  `.venv/Scripts/python tools/smoke-test.py` boots all four machines and the launcher and
  asserts a clean console and real paint on the canvas. `.venv/Scripts/python tools/drive-test.py`
  drives Highway and Raceway for 30 seconds with an autopilot and asserts speed, laps, fuel, tires,
  damage, the HUD, and page errors. **Run both before shipping anything.**
  The harnesses use the Chrome already on the machine when Playwright has no browser of its own,
  **and they print which engine they used** — a harness that silently changes engine produces
  numbers that cannot be compared between runs.
- `build` — `./pack.sh` builds and validates `effigy-arcade.zip` from an explicit whitelist;
  `./pack.sh --check` validates and builds nothing; `--standalone <id>` emits one self-contained
  HTML file. A build **regenerates `assets.js` and `sw.js ALL_FILES`** from what is shipping, so run
  it after any file is added, moved, or removed. **It needs `node` on PATH**, which the
  environment's shim provides. It uses `zip` when present and falls back to PowerShell's
  `Compress-Archive`, so it completes on a stock Windows box.
- `deploy` — GitHub Pages serves `main` directly. A push deploys. **A TESTABLE BUILD IS A RELEASE
  HERE, so push when there is something for the owner to test on the device** — not per commit, and
  not once per session. Rendering, audio mix, on-device layout and feel are only judged there, so
  unpushed work is untested work; 46 commits once sat local while the device tested a build fifteen
  versions old. There are no Actions workflows and Pages is a `legacy` build from `main`, so a push
  costs one Pages build against a documented soft limit of ten an hour — keep it under about six.
  **Never force-push and never rewrite pushed history.** Say the build number when handing over, and
  it must match the BUILD row in SETTINGS. See `docs/fragments/RLG-066.md` and `RLG-063.md`. `sync.sh` is inherited and
  **obsolete in its current form**: it clones the remote to a temporary folder and copies files over
  the top, from when the working folder was not a repository. This folder is the repository.

## Architecture (the load-bearing boundaries)

- **`index.html`** — the launcher: **one floor**, the rack, cabinet cards, the attract `draw` map,
  settings; **must not** hold any list of machines of its own, or any knowledge of one machine's
  rules.
- **`games.js`** — the catalog, one entry per machine; **must not** hold any code.
- **`arcade.js`** — the shell: title bar, pause, `gesture`, `pad`, `menu`, `save`, `crt`, `cinema`,
  `options`, `home`, `wordmark`, and the service worker registration; **must not** contain anything
  specific to one machine.
- **`audio.js`** — the synthesizer and the three buses (`sfx`, `music`, `ui`) with the mute state;
  **must not** know what a game is.
- **`road.js`** — the shared driving engine, 9,849 lines, serving Highway and Raceway; **must not**
  know which of its two games is running, except through a `CFG` seam.
- **`games/<cat>/<id>.html`** — one machine, whole. The `cat` folders `em` and `sw` are inherited
  from Tiny Arcade's shelves and now mean nothing: the floor shows every cabinet regardless. They
  are kept only because renaming paths churns both cache lists and every save key. A machine **must not** reach into another machine, or
  define `--stage-h` or `--safe-top`.
- **`sw.js`** / **`assets.js`** — the cache policy, and the generated cache list. `assets.js` is
  generated; **never edit it by hand.**

**EVERY MACHINE OWNS EVERYTHING IT STORES.** These are standalone games sharing a launcher for
convenience, so nothing persisted may be shared between them — anything shared is a thing that
breaks, or silently goes missing, on the day one is split out. `Arcade.scope` is the storage scope,
read from each cabinet's `<meta name="arcade-id">` (falling back to the file name, then `launcher`).
Every persisted key is `effigyarcade.<scope>.<what>.v1`, plus the save slots at
`effigyarcade.save.v1.<id>`:

| What | Key |
|---|---|
| the save | `effigyarcade.save.v1.<id>` and any `-suffix` |
| the shell's options | `effigyarcade.<id>.opts.v1` |
| audio settings | `effigyarcade.<id>.audio.v1` |
| intros already seen | `effigyarcade.<id>.cinema.v1` |
| anything the machine writes itself | `effigyarcade.<id>.<anything>` |

**A store outside those shapes is invisible to the eraser**, and `Arcade.save.clear` will report
success while leaving it behind. **Add a store, add it to the `saves()` check in `smoke-test.py`** —
that check exists so this rule cannot rot silently. `save`, `cinema` and `launcher` are reserved and
cannot be machine ids.

**The launcher seeds a cabinet once.** A machine with no audio settings of its own copies the
launcher's on first visit **and writes them down**, so it owns them from then on. Independent,
without being deaf to the volume you just set.

**Single sources of truth.** The catalog is `games.js`. The shell owns the room (`--stage-h`,
`--safe-top`). The engine owns driving — anything in `road.js` is in both driving games
automatically. **`Arcade.version` in `arcade.js` is the version**, and the git tag mirrors it.

**One floor, and the shelf mechanism is still there.** `SHELVES` holds a single entry whose id is
`all`, and `all` matches every cabinet. The launcher opens straight onto the rack; nothing lands on
a picker. A fifth machine, or a real second shelf, is one entry away.

## Conventions that bite if ignored

- **A static check cannot tell you the game works.** The packer has passed while it shipped a syntax
  error, a missing file, and two machines that booted to a black screen. **A green build is not
  evidence.** Run the harnesses, and check the artifact rather than the source.
- **When a check fails identically everywhere, suspect the check.** A scan once flagged every
  object-method shorthand; a selector once reported the pause button missing from every machine.
  **Test for the effect, not for your own implementation of it.**
- **Do not believe a number the driver can influence.** A harness run once reported that Raceway
  tires died in 20 seconds. The autopilot was sawing the wheel, and lateral load is what wears
  tires. Measure with a steady driver.
- **A machine must never define `--stage-h` or `--safe-top` in its own `:root`.** The shell appends
  its stylesheet during parse, so a later `:root` wins on source order and silently discards the
  shell's calculation. Use the fallback form at the point of use.
- **The launcher keeps its styles in one `<style>` block, and a stray `}` closes it early** and
  silently kills every rule below it — no error, no warning. If layout goes strange after an edit,
  check the brace balance before anything else.
- **Reskin a machine and update its attract card in the same unit of work.**
- **An `attract` name with no entry in the `draw` map renders a black card, with no error.**
- **Never splice a function by a search for `var draw`.** A cut to "the next `var draw =`" once
  matched the last one in the file and deleted eight attract functions at once. Splice on the
  function's own closing brace.
- **A variable font `@font-face` is silently refused when the declared weight range excludes what is
  asked for**, and the declared range must match the file's real axes. **Do not measure text width
  to test this** — `document.fonts` status or a screenshot is the ground truth.
- **The seam contract fills in two stages.** Anything a seam might touch is attached at the top of
  `ROAD()`, because `onReset` fires during setup, before the function returns. This has bitten three
  times.
- **Do not collapse the car painters, and do not delete `paintProfile` or `paintQuarter`.** The
  duplication is the record of tuning against screenshots; the two unused painters are groundwork
  for a kart racer.
- **The corner cap in the driving engine is a renderer limit, not a taste one.** Past about 90
  degrees the road leaves the frame.
- **Do not build for a keyboard, a mouse or a gamepad.** The shell still carries `Arcade.menu`, the
  `A.pad` layer and per-cabinet key handlers, inherited from Tiny Arcade and left in place because
  they work and cost nothing. **They are not load-bearing. Do not extend them to a new machine, and
  do not spend effort maintaining them.** If they are ever removed, note that `tools/drive-test.py`
  steers with a keyboard and is the only automated proof the driving engine still drives — **teach
  it to drive by touch first, then remove.** In that order.
- **Changes the tooling cannot observe need the owner's verdict on a real device.** Rendering,
  audio mix, on-device layout, and feel are not verified by a green harness run. Say so plainly.
- **Every tunable lives in configuration with a committed default** — never an edited-in-place code
  constant.
- **Never edit this product through the GitHub web UI.** An upload replaces a whole file, so there
  is no merge and no conflict to warn anyone. Six shipped fixes were silently reverted in the parent
  project that way, and they survived a green build. If it ever happens again, **read the diff
  against the last known-good commit before doing anything else.**
- **Commits are authored as the project owner** — no AI identity, no co-author trailer. One unit of
  work is one commit. The remote is `origin`, `github.com/EffigyMedia/effigy-arcade`, **public**, and
  it is also the deployed GitHub Pages site.
- **THE REPOSITORY NAME IS NOT THE PROJECT NAME, and the two follow different rules.** The project
  folder is `Effigy_Arcade` in `Pascal_Snake_Case` with underscores, which `Project_Identity.md` §5
  sets and which is unchanged. The REMOTE is lowercase with **hyphens**, and a development
  repository carries a `-dev` suffix while a production one drops it. This repository is public and
  Pages serves `main`, so it is the production repository and correctly has no suffix. It was
  `effigy_arcade` until 2026-09-05 and the underscore was simply wrong. Renamed on the owner's
  standard; see `docs/fragments/RLG-155.md`.
- **Never commit** (see `.gitignore`): the packaged zip, anything matching the scratch pattern `_*`
  (four instrumented debug builds once reached a public release that way), the generated dashboard
  and fragment index, and **any licensed or copyrighted reference material** — no sprite rips, no
  captured audio, and no artwork from anything these descend from. The product uses no keys, tokens,
  or credentials of any kind; if that ever changes, they go nowhere near this repository.
