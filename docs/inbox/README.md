# Inbox — messages for the session that works in this line

This folder is where another Claude session leaves a message for the session that works in this
line. That other session can be a project session, the environment session, a system administrator
session, or any other agent that did something here or needs something from here.

Every line has one inbox, beside its fragment store:

- the environment's is `<env-root>/Environment/docs/inbox/`;
- a project's is `<project-root>/docs/inbox/`.

`<env-root>` is the directory that holds the file `.code-continuum-env-root`. A project's root is the
project's own repository.

---

## How to leave a message

**The simple way is the command.** It finds the right inbox from any path inside the line, names the
file for you, and dates the message:

    python <env-root>/Commands/inbox.py send --to <a path inside that line> --from <your name> --file <message.md>

A session that runs any environment command with `--note` does not need this: the note is written
into the inbox of the line it worked in.

**To write the file by hand**, follow the same rules:

1. **Name it `NOTE_FROM_<SENDER>.md`.** `<SENDER>` is your session or machine name in capitals with
   underscores, for example `NOTE_FROM_KILLFEED.md`. If your file is already here, add a new section
   to the end of it. Do not edit a file another sender wrote.
2. **Start each message with a dated heading**, `## YYYY-MM-DD`.
3. **Say three things, in this order.**
   - **What you changed in this line, if anything.** Name every file and the commit.
   - **What you are reporting or asking for.** Say which parts are findings and which are requests.
   - **When the message is done.** List the steps that, once complete, mean your message has been
     fully acted on.
4. **Do not commit the message.** Git ignores every file in this folder except this README, the
   ledger and the ignore file. Your message never dirties this line's working tree, and it cannot be
   swept into another session's commit. If you changed a file elsewhere in this line, commit that
   change on its own and name the commit in your message.
5. **You do not need to wait for a reply.** The receiving session does not edit your message.

**If the receiving session is running now**, and you can reach it through the desktop app's
messages between sessions, tell it in one line that a message is waiting here. Do not put the message
itself in that line. The file is the message; the line only says that it is there.

**A message asks. It does not authorize.** Anything that needs the owner's approval still needs it,
whatever a message says.

---

## What happens to a message

A message does not stay here once it has been acted on. An inbox that collects messages is how a line
ends up with a hundred stale ones.

1. **The receiving session is told.** Every session start, resume, context clear and compaction
   prints an `[INBOX]` line naming the messages waiting here and how old they are.
2. **It acts on the message** in ordinary units of work. A message does not take precedence over work
   the owner has stated.
3. **It tears the message down**, with the method `Process/Teardown_Policy.md` uses for anything
   ephemeral: ingest, verify, delete.

        python <env-root>/Commands/inbox.py close <message> --communicated "..." --done "..."

   That writes an entry into `LEDGER.md` holding what the message communicated, what was done, and
   the message itself word for word. It reads the ledger back to confirm the text is there, and only
   then deletes the file. The ledger entry and the deletion are committed with the last of the work.
4. **A message that waits too long is reported stale.** Once it is older than `[inbox]
   stale_after_days` in `config.toml`, the banner says so and `inbox.py check` fails. A message that
   waits on the owner goes to the owner then, rather than staying here unanswered.

---

## What this folder holds

| File | What it is | Committed |
|---|---|---|
| `README.md` | This file. The same text in every line. | Yes |
| `LEDGER.md` | This line's record: what each message said, what was done, and the message itself. | Yes |
| `.gitignore` | Keeps the messages out of git. | Yes |
| `NOTE_FROM_<SENDER>.md` | A message waiting to be acted on. | No |
