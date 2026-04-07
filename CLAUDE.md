# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 Claude Code marketplace 仓库，用于管理个人的 Claude Code 插件和 skills。通过在 `~/.claude/settings.json` 的 `extraKnownMarketplaces` 中注册此仓库，可以在 Claude Code 中安装和使用其中的插件。

## 架构

```
.claude-plugin/marketplace.json   # marketplace 注册表，列出所有可安装的 plugin
plugins/<plugin-name>/            # 每个 plugin 一个目录
  .claude-plugin/plugin.json      # plugin 元数据
  skills/<skill-name>/SKILL.md    # skill 定义
  commands/                       # slash commands（可选）
  agents/                         # subagent 定义（可选）
  hooks/hooks.json                # event hooks（可选）
```

## 添加新 plugin

1. 在 `plugins/` 下创建新目录，包含 `.claude-plugin/plugin.json`
2. 在 `.claude-plugin/marketplace.json` 的 `plugins` 数组中注册

## 添加新 skill

在对应 plugin 的 `skills/<skill-name>/` 目录下创建 `SKILL.md`，使用 YAML frontmatter 定义 `name` 和 `description`。

## 外部引用

marketplace.json 支持通过 `source` 字段引用外部 git 仓库的 plugin，无需将代码复制到本仓库：

```json
{
  "name": "example",
  "description": "...",
  "source": {
    "source": "url",
    "url": "https://github.com/user/repo.git"
  }
}
```
