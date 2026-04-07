---
name: obsidian-lint
description: >
  Obsidian Vault 健康检查工具。扫描当前工作目录下的 Obsidian vault，
  检查 frontmatter 合规性、孤页、断链、交叉引用完整性、索引覆盖率、
  raw 素材覆盖率、TODO 过期项。输出检查报告和修复建议。
  Use when the user says "vault lint", "obsidian lint", "检查 vault",
  "vault 健康检查", "wiki lint", "lint wiki", "检查知识库".
---

# Obsidian Vault Lint

对当前 vault 执行 7 项健康检查，直接在终端输出结果。

## 前置条件

- 当前工作目录是一个 Obsidian vault（包含 .obsidian/ 目录或 CLAUDE.md）
- Vault 遵循 Karpathy LLM Wiki 架构（wiki 文章 + raw/ 原始素材 + _index.md）

## 检查流程

### 第 1 步：扫描 vault 结构

1. 用 Glob 找到所有 `.md` 文件（排除 `.obsidian/`、`node_modules/`）
2. 区分三类文件：
   - **Wiki 文章**：位于具体分类目录下的 .md 文件（如 `Intelligence/`、`Research/`、`Feedback/` 等子目录中的文件）
   - **元数据页**：`_index.md`、`log.md`、`TODO.md`、`CLAUDE.md`
   - **Raw 素材**：`raw/` 目录下的文件

### 第 2 步：逐项检查

对每个检查项，读取相关文件并分析：

#### 检查 1：Frontmatter 合规

- 每个 .md 文件（除 CLAUDE.md）必须有 YAML frontmatter
- 必须包含 `tags`（至少一个）和 `date`（YYYY-MM-DD 格式）
- 输出：列出不合规的文件及缺失字段

#### 检查 2：孤页检测

- 扫描所有文件中的 `[[wikilink]]` 引用（包括 `[[name|alias]]` 格式）
- 统计每个 wiki 文章的入站链接数（被其他文件引用的次数）
- 入站链接为 0 的 wiki 文章标记为孤页
- 元数据页（_index、log、TODO）不计入孤页
- 输出：列出孤页及建议链接到的页面

#### 检查 3：断链检测

- 提取所有 `[[wikilink]]` 目标
- 检查目标文件是否存在（支持模糊匹配：不含路径、不含 .md 后缀）
- 输出：列出断链及其所在文件

#### 检查 4：相关笔记缺失

- 所有 wiki 文章（子目录下的 .md 文件）应有 `## 相关笔记` 部分
- 检查该 section 是否存在且包含至少一个 wikilink
- 输出：列出缺失的文件

#### 检查 5：_index.md 完整性

- 读取 `_index.md`，提取所有 wikilink
- 与实际 wiki 文章列表对比
- 输出：列出未被索引收录的文章

#### 检查 6：raw/ 覆盖率

- 列出 `raw/` 下的子目录和文件
- 与 wiki 文章的 `source:` frontmatter 或文内 URL 对比
- 识别没有对应 raw 素材的 wiki 文章
- 输出：列出缺少原始素材的文章及其引用的来源 URL

#### 检查 7：TODO 过期项

- 读取 `TODO.md`，提取所有未完成项 `- [ ]`
- 检查每项内容是否已有对应的 wiki 文章（通过关键词匹配）
- 输出：列出应标记为完成的项及其对应 wiki 文章

### 第 3 步：输出报告

用以下格式输出：

```
## Obsidian Vault Lint Report

### 1. Frontmatter 合规 ✓ / ⚠️
（具体问题）

### 2. 孤页检测 ✓ / ⚠️
（具体问题）

...（7 项全部列出）

---

## 总分：XX/100

## 修复建议（按优先级）

**P0 — 立即修**
- ...

**P1 — 短期**
- ...

**P2 — 中期**
- ...
```

### 评分规则

- 每项基础分值：Frontmatter 20、孤页 15、断链 20、相关笔记 15、索引 15、raw 覆盖 10、TODO 5
- 每项按问题严重程度扣分：无问题满分，有问题按比例扣减

## 注意事项

- 不修改任何文件，只读取和报告
- 用中文输出
- 报告直接输出到终端，不写入文件
- 如果某个检查项不适用（如没有 raw/ 目录或没有 TODO.md），标记为 N/A 并给满分
