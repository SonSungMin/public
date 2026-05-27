#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
⚡ Neo's Local RAG MCP Server (v3.1 - Cloudless Fail-Fast proxy edition)
- HHI Shipyard Safe: SQLite 파일 락 분쟁 원천 해소 및 고속 예외 처리 추가
- 동작 원리: 
  MCP 프로세스에서 SQLite DB 파일을 직접 마운트하지 않고, 
  GUI 매니저(local_rag_manager.py)가 가동 중인 임베디드 API 서버(Port 8085)를 호출하여 
  데이터 작업을 전담 위임합니다.
- 예외 안전망:
  GUI 매니저가 미구동 상태인 경우, 1.5초 이내에 타임아웃을 발생시켜 
  무한 대기(데드락 오인) 없이 기동 권고 메시지를 뿜고 즉시 동작을 종료합니다.
"""

import os
import sys
import json
import asyncio
import builtins
import traceback
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

# 파이썬 레벨 print 안전 조치 (stdio 스트림 보호)
_orig_print = builtins.print
def mcp_safe_print(*args, **kwargs):
    kwargs["file"] = sys.stderr
    _orig_print(*args, **kwargs)
builtins.print = mcp_safe_print

from fastmcp import FastMCP
mcp = FastMCP("neos-local-rag")

# =========================================================================
# 📦 로그 설정 (stdout 오염 완전 차단)
# =========================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "mcp_debug.log")

def log_to_file(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] {msg}\n")
    except Exception:
        pass

# =========================================================================
# 📡 Zero-Dependency 초고속 Fail-Fast HTTP API 클라이언트 모듈
# =========================================================================
API_BASE_URL = "http://127.0.0.1:8085/api"

def _call_api_get(path, params=None):
    """경량 HTTP GET 호출 헬퍼 (타임아웃 1.5초 및 즉시 에러 반환)"""
    url = API_BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Neo-RAG-MCP'})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as res:
            return json.loads(res.read().decode('utf-8'))
    except urllib.error.URLError as e:
        log_to_file(f"[API_GET_ERR] Connection Refused or Timeout: {str(e)}")
        raise ConnectionError("❌ RAG DB Manager가 실행 중이 아닙니다. 바탕화면 또는 작업 폴더의 'local_rag_manager.py'를 먼저 실행해 주세요.")
    except Exception as e:
        raise Exception(f"API GET 오류: {str(e)}")

def _call_api_post(path, data):
    """경량 HTTP POST 호출 헬퍼 (타임아웃 1.5초 및 즉시 에러 반환)"""
    url = API_BASE_URL + path
    encoded_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
    
    req = urllib.request.Request(
        url, 
        data=encoded_data, 
        headers={'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'Neo-RAG-MCP'}
    )
    try:
        with urllib.request.urlopen(req, timeout=1.5) as res:
            return json.loads(res.read().decode('utf-8'))
    except urllib.error.URLError as e:
        log_to_file(f"[API_POST_ERR] Connection Refused or Timeout: {str(e)}")
        raise ConnectionError("❌ RAG DB Manager가 실행 중이 아닙니다. 바탕화면 또는 작업 폴더의 'local_rag_manager.py'를 먼저 실행해 주세요.")
    except Exception as e:
        raise Exception(f"API POST 오류: {str(e)}")

async def _run_api_op(func, *args, **kwargs):
    """FastMCP 비동기 루프를 블로킹하지 않기 위해 별도 스레드에서 API 호출"""
    return await asyncio.to_thread(func, *args, **kwargs)

# =========================================================================
# 🛠️ MCP 실전 비즈니스 도구 API 매핑
# =========================================================================

@mcp.tool(name="ingest_knowledge", description="검증된 지식을 로컬 RAG DB에 즉각 적재합니다.")
async def ingest_knowledge(category: str, issue_summary: str, root_cause: str = "", solution_code: str = "", tags: str = "") -> str:
    log_to_file(f"[TOOL:ingest_knowledge] 호출됨 - category='{category}'")
    try:
        payload = {
            "category": category,
            "issue_summary": issue_summary,
            "root_cause": root_cause,
            "solution_code": solution_code,
            "tags": tags
        }
        res = await _run_api_op(_call_api_post, "/add", payload)
        if res.get("success"):
            new_id = res.get("id")
            log_to_file(f"[TOOL:ingest_knowledge] ✅ 성공 (ID: {new_id})")
            return f"🎉 성공 (ID: {new_id})"
        else:
            raise Exception(res.get("error", "알 수 없는 API 서버 오류"))
    except ConnectionError as ce:
        return str(ce)
    except Exception as e:
        log_to_file(f"[TOOL:ingest_knowledge] ❌ 예외: {str(e)}")
        return f"❌ 에러: {str(e)}"

@mcp.tool(name="retrieve_knowledge", description="최적의 해결 컨텍스트를 검색합니다.")
async def retrieve_knowledge(query: str, limit: int = 3) -> str:
    log_to_file(f"[TOOL:retrieve_knowledge] 호출됨 - query='{query[:80]}', limit={limit}")
    try:
        params = {"q": query, "limit": limit}
        results = await _run_api_op(_call_api_get, "/search", params)
        log_to_file(f"[TOOL:retrieve_knowledge] ✅ 완료 (결과 수: {len(results)})")
        return json.dumps(results, ensure_ascii=False)
    except ConnectionError as ce:
        return str(ce)
    except Exception as e:
        log_to_file(f"[TOOL:retrieve_knowledge] ❌ 예외: {str(e)}")
        return f"❌ 에러: {str(e)}"

@mcp.tool(name="record_token_usage", description="대화 입출력 토큰량을 DB에 누적 기록합니다.")
async def record_token_usage(model_name: str, input_tokens: int, output_tokens: int) -> str:
    log_to_file(f"[TOOL:record_token_usage] 호출됨 - model='{model_name}', in={input_tokens}, out={output_tokens}")
    try:
        payload = {
            "model_name": model_name,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens)
        }
        res = await _run_api_op(_call_api_post, "/record_token", payload)
        if res.get("success"):
            log_to_file("[TOOL:record_token_usage] ✅ 성공")
            return "🎉 성공"
        else:
            raise Exception(res.get("error", "알 수 없는 API 서버 오류"))
    except ConnectionError as ce:
        return str(ce)
    except Exception as e:
        log_to_file(f"[TOOL:record_token_usage] ❌ 예외: {str(e)}")
        return f"❌ 에러: {str(e)}"

# =========================================================================
# 🔄 에이전트 자동 연계 파이프라인 (대화 전 조회 / 대화 후 요약 저장)
# =========================================================================

@mcp.tool(name="search_past_improvements", description="현재 질문과 연관된 과거 개선 사항이 RAG 데이터베이스에 있는지 확인합니다. 답변 전에 필수 호출하세요.")
async def search_past_improvements(current_query: str) -> str:
    log_to_file(f"[TOOL:search_past_improvements] 호출됨 - query='{current_query[:80]}'")
    try:
        params = {"q": current_query, "limit": 2}
        results = await _run_api_op(_call_api_get, "/search", params)

        if not results:
            log_to_file("[TOOL:search_past_improvements] 검색 결과 없음")
            return "확인 결과, 과거에 유사하게 개선한 내용이나 참고할 기존 정보가 없습니다. 일반적인 최선의 답변을 제공하세요."

        formatted_records = []
        for idx, item in enumerate(results, start=1):
            summary = item.get("issue_summary", "기록 없음")
            solution = item.get("solution_code", "") or item.get("root_cause", "")
            category = item.get("category", "General")
            record_str = f"[{idx}] (분류: {category}) 핵심: {summary}"
            if solution:
                record_str += f" | 조치 사항: {solution}"
            formatted_records.append(record_str)

        result_msg = "⚠️ [중요] 과거에 동일하거나 의미상 유사한 내용으로 개선한 이력이 존재합니다. 아래 내용을 반드시 반영하여 답변하세요:\n" + "\n".join(formatted_records)
        log_to_file(f"[TOOL:search_past_improvements] ✅ 완료 (결과 수: {len(results)})")
        return result_msg
    except ConnectionError as ce:
        return str(ce)
    except Exception as e:
        log_to_file(f"[TOOL:search_past_improvements] ❌ 예외: {str(e)}")
        return f"❌ 과거 이력 조회 실패: {str(e)}"

@mcp.tool(name="save_response_summary", description="답변 결과의 핵심 요약과 조치 내역을 RAG DB에 영구 백업 지식으로 적재합니다. 답변 종료 후 필수 호출하세요.")
async def save_response_summary(category: str, issue_summary: str, solution_code: str = "", tags: str = "improvement-summary") -> str:
    log_to_file(f"[TOOL:save_response_summary] 호출됨 - category='{category}'")
    try:
        payload = {
            "category": category,
            "issue_summary": issue_summary,
            "root_cause": "대화 요약 자동 수집",
            "solution_code": solution_code,
            "tags": tags
        }
        res = await _run_api_op(_call_api_post, "/add", payload)
        if res.get("success"):
            new_id = res.get("id")
            log_to_file(f"[TOOL:save_response_summary] ✅ 성공 (ID: {new_id})")
            return f"🎉 핵심 답변 요약이 RAG 장기 지식 베이스(ID: {new_id})에 동기화 완료되었습니다."
        else:
            raise Exception(res.get("error", "알 수 없는 API 서버 오류"))
    except ConnectionError as ce:
        return str(ce)
    except Exception as e:
        log_to_file(f"[TOOL:save_response_summary] ❌ 예외: {str(e)}")
        return f"❌ 요약 저장 실패: {str(e)}"

if __name__ == "__main__":
    log_to_file("[MAIN] MCP 서버 기동 시작")
    mcp.run(transport='stdio', show_banner=False)
    log_to_file("[MAIN] MCP 서버 정상 종료")
