---
name: generating-ai-usage-html-report
description: >-
  Builds a dark-themed HTML analytics report from team AI spend data: Excel（汇总数据）或组织导出 CSV（org_usage_*.csv）。费用分层按 Total；支持可选 AI_Ind；CSV 下 Total = ClaudeCode + Cursor。Use when generating or refreshing AI usage reports from .xlsx / .csv, 部门费用, CC/Cursor 合计, or org_usage exports.
---

# AI 使用分析 HTML 报表

## 何时使用

- 从 **`.xlsx`**（「汇总数据」）或 **`.csv`**（如 `org_usage_YYYY-MM-DD_*.csv`）生成**深色主题**单页 HTML。
- 用户要求**刷新数据**、**按部门**、**费用分层**、**全员明细**、**CC / Cursor 分项**时套用本流程。

## 数据源 A：Excel（汇总数据）

| 字段 | 是否必需 | 说明 |
|------|----------|------|
| `Total` | **必需** | AI 费用（数值），分层与汇总均基于此列 |
| `二级部门` | 推荐 | 缺失时合并为「未分配部门」 |
| `员工姓名` | 推荐 | 明细与计数 |
| `一级部门` / `岗位名称` | 可选 | 仅明细展示 |
| `AI_Ind` | **可选** | 无此列则**不做**任何依赖该字段的分析（见下节） |

## 数据源 B：组织导出 CSV（`org_usage_*.csv`）

首行可为元数据，例如：`时间范围,2026-04-01 ~ 2026-04-03`（脚本跳过，并写入报表副标题）。

| 导出列（示例） | 映射含义 |
|----------------|----------|
| `姓名` | 使用者姓名 → 内部统一为 `员工姓名` |
| `部门` | 使用者部门 → 内部统一为 `二级部门`（报表里表头显示「部门」） |
| `ClaudeCode ($)` 等 | **CC（Claude Code）费用** |
| `Cursor ($)` 等 | **Cursor 费用** |
| `合计 ($)` | 可与 CC+Cursor 交叉校验；**分析用 Total 一律取 CC+Cursor 相加**（与导出「合计」列若有分位舍入差属正常） |

可选列：`工号`、`邮箱`、`调用次数` — 若存在则写入全员明细。

**本数据源通常无 `AI_Ind`**：按「无 AI_Ind」规则，全员纳入分层与部门汇总。

## `AI_Ind` 存在与否（仅 Excel 常见）

**存在 `AI_Ind`：**

- 分析主体为 `AI_Ind == 1`；顶部含总人数、非必要、应使用等卡片。
- 分层与「按部门」表基于应使用人群。

**不存在 `AI_Ind`：**

- 不展示非必要 / 应使用等卡片。
- 分层与部门表基于**全表**；使用率 = `Total > 0` 人数 / 总人数。

## 费用分层（按 `Total`）

对参与分析的行逐人分层：

- `Total == 0` → 安装未使用(0)
- `0 < Total ≤ 10` → 刚上手(0.001~10)
- `10 < Total ≤ 100` → 中度使用(10~100)
- `Total > 100` → 重度使用(100+)

## 部门表（原「二级部门」逻辑）

- 维度列：Excel 用「二级部门」；组织 CSV 用「部门」（数据统一成内部 `二级部门` 字段做 groupby）。
- 按**使用率**降序；最后一行**总计**；分层条从左到右：**重度 → 中度 → 刚上手 → 未使用**（`flex-direction: row-reverse` + s0…s3）。

## 输出与样式

- 单文件 HTML，深色主题。
- 组织 CSV：明细表含 **CC 费用、Cursor 费用、合计（Total）**（及调用次数等若存在）。
- 页脚：生成时间；若有时间范围元数据则一并显示。

## 执行方式

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/generate_ai_usage_report.py \
  --input "/path/to/file.xlsx" \
  --output "/path/to/report.html"
# 或
python3 ${CLAUDE_SKILL_DIR}/scripts/generate_ai_usage_report.py \
  --input "/path/to/org_usage_2026-04-01_2026-04-03.csv" \
  --output "/path/to/report.html"
```

Excel 可加：`--sheet 汇总数据`（默认）。

按姓名筛选：`--names 张三 李四`（仅保留指定人员生成报表）。

依赖：`pandas`；Excel 另需 `openpyxl`（`pip install pandas openpyxl`）。

## 额外说明

- 姓名、部门等文本需 **HTML 转义**。
- CSV 列名可能带空格或 `($)`，脚本应对常见别名做解析（见 `${CLAUDE_SKILL_DIR}/scripts/generate_ai_usage_report.py`）。
