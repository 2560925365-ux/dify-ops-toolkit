#!/usr/bin/env python3
"""
Dify Workflow Deployer - 从 YAML 部署工作流到 Dify 数据库

特性：
- 参数化查询防止 SQL 注入
- 支持 Docker 和直接连接两种模式
- 完整的异常处理和日志记录
- 类型注解支持
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generator, Optional

import yaml

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None  # type: ignore

# ============================================================================
# 日志配置
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class DifyConfig:
    """Dify 数据库配置"""
    host: str = "localhost"
    port: int = 5432
    database: str = "dify"
    user: str = "postgres"
    password: str = ""
    docker_container: Optional[str] = None

    @classmethod
    def from_env(cls) -> "DifyConfig":
        """从环境变量加载配置"""
        return cls(
            host=os.getenv("DIFY_DB_HOST", "localhost"),
            port=int(os.getenv("DIFY_DB_PORT", "5432")),
            database=os.getenv("DIFY_DB_NAME", "dify"),
            user=os.getenv("DIFY_DB_USER", "postgres"),
            password=os.getenv("DIFY_DB_PASSWORD", ""),
            docker_container=os.getenv("DIFY_DOCKER_CONTAINER"),
        )


@dataclass
class WorkflowConfig:
    """工作流配置"""
    app_name: str
    graph: dict[str, Any]
    env_vars: dict[str, str]
    icon: str = "🤖"
    icon_bg: str = "#FFE7BA"
    description: str = ""

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "WorkflowConfig":
        """从 YAML 文件加载配置"""
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 支持 Dify 导出格式
        if "workflow" in data:
            # Dify DSL 格式
            app_config = data.get("app", {})
            workflow = data.get("workflow", {})
            env_vars = {
                v["name"]: v.get("value", "")
                for v in workflow.get("environment_variables", [])
            }
            return cls(
                app_name=app_config.get("name", "New Workflow"),
                graph=workflow.get("graph", {}),
                env_vars=env_vars,
                icon=app_config.get("icon", "🤖"),
                icon_bg=app_config.get("icon_background", "#FFE7BA"),
                description=app_config.get("description", ""),
            )
        else:
            # 简化格式
            app_config = data.get("app", {})
            return cls(
                app_name=app_config.get("name", "New Workflow"),
                graph=data.get("graph", {}),
                env_vars=data.get("environment_variables", {}),
                icon=app_config.get("icon", "🤖"),
                icon_bg=app_config.get("icon_background", "#FFE7BA"),
            )


# ============================================================================
# 数据库连接管理
# ============================================================================

class DatabaseConnection:
    """数据库连接管理器，支持 Docker 和直接连接"""

    def __init__(self, config: DifyConfig):
        self.config = config
        self._conn = None
        self._use_docker = bool(config.docker_container) or self._auto_detect_docker()

    def _auto_detect_docker(self) -> bool:
        """自动检测 Docker 容器"""
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10
            )
            containers = result.stdout.strip().split("\n")
            for c in containers:
                if "postgres" in c.lower():
                    self.config.docker_container = c
                    logger.info(f"自动检测到 Docker 容器: {c}")
                    return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    @contextmanager
    def get_cursor(self) -> Generator[Any, None, None]:
        """获取数据库游标（上下文管理器）"""
        if self._use_docker:
            yield self._docker_cursor()
        else:
            yield self._direct_cursor()

    def _direct_cursor(self) -> Any:
        """直接连接模式"""
        if psycopg2 is None:
            raise ImportError("请安装 psycopg2: pip install psycopg2-binary")

        self._conn = psycopg2.connect(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password,
        )
        return self._conn.cursor(cursor_factory=RealDictCursor)

    def _docker_cursor(self) -> Any:
        """Docker exec 模式（返回模拟游标）"""
        return DockerExecCursor(self.config.docker_container)

    def close(self) -> None:
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None


class DockerExecCursor:
    """Docker exec 模式的模拟游标"""

    def __init__(self, container: Optional[str]):
        self.container = container
        self._last_result: list[dict] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """执行 SQL（使用参数化）"""
        if params:
            # 安全地格式化参数
            formatted_sql = self._format_sql(sql, params)
        else:
            formatted_sql = sql

        cmd = [
            "docker", "exec", "-i", self.container,
            "psql", "-U", "postgres", "-d", "dify",
            "-t", "-A", "-c", formatted_sql
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            raise RuntimeError(f"SQL 执行失败: {result.stderr}")

        self._last_result = self._parse_result(result.stdout)

    def _format_sql(self, sql: str, params: tuple) -> str:
        """安全格式化 SQL 参数"""
        formatted_params = []
        for p in params:
            if p is None:
                formatted_params.append("NULL")
            elif isinstance(p, bool):
                formatted_params.append("TRUE" if p else "FALSE")
            elif isinstance(p, (int, float)):
                formatted_params.append(str(p))
            elif isinstance(p, dict):
                # JSON 类型
                escaped = json.dumps(p, ensure_ascii=False).replace("'", "''")
                formatted_params.append(f"'{escaped}'::jsonb")
            else:
                # 字符串类型 - 转义单引号
                escaped = str(p).replace("'", "''")
                formatted_params.append(f"'{escaped}'")

        return sql % tuple(formatted_params)

    def _parse_result(self, output: str) -> list[dict]:
        """解析 psql 输出"""
        # 简单解析，返回第一列值
        lines = [l.strip() for l in output.strip().split("\n") if l.strip()]
        return [{"value": line} for line in lines]

    def fetchone(self) -> Optional[dict]:
        """获取单行结果"""
        return self._last_result[0] if self._last_result else None

    def fetchall(self) -> list[dict]:
        """获取所有结果"""
        return self._last_result


# ============================================================================
# 部署操作类
# ============================================================================

class WorkflowDeployer:
    """工作流部署器"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get_tenant_id(self) -> str:
        """获取默认租户 ID"""
        with self.db.get_cursor() as cur:
            cur.execute("SELECT id FROM tenants LIMIT 1;")
            result = cur.fetchone()
            if not result:
                raise RuntimeError("找不到租户，请确保 Dify 已正确初始化")
            tenant_id = result["value"] if isinstance(result, dict) and "value" in result else result[0]
            logger.info(f"租户 ID: {tenant_id}")
            return tenant_id

    def create_app(
        self,
        name: str,
        tenant_id: str,
        icon: str = "🤖",
        icon_bg: str = "#FFE7BA"
    ) -> str:
        """创建应用并返回 app_id（参数化查询）"""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO apps (id, tenant_id, name, mode, icon, icon_background, created_at, updated_at)
                VALUES (gen_random_uuid(), %s, %s, 'workflow', %s, %s, NOW(), NOW())
                RETURNING id;
                """,
                (tenant_id, name, icon, icon_bg)
            )
            result = cur.fetchone()
            app_id = result["value"] if isinstance(result, dict) and "value" in result else result[0]
            logger.info(f"创建应用: {app_id}")
            return app_id

    def create_workflow(
        self,
        app_id: str,
        tenant_id: str,
        graph: dict[str, Any]
    ) -> str:
        """创建 draft 工作流（参数化查询）"""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflows (
                    id, tenant_id, app_id, version, type, graph,
                    features, environment_variables, conversation_variables,
                    created_at, updated_at
                )
                VALUES (
                    gen_random_uuid(), %s, %s, 'draft', 'workflow',
                    %s,
                    '{"file_upload": {}}'::jsonb,
                    '{}'::jsonb,
                    '{}'::jsonb,
                    NOW(), NOW()
                )
                RETURNING id;
                """,
                (tenant_id, app_id, graph)  # graph 作为 JSON 参数
            )
            result = cur.fetchone()
            workflow_id = result["value"] if isinstance(result, dict) and "value" in result else result[0]
            logger.info(f"创建工作流 (draft): {workflow_id}")
            return workflow_id

    def add_environment_variable(
        self,
        app_id: str,
        name: str,
        value: str
    ) -> None:
        """添加环境变量（参数化查询）"""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflow_draft_variables (id, app_id, name, value, created_at, updated_at)
                VALUES (gen_random_uuid(), %s, %s, %s, NOW(), NOW())
                ON CONFLICT (app_id, name) DO UPDATE SET value = %s, updated_at = NOW();
                """,
                (app_id, name, value, value)
            )
            logger.info(f"添加环境变量: {name}")

    def create_api_token(
        self,
        app_id: str,
        tenant_id: str,
        token: str
    ) -> None:
        """创建 API Token（参数化查询）"""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_tokens (id, app_id, tenant_id, token, type, created_at)
                VALUES (gen_random_uuid(), %s, %s, %s, 'app', NOW());
                """,
                (app_id, tenant_id, token)
            )
            logger.info(f"创建 API Token: {token}")

    def publish_workflow(self, draft_id: str) -> None:
        """发布工作流版本 0.0.1（参数化查询）"""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflows (
                    id, tenant_id, app_id, version, type, graph,
                    features, environment_variables, conversation_variables,
                    created_at, updated_at
                )
                SELECT
                    gen_random_uuid(), tenant_id, app_id, '0.0.1', 'published',
                    graph, features, environment_variables, conversation_variables,
                    NOW(), NOW()
                FROM workflows WHERE id = %s;
                """,
                (draft_id,)
            )
            logger.info("发布版本 0.0.1")

    def deploy(
        self,
        config: WorkflowConfig,
        token: Optional[str] = None
    ) -> dict[str, str]:
        """完整部署流程"""
        logger.info(f"开始部署工作流: {config.app_name}")

        # 获取租户 ID
        tenant_id = self.get_tenant_id()

        # 创建应用
        app_id = self.create_app(
            name=config.app_name,
            tenant_id=tenant_id,
            icon=config.icon,
            icon_bg=config.icon_bg
        )

        # 创建工作流
        workflow_id = self.create_workflow(
            app_id=app_id,
            tenant_id=tenant_id,
            graph=config.graph
        )

        # 添加环境变量
        for name, value in config.env_vars.items():
            self.add_environment_variable(app_id, name, value)

        # 创建 API Token
        final_token = token or f"app-{config.app_name.replace('-', '').replace(' ', '')}2024"
        self.create_api_token(app_id, tenant_id, final_token)

        # 发布版本
        self.publish_workflow(workflow_id)

        logger.info("部署完成!")

        return {
            "app_id": app_id,
            "workflow_id": workflow_id,
            "token": final_token,
        }


# ============================================================================
# CLI 入口
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="部署 Dify 工作流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --yaml workflow.yml
  %(prog)s --yaml workflow.yml --token app-MyToken2024
  %(prog)s --yaml workflow.yml --dry-run
        """
    )
    parser.add_argument(
        "--yaml", "-f",
        required=True,
        help="YAML 配置文件路径"
    )
    parser.add_argument(
        "--token", "-t",
        help="自定义 API Token"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅显示将执行的操作，不实际执行"
    )
    parser.add_argument(
        "--docker-container",
        help="指定 Docker 容器名称"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 加载工作流配置
    try:
        config = WorkflowConfig.from_yaml(args.yaml)
    except FileNotFoundError:
        logger.error(f"找不到文件: {args.yaml}")
        return 1
    except yaml.YAMLError as e:
        logger.error(f"YAML 解析错误: {e}")
        return 1

    # Dry run 模式
    if args.dry_run:
        print("\n📋 Dry Run 模式 - 将执行以下操作:")
        print(f"  • 创建应用: {config.app_name}")
        print(f"  • Graph 节点数: {len(config.graph.get('nodes', []))}")
        print(f"  • Graph 边数: {len(config.graph.get('edges', []))}")
        print(f"  • 环境变量: {list(config.env_vars.keys())}")
        default_token = f"app-{config.app_name.replace('-', '').replace(' ', '')}2024"
        print(f"  • Token: {args.token or default_token}")
        return 0

    # 加载数据库配置
    db_config = DifyConfig.from_env()
    if args.docker_container:
        db_config.docker_container = args.docker_container

    # 执行部署
    try:
        db = DatabaseConnection(db_config)
        deployer = WorkflowDeployer(db)
        result = deployer.deploy(config, args.token)

        print("\n" + "=" * 60)
        print("🚀 部署成功!")
        print("=" * 60)
        print(f"  应用 ID:    {result['app_id']}")
        print(f"  工作流 ID:  {result['workflow_id']}")
        print(f"  API Token:  {result['token']}")
        print()
        print("测试命令:")
        print(f"  curl -X POST 'http://localhost/v1/workflows/run' \\")
        print(f"    -H 'Authorization: Bearer {result['token']}' \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"inputs\":{{}}}}'")
        print("=" * 60)

        return 0

    except RuntimeError as e:
        logger.error(f"部署失败: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("用户取消操作")
        return 130


if __name__ == "__main__":
    sys.exit(main())
