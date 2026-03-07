# Dify Ops Toolkit

🛠️ **通过数据库/API 自动化管理 Dify 工作流 - Claude Code Skill**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Dify](https://img.shields.io/badge/Dify-0.15+-green.svg)](https://dify.ai)

## 🎯 项目价值

Dify 官方没有提供自动化 API 来管理工作流部署。本项目通过**数据库直接操作**实现了：

- ✅ **工作流批量部署** - 从 YAML/JSON 批量导入
- ✅ **API Token 自动管理** - 无需 UI 创建
- ✅ **Graph 格式修复** - 自动修复常见格式问题
- ✅ **环境变量批量配置** - 一键配置多个变量
- ✅ **插件凭据加密** - RSA+AES 混合加密支持

## 📦 包含内容

```
dify-ops-toolkit/
├── skills/
│   └── dify-ops.md          # Claude Code Skill 文件
├── scripts/
│   ├── deploy_workflow.py   # 工作流部署脚本
│   ├── create_token.py      # Token 创建脚本
│   ├── fix_graph.py         # Graph 修复脚本
│   └── encrypt_credential.py # 凭据加密脚本
├── examples/
│   ├── ai-insight-hub.yml   # 示例工作流
│   └── env-config.json      # 环境变量配置示例
└── docs/
    └── database-schema.md   # 数据库结构说明
```

## 🚀 快速开始

### 1. 安装 Claude Code Skill

```bash
# 复制 skill 到 Claude Code 配置目录
cp skills/dify-ops.md ~/.claude/commands/zcf/
```

### 2. 使用 Skill

```bash
# 在 Claude Code 中
/zcf:dify-ops list-apps
/zcf:dify-ops deploy-workflow ./examples/ai-insight-hub.yml
/zcf:dify-ops create-token "My App"
```

### 3. 直接使用脚本

```bash
# 部署工作流
python scripts/deploy_workflow.py --yaml examples/ai-insight-hub.yml

# 创建 Token
python scripts/create_token.py --app "AI-Insight-Hub" --token "app-MyToken2024"

# 修复 Graph
python scripts/fix_graph.py --input broken.json --output fixed.json
```

## 📊 数据库操作速查

### 查看所有应用

```sql
SELECT id, name, mode, created_at FROM apps ORDER BY created_at DESC;
```

### 查看工作流版本

```sql
SELECT a.name, w.id, w.version, w.type
FROM workflows w JOIN apps a ON w.app_id = a.id
WHERE a.name LIKE '%Hub%';
```

### 创建 API Token

```sql
INSERT INTO api_tokens (id, app_id, tenant_id, token, type, created_at)
VALUES (
    gen_random_uuid(),
    '<app_id>',
    '<tenant_id>',
    'app-YourToken',
    'app',
    NOW()
);
```

## 🔧 常见问题修复

| 错误 | 原因 | 解决方案 |
|-----|------|---------|
| `params Field required` | HTTP 节点缺少 params | 添加 `"params": ""` |
| `tool_configurations Field required` | 工具节点缺少配置 | 添加 `"tool_configurations": {}` |
| Token 无效 | Token 不存在 | 检查 api_tokens 表 |

## 🏆 案例展示

### AI Insight Hub

使用本工具包部署的 ArXiv 论文推送工作流：

- 📥 从 ArXiv 抓取最新 AI 论文
- 🤖 使用 Ernie-4.5 智能筛选
- 📊 生成 Markdown 报告

测试 API：`app-AqtTKul1I6xoNlPjRvvlahTA`

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

MIT License

## 🙏 致谢

- [Dify](https://dify.ai) - 强大的 LLM 应用开发平台
- [PaperFlow](https://github.com/LiaoYFBH/PaperFlow) - 论文推送灵感来源
