---
name: commit-messages
description: This repo's git commit conventions — atomic stage-per-commit changes, message style, and what belongs in plan.md vs. the commit body. Use when asked to commit changes in this repository.
---

# Commit conventions for this repo

- One logical change per commit — a new feature, a fix, a doc update.
  Don't bundle unrelated changes just because they happened in the same
  session.
- Every behavior change ships with its tests in the *same* commit, not a
  follow-up. Docs (README.md, plan.md) updates for a change can be their
  own small commit if the code commit is already large.
- Commit body explains *why*, not a restatement of the diff — the diff
  already shows what changed. Note anything learned live (a bug found
  while testing, a platform quirk) since that context is easy to lose.
- Never commit `dist/`, `logs/`, or `memory/` — all three are gitignored
  runtime/build output, not source.
- Run the full test suite (`pixi run test`) before committing a code
  change; don't commit on red.
- Never use `git commit --amend` or force-push unless explicitly asked —
  create a new commit instead, even to fix a mistake in the previous one.
