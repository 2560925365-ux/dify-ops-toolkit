#!/usr/bin/env python3
"""
Dify Workflow Deployer - 从 YAML 部署工作流到 Dify 数据库
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import yaml


def get_docker_postgres_container():
    """获取 Dify PostgreSQL 容器名"""
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    containers = result.stdout.strip().split("\n")
    for c in containers:
        if "postgres" in c.lower():
            return c
    return None


def execute_sql(sql: str, container: str = None) -> str:
    """执行 SQL 语句"""
    if container is None:
        container = get_docker_postgres_container()
        if not container:
            raise RuntimeError("找不到 PostgreSQL 容器")

    result = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", "dify", "-t", "-c", sql],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def get_tenant_id() -> str:
    """获取默认租户 ID"""
    result = execute_sql("SELECT id FROM tenants LIMIT 1;")
    return result.strip()


def create_app(name: str, tenant_id: str, icon: str = "🤖", icon_bg: str = "#FFE7BA") -> str:
    """创建应用并返回 app_id"""
    app_id = execute_sql(f"""
        INSERT INTO apps (id, tenant_id, name, mode, icon, icon_background, created_at, updated_at)
        VALUES (gen_random_uuid(), '{tenant_id}', '{name}', 'workflow', '{icon}', '{icon_bg}', NOW(), NOW())
        RETURNING id;
    """)
    return app_id.strip()


def create_workflow(app_id: str, tenant_id: str, graph: dict) -> str:
    """创建 draft 工作流"""
    graph_json = json.dumps(graph, ensure_ascii=False).replace("'", "''")
    workflow_id = execute_sql(f"""
        INSERT INTO workflows (
            id, tenant_id, app_id, version, type, graph,
            features, environment_variables, conversation_variables,
            created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), '{tenant_id}', '{app_id}', 'draft', 'workflow',
            '{graph_json}'::jsonb,
            '{{"file_upload": {{}}}}'::jsonb,
            '{{}}'::jsonb,
            '{{}}'::jsonb,
            NOW(), NOW()
        )
        RETURNING id;
    """)
    return workflow_id.strip()


def add_environment_variable(app_id: str, name: str, value: str):
    """添加环境变量"""
    execute_sql(f"""
        INSERT INTO workflow_draft_variables (id, app_id, name, value, created_at, updated_at)
        VALUES (gen_random_uuid(), '{app_id}', '{name}', '{value}', NOW(), NOW())
        ON CONFLICT (app_id, name) DO UPDATE SET value = '{value}', updated_at = NOW();
    """)


def create_api_token(app_id: str, tenant_id: str, token: str):
    """创建 API Token"""
    execute_sql(f"""
        INSERT INTO api_tokens (id, app_id, tenant_id, token, type, created_at)
        VALUES (gen_random_uuid(), '{app_id}', '{tenant_id}', '{token}', 'app', NOW());
    """)


def publish_workflow(draft_id: str):
    """发布工作流版本 0.0.1"""
    execute_sql(f"""
        INSERT INTO workflows (
            id, tenant_id, app_id, version, type, graph,
            features, environment_variables, conversation_variables,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(), tenant_id, app_id, '0.0.1', 'published',
            graph, features, environment_variables, conversation_variables,
            NOW(), NOW()
        FROM workflows WHERE id = '{draft_id}';
    """)


def load_yaml_config(yaml_path: str) -> dict:
    """加载 YAML 配置"""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="部署 Dify 工作流")
    parser.add_argument("--yaml", required=True, help="YAML 配置文件路径")
    parser.add_argument("--token", help="自定义 API Token")
    parser.add_argument("--dry-run", action="store_true", help="仅显示将执行的操作")
    args = parser.parse_args()

    # 加载配置
    config = load_yaml_config(args.yaml)

    app_name = config.get("app", {}).get("name", "New Workflow")
    graph = config.get("graph", {})
    env_vars = config.get("environment_variables", {})

    if args.dry_run:
        print(f"[Dry Run] 将创建应用: {app_name}")
        print(f"[Dry Run] Graph 节点数: {len(graph.get('nodes', []))}")
        print(f"[Dry Run] 环境变量: {list(env_vars.keys())}")
        return

    # 获取租户 ID
    tenant_id = get_tenant_id()
    print(f"✓ 租户 ID: {tenant_id}")

    # 创建应用
    app_id = create_app(app_name, tenant_id)
    print(f"✓ 创建应用: {app_id}")

    # 创建工作流
    workflow_id = create_workflow(app_id, tenant_id, graph)
    print(f"✓ 创建工作流 (draft): {workflow_id}")

    # 添加环境变量
    for name, value in env_vars.items():
        add_environment_variable(app_id, name, value)
        print(f"✓ 添加环境变量: {name}")

    # 创建 API Token
    token = args.token or f"app-{app_name.replace('-', '')}2024"
    create_api_token(app_id, tenant_id, token)
    print(f"✓ 创建 API Token: {token}")

    # 发布版本
    publish_workflow(workflow_id)
    print(f"✓ 发布版本 0.0.1")

    print(f"\n🚀 部署完成!")
    print(f"   API Token: {token}")
    print(f"   测试命令: curl -X POST 'http://localhost/v1/workflows/run' -H 'Authorization: Bearer {token}' -H 'Content-Type: application/json' -d '{{\"inputs\":{{}}}}'")


if __name__ == "__main__":
    main()
