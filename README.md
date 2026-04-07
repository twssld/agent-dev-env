# agent-dev-env

个人 Claude Code marketplace，管理自定义插件和 skills。

## 安装

1. 添加 marketplace（二选一）：

在 `~/.claude/settings.json` 中添加：

```json
{
  "extraKnownMarketplaces": {
    "agent-dev-env": {
      "source": {
        "source": "github",
        "repo": "twssld/agent-dev-env"
      }
    }
  }
}
```

或通过命令：

```shell
/plugin marketplace add https://github.com/twssld/agent-dev-env.git
```

2. 安装插件：

```shell
/plugin install dev-tools@agent-dev-env
```

## 插件列表

| 插件 | 说明 |
|------|------|
| **dev-tools** | AI 报告生成、Obsidian vault 检查、Git 推送工作流、设计评审等 |
