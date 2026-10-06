# Triage labels

Every open issue carries exactly one category label and exactly one state label.
The state labels use the `triage` skill's canonical role names unchanged.

## Category

| Label | Use |
|---|---|
| `bug` | Existing behaviour is broken |
| `enhancement` | New capability or improvement |
| `documentation` | Documentation only |
| `chore` | Dependencies, build, CI, release, cleanup |

`documentation` and `chore` count as the `enhancement` category for the `triage` skill.

## State

| Triage role | Label | Meaning |
|---|---|---|
| `needs-triage` | `needs-triage` | A maintainer must evaluate it |
| `needs-info` | `needs-info` | Waiting on the reporter for details |
| `ready-for-agent` | `ready-for-agent` | Acceptance criteria complete; an agent can take it |
| `ready-for-human` | `ready-for-human` | Needs a human decision, credentials, money, or a live host |
| `wontfix` | `wontfix` | Rejected; applied when closing |

## Modifiers and resolutions

| Label | Use |
|---|---|
| `blocked` | Waiting on something external; name the blocker in a comment and keep the state label |
| `epic` | Parent issue; the work happens in its sub-issues |
| `duplicate` | Closed in favour of another issue (Gitea; GitHub uses the duplicate close reason) |

## Workflow labels in this repo

| Label | Owner |
|---|---|
| `dependencies`, `python:uv` | Dependabot pull requests |
