# Dify Ops Toolkit

通过数据库直连实现 Dify 工作流自动化部署

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Dify](https://img.shields.io/badge/Dify-0.15+-green.svg)](https://dify.ai)

## 项目价值

### 问题背景

Dify 是一个优秀的 LLM 应用开发平台，但在工作流部署方面存在 API 缺口：

- **Service API**：只能**调用**已部署的应用，不能**部署**应用
- **Console API**：存在 `/console/api/apps/import` 端点，但未公开文档化，且需要 Console 认证
- **社区需求**：多次请求 DevOps 友好的部署 API（[GitHub Discussion #9007](https://github.com/langgenius/dify/discussions/9007)）

### 为什么选择数据库直连

| 方案 | 优点 | 缺点 |
|-----|------|------|
| Console API | 官方实现 | 未文档化、需要 Console 认证、可能随版本变化 |
| 数据库直连 | 稳定、可控、无需额外认证 | 依赖表结构 |

### 核心能力

- 工作流批量部署 - 从 YAML/JSON 批量导入
- API Token 自动管理 - 无需 UI 创建
- Graph 格式修复 - 自动修复常见格式问题
- 环境变量批量配置 - 一键配置多个变量

## 项目结构

```
dify-ops-toolkit/
├── scripts/
│   ├── deploy_workflow.py   # 工作流部署脚本
│   └── fix_graph.py         # Graph 修复脚本
├── skills/
│   └── dify-ops.md          # Claude Code Skill
├── examples/
│   └── AI-Insight-Hub-Lite.yml
├── docs/
│   ├── blog-post.md         # 技术博客
│   └── database-schema.md   # 数据库结构说明
├── requirements.txt
└── .env.example
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入数据库连接信息
```

### 部署工作流

```bash
# 从 YAML 部署
python scripts/deploy_workflow.py --yaml examples/AI-Insight-Hub-Lite.yml

# 预览模式（不实际执行）
python scripts/deploy_workflow.py --yaml workflow.yml --dry-run

# 指定自定义 Token
python scripts/deploy_workflow.py --yaml workflow.yml --token app-MyToken2024
```

### 修复 Graph 格式

```bash
python scripts/fix_graph.py --input broken.json --output fixed.json
```

## 部署流程

```
解析 YAML → 创建 App → 创建 Workflow → 添加环境变量 → 创建 Token → 发布版本
```

## 核心表结构

```sql
apps                        -- 应用信息
workflows                   -- 工作流定义（draft + published）
api_tokens                  -- API 令牌
workflow_draft_variables    -- 环境变量
```

## 安全性

所有 SQL 使用参数化查询，避免注入攻击：

```python
cur.execute(
    """
    INSERT INTO apps (id, tenant_id, name, mode, created_at, updated_at)
    VALUES (gen_random_uuid(), %s, %s, 'workflow', NOW(), NOW())
    RETURNING id;
    """,
    (tenant_id, name)
)
```

## 连接方式

支持两种模式：

```bash
# Docker exec（自动检测容器）
python scripts/deploy_workflow.py --yaml workflow.yml

# 直接连接
export DIFY_DB_HOST=192.168.1.100
export DIFY_DB_PASSWORD=xxx
python scripts/deploy_workflow.py --yaml workflow.yml
```

## 能力边界

| 支持 | 不支持 |
|-----|-------|
| 批量部署工作流 | 可视化编辑 |
| Token 管理 | 跨租户操作 |
| 环境变量配置 | 工作流回滚 |
| CI/CD 集成 | 实时监控 |
| Graph 格式修复 | Code 节点 self 调用自动修复 |

由于直接操作数据库，依赖 Dify 内部表结构。版本升级可能导致不兼容，建议先在测试环境验证。

## 常见问题修复

| 错误 | 原因 | 解决方案 |
|-----|------|---------|
| `params Field required` | HTTP 节点缺少 params | 添加 `"params": ""` |
| `tool_configurations Field required` | 工具节点缺少配置 | 添加 `"tool_configurations": {}` |
| Token 无效 | Token 不存在 | 检查 api_tokens 表 |

## 案例：AI Insight Hub

使用本工具包部署的 ArXiv 论文推送工作流：

```yaml
app:
  name: AI-Insight-Hub

workflow:
  environment_variables:
    - name: RESEARCH_TOPICS
      value: "LLM, Agent, RAG"
    - name: PUSH_LIMIT
      value: "5"
```

部署后可直接调用：

```bash
curl -X POST "http://localhost/v1/workflows/run" \
  -H "Authorization: Bearer app-YourToken" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{}}'
```

## 贡献

欢迎提交 Issue 和 Pull Request！

## License

MIT License

## 致谢

- [Dify](https://dify.ai) - 强大的 LLM 应用开发平台
