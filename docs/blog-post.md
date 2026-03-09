# Dify Ops Toolkit：通过数据库直连实现工作流自动化部署

Dify 是一个优秀的 LLM 应用开发平台，但在实际生产使用中，我们发现了一个问题：**工作流部署缺乏自动化 API**。

## 痛点

当需要批量部署工作流、创建 API Token 或配置环境变量时，只能通过 UI 手动操作。这导致：

- CI/CD 流程无法集成
- 多环境部署效率低
- 批量管理困难

举个例子，部署一个包含 6 个环境变量的工作流，需要在 UI 上点击至少 20 次。如果有 20 个工作流要部署，就是 400 次点击。

## 解决方案

Dify 的所有配置存储在 PostgreSQL 中。既然官方不提供 API，那就直接操作数据库。

**Dify Ops Toolkit** 是一个命令行工具，通过数据库直连实现自动化运维。

### 核心表结构

```sql
apps                        -- 应用信息
workflows                   -- 工作流定义（draft + published）
api_tokens                  -- API 令牌
workflow_draft_variables    -- 环境变量
```

### 使用方式

```bash
# 从 YAML 部署工作流
python scripts/deploy_workflow.py --yaml workflow.yml

# 预览模式
python scripts/deploy_workflow.py --yaml workflow.yml --dry-run

# 指定 Token
python scripts/deploy_workflow.py --yaml workflow.yml --token app-MyToken2024
```

### 部署流程

```
解析 YAML → 创建 App → 创建 Workflow → 添加环境变量 → 创建 Token → 发布版本
```

## 技术实现

### 安全性

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

### 连接方式

支持两种模式：

```bash
# Docker exec（自动检测容器）
python scripts/deploy_workflow.py --yaml workflow.yml

# 直接连接
export DIFY_DB_HOST=192.168.1.100
export DIFY_DB_PASSWORD=xxx
python scripts/deploy_workflow.py --yaml workflow.yml
```

## Graph 修复器

工作流导入时常遇到格式问题：

- HTTP 节点缺少 `params` 字段
- 工具节点缺少 `tool_configurations` 字段
- 模板语法 `{{#xxx#}}` 格式错误

提供了修复脚本：

```bash
python scripts/fix_graph.py --input broken.json --output fixed.json
```

输出修复报告，标注问题节点。

## 实际案例

部署一个 ArXiv 论文筛选工作流：

```yaml
app:
  name: AI-Insight-Hub

workflow:
  environment_variables:
    - name: RESEARCH_TOPICS
      value: "LLM, Agent, RAG"
    - name: PUSH_LIMIT
      value: "5"

  graph:
    nodes:
      - id: arxiv_fetch
        type: http-request
      - id: llm_filter
        type: llm
      - id: template
        type: template-transform
```

执行部署：

```bash
$ python scripts/deploy_workflow.py --yaml ai-insight-hub.yml

租户 ID: xxx-xxx-xxx
创建应用: yyy-yyy-yyy
创建工作流 (draft): zzz-zzz-zzz
添加环境变量: RESEARCH_TOPICS
添加环境变量: PUSH_LIMIT
创建 API Token: app-AIInsightHub2024
发布版本 0.0.1

部署完成!
API Token: app-AIInsightHub2024
```

测试：

```bash
curl -X POST "http://localhost/v1/workflows/run" \
  -H "Authorization: Bearer app-AIInsightHub2024" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{}}'
```

## 能力边界

| 支持 | 不支持 |
|-----|-------|
| 批量部署工作流 | 可视化编辑 |
| Token 管理 | 跨租户操作 |
| 环境变量配置 | 工作流回滚 |
| CI/CD 集成 | 实时监控 |
| Graph 格式修复 | Code 节点 self 调用自动修复 |

另外，由于直接操作数据库，依赖 Dify 内部表结构。版本升级可能导致不兼容。

建议先在测试环境验证。

## 项目结构

```
dify-ops-toolkit/
├── scripts/
│   ├── deploy_workflow.py
│   └── fix_graph.py
├── skills/
│   └── dify-ops.md          # Claude Code Skill
├── examples/
│   └── AI-Insight-Hub-Lite.yml
├── requirements.txt
└── .env.example
```

## 开源地址

https://github.com/2560925365-ux/dify-ops-toolkit

---

参考资料：
- [Dify 官方文档](https://docs.dify.ai)
- [Claude Code](https://claude.ai/code)
