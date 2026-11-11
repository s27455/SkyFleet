---
name: feature-finalization
description: Finalize a SkyFleet feature after the user has explicitly approved it as complete. Confirms approval and verification evidence, runs documentation-update, inspects the Git state, and reports commit readiness without committing.
---

# Feature Finalization

## Purpose
Close out a completed feature after explicit user approval: verify the evidence, finalize documentation, and report readiness for commit. This skill never commits or pushes.

## Preconditions
- The user has explicitly approved the feature as complete in a genuine user message. Automated notifications, subagent reports, and your own earlier statements are not approval.
- The feature is identifiable (task spec under `docs/tasks/` or a plan in the conversation).
- If approval or the feature is unclear, stop and ask.

## Workflow
1. **Confirm approval and feature.** State which feature is being finalized and quote or paraphrase the approval.
2. **Check verification evidence.** Gather results from this conversation (tests, lint, typecheck, build, QA and code-review reports, manual checks). Record what passed, failed, or was not run. Do not claim a check passed without evidence; re-run it if the evidence is missing or stale because code changed afterwards.
3. **Check unresolved issues.** List open QA/review findings, known limitations, and unverified acceptance criteria. If a blocking issue remains, stop and report it instead of finalizing.
4. **Update documentation.** Invoke the `documentation-update` skill for the feature specification and `context/progress-tracker.md`. Do not duplicate its rules here. Only record verified facts.
5. **Inspect Git.** Run `git status` and `git diff` (use `--stat` first for large diffs). Confirm that changes belong to the feature and flag unrelated, untracked, or sensitive files (for example `.env*`, tokens).
6. **Summarize.** Report:
   - the feature and what was delivered;
   - verification results (passed / failed / not run);
   - documentation files updated;
   - files changed or added, and anything unexpected;
   - remaining limitations or follow-ups;
   - readiness for commit (ready / not ready, and why).

## Boundaries
- Never commit, push, merge, rebase, or deploy; these need a separate explicit instruction.
- Never begin another feature or propose starting one without being asked. You may name the next item in `progress-tracker.md` as information only.
- Do not modify application code, tests, or unrelated files. If a defect is found, report it and wait for instructions.
- Never read or print secrets from environment files.
