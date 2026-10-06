# Domain docs

How agents use this repo's domain documentation.

## Before exploring, read these

- `CONTEXT.md` at the repo root: the glossary.
- There is no ADR directory yet; decisions live in commit history, `docs/xtdata-alignment.md`, and `docs/xttrader-alignment.md`.

If either is missing, proceed without flagging it. `/domain-modeling` creates them when a term or decision is actually resolved.

## Use the glossary's vocabulary

Name domain concepts with the `CONTEXT.md` term in issue titles, proposals, test names, and code. A term the glossary lists under `_Avoid_` is a synonym to replace. A concept with no entry is either invented language (reconsider it) or a real gap (note it for `/domain-modeling`).

## Flag decision conflicts

When your output contradicts a decision record, say so explicitly instead of overriding it:

> _Contradicts the `docs/xttrader-alignment.md` mapping for guarded order placement, but worth reopening because…_
