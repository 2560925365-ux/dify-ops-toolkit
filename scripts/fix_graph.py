#!/usr/bin/env python3
"""
Dify Graph Fixer - 修复工作流 Graph 常见格式问题

特性：
- 支持多种模板语法修复
- 完整的类型注解
- 详细的修复报告
- 可选择性地执行特定修复
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

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

class FixType(Enum):
    """修复类型枚举"""
    HTTP_PARAMS = "http_params"
    TOOL_CONFIG = "tool_config"
    TEMPLATE_SYNTAX = "template_syntax"
    CODE_SELF_CALL = "code_self_call"
    VARIABLE_REFERENCE = "variable_reference"
    NODE_ID_DUPLICATE = "node_id_duplicate"


@dataclass
class FixReport:
    """修复报告"""
    fix_type: FixType
    node_id: str
    description: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None


@dataclass
class FixResult:
    """修复结果"""
    graph: dict[str, Any]
    reports: list[FixReport] = field(default_factory=list)

    @property
    def fix_count(self) -> int:
        return len(self.reports)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.reports if "警告" in r.description or "⚠️" in r.description)


# ============================================================================
# 修复器类
# ============================================================================

class GraphFixer:
    """Graph 修复器"""

    # 模板语法模式 - 支持多种变体
    TEMPLATE_PATTERNS = [
        # {{#xxx#}} -> {{ xxx }}
        (r'\{\{#([^#]+)#\}\}', r'{{ \1 }}'),
        # {{#xxx.yyy#}} -> {{ xxx.yyy }}
        (r'\{\{#([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)#\}\}', r'{{ \1 }}'),
        # {{xxx}} (无空格) -> {{ xxx }}
        (r'\{\{([^#\{\}]+)\}\}(?!\s)', r'{{ \1 }}'),
    ]

    # 变量引用模式
    VARIABLE_REF_PATTERNS = [
        # {{#node.field#}} (Dify 旧语法) -> {{ node.field }}
        (r'\{\{#([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)#\}\}', r'{{ \1 }}'),
        # {{#171xxxxx.field#}} (带 ID 的引用) -> 需要特殊处理
        (r'\{\{#([a-f0-9\-]+\.[a-zA-Z_][a-zA-Z0-9_]*)#\}\}', r'{{ \1 }}'),
    ]

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def fix_all(self, graph: dict[str, Any]) -> FixResult:
        """执行所有修复"""
        result = FixResult(graph=graph)

        # 执行各项修复
        self._fix_http_nodes(result)
        self._fix_tool_nodes(result)
        self._fix_template_syntax(result)
        self._fix_code_self_calls(result)
        self._fix_variable_references(result)
        self._check_duplicate_ids(result)

        return result

    def fix_specific(self, graph: dict[str, Any], fix_type: FixType) -> FixResult:
        """执行特定类型的修复"""
        result = FixResult(graph=graph)

        if fix_type == FixType.HTTP_PARAMS:
            self._fix_http_nodes(result)
        elif fix_type == FixType.TOOL_CONFIG:
            self._fix_tool_nodes(result)
        elif fix_type == FixType.TEMPLATE_SYNTAX:
            self._fix_template_syntax(result)
        elif fix_type == FixType.CODE_SELF_CALL:
            self._fix_code_self_calls(result)
        elif fix_type == FixType.VARIABLE_REFERENCE:
            self._fix_variable_references(result)
        elif fix_type == FixType.NODE_ID_DUPLICATE:
            self._check_duplicate_ids(result)

        return result

    def _fix_http_nodes(self, result: FixResult) -> None:
        """修复 HTTP 节点 - 添加 params 字段"""
        for node in result.graph.get("nodes", []):
            node_type = node.get("data", {}).get("type")
            if node_type == "http-request":
                if "params" not in node.get("data", {}):
                    node["data"]["params"] = ""
                    result.reports.append(FixReport(
                        fix_type=FixType.HTTP_PARAMS,
                        node_id=node.get("id", "unknown"),
                        description="添加缺失的 params 字段",
                        old_value=None,
                        new_value=""
                    ))
                    logger.info(f"  ✓ HTTP 节点 [{node.get('id')}]: 添加 params 字段")

    def _fix_tool_nodes(self, result: FixResult) -> None:
        """修复工具节点 - 添加 tool_configurations 字段"""
        for node in result.graph.get("nodes", []):
            node_type = node.get("data", {}).get("type")
            if node_type == "tool":
                if "tool_configurations" not in node.get("data", {}):
                    node["data"]["tool_configurations"] = {}
                    result.reports.append(FixReport(
                        fix_type=FixType.TOOL_CONFIG,
                        node_id=node.get("id", "unknown"),
                        description="添加缺失的 tool_configurations 字段",
                        old_value=None,
                        new_value="{}"
                    ))
                    logger.info(f"  ✓ 工具节点 [{node.get('id')}]: 添加 tool_configurations 字段")

    def _fix_template_syntax(self, result: FixResult) -> None:
        """修复模板语法 - 支持多种模式"""
        for node in result.graph.get("nodes", []):
            node_type = node.get("data", {}).get("type")
            if node_type == "template-transform":
                template = node.get("data", {}).get("template", "")
                if not template:
                    continue

                original = template
                fixed = template

                # 应用所有模板修复模式
                for pattern, replacement in self.TEMPLATE_PATTERNS:
                    new_fixed = re.sub(pattern, replacement, fixed)
                    if new_fixed != fixed:
                        fixed = new_fixed

                if fixed != original:
                    node["data"]["template"] = fixed
                    result.reports.append(FixReport(
                        fix_type=FixType.TEMPLATE_SYNTAX,
                        node_id=node.get("id", "unknown"),
                        description="修复模板语法",
                        old_value=original[:100] + "..." if len(original) > 100 else original,
                        new_value=fixed[:100] + "..." if len(fixed) > 100 else fixed
                    ))
                    logger.info(f"  ✓ 模板节点 [{node.get('id')}]: 修复模板语法")

    def _fix_code_self_calls(self, result: FixResult) -> None:
        """检查 Code 节点中的 self 调用（需要手动修复）"""
        for node in result.graph.get("nodes", []):
            node_type = node.get("data", {}).get("type")
            if node_type == "code":
                code = node.get("data", {}).get("code", "")
                if "self." in code:
                    # 找出所有 self 调用
                    self_calls = re.findall(r'self\._?[a-zA-Z_][a-zA-Z0-9_]*\(', code)
                    result.reports.append(FixReport(
                        fix_type=FixType.CODE_SELF_CALL,
                        node_id=node.get("id", "unknown"),
                        description=f"⚠️ 包含 self 调用，需要手动修复: {', '.join(set(self_calls))}",
                        old_value=None,
                        new_value=None
                    ))
                    logger.warning(f"  ⚠️ 代码节点 [{node.get('id')}]: 包含 self 调用，需手动修复")

    def _fix_variable_references(self, result: FixResult) -> None:
        """修复变量引用语法"""
        for node in result.graph.get("nodes", []):
            data = node.get("data", {})

            # 检查 variables 字段
            for var in data.get("variables", []):
                selector = var.get("value_selector", [])
                if selector:
                    # 检查是否使用了旧语法
                    pass  # 新语法已经使用数组形式，无需修复

            # 检查模板中的变量引用
            for key in ["prompt_template", "template"]:
                content = data.get(key, "")
                if isinstance(content, str):
                    for pattern, replacement in self.VARIABLE_REF_PATTERNS:
                        if re.search(pattern, content):
                            result.reports.append(FixReport(
                                fix_type=FixType.VARIABLE_REFERENCE,
                                node_id=node.get("id", "unknown"),
                                description=f"发现旧版变量引用语法，建议更新",
                                old_value=content[:50],
                                new_value=None
                            ))

    def _check_duplicate_ids(self, result: FixResult) -> None:
        """检查重复的节点 ID"""
        node_ids = []
        for node in result.graph.get("nodes", []):
            node_id = node.get("id")
            if node_id:
                if node_id in node_ids:
                    result.reports.append(FixReport(
                        fix_type=FixType.NODE_ID_DUPLICATE,
                        node_id=node_id,
                        description=f"⚠️ 发现重复的节点 ID",
                        old_value=None,
                        new_value=None
                    ))
                    logger.warning(f"  ⚠️ 重复节点 ID: {node_id}")
                else:
                    node_ids.append(node_id)


# ============================================================================
# CLI 入口
# ============================================================================

def print_summary(result: FixResult) -> None:
    """打印修复摘要"""
    print("\n" + "=" * 60)
    print("📊 修复报告")
    print("=" * 60)
    print(f"  总修复数: {result.fix_count}")
    print(f"  警告数:   {result.warning_count}")
    print()

    # 按类型分组
    by_type: dict[FixType, list[FixReport]] = {}
    for report in result.reports:
        if report.fix_type not in by_type:
            by_type[report.fix_type] = []
        by_type[report.fix_type].append(report)

    for fix_type, reports in by_type.items():
        print(f"  {fix_type.value}: {len(reports)} 项")
        for r in reports[:3]:  # 只显示前3个
            print(f"    - [{r.node_id}] {r.description}")
        if len(reports) > 3:
            print(f"    ... 还有 {len(reports) - 3} 项")

    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="修复 Dify Graph 格式问题",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --input graph.json --output fixed.json
  %(prog)s --input graph.json --output fixed.json --fix http_params
  %(prog)s --input graph.json --output fixed.json --verbose
        """
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入 JSON 文件路径"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="输出 JSON 文件路径"
    )
    parser.add_argument(
        "--fix",
        choices=["all", "http_params", "tool_config", "template_syntax", "code_self_call"],
        default="all",
        help="选择修复类型 (默认: all)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 读取输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"找不到输入文件: {args.input}")
        return 1

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            graph = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析错误: {e}")
        return 1

    # 打印输入信息
    print(f"\n📄 输入文件: {args.input}")
    print(f"   节点数: {len(graph.get('nodes', []))}")
    print(f"   边数: {len(graph.get('edges', []))}")
    print()

    # 执行修复
    fixer = GraphFixer(verbose=args.verbose)

    if args.fix == "all":
        result = fixer.fix_all(graph)
    elif args.fix == "http_params":
        result = fixer.fix_specific(graph, FixType.HTTP_PARAMS)
    elif args.fix == "tool_config":
        result = fixer.fix_specific(graph, FixType.TOOL_CONFIG)
    elif args.fix == "template_syntax":
        result = fixer.fix_specific(graph, FixType.TEMPLATE_SYNTAX)
    elif args.fix == "code_self_call":
        result = fixer.fix_specific(graph, FixType.CODE_SELF_CALL)
    else:
        result = fixer.fix_all(graph)

    # 写入输出文件
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.graph, f, ensure_ascii=False, indent=2)

    # 打印摘要
    print_summary(result)
    print(f"\n✓ 修复完成，输出到: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
