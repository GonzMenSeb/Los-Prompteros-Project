# Working with a second agent on this repo

Two Claude Code sessions have been working this codebase in parallel for a day. It has
gone well — the second session caught **six** defects the first one shipped, none of
which its own tests would have found. This file is what that cost us to learn, written
so the next pair does not pay it again.

It is not a process document. It is a list of the specific things that went wrong.

---

## What the split should be

**One session writes, the other reviews.** Not "both write different features" — that
is where the collisions happened. The review session's job is to be adversarial about
work it did not write, because that is the only thing that reliably caught anything.

The reviewer's edge is not intelligence, it is **not sharing the author's assumptions**.
Every one of the six catches below came from checking a claim against reality rather
than against the author's mental model.

## The six things a second session caught

Read these before reviewing anything here. They are the shapes to look for.

1. **A lookup table keyed on the wrong vocabulary.** `_STAGE_STATUS` was keyed on the
   *fixture's* event names. Six of nine keys had no live emitter, so the loading caption
   still froze through retrieval and sizing — the longest part of the turn, and the whole
   reason the table exists. It looked perfect in fixture mode.
   **Check:** for any name-keyed map, grep that every key is actually emitted by live
   code. There is now a test that does this (`test_it_keys_on_events_that_are_actually_emitted`).

2. **A blocklist that cannot be completed.** A unit blocklist was added so the budget
   parser would not read "around 3800 m" as $3800. "meters", "litres" and "litre pack"
   all got through it. The structural fix was to run that pattern over `answers` only,
   never over the trip description.
   **Check:** if a fix is a list of things to exclude, ask what the list is missing.

3. **A regex keyed to one apostrophe.** `\bmen's\b` with U+0027, when Decathlon sends
   U+2019. The gendered-mix guardrail was dead against every real product title. The
   author had tested it against strings **they typed by hand**.
   **Check:** every string matcher must be exercised against `fixtures/`, never against
   an example in the test file. `AGENTS.md` says this outright; it still happened.

4. **A guardrail emitted after the last drain.** `_refresh_open_asks` fired after the
   final `_drain(sink)` of the turn, so in fixture mode its trace row never reached the
   panel. A guardrail nobody can see is not one.
   **Check:** anything that `emit()`s must be followed by a drain on every path.

5. **A computed value assigned to prose but not to the result.** The injection branch
   built its open questions, used them in the message, and left
   `result.open_questions` at its default — so the confirm bar lost every ask on a turn
   that HAS a kit.
   **Check:** when a value is computed once and used twice, grep both uses.

6. **A feature wired only into the live path.** This happened *three times*: stage
   captions, open questions, and item removal. Fixture mode never reaches `_continue`,
   and fixture mode is what runs on stage when Gemini quota is gone.
   **Check:** for any new behaviour, ask "does this exist in `_fixture_turn` too?"

## The pattern behind all six

Every one is the same mistake: **verifying against your own model of the system instead
of against the system.** The tests passed in all six cases. What found them was running
the real thing, reading the real fixture, or grepping the real emitters.

So the reviewing session's most valuable single habit is: *for each claim in the PR
description, what would prove it false?* Then check that.

---

## Practical rules that stopped collisions

**Never `git add -A`.** Both sessions share one working tree. `git add -A` swept up
`docs/MARKET-RESEARCH.md` and `docs/COTIZACION-COROS-COLOMBIA.md` — another author's
untracked drafts — twice. Stage explicit paths: `git add concierge tests docs/DECISIONS.md`.

**Check the base before opening a PR.** The stack moved under us repeatedly: PRs merged
into their *base branches*, not into `main`, so `main` looked stale while everything was
"MERGED". Before opening anything, run:

```
git fetch origin
git log --oneline origin/main -3
gh pr view <n> --json state,baseRefName
```

A PR that says MERGED may have merged into another feature branch.

**Expect the base to move mid-work.** Twice a branch went `MERGEABLE` → `CONFLICTING`
while work was in flight, because the reviewing session pushed fixes to its base. Merge
the base back in rather than rebasing — the review commits carry their own reasoning in
the message and rebasing buries it.

**`docs/DECISIONS.md` is append-only and will always conflict.** Both sides append. The
resolution is always: keep both entries, the one that landed first goes first. Never
take one side.

**One dev server.** Reflex holds ports 3000 and 8000 and hot-reloads on every write, so
the second session's edits restart the first session's server mid-test. If the server
must stay up for someone to look at, say so and do not write to `concierge/` until they
are done. A killed Reflex parent also leaves an orphaned `multiprocessing` worker holding
port 8000 that `tasklist` will not show — find it with
`Get-CimInstance Win32_Process -Filter "Name='python.exe'"` and look for `spawn_main`.

**Never put a Chrome profile under the repo.** Three screenshot runs failed before this
was found: the profile writes triggered Reflex's file watcher, which restarted the
backend mid-run. Profiles go in the scratchpad; only the PNGs go in the repo.

---

## What is worth the second session's time here

In rough order of what has actually paid off:

1. **Reviewing the other session's PRs** — six for six.
2. **Running the app and reading a real run bundle.** Every serious defect in this
   project was found in a bundle, not in a test: the invented Edmonton race, the kit
   rebuilt on a size answer, the XL→S substitution, the fabricated "not stocked".
3. **Checking the live path separately from fixture mode.** They diverge, and the
   fixture is what a judge sees when quota runs out.
4. Writing new features. Least valuable of the four right now — there is more value in
   verifying what exists than in adding to it.

## What neither session can do

A **live Gemini run** needs quota. Several fixes are prompt-level — not inventing a
location, keeping replies short, not greeting twice — and a prompt is a suggestion.
Their deterministic halves are tested; the prompt halves are **not verified against the
model**, and cannot be until someone spends quota on a two-turn run.

That is the single biggest hole in this repo's verification story, and no amount of
parallel agents closes it.
