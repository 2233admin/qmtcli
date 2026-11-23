# Report template

Save as `docs/prior-art/<topic>.md`. Keep every section, and write "none" where one is empty:
an empty section tells the next reader the question was asked.

```markdown
# Prior art: <topic>

- Date: YYYY-MM-DD
- Mode: quick | deep
- Searches used: N
- Saturated: yes | no

## Need
One sentence: who it is for, what goes in, what comes out.
Constraints: language, platform, licence, anything else that rules candidates out.

## Verdict
| Part | Verdict | Project | Why |
|---|---|---|---|
| <part 1> | Adopt / Extend / Compose / Build / Keep | <project or —> | one line |

For each Build: "Existing <X> cannot do ___ because ___." Then its rough size and what will
need maintaining.

For each Adopt or Extend: source, version, date taken, and how it gets updated.

## Read
Projects opened and read. For each, say what was read (README, which source file, issues).

| Project | Link | Covers | Lacks | Licence | Last commit | Cost to adopt | Access it needs |
|---|---|---|---|---|---|---|---|

## Seen, not read
Shortlisted or mentioned by others, but not opened. Nothing here is a claim about what the
project does.

| Project | Link | Where it came from |
|---|---|---|

## Ruled out
| Project | Reason |
|---|---|

## How it was searched
- Names tried for each part:
- Sources searched:
- Sources that failed or were unavailable:
- Seeds snowballed from:

## Not covered
Directions not explored, and why the search stopped.
```

## Notes

- Dates matter. A report is a snapshot; star counts and "last commit" go stale in weeks.
- Separate "read" from "seen". The most common error in a survey is describing a project
  from its one-line listing.
- If the search was cut short, "Saturated: no" plus an honest "Not covered" is the correct
  report. Do not round it up.
