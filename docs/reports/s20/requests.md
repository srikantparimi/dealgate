# S20 · cross-worker requests (Lead routes)

Workers append a block here whenever they need a change on a file they
don't own (per `contracts.md` §6) — the Lead applies within the hour and
tags the responsible worker + a link to the requesting commit.

Format:
```
## <Wn>-<UTC>-<seq> · <one-line title>
Reason: <why>
File(s): <paths>
Change: <exact behavior/API>
Rollback: <how to undo>
Test: <acceptance>
Requested-in: <sha of requesting commit or `plan-only`>
```

---

(seeded empty; workers append during their runs)
