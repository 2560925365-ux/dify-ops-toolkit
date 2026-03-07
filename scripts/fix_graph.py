#!/usr/bin/env python3
"""
Dify Graph Fixer - 修复工作流 Graph 常见格式问题
"""

import argparse
import json
import re


def fix_http_nodes(graph: dict) -> dict:
    """修复 HTTP 节点 - 添加 params 字段"""
    for node in graph.get("nodes", []):
        if node.get("data", {}).get("type") == "http-request":
            if "params" not in node["data"]:
                node["data"]["params"] = ""
                print(f"  ✓ 添加 params 字段: {node['id']}")
    return graph


def fix_tool_nodes(graph: dict) -> dict:
    """修复工具节点 - 添加 tool_configurations 字段"""
    for node in graph.get("nodes", []):
        if node.get("data", {}).get("type") == "tool":
            if "tool_configurations" not in node["data"]:
                node["data"]["tool_configurations"] = {}
                print(f"  ✓ 添加 tool_configurations 字段: {node['id']}")
    return graph


def fix_template_syntax(graph: dict) -> dict:
    """修复模板语法 - {{#xxx#}} -> {{ xxx }}"""
    for node in graph.get("nodes", []):
        if node.get("data", {}).get("type") == "template-transform":
            template = node["data"].get("template", "")
            # 修复 {{#node.field#}} 语法
            fixed = re.sub(r'\{\{#([^#]+)#\}\}', r'{{ \1 }}', template)
            if fixed != template:
                node["data"]["template"] = fixed
                print(f"  ✓ 修复模板语法: {node['id']}")
    return graph


def fix_code_self_calls(graph: dict) -> dict:
    """修复 Code 节点中的 self 调用"""
    for node in graph.get("nodes", []):
        if node.get("data", {}).get("type") == "code":
            code = node["data"].get("code", "")
            if "self." in code:
                print(f"  ⚠️ 代码节点 {node['id']} 包含 self 调用，需要手动修复")
    return graph


def fix_all(graph: dict) -> dict:
    """执行所有修复"""
    print("正在修复 Graph...")
    graph = fix_http_nodes(graph)
    graph = fix_tool_nodes(graph)
    graph = fix_template_syntax(graph)
    graph = fix_code_self_calls(graph)
    return graph


def main():
    parser = argparse.ArgumentParser(description="修复 Dify Graph 格式问题")
    parser.add_argument("--input", required=True, help="输入 JSON 文件")
    parser.add_argument("--output", required=True, help="输出 JSON 文件")
    parser.add_argument("--fix", choices=["http", "tool", "template", "all"], default="all")
    args = parser.parse_args()

    # 读取输入
    with open(args.input, "r", encoding="utf-8") as f:
        graph = json.load(f)

    print(f"输入文件: {args.input}")
    print(f"节点数: {len(graph.get('nodes', []))}")
    print(f"边数: {len(graph.get('edges', []))}")
    print()

    # 执行修复
    if args.fix == "all":
        graph = fix_all(graph)
    elif args.fix == "http":
        graph = fix_http_nodes(graph)
    elif args.fix == "tool":
        graph = fix_tool_nodes(graph)
    elif args.fix == "template":
        graph = fix_template_syntax(graph)

    # 写入输出
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 修复完成，输出到: {args.output}")


if __name__ == "__main__":
    main()
