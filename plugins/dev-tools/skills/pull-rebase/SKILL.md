---
name: pull-rebase
description: This skill should be used when the user asks to "pull and rebase", "同步远端并 rebase", "git pull --rebase", "拉取远端改动", "rebase 到最新 main", "同步 worktree", or wants to sync the current branch/worktree with remote via rebase. Handles upstream setup, pre-rebase context gathering, conflict resolution, and post-rebase follow-up changes. Works for both regular branches and worktrees.
---

# Pull & Rebase

同步当前分支或 worktree 到最新远端，采用 rebase 策略。在执行前先把**本地 vs 远端的增量**摸清楚，为冲突解决做准备；rebase 成功后若仍有需要跟进的改动，一并处理完。

## Prerequisites

- 工作区干净（无未提交改动）。若有未提交改动，先问用户是否 `git stash`。
- 当前分支的所有本地 commits 已确定为保留目标（不是半成品想丢弃的）。

## Workflow

### Step 1: Gather Context（在执行前读懂两侧的增量）

并行执行：

```bash
git branch --show-current
git status --porcelain
git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "NO_UPSTREAM"
git rev-parse --git-dir
```

判定：
- **current branch**：当前分支名
- **is worktree**：`git rev-parse --git-dir` 输出包含 `worktrees/` → 是 worktree 会话
- **has upstream**：上一行不是 `NO_UPSTREAM` → 已设置 upstream
- **is dirty**：`git status --porcelain` 非空 → 工作区不干净，先停下来确认

**如果没有 upstream**：

upstream 目标**只会是远端默认分支**（`origin/main` 或 `origin/master`），不要去匹配同名远端分支。

```bash
# 优先用 symbolic-ref 拿默认分支
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null
# 若上面为空（未设置 origin/HEAD），退回枚举看仓库用哪个
git branch -r | grep -E 'origin/(main|master)$'
```

按结果挑出 `origin/main` 或 `origin/master`，然后：

```bash
git branch --set-upstream-to=origin/<main-or-master> <current-branch>
```

两个都不存在（极少见）时停下来问用户。

### Step 2: 预读两侧增量（为冲突解决做准备）

先 fetch 再对比，**不要**直接 pull：

```bash
git fetch <remote>
```

然后并行执行以下 3 组命令，把本地与远端的增量都摸清：

```bash
# 本地领先远端的 commits（我自己做了什么）
git log @{u}..HEAD --oneline
git diff @{u}..HEAD --stat

# 远端领先本地的 commits（远端增量）
git log HEAD..@{u} --oneline
git diff HEAD..@{u} --stat

# 两侧都改过的文件（最可能产生冲突的地方）
git diff @{u}..HEAD --name-only | sort > /tmp/local_changed.txt
git diff HEAD..@{u} --name-only | sort > /tmp/remote_changed.txt
comm -12 /tmp/local_changed.txt /tmp/remote_changed.txt
```

**判断**：
- 若 `HEAD..@{u}` 为空：远端无增量，直接跳到 Step 5 报告"已是最新"
- 若 `@{u}..HEAD` 为空：本地无增量，rebase 退化为 fast-forward，风险最低
- 若两边都非空，且交集文件列表非空：**高冲突风险**。对交集中的每个文件，读一下本地侧和远端侧的 diff 细节（`git diff @{u}..HEAD -- <file>` 与 `git diff HEAD..@{u} -- <file>`），心里对冲突位置有预期

这一步的目的不是生成报告，是**让自己在冲突发生前就知道该怎么合**。

### Step 3: 执行 Rebase

```bash
git pull --rebase
```

### Step 4: 冲突处理

**若 rebase 冲突**：

1. `git status` 查看冲突文件清单
2. 对每个冲突文件：
   - 读文件，找 `<<<<<<<` / `=======` / `>>>>>>>` 标记
   - 结合 Step 2 预读的两侧意图来合并：
     - 本地侧（`HEAD` 之后的 commits）要保留的意图是什么
     - 远端侧引入的改动是什么
     - 正确合并后的代码应该同时体现两侧意图
   - 解决后 `git add <file>`
3. `git rebase --continue`
4. 若出现需要 `--skip` 或 `--abort` 的情况：**停下来问用户**，不要自作主张放弃本地 commits

**若 rebase 成功无冲突**：继续 Step 5。

### Step 5: Rebase 后的增量适配

Rebase 成功后，本地 commits 已基于远端最新 HEAD 重放。此时检查是否存在"语法上 rebase 成功，但语义上需要跟进"的情况：

并行执行：

```bash
git status
git log --oneline -n 10
# 如果项目有快速校验手段（按项目实际选择）：
# 编译：构建命令
# 类型检查：tsc --noEmit / mypy 等
# 测试：项目测试入口
```

判断是否需要跟进改动：
- 远端 Step 2 预读中发现的 API 改名、字段重命名、依赖升级、配置结构变更，本地 commits 是否已经适配？
- 若本地 commits 中涉及的符号、文件、接口在远端已被改动，rebase 不会自动帮你更新本地 commits 里**未冲突但已过时**的调用点
- 常见踩坑：远端把 `methodA` 改成 `methodB`，本地 commits 里新增的代码还在调用 `methodA` → rebase 不报冲突但运行时坏

如果发现需要跟进的改动：
- **先问用户** 是否允许在当前分支上追加一个修复 commit 来适配
- 用户同意后：修改 → 验证（编译/类型检查/测试按项目情况）→ `git add` → `git commit`

### Step 6: Report Result

只报核心信息，一到两句话。默认模板：

> `<结果>`。本地领先/落后 N 个 commit。

其中 `<结果>` 从以下挑一个：
- `已是最新，无需 rebase`（远端无增量）
- `fast-forward N 个远端 commit`（本地无增量）
- `rebase N 个本地 commit 完成`（正常 rebase 无冲突）
- `rebase 完成，解决 M 个冲突文件`（有冲突）

**只在以下情况追加信息**：
- 新设了 upstream：加一句 `upstream 设为 origin/<branch>`
- 有冲突：列冲突文件名
- 有跟进 commit：附 hash
- 用户明确要求详情：再给完整 `git log --oneline -n 3`

不要默认输出最终 HEAD、diff stat、未变化的 upstream 状态等用户不问也知道的东西。

## Error Handling

- **工作区不干净**：停下来报告未提交文件，问用户是 stash 还是先 commit
- **upstream 推断不出**（同名远端不存在、无默认分支）：列出 `git branch -r`，让用户指定
- **fetch 失败**（网络/权限）：停下来报告，不要继续
- **rebase 冲突卡住**（同一文件反复冲突、二进制文件冲突、大量重命名）：停下来，报告当前状态，让用户决定是 `--abort` 还是人工介入
- **pre-commit / CI hook 本地失败**：跟进 commit 阶段若 hook 失败，**修复根因**再重新 commit，不要 `--no-verify`

## Worktree vs Regular Branch

本 skill 对两者处理逻辑**完全一致**，差异仅在诊断信息：

- **Regular branch**：`git rev-parse --git-dir` 输出 `.git`
- **Worktree**：`git rev-parse --git-dir` 输出类似 `<main-repo>/.git/worktrees/<name>`

在 Report 中标注这一信息即可，不需要分叉流程。Worktree 的 rebase 行为与普通分支无差别。
