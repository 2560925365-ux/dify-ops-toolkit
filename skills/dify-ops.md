---
description: 'Dify 自动化运维工具 - 通过数据库/API 管理 Dify 工作流、Token、环境变量，支持 Graph 修复和插件配置'
---

# Dify Ops - Dify 自动化运维工具

通过数据库直接操作实现 Dify 平台的自动化运维，绕过 UI 限制。

## 使用方法

```bash
/zcf:dify-ops <操作> [参数]

# 示例
/zcf:dify-ops deploy-workflow ./workflow.yml    # 部署工作流
/zcf:dify-ops create-token <app_name>           # 创建 API Token
/zcf:dify-ops fix-graph <workflow_id>           # 修复 Graph 格式
/zcf:dify-ops set-env <key> <value>             # 设置环境变量
/zcf:dify-ops list-apps                         # 列出所有应用
```

## 上下文

- 操作类型：$ARGUMENTS
- Dify 数据库：PostgreSQL
- 默认连接方式：Docker exec

## 前置条件

1. Dify 使用 PostgreSQL 数据库
2. 有数据库访问权限（Docker 或直接连接）
3. 知道数据库连接信息

## 数据库连接

```bash
# Docker 方式（推荐）
docker exec -i <postgres_container> psql -U postgres -d dify

# 直接连接
psql "postgresql://<user>:<password>@<host>:<port>/dify"
```

## 核心操作

### 1. 列出所有应用

```sql
SELECT id, name, mode, created_at FROM apps ORDER BY created_at DESC;
```

### 2. 查看工作流状态

```sql
SELECT a.name, w.id, w.version, w.type, w.created_at
FROM workflows w
JOIN apps a ON w.app_id = a.id
WHERE a.name LIKE '%关键词%'
ORDER BY w.created_at DESC;
```

### 3. 创建 API Token

```sql
-- 先获取 app_id 和 tenant_id
SELECT id, tenant_id FROM apps WHERE name = '应用名称';

-- 创建 Token
INSERT INTO api_tokens (id, app_id, tenant_id, token, type, created_at)
VALUES (
    gen_random_uuid(),
    '<app_id>',
    '<tenant_id>',
    'app-<自定义Token>',
    'app',
    NOW()
);
```

### 4. 更新工作流 Graph

```sql
-- 导出当前 Graph
SELECT graph::text FROM workflows WHERE id = '<workflow_id>';

-- 更新 Graph（需要转义）
UPDATE workflows SET graph = '<json_graph>'::jsonb WHERE id = '<workflow_id>';
```

### 5. 设置环境变量

```sql
-- 插入环境变量
INSERT INTO workflow_draft_variables (id, app_id, name, value, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    '<app_id>',
    '<变量名>',
    '<变量值>',
    NOW(),
    NOW()
);
```

### 6. 创建发布版本

```sql
INSERT INTO workflows (id, tenant_id, app_id, version, type, graph, features, environment_variables, conversation_variables, created_at, updated_at)
SELECT
    gen_random_uuid(),
    tenant_id,
    app_id,
    '0.0.1',
    'published',
    graph,
    features,
    environment_variables,
    conversation_variables,
    NOW(),
    NOW()
FROM workflows
WHERE id = '<draft_workflow_id>';
```

## Graph 修复指南

### 常见问题

1. **HTTP 节点缺少 params 字段**
   ```python
   # 修复：添加 params 字段
   node['data']['params'] = ""
   ```

2. **工具节点缺少 tool_configurations 字段**
   ```python
   # 修复：添加空配置
   node['data']['tool_configurations'] = {}
   ```

3. **模板语法错误**
   ```
   错误: {{#node.field#}}
   正确: {{ variable }}  (Jinja2 语法)
   ```

4. **Code 节点调用 self 方法**
   ```python
   # 错误：不能在 main 函数中调用 self
   query = self._build_query()

   # 正确：内联实现
   def main(...):
       query = "inline logic"
   ```

### 修复脚本模板

```python
import json

def fix_graph(input_file, output_file):
    with open(input_file, 'r') as f:
        graph = json.load(f)

    for node in graph.get('nodes', []):
        node_type = node.get('data', {}).get('type')

        # 修复 HTTP 节点
        if node_type == 'http-request':
            if 'params' not in node['data']:
                node['data']['params'] = ""

        # 修复工具节点
        if node_type == 'tool':
            if 'tool_configurations' not in node['data']:
                node['data']['tool_configurations'] = {}

    with open(output_file, 'w') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    return graph
```

## 测试工作流 API

```bash
curl -X POST "http://localhost/v1/workflows/run" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{},"response_mode":"blocking","user":"test"}'
```

## 插件凭据加密

Dify 使用 RSA+AES 混合加密：

```python
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import base64
import os

def encrypt_credential(public_key_pem: str, value: str) -> str:
    """加密插件凭据"""
    # 生成 AES 密钥
    aes_key = os.urandom(32)
    iv = os.urandom(16)

    # AES 加密数据
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    padded_value = value + (16 - len(value) % 16) * chr(16 - len(value) % 16)
    encrypted_value = encryptor.update(padded_value.encode()) + encryptor.finalize()

    # RSA 加密 AES 密钥
    public_key = serialization.load_pem_public_key(public_key_pem.encode())
    encrypted_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    # 组合格式: HYBRID:<base64_rsa_key>:<base64_iv>:<base64_encrypted_value>
    return f"HYBRID:{base64.b64encode(encrypted_key).decode()}:{base64.b64encode(iv).decode()}:{base64.b64encode(encrypted_value).decode()}"
```

## 完整部署流程

### 从 YAML 部署工作流

1. **解析 YAML 文件**
   ```python
   import yaml
   with open('workflow.yml', 'r') as f:
       config = yaml.safe_load(f)
   ```

2. **创建应用**
   ```sql
   INSERT INTO apps (id, tenant_id, name, mode, icon, icon_background)
   VALUES (gen_random_uuid(), '<tenant_id>', '<name>', 'workflow', '🤖', '#FFE7BA');
   ```

3. **创建 Draft 工作流**
   ```sql
   INSERT INTO workflows (id, tenant_id, app_id, version, type, graph, ...)
   VALUES (gen_random_uuid(), '<tenant_id>', '<app_id>', 'draft', 'workflow', '<graph_json>'::jsonb, ...);
   ```

4. **添加环境变量**
   ```sql
   INSERT INTO workflow_draft_variables (id, app_id, name, value, ...)
   VALUES (gen_random_uuid(), '<app_id>', '<name>', '<value>', ...);
   ```

5. **创建 API Token**
   ```sql
   INSERT INTO api_tokens (id, app_id, tenant_id, token, type, ...)
   VALUES (gen_random_uuid(), '<app_id>', '<tenant_id>', '<token>', 'app', ...);
   ```

6. **发布版本**
   ```sql
   INSERT INTO workflows (...) SELECT ... FROM workflows WHERE id = '<draft_id>';
   ```

## 安全注意事项

1. **Token 命名规范**：使用有意义的前缀，如 `app-ProdHub2024`
2. **数据库访问**：仅在内网环境操作
3. **备份**：修改前先备份原始 Graph
4. **测试**：先用 Lite 版本测试，确认无误后再操作完整版

## 故障排查

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `params Field required` | HTTP 节点缺少 params | 添加 `params: ""` |
| `tool_configurations Field required` | 工具节点缺少配置 | 添加 `tool_configurations: {}` |
| `features Field required` | 发布版本缺少 features | 从 draft 复制 features |
| Token 无效 | Token 不存在或类型错误 | 检查 api_tokens 表 |

## 执行任务

**当前任务**：$ARGUMENTS

正在执行 Dify 自动化操作...
