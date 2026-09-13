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
