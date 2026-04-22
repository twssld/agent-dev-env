---
name: context-hub-digest
description: >
  Generate a concise weekly FYI digest of plugin changes in the context-hub
  repository only, formatted as an emoji-categorized single-line bullet list
  suitable for group-chat broadcast. Scoped strictly to the four plugins under
  /Users/taowei/code/context-hub (java-dev-kit, quality-kit, sdd, utilities)
  over the past 7 days. Output is Chinese and 14 lines or fewer.
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

## 调研步骤
1. `cd /Users/taowei/code/context-hub && git log --since=... --name-status -- <4 个目录>` 拉取窗口内的 commits。
2. 对口语化/疑似笔误的 commit message，用 `git show <hash>` 看真实 diff 再下结论。
3. 按 **plugin → 主题维度** 提炼 2-4 个主线改动，同功能域合并。
4. 应用「克制原则」：选择规则枚举、文案修订、文档同步、枚举值扩展等次级项一律砍掉。

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
必须是**抽象名词短语**：
- ✅「需求阶段克制」「任务模型精简」「Diff 生成链路修复」「执行流程加固」
- ❌「移除 integrates 字段」（动作描述）/「diff 改走 pathspec」（实现细节）

### Bullet 描述（三条红线）

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

### 篇幅
全文整体 ≤ **14 行**（含空行、含标题）

## 自检清单（输出前逐条核对）

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
- [ ] 无改动 plugin 合并到 `💤 本周无改动`
- [ ] 无"影响的 skill/行为变化/一句话总结/飞书链接"收尾
- [ ] 全文 ≤ 14 行

## 参考产出样例

```
📣 Context Hub 本周插件改动速览（2026-04-15 ~ 2026-04-22）

📐 SDD · 验收驱动的任务模型收敛
    • 需求阶段克制：clarify 禁 HOW 提问，Clarifications log 章节删除并就地回填
    • 任务模型精简：tasks 去掉 integrates 字段，symbols 只列符号名，task 描述自包含
    • 验收方法标准化：Acceptance/Edge 统一 US{N}-{M} 编号，门禁按测试类合并为一条 checkbox
    • 轻量路径扩展：implement 支持 sketch.md 作为 tasks.md 的替代入口

🔧 Quality-Kit · code-reviewer 结果产出链路修复
    • Diff 生成链路修复：脚本与展示字段对齐到 topic
    • 执行流程加固：code-reviewer 与 phab-aicr-fix 强制按 Step 顺序执行，禁止跳过

💤 本周无改动
    • java-dev-kit、utilities
```
