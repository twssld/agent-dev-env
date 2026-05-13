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
   # Add --json for machine-readable output, --limit N to cap candidates.
   ```

3. Manually validate top candidates with the evidence-chain standard.
   - The scanner output is a coarse filter only. It reports **hint locations**, not labels. Do not treat `strong-vocab-hit:7` as "7 strong corrections"—a vocab hit just means a user message contained a word from the watch list near an agent action.
   - For each candidate, run the **decision vs steer test** (single core question, see `references/failure-criteria.md` → Decision vs Steer):
     > Can adding or improving repo feedforward / feedback meaningfully reduce the same kind of intervention from happening again, **with net-positive effect on the repo**?
     - Yes → steer, keep going. No → decision, drop the candidate.
     - Do not match on user wording. The same phrase ("先别猜先加日志", "你又改错了", "UT 写得不好") can be decision or steer depending on whether a useful, non-over-reaching repo harness exists for it.
     - Working-mode preferences for this task ("先 observe", "先讨论方案", "dry-run") are decisions, not steer — encoding them into `AGENTS.md` would replace the user's per-task judgment.
     - A first-time taste call that recurs across many sessions can be reclassified as steer at aggregation time (step 6) — judge in isolation first, then re-check after grouping.
   - Confirm original user intent (read raw excerpts; ignore scanner labels).
   - Confirm the agent took an evaluable action.
   - Confirm a steer, rollback, repeated instruction, failure loop, or costly detour happened after that action.
   - For verification loops, separate invalid repeated attempts, diagnostic probes, code fixes, and final validation.

   **When candidate excerpts are not enough, re-query the raw transcript.** The candidate JSON only carries truncated snippets; the moment you cannot tell decision-vs-steer from the snippet alone, go back to the source. Common triggers:
   - The hit text looks like pasted skill content / docs / spec rather than the user's own words (e.g. `wrong` appears inside a `/explore` template). Read the surrounding messages to see who is speaking.
   - A `similarity_hit` shows two near-duplicate user messages but no agent activity between them in the snippet. You need the actual messages in between to know whether the user repeated themselves or reacted to new agent output.
   - A `shell_failure_hit` only shows the command line; you need the full stderr / stack trace, and the agent's reply afterward, to decide whether it was a real loop or a one-shot transient failure.
   - A `git_revert` is reported but the snippet does not show what the agent actually edited before the revert.
   - The `preceding_user_intent` is generic (e.g. `继续`, `ok`); you must walk backward to find the real instruction that started this episode.
   - Multi-turn causal chains (3+ messages spanning user → agent → tool → user) where the candidate only previews two ends.

   **How to locate the line.** Every hit in the candidate carries a line/index pointer (`line`, `first_line`, `second_line`, `preceding_action_line`). The `path` is relative to the scan root. For Cursor `store.db`, the line is a virtual index over the deduplicated message stream produced by the scanner—use the `show` subcommand (below) rather than reading the SQLite file directly.

   **How to read the raw transcript.**
   - `*.jsonl` (Claude Code, Cursor JSONL exports): use the standard `Read` tool with the `path` and an `offset` near the hit line. Each line is one event; reading a window of ±10 lines around the hit usually covers the local turn.
   - `store.db` (Cursor SQLite): use the bundled `show` subcommand to print a re-rendered window of messages with envelope tags stripped and tool-calls compacted:

     ```bash
     python3 /path/to/ai-transcript-failure-analysis/scripts/scan_transcripts.py show \
         <relative_or_absolute_path_to_store.db> \
         --line <hit_line> --context 5
     ```

     The output shows `[line=N, role=...]` headers, real user text after envelope stripping, and `→ tool_use` / `← tool_result` summaries for assistant turns. Use `--context 10` or larger when the relevant chain spans more turns.

4. Apply the repo Harness gate.
   - Count the candidate only if it can map to at least one of the three repo-improvable categories (full list in `references/failure-criteria.md`):
     - **Feedforward**: knowledge that should be available before action — `AGENTS.md`, rules, skills, docs, SDD/spec, examples, architecture boundary notes, command/SOP references.
     - **Feedback**: signals that fire during or after action — tests (unit/integration/browser), fixtures, lint, custom lint, architecture checks, AI review prompts, CI/local checks, read-only probes.
     - **Harnessability**: the repo itself — structure, naming consistency, module boundaries, fast test targets, stable build entrypoints, clear code patterns.
   - The artifact form (docs / command template / wrapper script / CI check / lint / fixture) is an implementation choice for the team that will fix the gap, not a separate category. Classify by what is missing (knowledge / signal / structure).
   - Exclude one-off human decisions, new business choices, changed requirements, working-mode preferences, personal taste calls, external incidents, and anything whose harness would be over-reach (encoding it into `AGENTS.md` / docs / lint would constrain unrelated tasks more than it would help).

5. Classify the repo Harness gap by root cause, not by user wording.
   - Ask one more "why" before assigning a category: the user's complaint tells you a steer happened, not why it happened. The same surface complaint (e.g. "stop guessing, look at the logs") can come from missing knowledge, missing probe, or unclear structure. See `references/failure-criteria.md` → Root Cause Analysis.
   - If a single complaint splits across multiple root causes, do not blend them into one pattern; report each root cause as its own pattern.
   - Subtype within each category (full list in `references/failure-criteria.md` → Repo Harness Gap Types):
     - Feedforward: missing or stale repo context · missing intent/scope feedforward · missing architecture / module-boundary documentation · missing output / style guide
     - Feedback: missing verification/test harness · missing cheap probe · missing enforcement check
     - Harnessability: low repo harnessability (inconsistent patterns, slow tests, unclear structure, weak implicit feedforward)

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
