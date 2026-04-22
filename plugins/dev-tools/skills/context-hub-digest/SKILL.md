---
name: context-hub-digest
description: >
  Generate a concise weekly FYI digest of plugin changes in the context-hub
  repository only, formatted as an emoji-categorized single-line bullet list
  suitable for group-chat broadcast. Scoped strictly to the four plugins under
  /Users/taowei/code/context-hub (java-dev-kit, quality-kit, sdd, utilities)
  over the past 7 days. Output is Chinese and stays short: line count
  scales linearly with the number of changed plugins.
  Use when the user says "context-hub 周报",
  "context-hub 插件周报", "context-hub 本周改动", "context-hub 改动速览",
  or pastes the context-hub path and asks for a weekly summary.
repo: /Users/taowei/code/context-hub
target_dirs:
  - plugins/java-dev-kit
  - plugins/quality-kit
  - plugins/sdd
  - plugins/utilities
---

# Context Hub 插件周报速览

生成面向技术团队群聊的**插件改动速览**，风格：emoji 分类 + 单行 bullet + 极简。仅用于 `context-hub` 仓库。

## 范围
- 仓库：`/Users/taowei/code/context-hub`
- 目标目录：`plugins/java-dev-kit/`、`plugins/quality-kit/`、`plugins/sdd/`、`plugins/utilities/`
- 时间窗口：最近 7 天（用 `git log --since` 过滤，以 `date` 命令的今天为基准）
- **分支约束**：只统计已合入 `origin/master` 的 commits，未合并的 feature 分支**不纳入**

## 调研步骤

### Step 1：同步远端并锁定时间窗口与基线

```bash
cd /Users/taowei/code/context-hub && git fetch origin master
```

用 `date` 算出 `SINCE`（7 天前，格式 `YYYY-MM-DD`）和 `END`（今天）。后续所有查询**都基于 `origin/master`**：

```bash
# 拉出 origin/master 上本窗口内的 commit 列表（只做 plugin 级统计用）
git log origin/master --since="$SINCE" --pretty=format:"%h %ad %s" --date=short -- \
  plugins/java-dev-kit plugins/quality-kit plugins/sdd plugins/utilities
```

- **严禁使用 `--all`**（会把未合并的 feature 分支混进来）
- **严禁裸 `git log`**（默认 HEAD 可能漂到 feature 分支）
- 如果需要对单个 commit 做身份交叉验证：`git branch -r --contains <hash> | grep -x '  origin/master'`，空输出 → 丢弃

### Step 2：为每个"有改动"的 plugin 生成聚合 diff

**核心原则：以 plugin 为维度汇总整个窗口的代码改动，不依赖单个 commit message 做总结。**

对每个目标 plugin 分别执行（确定窗口首尾两个端点）：

```bash
# 找到 origin/master 上窗口开始日之前的最后一次提交，作为 BASE
BASE=$(git rev-list -1 --before="$SINCE 00:00:00" origin/master)
HEAD=origin/master

# 该 plugin 在整个窗口内的"最终净变化"
git diff --stat "$BASE" "$HEAD" -- plugins/<name>
git diff "$BASE" "$HEAD" -- plugins/<name>
```

若 `--stat` 为空 → 该 plugin **本周无改动**，直接归入 `💤`，不需要进入后续分析。

### Step 3：并行派发 subagent 做 plugin 级分析

对"有改动"的 plugin，**同一条消息里并行发出多个 Agent 调用**（每个 plugin 一个 subagent），要求：

- 每个 subagent 只看**自己那一个 plugin** 的 `--stat` 和 `diff`，**不看 commit message**
- 基于**代码实际改动**提炼 2-4 条主线，每条要能回答"改的是哪个字段/文件/行为"
- 输出固定结构（便于主 agent 拼装）：

  ```
  ## <plugin 名>
  主线判断: <一句话，带判断词如"规范收敛"/"稳定性修复"/"能力扩展"，主线必须单一>
  emoji: <📐/🔧/✨/🧩 等，按主线语义选>

  主题 1
  - 维度标签: <抽象名词短语>
  - 描述: <≤50 中文字，含 skill 名 + 关键字段/文件/行为>
  - 证据文件: <列 1-3 个最代表性的文件路径>

  主题 2
  ...
  ```

- Subagent prompt 中需复述本 SKILL 的 **Bullet 规则 + 三条红线 + 克制原则**（见下文），防止 subagent 自由发挥。

### Step 4：主 agent 合成最终周报

1. 收集各 subagent 结果
2. 按 `本文件「输出骨架」` 拼装
3. 过「自检清单」逐项验证
4. 未改动的 plugin 合并到 `💤 本周无改动` 节

### 克制原则（subagent 与主 agent 都遵守）

选择规则枚举、文案修订、文档同步、枚举值扩展等次级项一律砍掉。问自己：**这条信息对群聊读者的价值，是否值得占掉一条 bullet？** 否 → 删。

## 输出骨架

```
📣 Context Hub 本周插件改动速览（YYYY-MM-DD ~ YYYY-MM-DD）

<emoji> <插件名> · <一句话主线判断>
    • <维度标签>：<一句话描述>
    • <维度标签>：<一句话描述>
    • <维度标签>：<一句话描述>
    • <维度标签>：<一句话描述>   ← 可选第 4 条

<emoji> <第二个插件> · <一句话主线判断>
    • <维度标签>：<一句话描述>
    • <维度标签>：<一句话描述>

💤 本周无改动
    • <插件名>、<插件名>
```

## 各部位规则

### 顶部
固定 `📣 Context Hub 本周插件改动速览（日期 ~ 日期）`

### 插件分类标题
- 格式：`<emoji> <插件名> · <一句话主线>`
- emoji 选择：规范收敛 📐/📏；稳定性修复 🔧/🛠；新能力扩展 ✨/🚀；治理 🧹/🧩
- 主线必须带判断词（"规范收敛"/"稳定性修复"/"能力扩展"）
- **主线必须单一**：不得用 `+`/`/`/`与` 连接两个主线
- 主线不用流程箭头

### Bullet 格式
- `    • ` 开头（4 空格 + Unicode 中点 `•`），**不用 markdown `-`**
- 数量 **2-4 条**，不硬凑
- 固定结构：`<维度标签>：<一句话>`
- 每条 ≤ 50 中文字

### Bullet 维度标签

标签是一个短标题，概括这条 bullet 讲的"哪一块变了"。两条要求：

**1. 自然短语，不是动作描述也不是实现细节**
- ✅「clarify 不再讨论 HOW」「tasks 精简」「Diff 生成修复」「执行顺序收紧」
- ❌「移除 integrates 字段」（动作描述）/「diff 改走 pathspec」（实现细节）

**2. 字数不要刻意对齐**

这是最容易出"AI 味"的地方。不要把一组标签凑成整齐的四字短语（"验收编号贯通 / 门禁模型重塑 / 阶段职责收敛 / 轻量路径接通"——这种排比读起来假，人写周报不会这样）。按内容自然长度来，有的 2-3 字，有的 6-8 字，混杂是正常的。

- ❌ AI 味：「验收编号贯通」「门禁模型重塑」「阶段职责收敛」「轻量路径接通」（四条整齐四字）
- ✅ 参差：「验收场景统一编号」「tasks 精简」「clarify 限定在 WHAT/WHY」「sketch 接通 implement」

### Bullet 描述（五条红线）

#### 🔴 红线 1：禁空心描述
读完必须能答"改的是哪个字段/文件/行为"。
- ❌ 空心：「diff 文件生成逻辑收敛」
- ✅ 具体：「脚本与展示字段对齐到 topic」

#### 🔴 红线 2：禁实现级证据
**绝对不能出现**：
- 函数名（`filter_diff_by_extensions`）
- **git 内部术语**（`pathspec`、`commit^`、`HEAD^`、`base_commit`、`rev-parse`）
- 正则、命令行参数
- 被删旧编号详细名（G{N}-{序号}、Replan 章节等，只能作"替代对象"一笔带过）

读者是**周会观众**，不是 git 用户手册读者。"diff 更准了"的事实就够了，**不讲怎么准的**。

#### 🔴 红线 3：同功能域必须合并
判断："这些变化对下游呈现为同一个接口变化吗？" 是 → 合并。

**典型示例**：code-reviewer 的 diff 生成修复 + `agent → topic` 字段对齐 + 脚本更新 → 全部属于"结果产出链路"一个功能域，**必须合并到一条 bullet**，不要把字段对齐拆到"执行流程加固"。

#### 🔴 红线 4：只写"本周新增的变化"，不写既有能力
读者默认已经知道每个 skill 本来能做什么。bullet 只能描述**这周 diff 里真实发生的增量动作**（新增、删除、改名、迁移、约束变化），**不要**把"既有设计"当成本周变化写。

自检法：把描述里的动词抠出来 →"支持/接受/可以/允许"之类静态能力描述 → 高度警惕，大概率是在讲既有功能。应该换成**本周发生的动作**：新增、移除、迁出、改为、统一到、合并、拆分、下线、接通、替换。

- ❌ 既有能力：「implement 接受 sketch.md 作为 tasks.md 的替代入口」（implement 本来就是执行入口，这句读完不知道**本周**发生了什么）
- ❌ 反推不出动作：「小改动写 sketch.md 即可，不必展开 tasks.md」（sketch 本来就是给小改动用的）
- ✅ 增量动作：「sketch 接通 implement：implement 新增对 sketch.md 的直接读取」
- ✅ 增量动作：「feishu-doc 迁出：feishu-doc skill 与 lark-mcp 配置迁出为独立 plugin」

#### 🔴 红线 5：去 AI 味

AI 生成的技术周报有几个典型坏味：

**a. 对仗/排比结构**：整页 bullet 标签都是同字数短语（四字、六字），或动宾结构高度整齐。人写不会这样——真实周报的标签长度必然**参差不齐**。

**b. 宏大动词**：「重塑 / 重构 / 贯通 / 收敛 / 治理 / 闭环 / 体系化 / 标准化」——这类词本身没错，但 bullet 里**扎堆出现就显假**。一份周报里最多出现 1-2 次这类词。其余用**具体动词**：新增、删除、改为、迁出、合并、统一到、接通。

**c. 主线判断也不能扎堆用宏大词**：如果分类主线是「XX 体系重构」+「XX 闭环修复」+「XX 边界调整」三条并排，整份报告就"AI 味拉满"。至少一条用更平实的表述（例："code-reviewer 修脚本"、"utilities 拆出 feishu-doc"）。

**d. 自检法**：把周报给自己读一遍，如果读起来像技术公众号标题 → AI 味过重，重写。

- ❌ AI 味：「验收体系重构」「评审闭环修复」「门禁模型重塑」「轻量路径接通」
- ✅ 自然：「验收方式统一」「code-reviewer 脚本修复」「tasks 模板精简」「sketch 接通 implement」

### 允许出现的证据
- skill 名（`clarify`、`tasks`）
- 关键字段名（`integrates`、`topic`、`agent`）
- 关键文件名（`sketch.md`、`tasks.md`）
- 脚本名（作为整体代称，不展开 git 语法）

### 💤 无改动
```
💤 本周无改动
    • <插件名>、<插件名>
```

### 末尾
以 `💤 本周无改动` 小节作为整篇的收尾（若所有 plugin 都有改动则省略此节，自然结束）。

**不写**"一句话总结"/"行为变化提醒"/"影响的 skill 清单"/飞书文档链接。

### 全局禁项
- ❌ commit hash、commit 标题原文翻译
- ❌ 函数名、git 内部术语、命令行参数、正则
- ❌ `▎` 收尾行、`---` 分隔线、`**一句话总结**`、飞书文档链接
- ❌ 分类主线复合（`+`/`/`/`与` 连接两个主线）
- ❌ 次级增强项（选择规则分类枚举、文案修订、文档同步单列、枚举值扩展）
- ❌ 超过 50 字的 bullet、空心描述

### 篇幅（按 plugin 数量线性计算）

全文行数 = 2（标题+空行）+ **每个有改动 plugin 约 (bullet 数 + 2) 行** + 💤 节 2 行（若有）。

典型规模参考：

| 有改动 plugin 数 | 是否有 💤 | 预期行数 |
|---|---|---|
| 1 | 是 | ~8 行 |
| 2 | 是 | ~14 行 |
| 3 | 是 | ~17 行 |
| 4 | 否 | ~20 行 |

**目标仍是极简**：每个 plugin 的 bullet 数**宁少勿多**，按「克制原则」砍次级。如果某个 plugin 只能凑出 1 条像样的 bullet，说明它这周没有"主线级"改动，考虑把它改为"轻微动态"一句话带过（例：`🧩 utilities · feishu-doc 迁出为独立 plugin`，不展开 bullet），或合并到 💤 后面加「+ 轻微调整」一句话。

## 自检清单（输出前逐条核对）

- [ ] 所有查询都基于 `origin/master`，没有用 `--all` 也没有用裸 `git log`
- [ ] 每个"有改动"的 plugin 都已用 `git diff BASE HEAD -- plugins/<name>` 产出**聚合 diff** 并作为 subagent 分析依据
- [ ] 主线判断基于**聚合 diff 的实际代码改动**，**不依赖 commit message**
- [ ] 多个 plugin 的分析是通过**并行 subagent** 处理的（同一条消息里多个 Agent 调用）
- [ ] 顶部用 📣 开头
- [ ] 每个插件分类独立 emoji
- [ ] 分类主线单一判断，无 `+`/`/`/`与` 复合
- [ ] Bullet 用 `    • `（4 空格 + `•`），不是 `-`
- [ ] 每条 bullet ≤ 50 中文字
- [ ] 维度标签是抽象名词短语
- [ ] **每条 bullet 都能回答"改的是 XX 字段/文件/行为"**（无空心）
- [ ] **Bullet 内无 git 内部术语**（pathspec/commit^/HEAD^/base_commit/rev-parse 等绝对禁止）
- [ ] **字段对齐/展示变更已并入其所属功能域 bullet**，未被错拆到"执行流程加固"之类
- [ ] 同功能域改动已合并
- [ ] **每条 bullet 都是本周 diff 里真实发生的增量动作**（新增/移除/迁出/改为/统一到/合并/拆分/接通等），不是既有能力描述（"支持/接受/可以/允许"高度警惕）
- [ ] **维度标签字数参差不齐**，不是整齐的四字/六字排比
- [ ] 「重塑/重构/贯通/收敛/治理/闭环/体系化」这类宏大词在**整份周报**里不超过 1-2 处，主线 + bullet 标签加起来算
- [ ] 无改动 plugin 合并到 `💤 本周无改动`
- [ ] 无"影响的 skill/行为变化/一句话总结/飞书链接"收尾
- [ ] 行数落在「篇幅线性规则」的典型值附近，每个 plugin 的 bullet 数已按克制原则压到最小

## 参考产出样例

```
📣 Context Hub 本周插件改动速览（2026-04-15 ~ 2026-04-22）

📐 SDD · 验收方式统一
    • clarify 限定在 WHAT/WHY：禁 HOW 类追问，Clarifications log 章节删除并就地回填
    • tasks 精简：去掉 integrates 字段，symbols 只列符号名
    • 验收场景统一编号：Acceptance/Edge 改用 US{N}-{M} 编号，门禁按测试类合并
    • sketch 接通 implement：implement 新增对 sketch.md 的直接读取

🔧 Quality-Kit · code-reviewer 脚本修复
    • Diff 生成修复：脚本与展示字段对齐到 topic
    • 执行顺序收紧：code-reviewer 与 phab-aicr-fix 强制按 Step 顺序执行，禁止跳过

💤 本周无改动
    • java-dev-kit、utilities
```
