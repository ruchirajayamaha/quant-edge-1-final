# Role A/B/C/D handoff

Use one file per role in the IMPLEMENTATION repository: `handoff/A.md`, etc. Update it at checkpoints, especially before changing session/account. Do not copy secrets or the whole chat.

- Role and branch:
- Baseline commit / latest own commit:
- Contract/schema version:
- Completed milestone:
- Owned files changed:
- Next bounded task:
- Dataset ID / actual data bounds / manifest location:
- Config hash / seed / result bundle IDs:
- Public API signatures provided:
- Inputs still required, and their owners:
- Shared changes requested from D:
- Tests/checks actually run (command and result):
- Failures, known limitations and unverified claims:
- Methodology/limitations/AI-log section paths:
- Human validation: PENDING / actual completed checks with reviewer and date:

## Resume prompt

```text
Continue Role [A/B/C/D] on this existing repository.
Read COMMON_CONTEXT.md, CONTRACTS.md, my role prompt and handoff/[ROLE].md.
Inspect the existing diff and owned files. Preserve completed work.
Implement only the next bounded milestone recorded in that handoff.
Do not replan the project, redownload data unnecessarily or edit other roles' files.
Run relevant checks and update the handoff with actual results.
Report changed files, tests, real blockers and next task concisely.
```

## Per-role AI log entry

| Tool / model if known | Purpose | Generated or materially changed components | Checks actually performed by AI | Human validation performed/status |
|---|---|---|---|---|
| Fill actual tool/model; do not guess | Specific assistance | Files/functions/analysis | Commands/results, or not run | PENDING until actually reviewed |

Record upstream Claude planning and Codex review support when used. The final disclosure must distinguish automated checks from independent human validation and describe the team's own investment judgement.
