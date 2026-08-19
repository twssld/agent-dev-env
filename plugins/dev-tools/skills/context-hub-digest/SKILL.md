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
- **Plugin 黑名单**：枚举后直接剔除，不分析、不汇总、不进 💤。完整名单见 Step 1 的 `BLACKLIST` 正则

## 调研步骤

### Step 1：同步远端、枚举 plugin、锁定时间窗口

```bash
cd /Users/taowei/code/context-hub && git fetch origin master

# 从 origin/master tree 枚举所有 plugin（本地未推送的目录会被自动排除）
# 并剔除黑名单
BLACKLIST='^(atticus-chat|cn-backend-workflow|data-security|docx-operator|emr-serverless-spark-workflow|fe-b-react-dev-kit|fe-b-vue2-dev-kit|fe-b-vue3-dev-kit|fe-c-dev-kit|fe-d2c|fe-plugin-report|fe-sdd|fe-workflow|indo-backend-workflow|internal-office|jar-inspect|model-market|oa-flow-submitter|pm-profile|project-plugin-check|rnd-workflow|risk-etl-tools|sea-backend-workflow|sea-risk|smartcall-kit|test-kit|wecom-doc-general|wecom-meeting-report)$'
git ls-tree -d --name-only origin/master plugins/ | sed 's|^plugins/||' | grep -Ev "$BLACKLIST"

# 按解析出的 SINCE / END，拉 origin/master 上本窗口内的 commit 列表
git log origin/master --since="$SINCE" --until="$END 23:59:59" \
  --pretty=format:"%h %ad %s" --date=short -- plugins/
```

**黑名单处理**：枚举结果里的黑名单 plugin 直接丢弃；后续 Step 2/3 不为它们生成 diff、不派 subagent、💤 节也不列出它们——整份周报完全不提及。

如需对单个 commit 做身份交叉验证：`git branch -r --contains <hash> | grep -x '  origin/master'`，空输出 → 丢弃。

### Step 2：为每个"有改动"的 plugin 生成聚合 diff

**核心原则：以 plugin 为维度汇总整个窗口的代码改动，不依赖单个 commit message 做总结。**（此原则防的是"照抄单条 commit 标题当总结"。）

**WHAT 看 diff，WHY 看 MR 正文——分清事实层与重点层：**

- **事实层（WHAT，到底改没改、改成什么样）以 diff 为准**。这是"以代码为准"的真正含义——防的是 MR summary 过时（作者改了代码却没更新描述）而吹牛或漏说。
- **重点层（WHY，这次改动的主线/初衷是什么）以 MR 正文为准**。diff 只能告诉你哪些行变了，**提炼不出重点**；一组变化服务于什么目标、哪个是主线、哪个是附带动作，只有作者写在 MR 正文里的初衷说得清。**不要从机械 diff 里硬凑主线**——那正是把附带动作（如某个枚举值被删）误当主线的根源。
- **冲突时**：MR 正文说了某改动但 diff 里查无此事 → 信 diff（summary 过时，不写）；diff 里有改动但 MR 正文没提 → 作为补充事实核实清楚，但**不擅自升格为主线**，除非它本身就是一条独立的用户可感价值。

> 反面实例（真实教训）：某次 sketch 的测试层从 `UT|API|UI/E2E` 收成 `UT|API|E2E`，diff 里"删掉 UI"很显眼，于是被当成主线写「测试层砍掉 UI」。但 MR 正文的初衷是"不同模型对是否写 API/E2E 不稳定，**加强 sketch 测试层约束**"——砍 UI 只是收紧口径的附带动作。**diff 给了 WHAT，MR 正文才给了 WHY**；只看 diff 必然抓错重点。

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

### Step 2.5：拉全每个 plugin 的 MR 正文（硬步骤，主线来源）

MR 正文是作者写的**初衷说明**，是重点层（WHY）的来源。**这一步不是可选辅助**——每个有改动的 plugin，都必须先把窗口内动过它的所有 MR 正文拉全，再喂给对应 subagent，否则 subagent 只能从 diff 硬凑、必然抓错重点。

**① 列出窗口内所有 merge commit（拿到 MR 编号）：**

```bash
git log origin/master --merges --since="$SINCE" --until="$END 23:59:59" \
  --pretty=format:"%h|%ad|%s|%b" --date=short
```

**② 把每个 plugin 的改动追到具体 MR（commit → MR 映射）：**

merge commit 本身不改文件，直接按路径过滤 `--merges` 追不到。正确做法是先找出窗口内**直接改了该 plugin 文件的非 merge commit**，再把每个 commit 映射到包含它的那个 merge：

```bash
# 该 plugin 窗口内的非 merge commit
git log origin/master --no-merges --since="$SINCE" --until="$END 23:59:59" \
  --pretty=format:"%h %s" -- plugins/<name>

# 每个 commit <c> 属于哪个 MR（取第一个 merge，其 body 含 "See merge request ai/context-hub!<iid>"）
git log origin/master --merges --ancestry-path <c>..origin/master \
  --pretty=format:"%h %s%n  %b" --reverse | head -3
```

**③ 按编号拉全 MR 正文（含初衷、主要改动说明）：**

```bash
glab mr view <iid>
```

- **拉正文时读的是 `glab mr view` 的 description，不是 merge commit 的一行标题**。标题只够定位，初衷全在正文里。
- **搭便车 commit**：某 plugin 的改动若合在别的主题分支/MR 里（例：某脚手架改动搭在另一个 SSO 文档 MR 里合入），没有属于自己的 MR 正文 → 回退纯 diff 分析，据 diff 实际改动老实描述，不硬套那个无关 MR 的初衷。
- 正文 bullet **不出现 MR 编号**
- MR 一览（编号/合入时间/作者/summary 要点）仅在用户明确要求时作为附录输出，不进群聊正文

### Step 3：并行派发 subagent 做 plugin 级分析

对"有改动"的 plugin，**同一条消息里并行发出多个 Agent 调用**（每个 plugin 一个 subagent）：

- 每个 subagent 拿到**自己那一个 plugin** 的两份输入：`--stat`+`diff`（事实层 WHAT），以及 Step 2.5 拉全的该 plugin **MR 正文**（重点层 WHY）。**主线来自 MR 正文的初衷，diff 用来核实事实和补细节**——按 Step 2 的 WHAT/WHY 分层办
- 提炼 2-4 条主线，每条要能回答"改的是哪个字段/文件/行为"，且主线是 MR 正文点明的目标，不是 diff 里最显眼的机械改动
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

收集各 subagent 结果 → **按价值主题二次合并（红线 3）、逐条二次过克制原则** → 按「输出骨架」拼装 → 过「自检清单」核对 → 未改动 plugin 合并到 `💤` 节。subagent 给的条目不是照单全收：读者无感的删，同一价值主题的合并。

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
sdd → quality-kit → java-dev-kit → devops-workflow
```

- 名单里有改动的按上述顺序排在最前，无改动的自动跳过
- 其余有改动 plugin 按"改动量 / 主线重要性"由大到小排，平级按字母序

### sdd 特权

sdd 是 context-hub 里最核心的 plugin，分析要最深入（全量 diff + 窗口内全部相关 MR summary），bullet 上限放宽到 **3-5 条**（其他 plugin 2-4 条）。深入是指分析深入，不是条数多——同样要按价值主题合并；但也不为了压缩条数而合并掉真正独立的主线。

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
- 数量 **2-4 条**（sdd 3-5 条，见上），不硬凑
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

**3. 口语也有下限**

像群聊吐槽而不是周报的标签不行。标签是自然的**书面短语**，介于章节标题和聊天口水话之间，且尽量点出主体（skill 名或功能域名词）。

- ❌ 口水话：「界面还要比设计稿」「删页残链清理方式变了」「不许虚报通过」
- ✅ 书面短语：「设计稿还原度检测」「断连场景防误报」「repair 改为按层路由」

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

合并还有更高一层判断：**同一价值主题**——多个变化服务于同一个大机制/目标时，合并为一条，配套调整不单列。例：verify 新增 + implement-loop 新增 + 跨 Phase 门禁编排调整，都属于"交付验证流水线"一个主题，门禁编排作为流水线的一环并入，不单占 bullet。又如：plan 模板瘦身 + specify 澄清收紧，同属"产物质量"，视条数压力可合并。

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

#### 🔴 红线 7：写意义，不写编排机制

描述优先回答"这对使用 plugin 的人意味着什么"，而不是内部编排怎么动。尤其是合并后的大主题：描述 = 共同意义 + 1-2 个最有感知的具体动作；调度/编排细节不进正文。

- ❌ 机制：「新增 verify 与 implement-loop，跨 Phase 门禁合并编排」
- ✅ 意义：「新增 verify 与 implement-loop，实现完由独立视角验证、循环修复后再交付」

注意与红线 1 的平衡：写意义不等于写空话，仍要落到具体的 skill 名/文件/行为上。

#### 🔴 红线 8：禁内部校验/安全/门禁机制当用户价值

dry-run 试跑、二次确认、清单预览、权限/时效校验、幂等补齐这类**内部门禁与安全机制**，对读者是"看不见的底层保障"，默认不占 bullet。只有当它**直接改变了用户的操作步骤**（例：以前一步完成、现在必须先确认再执行）时才值得一提，且并进它所服务的功能主题，不单列。

自检法：问"这条讲的是这个功能**能干什么**，还是它**内部怎么自我保护**？"是后者 → 删或并入。

- ❌ 内部机制：「落库前都要 dry-run 真跑验证」「批量操作加二次确认护栏」「逾期罚息改为幂等补齐」
- ✅ 用户价值：「新增三个运维 harness：建 agent、写告警 SOP、管巡检」（验证/确认机制不单写）

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
- ❌ commit hash、MR/PR 编号（`!96` 这类）、commit 标题原文翻译
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

- [ ] Plugin 列表通过 `git ls-tree origin/master plugins/` 从 git tree 枚举（不是 `ls plugins/`），并已用黑名单过滤
- [ ] 黑名单 plugin 在整份周报里完全未出现（不分析、不进 💤、不被提及）
- [ ] 时间窗口按 `$ARGUMENTS` 解析（默认过去 7 天；`END` ≤ 今天-1d），标题/打招呼时段词与 `SINCE~END` 一致
- [ ] **每个有改动 plugin 的 MR 正文已用 `glab mr view` 拉全**（不是只看 merge commit 标题），并作为对应 subagent 的输入
- [ ] **主线（WHY）来自 MR 正文的初衷，事实（WHAT）以 diff 为准**；没把 diff 里最显眼的机械改动（如删枚举值）误当主线；搭便车、无独立 MR 正文的改动已回退纯 diff 分析
- [ ] 多个 plugin 的分析通过**并行 subagent** 处理（同一条消息里多个 Agent 调用）
- [ ] 合成时已按**价值主题**二次合并、逐条二次过克制原则，读者无感的条目已删
- [ ] 正文 bullet 无 MR/PR 编号；MR 一览仅在用户要求时作附录
- [ ] **优先 plugin 顺序正确**：`sdd → quality-kit → java-dev-kit → devops-workflow` 中有改动的已按此顺序排在最前
- [ ] **每个 emoji 在整份周报里最多出现一次**，语义相近的已改用同类不同变体
- [ ] **维度标签字数参差**，不是整齐的四字/六字排比，也没有群聊吐槽式口语标签
- [ ] 「重塑/重构/贯通/收敛/治理/闭环/体系化」在整份周报里不超过 1-2 处
- [ ] 字段对齐/展示变更已并入其所属功能域 bullet（红线 3）
- [ ] 无"对读者无感"的打包/发行/镜像细节（红线 6）
- [ ] 无 dry-run/二次确认/权限校验等内部门禁机制被当用户价值单列（红线 8）
