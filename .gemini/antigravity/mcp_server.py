# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp",
# ]
# ///

import os
import ast
import subprocess
import re
import sys
import asyncio
import logging
from typing import List, Optional
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server.stdio import stdio_server

# 로깅 설정 (stderr 전용)
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("my-vibe-mcp")

# =================================================================
# MCP 서버 초기화
# =================================================================
server = Server("my-vibe-mcp")

# =================================================================
# LANGUAGE SPECS (언어별 명세 정의)
# =================================================================
LANG_SPECS = {
    "python": {
        "ext": [".py"], 
        "debug_logs": ["print("], 
        "comment": "#", 
        "type": "ast"
    },
    "java": {
        "ext": [".java", ".jsp"], 
        "debug_logs": ["System.out.print"], 
        "comment": "//", 
        "type": "bracket"
    },
    "javascript": {
        "ext": [".js", ".ts"], 
        "debug_logs": ["console.log"], 
        "comment": "//", 
        "type": "bracket"
    },
    "vue": {
        "ext": [".vue"], 
        "debug_logs": ["console.log"], 
        "comment": "//", 
        "type": "vue"
    }
}

def get_lang_spec(filename: str) -> dict:
    for spec in LANG_SPECS.values():
        if any(filename.endswith(ext) for ext in spec["ext"]):
            return spec
    return {"ext": [], "debug_logs": [], "comment": "//", "type": "text"}

# =================================================================
# CONTEXT EXTRACT LOGIC
# =================================================================

def extract_python_ast(code: str, symbol: str) -> str:
    try:
        tree = ast.parse(code)
    except:
        return code[:1200]
    
    lines = code.split("\n")
    imports, target = [], []
    
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.extend(lines[node.lineno-1:node.end_lineno])
        if hasattr(node, "name") and node.name == symbol:
            target = lines[node.lineno-1:node.end_lineno]
            
    if not target:
        return code[:1200]
    return "\n".join(imports) + "\n\n# ... [omitted] ...\n\n" + "\n".join(target)

def extract_vue(code: str) -> str:
    match = re.search(r'<script.*?>.*?</script>', code, re.DOTALL)
    if not match:
        return code[:1000]
    script = match.group(0)
    return script[:800] if "setup" in script else script[:1000]

def extract_context(code: str, symbol: str, filename: str) -> str:
    spec = get_lang_spec(filename)
    if spec["type"] == "ast":
        return extract_python_ast(code, symbol)
    elif spec["type"] == "vue":
        return extract_vue(code)
    return code[:1000]

# =================================================================
# MCP TOOLS HANDLERS
# =================================================================

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="planner",
            description="Git 상태를 확인하거나 최근 24시간 이내에 수정된 파일 목록을 반환합니다.",
            inputSchema={
                "type": "object",
                "properties": {"target_dir": {"type": "string", "default": "."}},
            },
        ),
        types.Tool(
            name="coder",
            description="LLM에게 코딩 지시를 내리기 위한 최적화된 프롬프트를 생성합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "code": {"type": "string"},
                    "requirements": {"type": "array", "items": {"type": "string"}},
                    "symbol": {"type": "string", "default": ""},
                },
                "required": ["file", "code", "requirements"],
            },
        ),
        types.Tool(
            name="reviewer",
            description="작성된 코드에 대해 보안 및 코드 품질 검사를 수행합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "patch": {"type": "string"},
                },
                "required": ["file", "patch"],
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    if not arguments:
        return [types.TextContent(type="text", text="Arguments required")]

    if name == "planner":
        import time
        target_dir = os.path.abspath(arguments.get("target_dir", "."))
        git_dir = os.path.join(target_dir, ".git")
        loop = asyncio.get_running_loop()
        
        # 동기 작업을 비동기 스레드 풀에서 안전하게 2.0초 타임아웃으로 제어하는 헬퍼 (Stdio 오염 방지 가드 장착)
        async def run_sync_with_timeout(func, *args, **kwargs):
            import functools
            
            def sync_task_with_stdio_guard():
                old_stdout = sys.stdout
                sys.stdout = sys.stderr
                try:
                    return func(*args, **kwargs)
                finally:
                    sys.stdout = old_stdout

            try:
                return await asyncio.wait_for(
                    loop.run_in_executor(None, sync_task_with_stdio_guard),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                raise TimeoutError("⏱️ 파일 탐색/명령어 실행 시간 초과 (2.0초 초과) — 안전을 위해 작업을 즉각 건너뜁니다.")

        if os.path.exists(git_dir):
            try:
                def run_git():
                    return subprocess.run(["git", "status", "--porcelain"], cwd=target_dir, capture_output=True, text=True, timeout=1.5)
                
                result = await run_sync_with_timeout(run_git)
                files = [line[3:].strip() for line in result.stdout.split("\n") if line.strip()]
                res = f"[Git: {target_dir}] Changes: {', '.join(files)}" if files else "[Git] No changes."
                return [types.TextContent(type="text", text=res)]
            except Exception as e:
                return [types.TextContent(type="text", text=f"⚠️ Git Skip: {str(e)}")]
        else:
            try:
                def walk_dir():
                    recent_files = []
                    now = time.time()
                    for root, dirs, files in os.walk(target_dir):
                        dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "venv", ".venv", "__pycache__"]]
                        for file in files:
                            filepath = os.path.join(root, file)
                            try:
                                mtime = os.path.getmtime(filepath)
                                if now - mtime < 86400:
                                    rel_path = os.path.relpath(filepath, target_dir)
                                    recent_files.append((mtime, rel_path))
                            except OSError:
                                continue
                    recent_files.sort(key=lambda x: x[0], reverse=True)
                    return recent_files

                recent_files = await run_sync_with_timeout(walk_dir)
                top_files = [f[1] for f in recent_files[:15]]
                res = f"[Local: {target_dir}] Recent files: {', '.join(top_files)}" if top_files else "[Local] No recent changes."
                return [types.TextContent(type="text", text=res)]
            except Exception as e:
                return [types.TextContent(type="text", text=f"⚠️ Disk Skip: {str(e)}")]

    elif name == "coder":
        file = arguments.get("file", "")
        code = arguments.get("code", "")
        requirements = arguments.get("requirements", [])
        symbol = arguments.get("symbol", "")
        context = extract_context(code, symbol, file)
        spec = get_lang_spec(file)
        cmt = spec["comment"]
        reqs_str = "\n".join([f"{cmt} {r}" for r in requirements])
        prompt = f"You are a senior developer.\nSTRICT RULES:\n- ONLY unified diff or code blocks.\n- NO yapping.\n\nRequirements:\n{reqs_str}\n\nContext:\n{context}\n"
        return [types.TextContent(type="text", text=prompt)]

    elif name == "reviewer":
        file = arguments.get("file", "")
        patch = arguments.get("patch", "")
        spec = get_lang_spec(file)
        issues = []
        for log in spec["debug_logs"]:
            if log in patch: issues.append(f"Remove debug: {log}")
        if spec["type"] == "ast" and "try:" in patch and "except" not in patch:
            issues.append("Missing except block")
        res = "PASS" if not issues else f"FAIL: {', '.join(issues)}"
        return [types.TextContent(type="text", text=res)]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="my-vibe-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
