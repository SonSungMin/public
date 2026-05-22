#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
⚡ Neo's Local RAG MCP Server (v2.0 - FastMCP Refactoring Edition)
- 데드락 요인이던 로우레벨 stdio_server 스트림 핸들러를 제거하고, groq_mcp.py에서 검증된 고수준 FastMCP 런타임으로 전격 전환합니다.
"""

import os
import sys
import logging
from fastmcp import FastMCP

# 1. 로깅 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_LOG_PATH = os.path.join(BASE_DIR, "rag_mcp_runtime.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=RUNTIME_LOG_PATH,
    encoding="utf-8"
)
logger = logging.getLogger("neos-local-rag-fastmcp")

# RAG DB 엔진이 로컬 디렉터리에 위치하므로 경로 탐색 추가
sys.path.append(BASE_DIR)

# 2. FastMCP 인스턴스 생성
mcp = FastMCP("neos-local-rag")

# 3. 레이지(Lazy) 엔진 로딩 구조 (DB 락 지연 시 부팅 크래시 방어)
_engine_instance = None

def get_engine():
    global _engine_instance
    if _engine_instance is None:
        try:
            logger.info("📦 [LAZY] local_rag_engine 임포트 시도")
            from local_rag_engine import LocalRAGEngine
            _engine_instance = LocalRAGEngine()
            logger.info("📦 [LAZY] local_rag_engine 초기화 성공!")
        except Exception as ie:
            logger.error(f"❌ [LAZY_ERR] 임포트 실패: {str(ie)}")
            # 임포트 실패 시 복구 가능한 Fallback Dummy 엔진 제공
            class FallbackEngine:
                def add_knowledge(self, *args, **kwargs): raise ImportError(str(ie))
                def hybrid_search(self, *args, **kwargs): raise ImportError(str(ie))
                def record_token_usage(self, *args, **kwargs): raise ImportError(str(ie))
            _engine_instance = FallbackEngine()
    return _engine_instance

# =========================================================================
# 🛠️ MCP 최적화 도구 API 매핑
# =========================================================================

@mcp.tool(name="ingest_knowledge", description="검증된 지식을 로컬 RAG DB에 즉각 적재합니다.")
def ingest_knowledge(category: str, issue_summary: str, root_cause: str = "", solution_code: str = "", tags: str = "") -> str:
    """새로운 지식 카드를 추가합니다."""
    try:
        engine = get_engine()
        new_id = engine.add_knowledge(
            category=category,
            issue_summary=issue_summary,
            root_cause=root_cause,
            solution_code=solution_code,
            tags=tags
        )
        logger.info(f"🎉 지식 적재 성공 (ID: {new_id})")
        return f"🎉 성공 (ID: {new_id})"
    except Exception as e:
        logger.error(f"Error in ingest_knowledge: {str(e)}")
        return f"❌ 에러: {str(e)}"

@mcp.tool(name="retrieve_knowledge", description="최적의 해결 컨텍스트를 검색합니다.")
def retrieve_knowledge(query: str, limit: int = 3) -> str:
    """하이브리드 유사도 검색을 수행합니다."""
    import json
    try:
        engine = get_engine()
        results = engine.hybrid_search(query=query, top_k=limit)
        logger.info(f"🔍 RAG 검색 수행 완료 - 쿼리: '{query}'")
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in retrieve_knowledge: {str(e)}")
        return f"❌ 에러: {str(e)}"

@mcp.tool(name="record_token_usage", description="대화 입출력 토큰량을 DB에 누적 기록합니다.")
def record_token_usage(model_name: str, input_tokens: int, output_tokens: int) -> str:
    """오늘 소모된 AI 모델별 토큰을 DB에 안전하게 기록합니다."""
    try:
        engine = get_engine()
        engine.record_token_usage(
            model_name=model_name,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens)
        )
        logger.info(f"📊 토큰 사용량 기록 완료 - {model_name} (in: {input_tokens}, out: {output_tokens})")
        return "🎉 성공"
    except Exception as e:
        logger.error(f"Error in record_token_usage: {str(e)}")
        return f"❌ 에러: {str(e)}"

if __name__ == "__main__":
    # fastmcp 자체의 무거운 CLI 로깅 출력을 억제하여 JSON-RPC 통신 오염 차단
    os.environ["FASTMCP_LOG_LEVEL"] = "ERROR"
    # StdIO 트랜스포트로 FastMCP 서버 구동 개시
    mcp.run(transport='stdio', show_banner=False)
