---
name: ai-transcript-failure-analysis
description: Analyze Claude Code and Cursor transcript exports to identify repo-level Harness gaps behind steer patterns, repeated correction patterns, and efficiency failures. Use when Codex is asked to review AI agent transcripts, scan .jsonl/store.db conversation logs, classify decision vs steer, produce failure-pattern reports, or decide what repo rules/skills/docs/tests/checks should be built from repeated human interventions.
---

# AI Transcript Failure Analysis

## Goal

Turn AI coding transcripts into actionable repo Harness signals. Treat a failure as a repeated or costly steer, rollback, or invalid loop that can be reduced by better repo-level feedforward, feedback, or harnessability. See `references/failure-criteria.md` for the three-category breakdown and the root-cause analysis methodology.

Do not use this skill to blame people or agents. The unit of analysis is the repo: what knowledge, signal, or structure did the repo fail to provide?

## Workflow

1. Pick the transcript roots.
   - If the user gave an explicit path, use it.
   - Otherwise default to whichever of `~/.claude` and `~/.cursor` exist on this machine — pass both when both exist.
   - The script requires at least one root; it does not auto-discover.

2. Run a candidate scan. The script reads JSONL and Cursor `store.db` in one pass and emits cleaned candidates (envelope stripped, tool_result filtered, generated command output removed).

   ```bash
   python3 /path/to/ai-transcript-failure-analysis/scripts/scan_transcripts.py <root> [<root> ...]
   ```

3. Validate every candidate against the evidence chain.
   - Walk the full list. The scanner emits **hint locations, not labels** — `strong-vocab-hit:7` means "7 watch-list words landed near an agent action", not "7 corrections". `score` is hit density; sort by it, do not truncate by it.
   - For each candidate, apply the decision-vs-steer test from `references/failure-criteria.md` → Decision vs Steer. Then confirm: (a) original user intent, (b) an evaluable agent action, (c) a steer / rollback / repeat / loop / costly detour after that action. For verification loops, separate invalid repeated attempts, diagnostic probes, code fixes, and final validation.
   - **Go back to the raw transcript whenever the snippet is not enough.** Common triggers: hit text looks like pasted skill/doc content rather than user words; a `similarity_hit` with no agent turn shown between the two messages; a `shell_failure_hit` without the stderr / agent reply; a `git_revert` without the preceding edits; a generic `preceding_user_intent` ("继续", "ok"); multi-turn causal chains the snippet only previews at the ends.
   - **Locating and reading the source.** Every hit carries a `path` (relative to scan root) and a line/index pointer. For `*.jsonl` use `Read` at that offset (±10 lines). For Cursor `store.db` the line is a virtual index — use the bundled `show` subcommand, do not read the SQLite directly:

     ```bash
     python3 /path/to/scripts/scan_transcripts.py show <path> --line <n> --context 5
     ```

     Run `scan_transcripts.py show --help` for flags.

4. Apply the repo Harness gate. Count the candidate only if a repo change (knowledge / signal / structure) could meaningfully reduce recurrence with net-positive effect. Full criteria and exclusions in `references/failure-criteria.md` → Repo Harness Gate. Classify by what is missing, not by the artifact that would fix it.

5. Classify by root cause, not by user wording. Ask one more "why" before picking a category — the same surface complaint can come from missing knowledge, missing probe, or unclear structure. If one complaint splits across multiple root causes, report each as its own pattern. Categories and subtypes in `references/failure-criteria.md` → Root Cause Analysis and Repo Harness Gap Types.

6. Aggregate by repeated repo Harness gap, not by isolated transcript.
   - Prefer "same steer repeated across sessions/users/projects" over one-off anecdotes.
   - Prioritize repo Harness work only by frequency: count how many times the same repo Harness gap appears.
   - **Re-check decisions after grouping.** A first-time taste call or working-mode preference that recurs across sessions/users is a signal that the underlying frame should be fixed in repo (typically as feedforward). Such a recurring decision can be promoted to steer at this step. Single-occurrence decisions stay decisions.
   - Report patterns first. Individual failures are evidence, not the main output.

Read `references/failure-criteria.md` when judging ambiguous cases or writing the final report.

## False Positive Rules

The scanner already filters obvious recording artifacts (envelope wrappers, tool_result, exact adjacent duplicates, `git checkout branch`, `ERROR 0` dashboards). Beyond that, the agent must still check:

- Repeated edits to a design document during collaborative design are often normal iteration.
- "Do not agree with me; tell me if this is right" is usually a decision request, not a steer.
- Do not count all test/build commands in a long session as one failure. Count only repeated attempts with the same wrong assumption or same preventable command-context error.
- Do not count a candidate if it cannot be reduced by a repo-level harness. Record it as normal decision-making, changed requirements, or non-repo external noise.

## Report Shape

The final report must be pattern-first and repo-harness-first. Group validated failures by normalized repo Harness gap / failure pattern, sort groups by occurrence count, and include only representative evidence.

```markdown
## Repo Harness Failure Patterns

### Pattern: <normalized pattern name> (count: <n>)
- What repeats: <one-sentence repeated steer/failure behavior>
- Typical trigger: <when this tends to happen>
- Repo Harness gap: <rule/skill/doc/check/tool/script/template to build>
- Attempt count: <invalid repeated attempts only; omit if not relevant>
- Representative evidence:
  - `<transcript path>`: <short evidence chain>
  - `<transcript path>`: <short evidence chain>
- Confidence: high|medium|low

## Frequency Ranking

| Rank | Pattern | Count | Repo Harness gap |
|------|---------|-------|-------------|
| 1 | <pattern> | <n> | <gap> |
```

Only include a per-failure appendix when the user explicitly asks for details or when auditability requires it. If included, keep it under each pattern as representative cases, not as the primary structure.
