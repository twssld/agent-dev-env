---
name: context-hub-digest
description: >
  Generate a concise FYI digest of plugin changes in the context-hub
  repository only, formatted as an emoji-categorized single-line bullet list
  suitable for group-chat broadcast. Plugin list is dynamically enumerated
  from origin/master under plugins/. Default window is the past 7 days;
  user can override with phrases like "过去两周"/"最近 3 天"/"上个月"/
  "2026-04-01 到今天". Output is Chinese.
  Use when the user says "context-hub 周报",
  "context-hub 插件周报", "context-hub 本周改动", "context-hub 改动速览",
  "context-hub 过去两周/最近 N 天改动", or pastes the context-hub path and
  asks for a summary.
repo: /Users/taowei/code/context-hub
target_root: plugins
---

# Context Hub 插件周报速览

生成面向技术团队群聊的**插件改动速览**，风格：emoji 分类 + 单行 bullet + 极简。仅用于 `context-hub` 仓库。

## 范围
- 仓库：`/Users/taowei/code/context-hub`，目标 `plugins/` 下所有子目录
- **数据源锁定**：全程只看 `origin/master`（git log / git diff / `git show origin/master:<path>`）。**不 Read 本地文件**，不用 `--all`，不用裸 `git log`，不用 `ls plugins/`——本地工作区、feature 分支、未追踪目录都可能与 origin 不一致
- 时间窗口：`$ARGUMENTS` 里解析时间短语为 `SINCE`/`END`（`YYYY-MM-DD`），默认 "过去 7 天"（`SINCE=今天-7d, END=今天-1d`，例：今天 29 号 → 22 ~ 28）。**`END` 始终 ≤ 今天-1d**；标题/招呼里的时段词与窗口一致；解析不明先追问

## 调研步骤

### Step 1：同步远端、枚举 plugin、锁定时间窗口

```bash
cd /Users/taowei/code/context-hub && git fetch origin master

# 从 origin/master tree 枚举所有 plugin（本地未推送的目录会被自动排除）
git ls-tree -d --name-only origin/master plugins/ | sed 's|^plugins/||'

# 按解析出的 SINCE / END，拉 origin/master 上本窗口内的 commit 列表
git log origin/master --since="$SINCE" --until="$END 23:59:59" \
  --pretty=format:"%h %ad %s" --date=short -- plugins/
```

如需对单个 commit 做身份交叉验证：`git branch -r --contains <hash> | grep -x '  origin/master'`，空输出 → 丢弃。

### Step 2：为每个"有改动"的 plugin 生成聚合 diff

**核心原则：以 plugin 为维度汇总整个窗口的代码改动，不依赖单个 commit message 做总结。**

```bash
# 窗口起点之前的最后一次 origin/master 提交，作为 BASE
BASE=$(git rev-list -1 --before="$SINCE 00:00:00" origin/master)
# 窗口终点那一刻 origin/master 上的最后一次提交，作为 HEAD
HEAD=$(git rev-list -1 --before="$END 23:59:59" origin/master)

# 该 plugin 在整个窗口内的"最终净变化"
git diff --stat "$BASE" "$HEAD" -- plugins/<name>
git diff "$BASE" "$HEAD" -- plugins/<name>
```

若 `--stat` 为空 → 该 plugin 本周无改动，直接归入 `💤`。

### Step 3：并行派发 subagent 做 plugin 级分析

对"有改动"的 plugin，**同一条消息里并行发出多个 Agent 调用**（每个 plugin 一个 subagent）：

- 每个 subagent 只看**自己那一个 plugin** 的 `--stat` 和 `diff`，**不看 commit message**
- 基于**代码实际改动**提炼 2-4 条主线，每条要能回答"改的是哪个字段/文件/行为"
- 输出固定结构：

  ```
  ## <plugin 名>
  emoji: <📐/🔧/✨/🧩 等，按本周改动的整体语义选>

  主题 1
  - 维度标签: <抽象名词短语>
  - 描述: <≤50 中文字，含 skill 名 + 关键字段/文件/行为>
  - 证据文件: <列 1-3 个最代表性的文件路径>

  主题 2
  ...
  ```

- Subagent prompt 中需复述本 SKILL 的 **Bullet 规则 + 红线 + 克制原则**，防止自由发挥

### Step 4：主 agent 合成最终周报

收集各 subagent 结果 → 按「输出骨架」拼装 → 过「自检清单」核对 → 未改动 plugin 合并到 `💤` 节。

### 克制原则

选择规则枚举、文案修订、文档同步、枚举值扩展等次级项一律砍掉。问自己：**这条信息对群聊读者的价值，是否值得占掉一条 bullet？** 否 → 删。（后续所有"克制原则"均指此条。）

## 输出骨架

```
📣 Context Hub <标题标签>插件改动速览（YYYY-MM-DD ~ YYYY-MM-DD）

Hi 各位，<打招呼句，根据时间范围替换> 👇

<emoji> <插件名>
    • <维度标签>：<一句话描述>
    • <维度标签>：<一句话描述>
    • <维度标签>：<一句话描述>
    • <维度标签>：<一句话描述>   ← 可选第 4 条

<emoji> <第二个插件>
    • <维度标签>：<一句话描述>
    • <维度标签>：<一句话描述>

💤 本周无改动
    • <插件名>、<插件名>
```

## 各部位规则

### 顶部（标题 + 打招呼）

群聊消息，不是技术文档。顶部固定两行，时段词按解析出的窗口自然替换：

```
📣 Context Hub <时段词>插件改动速览（YYYY-MM-DD ~ YYYY-MM-DD）

Hi 各位，<时段词> context-hub 这边的主要变动如下 👇
```

示例：默认 → "本周"；14 天 → "近两周"；其他按"近 N 天 / 上月 / MM-DD 至 MM-DD"口语化处理。

### 插件排序规则

**优先 plugin（有改动必须按此顺序排在最前）**：

```
sdd → fe-sdd → quality-kit → java-dev-kit → test-kit → devops-workflow
```

- 名单里有改动的按上述顺序排在最前，无改动的自动跳过
- 其余有改动 plugin 按"改动量 / 主线重要性"由大到小排，平级按字母序

### sdd 特权

sdd 是 context-hub 里最核心的 plugin，需要深入分析，**不设 bullet 数上限**——有多少值得讲的主线就写多少。克制原则仍然适用，但不为了压缩 bullet 数而合并掉真正独立的主线。

### Emoji 选择池（按语义选，**同份周报内不重复**）

每类多个变体，按 plugin 改动的具体语义选最贴切的一个；整份周报里每个 emoji 最多出现一次，两个 plugin 语义相近时改用同类不同变体。

| 语义 | 可选 emoji |
|---|---|
| 规范收敛 / 标准化 | 📐 📏 🧭 🎯 |
| 稳定性修复 / 小补丁 | 🔧 🛠 🩹 🧯 |
| 新能力扩展 | ✨ 🚀 🌱 🎁 🧪 |
| 治理 / 目录重组 / 拆分 | 🧹 🗂 🏗 |
| 迁出 / 独立化 / 打包 | 🧩 📦 🛫 |
| 度量 / 观察 / 统计 | 📊 📈 🔍 |
| 文档 / 模板类变动 | 📝 📄 📚 |
| 自动化 / 流程接通 | 🤖 ⚙️ 🔁 |

### Bullet 格式
- `    • ` 开头（4 空格 + Unicode 中点 `•`），**不用 markdown `-`**
- 数量 **2-4 条**（sdd 不设上限，见上），不硬凑
- 固定结构：`<维度标签>：<一句话>`
- 每条 ≤ 50 中文字

### Bullet 维度标签

标签是一个短标题，概括这条 bullet 讲的"哪一块变了"。要求：

**1. 自然短语，不是动作描述也不是实现细节**
- ✅「clarify 不再讨论 HOW」「tasks 精简」「Diff 生成修复」「执行顺序收紧」
- ❌「移除 integrates 字段」（动作描述）/「diff 改走 pathspec」（实现细节）

**2. 按内容自然长度，不要刻意对齐也不要硬压缩**

最容易出"AI 味"的地方。不要把一组标签凑成整齐的四字/六字短语——人写周报不会那样。长度跟着内容走，该几个字就几个字，参差正常。

- ❌ AI 味：「验收编号贯通」「门禁模型重塑」「阶段职责收敛」「轻量路径接通」（整齐四字）
- ✅ 参差：「验收场景统一编号」「tasks 精简」「clarify 限定在 WHAT/WHY」「sketch 接通 implement」

**另一种反面**：为了短而造非词、砍正常词的字，比刻意对齐更伤语感。

- ❌ 硬压缩：「clarify 限在 WHAT/WHY」（"限"不独立作动词）、「自动判模」（"判模"非词）
- ✅ 自然：「clarify 限定在 WHAT/WHY」「自动判断运行模式」

**判断法**：标签朗读出来像章节标题 → AI 味；像对话里会说的一句话 → 没问题。

### Bullet 描述（红线）

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

读者是周会观众，不是 git 用户手册读者。"diff 更准了"的事实就够了。

#### 🔴 红线 3：同功能域必须合并
判断："这些变化对下游呈现为同一个接口变化吗？" 是 → 合并。

典型：code-reviewer 的 diff 生成修复 + `agent → topic` 字段对齐 + 脚本更新 → 全部属于"结果产出链路"一个功能域，**必须合并到一条 bullet**，不要把字段对齐拆到"执行流程加固"。

#### 🔴 红线 4：只写"本周新增的变化"，不写既有能力
读者默认已经知道每个 skill 本来能做什么。bullet 只能描述**这周 diff 里真实发生的增量动作**（新增、删除、改名、迁移、约束变化），**不要**把"既有设计"当成本周变化写。

自检法：把描述里的动词抠出来 →"支持/接受/可以/允许"之类静态能力描述 → 高度警惕，大概率是在讲既有功能。应该换成**本周发生的动作**：新增、移除、迁出、改为、统一到、合并、拆分、下线、接通、替换。

- ❌ 既有能力：「implement 接受 sketch.md 作为 tasks.md 的替代入口」（implement 本来就是执行入口）
- ❌ 反推不出动作：「小改动写 sketch.md 即可，不必展开 tasks.md」（sketch 本来就是给小改动用的）
- ✅ 增量动作：「sketch 接通 implement：implement 新增对 sketch.md 的兼容」
- ✅ 增量动作：「feishu-doc 迁出：feishu-doc skill 与 lark-mcp 配置迁出为独立 plugin」

#### 🔴 红线 5：去 AI 味——宏大动词克制

「重塑 / 重构 / 贯通 / 收敛 / 治理 / 闭环 / 体系化 / 标准化」——这类词本身没错，但 bullet 里**扎堆出现就显假**。一份周报里最多出现 1-2 次，其余用**具体动词**：新增、删除、改为、迁出、合并、统一到、接通。

自检法：把周报读一遍，如果像技术公众号标题 → AI 味过重，重写。

- ❌ AI 味：「验收体系重构」「评审闭环修复」「门禁模型重塑」
- ✅ 自然：「验收方式统一」「code-reviewer 脚本修复」「tasks 模板精简」

#### 🔴 红线 6：禁"对读者无感"的打包/发行/镜像类变化

对最终使用者行为**没有感知差异**的改动，不占 bullet：

- ❌ 「双发行：同步提供 Claude 与 Cursor 两套 mcp 清单」
- ❌ 「同步调整 .claude-plugin 与 .cursor-plugin 元数据」
- ❌ 「README 与 plugin.json 描述对齐」
- ❌ 「文件路径重命名但对外接口不变」

自检法：问"读者明天用这个 plugin 会注意到什么不一样？"答"没啥" → 删。

迁出 / 合并 / 拆分类变化**只写一条最顶层的事实**即可（例："从 utilities 迁出为独立 plugin"），不追加"同步更新 mcp 清单"这种镜像细节。

### 允许出现的证据
- skill 名（`clarify`、`tasks`）
- 关键字段名（`integrates`、`topic`、`agent`）
- 关键文件名（`sketch.md`、`tasks.md`）
- 脚本名（作为整体代称，不展开 git 语法）

### 💤 无改动

标题里的时段词与顶部保持一致（"本周 / 近两周 / 近 N 天 / 本月 / 上月 / 窗口内"）。

```
💤 <时段词>无改动或轻微调整
    • 无改动：<插件名>、<插件名>
    • 轻微调整：<插件名>（一句话说明）
```

### 末尾
以 `💤` 小节作为整篇收尾（若所有 plugin 都有改动则省略）。

**不写**"一句话总结"/"行为变化提醒"/"影响的 skill 清单"/飞书文档链接。

### 全局禁项
- ❌ commit hash、commit 标题原文翻译
- ❌ 函数名、git 内部术语、命令行参数、正则
- ❌ `▎` 收尾行、`---` 分隔线、`**一句话总结**`、飞书文档链接
- ❌ 次级增强项（按克制原则）
- ❌ 超过 50 字的 bullet、空心描述

### 篇幅（按 plugin 数量线性计算）

全文行数 = 2（标题+空行）+ 每个有改动 plugin 约 (bullet 数 + 2) 行 + 💤 节 2 行。

| 有改动 plugin 数 | 预期行数（含 💤） |
|---|---|
| 1 | ~8 行 |
| 2 | ~14 行 |
| 3 | ~17 行 |
| 4 | ~22 行 |
| 5+ | 每多一个 +(bullet 数+2) 行 |

**目标仍是极简**：每个 plugin 的 bullet 数宁少勿多（按克制原则砍次级）。如果某 plugin 只能凑出 1 条像样的 bullet，考虑改为"轻微动态"一句话带过或合并到 💤 后加「+ 轻微调整」。

## 自检清单（主 agent 易漏项，逐条核对）

- [ ] Plugin 列表通过 `git ls-tree origin/master plugins/` 从 git tree 枚举（不是 `ls plugins/`）
- [ ] 时间窗口按 `$ARGUMENTS` 解析（默认过去 7 天；`END` ≤ 今天-1d），标题/打招呼时段词与 `SINCE~END` 一致
- [ ] 主线判断基于**聚合 diff 的实际代码改动**，不依赖 commit message
- [ ] 多个 plugin 的分析通过**并行 subagent** 处理（同一条消息里多个 Agent 调用）
- [ ] **优先 plugin 顺序正确**：`sdd → fe-sdd → quality-kit → java-dev-kit → test-kit → devops-workflow` 中有改动的已按此顺序排在最前
- [ ] **每个 emoji 在整份周报里最多出现一次**，语义相近的已改用同类不同变体
- [ ] **维度标签字数参差**，不是整齐的四字/六字排比
- [ ] 「重塑/重构/贯通/收敛/治理/闭环/体系化」在整份周报里不超过 1-2 处
- [ ] 字段对齐/展示变更已并入其所属功能域 bullet（红线 3）
- [ ] 无"对读者无感"的打包/发行/镜像细节（红线 6）
