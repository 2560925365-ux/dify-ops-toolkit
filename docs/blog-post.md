# 我在 Dify 上搭建了 20 个工作流后，终于忍不住写了一套自动化运维工具

> 作者：某不知名 AI 工程师
> 发布时间：2026-03-09
> 阅读时长：约 8 分钟

---

## 起因：一个深夜的崩溃

凌晨两点，我盯着屏幕上的 Dify 控制台，第 17 次执行同样的操作：

1. 点击「创建应用」
2. 选择「工作流」
3. 导入 YAML 文件
4. 配置环境变量（6 个，逐个填写）
5. 创建 API Token
6. 点击「发布」

一套流程下来，5 分钟没了。而我要部署 20 个工作流。

「这玩意儿没有 API 吗？」我打开 Dify 文档，搜索 "workflow api"、"deploy automation"、"batch import"...

结果：**没有**。

Dify 官方确实提供了工作流调用的 API，但**工作流本身的部署和管理，只能通过 UI 手动操作**。

那一刻，我决定自己动手。

---

## 思路：绕过 UI，直连数据库

作为一个有尊严的程序员，我不会去写 Selenium 脚本模拟点击（虽然我确实考虑过）。

我想到的是：**Dify 的所有数据都存在 PostgreSQL 里，为什么不直接操作数据库？**

于是我开始研究 Dify 的数据库结构：

```sql
-- 核心表结构
apps                        -- 应用信息
├── workflows               -- 工作流定义（draft + published）
├── api_tokens              -- API 令牌
└── workflow_draft_variables -- 环境变量
```

这套结构搞清楚后，一切都变得简单了。

---

## 实现：Dify Ops Toolkit

我用一个周末写了一套命令行工具：**Dify Ops Toolkit**。

### 核心功能

```bash
# 一键部署工作流
python scripts/deploy_workflow.py --yaml workflow.yml

# 预览模式（先看看会做什么）
python scripts/deploy_workflow.py --yaml workflow.yml --dry-run

# 自定义 Token
python scripts/deploy_workflow.py --yaml workflow.yml --token app-MyToken2024
```

一套命令，完成原来 5 分钟的操作。

### 部署流程

```
YAML 解析 → 创建 App → 创建 Workflow → 添加环境变量 → 创建 Token → 发布版本
```

底层全是参数化 SQL，安全可靠：

```python
cur.execute(
    """
    INSERT INTO apps (id, tenant_id, name, mode, icon, icon_background, created_at, updated_at)
    VALUES (gen_random_uuid(), %s, %s, 'workflow', %s, %s, NOW(), NOW())
    RETURNING id;
    """,
    (tenant_id, name, icon, icon_bg)  # 参数化查询，防 SQL 注入
)
```

---

## 附带收获：Graph 修复器

在折腾过程中，我还发现了一个坑：

Dify 工作流的 Graph（节点图）有很多格式要求，比如：
- HTTP 节点必须有 `params` 字段（即使是空的）
- 工具节点必须有 `tool_configurations` 字段
- 模板语法 `{{#xxx#}}` 和 `{{ xxx }}` 是不同的

这些错误报出来很模糊，调试起来非常痛苦。

于是我又写了一个 **Graph 修复器**：

```bash
python scripts/fix_graph.py --input broken.json --output fixed.json
```

输出详细的修复报告：

```
📊 修复报告
============================================================
  总修复数: 5
  警告数:   1

  http_params: 2 项
    - [arxiv_fetch] 添加缺失的 params 字段
    - [http_request_1] 添加缺失的 params 字段

  template_syntax: 2 项
    - [template] 修复模板语法
    - [template_2] 修复模板语法

  code_self_call: 1 项
    - [config] ⚠️ 包含 self 调用，需要手动修复: self._build_query(
============================================================
```

---

## 实战案例：AI Insight Hub

我用这套工具部署了一个 **ArXiv 论文推送工作流**：

```yaml
app:
  name: AI-Insight-Hub
  icon: 🤖

workflow:
  environment_variables:
    - name: RESEARCH_TOPICS
      value: "LLM, Agent, RAG"
    - name: PUSH_LIMIT
      value: "5"
    - name: ARXIV_CATEGORIES
      value: "cs.CL, cs.AI"

  graph:
    nodes:
      - id: start
        type: start
      - id: arxiv_fetch
        type: http-request
      - id: llm_filter
        type: llm
      - id: template
        type: template-transform
      - id: end
        type: end
```

一键部署：

```bash
python scripts/deploy_workflow.py --yaml ai-insight-hub.yml

🚀 部署成功!
============================================================
  应用 ID:    550e8400-e29b-41d4-a716-446655440000
  工作流 ID:  6ba7b810-9dad-11d1-80b4-00c04fd430c8
  API Token:  app-AIInsightHub2024
============================================================
```

测试一下：

```bash
curl -X POST "http://localhost/v1/workflows/run" \
  -H "Authorization: Bearer app-AIInsightHub2024" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{}}'
```

返回：

```json
{
  "status": "succeeded",
  "outputs": {
    "report": "# 🤖 AI Insight Hub 测试报告\n> 2026-03-09 | 抓取 20 篇，筛选 3 篇\n\n## 📄 精选论文\n\n### [1] Attention Is Still All You Need\n**评分**: 9/10\n..."
  }
}
```

完美运行。

---

## 进阶：Claude Code 集成

如果你也是 Claude Code 用户，可以直接安装 Skill：

```bash
cp skills/dify-ops.md ~/.claude/commands/zcf/
```

然后在 Claude Code 里直接用：

```
/zcf:dify-ops list-apps
/zcf:dify-ops deploy-workflow ./workflow.yml
/zcf:dify-ops create-token "My App"
```

不用记命令，直接跟 AI 说就行。

---

## 技术细节

### 安全性

- **参数化查询**：所有 SQL 都使用 `%s` 占位符，防止注入攻击
- **环境变量隔离**：敏感配置通过 `.env` 文件管理
- **Git 忽略**：自动忽略 `.env` 和敏感文件

### 支持的连接方式

```bash
# 方式 1：Docker exec（自动检测）
python scripts/deploy_workflow.py --yaml workflow.yml

# 方式 2：指定容器
python scripts/deploy_workflow.py --yaml workflow.yml --docker-container dify-postgres

# 方式 3：直接连接（通过环境变量）
export DIFY_DB_HOST=192.168.1.100
export DIFY_DB_PASSWORD=xxx
python scripts/deploy_workflow.py --yaml workflow.yml
```

### 项目结构

```
dify-ops-toolkit/
├── scripts/
│   ├── deploy_workflow.py   # 部署脚本
│   └── fix_graph.py         # Graph 修复
├── skills/
│   └── dify-ops.md          # Claude Code Skill
├── examples/
│   ├── AI-Insight-Hub-Lite.yml
│   └── env-config.json
├── requirements.txt
└── .env.example
```

---

## 能力边界

说实话，这套工具有它的局限性：

| 能做 | 不能做 |
|-----|-------|
| ✅ 批量部署工作流 | ❌ 可视化编辑 |
| ✅ 创建/管理 Token | ❌ 跨租户操作 |
| ✅ 环境变量批量配置 | ❌ 工作流回滚 |
| ✅ CI/CD 集成 | ❌ 实时监控 |
| ✅ Graph 格式修复 | ❌ Code 节点 self 调用自动修复 |

另外，因为直接操作数据库，**依赖 Dify 内部表结构**。如果 Dify 版本更新导致表结构变化，可能需要适配。

建议：**先在测试环境验证，再操作生产环境**。

---

## 开源地址

🔗 **GitHub**: https://github.com/2560925365-ux/dify-ops-toolkit

欢迎 Star、提 Issue、贡献代码！

---

## 写在最后

其实我写这套工具的初衷很简单：**程序员的时间很贵，不应该浪费在重复劳动上**。

Dify 是一个很棒的低代码平台，但它在自动化运维方面确实有欠缺。希望官方未来能提供正式的 API。在此之前，这套工具应该能帮到有同样需求的朋友。

如果你也在用 Dify 做项目，欢迎交流！

---

**相关资源**：
- [Dify 官方文档](https://docs.dify.ai)
- [Claude Code](https://claude.ai/code)
- [项目 GitHub](https://github.com/2560925365-ux/dify-ops-toolkit)
