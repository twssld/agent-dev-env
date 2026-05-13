# Failure Criteria

## Definition

A transcript failure is not simply "the AI made a mistake". For this skill, a failure is a human steer or costly execution loop that points to a repo-level Harness gap.

Do not attribute the failure to the human or the agent. Attribute it to missing or weak repo feedforward, feedback, or harnessability.

Use this evidence chain:

```text
user intent -> agent evaluable action -> deviation or inefficient loop -> steer/evidence -> preventable repo Harness gap
```

If any link is missing, mark the item as a candidate only.

## Repo Harness Gate

Count a candidate only if the repo can reduce recurrence by adding or improving at least one of:

- Feedforward: knowledge that should be available before the agent acts — `AGENTS.md`, rules, skills, docs, SDD/spec artifacts, examples, architecture boundary notes, generated-code notes, command/SOP references.
- Feedback: signals that fire during or after action — unit/integration/browser tests, fixtures, lint, custom lint, architecture checks, AI review prompts, CI/local checks, read-only probes such as fixture loaders or log helpers.
- Harnessability: the repo itself — structure, naming consistency, module boundaries, fast test targets, stable build entrypoints, clear code patterns.

A repo Harness can be delivered as docs, command templates, scripts, wrappers, checklists, or CI checks. The artifact form is an implementation choice. Classify the gap by what is missing (knowledge / signal / structure), not by what artifact will fix it.

Exclude candidates that are only:

- Human product / architecture decisions.
- First-time business rules or changed requirements.
- Working-mode choices for the current task ("observe first", "discuss before coding", "dry-run") — see Decision vs Steer below.
- One-off personal preference or taste call the project context could not predict.
- External system noise the repo cannot observe or constrain.
- Model limitation with no practical repo-level mitigation.
- Anything whose harness would be over-reach: encoding it into `AGENTS.md` / docs / lint would constrain unrelated tasks more than it would help. The fix is **not** "add another rule"; it is to leave the choice with the user per task.

## Decision vs Steer

The judgment serves one purpose: filter for failures the repo can actually reduce. So use this single test:

> Can adding or improving repo feedforward / feedback meaningfully reduce the same kind of intervention from happening again, with net-positive effect on the repo?

- Yes → **steer**. The intervention points to a repo Harness gap. Send it through the rest of the pipeline.
- No → **decision**. The intervention is the user's per-task judgment, business choice, or taste call that the repo cannot or should not pre-equip. Do not count as failure.

Notes:

- "Net-positive" matters. Some interventions could technically be hard-coded into `AGENTS.md` (e.g. "always observe before patching", "always use BDD style", "always discuss before coding"), but doing so replaces the user's per-task decision-making and constrains unrelated tasks. If the harness would be over-reach, treat the intervention as decision, not steer.
- Repeated decisions can become steer. The same first-time judgment recurring across sessions/users/projects is a signal that the underlying frame should be fixed in repo (typically as feedforward). Once it is fixed, the same intervention thereafter is steer. Always aggregate before classifying — do not judge each occurrence in isolation.
- Do not match on user wording. The same phrase ("先别猜先加日志", "你又改错了", "UT 写得不好") can be decision or steer depending on whether a useful repo harness exists for it.

Examples (illustrative, not exhaustive — always run the test above first):

Steer:
- Agent violated a project rule, business rule, API behavior, module boundary, language constraint, test command, or commit convention that the repo could expose via feedforward / feedback.
- Agent kept retrying methods objectively invalid for a known problem (a lint, fixture, or check could have caught it).
- User repeats the same instruction because the agent ignored or misapplied it.
- Agent guessed because the repo lacked a cheap probe (no fixture, no read-only SQL, no log helper, no profiling shortcut).
- A first-time taste / working-mode preference recurs across many sessions and is worth fixing in feedforward.

Decision:
- User defines goal, scope, tradeoff, business rule, or first-time requirement specific to this task.
- User chooses between valid options, including working-mode choices for this task ("先 observe", "先讨论方案", "dry-run 一下", "draft first then refine").
- User makes a one-off taste call the project context could not predict.
- User asks the agent to do something that, if encoded into the repo, would over-constrain unrelated tasks (the harness fails the net-positive test).

Practical rule: when ambiguous, ask "would adding this to feedforward/feedback genuinely improve the repo without over-reaching?" If yes, steer. If no — or the harness would do more harm than good — decision.

## Root Cause Analysis

After a candidate passes the evidence chain and the Repo Harness Gate, do not assign a gap category by what the user said. Assign it by **why the agent took the wrong action in the first place**. Always ask one more "why" before classifying.

The same surface complaint can map to different gaps:

- User says "先别猜，先加日志" / "stop guessing, look at the logs first" → why did the agent guess?
  - Lacked repo-specific knowledge (data source map, env profile, config layout, business rule) → feedforward
  - Could not run a cheap probe (no fixture, no read-only SQL helper, no log lookup script) → feedback
  - Repo structure made it hard to know where to look at all → harnessability

- User says "你又改错了，重做" / "wrong again, redo" → why did the first fix miss?
  - Wrong mental model of the module → feedforward
  - No test / lint caught the wrong fix → feedback
  - Module boundaries unclear → harnessability

- User says "输出格式不对" / "output style is wrong" → why did the agent default to the wrong style?
  - No style guide / output rule documented → feedforward
  - No lint or check on output format → feedback

The user's wording is a steer indicator, not a root cause label. Classify by what knowledge, signal, or structure was missing.

If a single surface complaint splits across multiple root causes, do not blend them into one pattern. Split into separate patterns by root cause and report each with its own count.

## Repo Harness Gap Types

Group gaps by the root cause type from the analysis above. Within a group, pick the most specific subtype that fits the evidence.

### Feedforward gaps (missing knowledge / context)

Missing or stale repo context:
- The repo did not expose layout, data sources, env profiles, config matrix, internal APIs, branches, generated code, dependency direction, or conventions clearly enough for the agent to act without guessing.

Missing intent/scope feedforward:
- The repo did not provide enough task framing, accepted scope, non-goals, examples, or spec anchors to keep implementation aligned.

Missing architecture / module-boundary documentation:
- The repo did not make layers, country/module boundaries, dependency direction, or abstraction ownership discoverable.

Missing output / style guide:
- The repo did not expose output language, format, generated-doc, or communication constraints clearly enough.

### Feedback gaps (missing signals during / after action)

Missing verification/test harness:
- The repo did not provide stable, discoverable validation entrypoints, targeted tests, or fast feedback loops.
- The agent lost cwd/module/reactor context and repeatedly ran invalid validation commands before finding the real error.

Missing cheap probe:
- The repo did not provide read-only SQL templates, fixture loaders, log helpers, or other lightweight observation tools that would let the agent verify before patching.

Missing enforcement check:
- The repo did not have lint, architecture checks, or CI gates to catch boundary violations, output-style mismatches, or commit/branch convention errors.

### Harnessability gaps (the repo itself)

Low repo harnessability:
- Inconsistent patterns, slow tests, unclear structure, weak module boundaries, or implicit-only conventions caused excessive iterations, tools, time, or tokens — even when individual answers were correct.

## Verification Attempt Counting

When analyzing build/test failures, count attempts by the repeated wrong assumption, not by every command.

Use these buckets:
- Invalid repeated attempts: commands that fail for the same preventable reason, such as wrong cwd, wrong module path, wrong reactor root, or stale relative `pom.xml` path.
- Diagnostic probes: `pwd`, `ls`, `find`, `grep`, reading POMs, or commands used to understand the environment. Do not count these as failed attempts.
- Real issue validation: commands that expose a genuine compile/test problem after the command context is fixed. Count under the real issue, not under the earlier command-context error.
- Final validation: reruns across profiles/modules after fixes. Do not count as failure attempts unless they repeat the same preventable mistake.

Self-recovered loops can still be failures. If there is no user steer but the agent wastes multiple attempts on a preventable validation-context mistake, classify it as medium or low confidence `Missing verification/test harness + low repo harnessability`.

Example wording:

```text
Verification workflow failure: the repo lacks a stable validation entrypoint. The agent tried 3 invalid Maven commands from the wrong cwd/reactor context before returning to the repo root. The later compile failures were real stub/interface issues and should be counted separately.
```

## Repo Harness Recommendation Priority

Prioritize repo Harness gaps only by observed frequency:

```text
priority = occurrence count of the same repo Harness gap
```

Count the same repo Harness gap across sessions, users, projects, or repeated turns. When two gaps have the same frequency, keep them tied or use recency only as a display tiebreaker. Do not invent a weighted score.

## Pattern Aggregation

After validating candidates, normalize them into repeated repo Harness patterns before reporting. A pattern is the same recurring steer or repo Harness gap, even if the concrete files, repos, or features differ.

Examples:
- "Agent guessed production data root cause and changed code before observing real data."
- "Agent crossed module/country boundaries instead of preserving established abstraction layers."
- "Agent widened frontend fix scope beyond the user-requested state."
- "Agent repeatedly used the wrong validation cwd/module context before reaching the real test failure."

Rewrite these as repo gaps in final reports. Pick the wording that matches the root cause type:
- "Repo lacks data source / env-config feedforward for production data issues."
- "Repo lacks enforceable module/country boundary check."
- "Repo lacks frontend state-scope verification harness."
- "Repo lacks stable Maven/reactor validation entrypoint."

The final answer should lead with these patterns and their counts. Individual transcript cases should be short evidence under a pattern, not separate top-level report sections.

## Recommended Evidence Standards

High confidence:
- Strong steer text or rollback command after agent edits, plus clear original intent.

Medium confidence:
- Multiple medium signals such as repeated edits, weak correction language, and validation loops.

Low confidence:
- Only weak signals, no clear steer, or likely design discussion.

Do not over-classify. It is better to output fewer high-signal failures than a noisy list that people stop trusting.
