# EFFIGY ARCADE

Four games on one floor. No server, no build step, and no network call at launch.

## Play it

**https://effigymedia.github.io/effigy-arcade/**

On a phone, open it and use **Share → Add to Home Screen**. It installs as EFFIGY ARCADE, launches
full screen, and works with no signal after the first visit.

| Machine | What it is |
|---|---|
| **Quietus** | A dead ship. Nothing aboard is alive; plenty of it still moves. |
| **Hardpoint** | A small-scope FPS SIMcade RPG. Fly it, leave the chair, board, fight. Pirate or bounty hunter. |
| **Redline Interstate** | The endless road. |
| **Redline Motorsport** | The circuit. |

Each one is being built out into a full multi-scene game rather than filled in.

## Not to be confused with

**[Tiny Arcade](https://effigymedia.github.io/tiny-arcade/)** — nineteen small machines on three
shelves, and the project this one grew out of. It is complete, parked, and still playable. Four of
its cabinets came here to be taken further; nothing done here changes it.

## The layout

    index.html            the launcher - one floor, four cabinets
    games/<shelf>/*.html  one self-contained game per file
    games.js              the catalog - one entry per machine
    arcade.js             the shell: title bar, pause, gamepad, menus, saves, scanlines
    audio.js              the synthesizer - every sound is generated at runtime
    road.js               the shared driving engine, behind Highway and Raceway
    sw.js / assets.js     offline play, and the generated cache list
    fonts/                self-hosted and subset, licenses included

## Running it

Open `index.html`. That is the whole procedure.

## Building it

    ./pack.sh                    build and validate effigy-arcade.zip
    ./pack.sh --check            validate only, build nothing
    ./pack.sh --standalone <id>  one self-contained HTML file for one machine

The build works from an explicit whitelist rather than from whatever is in the folder, and it
refuses to build when a check fails. It needs `node`.

**The build cannot tell you the game works.** That is what the two harnesses are for:

    python tools/smoke-test.py    every machine boots, no errors, real paint on the canvas
    python tools/drive-test.py    both driving games play - speed, laps, fuel, tires, damage

## The documents

The live documents are in `docs/`, and `docs/fragments/` is the work record. `docs/reference/` holds
inherited documents that are frozen and kept for the reasoning in them.

Development instructions for an agent working in this repository are in `CLAUDE.md` at the root.

---

© 2026 Effigy Media. All rights reserved.
