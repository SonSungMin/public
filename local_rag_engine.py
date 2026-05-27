#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
HHI Shipyard Environment Compatible Zero-Dependency Local RAG Engine
- 데이터베이스: SQLite3 (FTS5 키워드 검색 활용)
- 임베딩/유사도: 순수 Python 구현 TF-IDF 및 코사인 유사도 (외부 패키지 설치 0%)
- 사용 용도: 대화에서 발생한 트러블슈팅 사례(에러, 원인, 해결책) 로컬 저장 및 검색 공급
"""

import os
import sqlite3
import math
import re
import json
import argparse
from datetime import datetime

# 데이터베이스 파일 경로 설정 (동일 디렉터리에 데이터베이스 자동 생성)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_knowledge_rag.db")

class LocalRAGEngine:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        # 다중 프로세스/스레드 환경의 락 경합 방지를 위해 타임아웃을 10초로 설정
        # check_same_thread=False: MCP run_in_executor(스레드풀) 환경에서 크로스 스레드 접근 허용
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        # Windows 파일 락 경합 시 즉시 SQLITE_BUSY 대신 5초간 재시도
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        """데이터베이스 스키마 및 가상 테이블(FTS5) 초기화"""
        # 초기화 시에는 충분한 타임아웃을 두어 초기 세팅 락 방지
        conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
        try:
            # WAL(Write-Ahead Logging) 모드를 최초 1회 전격 활성화하여 읽기/쓰기 병렬 동시 처리 확보
            conn.execute("PRAGMA journal_mode=WAL;")
            # 동기 모드를 NORMAL로 설정하여 WAL 성능 극대화 및 디스크 I/O 블로킹 최소화
            conn.execute("PRAGMA synchronous=NORMAL;")
            
            cursor = conn.cursor()
            
            # 1. 원본 지식 데이터 테이블 생성
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS troubleshooting_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                issue_summary TEXT NOT NULL,
                root_cause TEXT,
                solution_code TEXT NOT NULL,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 2. AI 모델별 일일 토큰 사용량 제어 테이블 생성
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_token_usage (
                model_name TEXT PRIMARY KEY,
                limit_tpd INTEGER DEFAULT 100000,
                used_tokens_today INTEGER DEFAULT 0,
                first_chat_today TEXT,
                last_chat_today TEXT,
                last_reset_date TEXT
            );
            """)

            # 주요 인텔리전스 모델 기본 가치 사전 주입
            default_models = [
                ("Claude 3.5 Sonnet", 250000),
                ("Gemini 3.5 Flash", 1000000),
                ("Llama 70B (Groq)", 131072),
                ("DeepSeek V3 (Groq)", 32768)
            ]
            for model_name, limit in default_models:
                cursor.execute("""
                INSERT OR IGNORE INTO ai_token_usage (model_name, limit_tpd, used_tokens_today, last_reset_date)
                VALUES (?, ?, 0, strftime('%Y-%m-%d', 'now', 'localtime'))
                """, (model_name, limit))
            
            # 3. 고속 텍스트 검색을 위한 SQLite FTS5 가상 테이블 생성
            try:
                cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS troubleshooting_knowledge_fts USING fts5(
                    issue_summary,
                    root_cause,
                    solution_code,
                    tags,
                    content='troubleshooting_knowledge',
                    content_rowid='id'
                );
                """)
                
                # Insert 트리거: 원본 테이블 삽입 시 FTS5에 자동 인덱싱
                cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_knowledge_insert AFTER INSERT ON troubleshooting_knowledge
                BEGIN
                    INSERT INTO troubleshooting_knowledge_fts(rowid, issue_summary, root_cause, solution_code, tags)
                    VALUES (new.id, new.issue_summary, new.root_cause, new.solution_code, new.tags);
                END;
                """)

                # Update 트리거: 원본 테이블 업데이트 시 FTS5 자동 동기화
                cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_knowledge_update AFTER UPDATE ON troubleshooting_knowledge
                BEGIN
                    UPDATE troubleshooting_knowledge_fts
                    SET issue_summary = new.issue_summary,
                        root_cause = new.root_cause,
                        solution_code = new.solution_code,
                        tags = new.tags
                    WHERE rowid = old.id;
                END;
                """)

                # Delete 트리거: 원본 테이블 삭제 시 FTS5 자동 소거
                cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_knowledge_delete AFTER DELETE ON troubleshooting_knowledge
                BEGIN
                    DELETE FROM troubleshooting_knowledge_fts WHERE rowid = old.id;
                END;
                """)
            except sqlite3.OperationalError:
                # FTS5가 활성화되지 않은 구버전 SQLite 환경 대응 (FTS4 또는 단순 Like 검색 대비용)
                pass
            
            conn.commit()
        finally:
            conn.close()

    def _merge_text_history(self, existing_text, new_text, max_items=3):
        """기존 텍스트와 새 텍스트를 파싱하여 최근 max_items개의 고유 이력만 유지하고 병합합니다."""
        if not existing_text:
            return new_text if new_text else ""
        if not new_text:
            return existing_text
            
        # 기존 항목 분할 (--- 기준으로 나눔)
        chunks = [c.strip() for c in re.split(r'\n-+\s*(?:\[History\])?\s*-+\n|\n-+\n', existing_text) if c.strip()]
        
        new_chunk = new_text.strip()
        
        # 중복 체크: 새 항목이 기존 항목 중 하나와 완전히 동일한지 확인
        duplicated = False
        new_norm = re.sub(r'\s+', '', new_chunk)
        for chunk in chunks:
            if re.sub(r'\s+', '', chunk) == new_norm:
                duplicated = True
                break
                
        if not duplicated:
            chunks.append(new_chunk)
            
        # 최대 개수 제한 (최신 것 위주로 유지하기 위해 뒤에서부터 max_items개 선택)
        if len(chunks) > max_items:
            chunks = chunks[-max_items:]
            
        return "\n---\n".join(chunks)

    def add_knowledge(self, category, issue_summary, root_cause, solution_code, tags=""):
        """
        새로운 지식(트러블슈팅 사례) 카드를 로컬 DB에 추가 또는 유사한 기존 카드에 스마트 업데이트.
        - 유사도 임계값 0.75 기준으로 기존 중복 카드 자동 검색
        - 기존 카드 존재 시 최근 3개 이력으로 슬라이딩 윈도우 스마트 병합 수행
        """
        existing_id = None
        existing_data = None
        
        try:
            # 자기 자신을 검색 (top_k=1)
            search_results = self.hybrid_search(query=issue_summary, top_k=1)
            if search_results and search_results[0]['relevance_score'] >= 0.75:
                existing_data = search_results[0]
                existing_id = existing_data['id']
        except Exception:
            pass

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if existing_id is not None:
                # 1. 태그 병합 및 중복 소거
                existing_tags = existing_data.get('tags', '') or ''
                all_tags = [t.strip() for t in (existing_tags + "," + tags).split(",") if t.strip()]
                merged_tags = ", ".join(sorted(list(set(all_tags))))
                
                # 2. root_cause 병합 (최근 3개 이력 제한)
                existing_cause = existing_data.get('root_cause', '') or ''
                merged_cause = self._merge_text_history(existing_cause, root_cause)
                
                # 3. solution_code 병합 (최근 3개 이력 제한)
                existing_solution = existing_data.get('solution_code', '') or ''
                merged_solution = self._merge_text_history(existing_solution, solution_code)
                
                # 4. 기존 레코드 업데이트 (FTS5는 UPDATE 트리거로 자동 동기화됨)
                cursor.execute("""
                UPDATE troubleshooting_knowledge 
                SET category = ?, issue_summary = ?, root_cause = ?, solution_code = ?, tags = ?
                WHERE id = ?
                """, (category, issue_summary, merged_cause, merged_solution, merged_tags, existing_id))
                
                conn.commit()
                return existing_id
            else:
                # 유사 카드 미발견 시 신규 지식 적재
                cursor.execute("""
                INSERT INTO troubleshooting_knowledge (category, issue_summary, root_cause, solution_code, tags)
                VALUES (?, ?, ?, ?, ?)
                """, (category, issue_summary, root_cause, solution_code, tags))
                conn.commit()
                return cursor.lastrowid
        finally:
            conn.close()

    # =========================================================================
    # ⚡ AI 토큰 사용량 제어 모듈 비즈니스 로직
    # =========================================================================
    def record_token_usage(self, model_name, input_tokens, output_tokens):
        """매 대화 시 호출되어 토큰 소모량을 누적하고 시작/마지막 시간을 정밀 동기화"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            today_date = datetime.now().strftime("%Y-%m-%d")
            total_tokens = input_tokens + output_tokens

            # 먼저 해당 모델 레코드가 존재하는지 확인
            cursor.execute("SELECT last_reset_date, used_tokens_today, first_chat_today FROM ai_token_usage WHERE model_name = ?", (model_name,))
            row = cursor.fetchone()

            if not row:
                # 레코드가 없다면 기본값과 함께 신규 등록
                cursor.execute("""
                INSERT INTO ai_token_usage (model_name, limit_tpd, used_tokens_today, first_chat_today, last_chat_today, last_reset_date)
                VALUES (?, 100000, ?, ?, ?, ?)
                """, (model_name, total_tokens, now_str, now_str, today_date))
            else:
                last_reset_date, used_tokens_today, first_chat_today = row
                
                # 일일 자가 리셋 날짜 검출 (자정 기준 초기화)
                if last_reset_date != today_date:
                    cursor.execute("""
                    UPDATE ai_token_usage 
                    SET used_tokens_today = ?, first_chat_today = ?, last_chat_today = ?, last_reset_date = ?
                    WHERE model_name = ?
                    """, (total_tokens, now_str, now_str, today_date, model_name))
                else:
                    new_used = used_tokens_today + total_tokens
                    # 첫 대화가 기록되어 있지 않은 특수한 경우 백업 처리
                    new_first = first_chat_today if first_chat_today else now_str
                    cursor.execute("""
                    UPDATE ai_token_usage 
                    SET used_tokens_today = ?, first_chat_today = ?, last_chat_today = ?
                    WHERE model_name = ?
                    """, (new_used, new_first, now_str, model_name))
            conn.commit()
            return True
        finally:
            conn.close()

    def get_all_token_usage(self):
        """저장된 모든 모델별 토큰 사용량과 한도 및 리셋 여부를 자가 정렬하여 가져오기"""
        conn = self._get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            today_date = datetime.now().strftime("%Y-%m-%d")
            
            # 먼저 날짜가 넘어간 레코드들에 대해 자가 리셋 처리 수행 (Lazy-Sync 보장)
            cursor.execute("SELECT model_name, last_reset_date FROM ai_token_usage")
            rows = cursor.fetchall()
            for r in rows:
                if r["last_reset_date"] != today_date:
                    cursor.execute("""
                    UPDATE ai_token_usage 
                    SET used_tokens_today = 0, first_chat_today = NULL, last_chat_today = NULL, last_reset_date = ?
                    WHERE model_name = ?
                    """, (today_date, r["model_name"]))
            conn.commit()

            cursor.execute("SELECT * FROM ai_token_usage ORDER BY used_tokens_today DESC")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_all_knowledge(self):
        """저장된 모든 지식 목록 가져오기"""
        conn = self._get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM troubleshooting_knowledge ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_knowledge(self, knowledge_id):
        """특정 지식 카드를 원본 DB 및 FTS5 검색 테이블에서 영구 소거"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM troubleshooting_knowledge WHERE id = ?", (knowledge_id,))
            try:
                cursor.execute("DELETE FROM troubleshooting_knowledge_fts WHERE rowid = ?", (knowledge_id,))
            except sqlite3.OperationalError:
                pass
            conn.commit()
        finally:
            conn.close()

    # =========================================================================
    # 순수 파이썬 구현 TF-IDF 및 코사인 유사도 매칭 (시맨틱 검색 대체)
    # =========================================================================
    def _tokenize(self, text):
        """한글, 영문, 주요 기호 및 코드를 토큰화하는 단순 형태소/토크나이저"""
        if not text:
            return []
        # 소문자 변환 후 알파벳, 숫자, 한글 단어 단위 분리
        text = text.lower()
        words = re.findall(r'[a-zA-Z0-9가-힣\_]+', text)
        return words

    def _calculate_tfidf(self, query, documents):
        """
        순수 파이썬 기반 TF-IDF 연산 엔진
        documents: list of dict, 각각 'id'와 'text'를 포함함
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return {}

        # 1. 모든 문서 토큰화
        doc_tokens = {}
        all_vocab = set(query_tokens)
        
        for doc in documents:
            tokens = self._tokenize(f"{doc['issue_summary']} {doc['root_cause']} {doc['tags']}")
            doc_tokens[doc['id']] = tokens
            all_vocab.update(tokens)

        # 2. IDF 계산
        num_docs = len(documents)
        idf = {}
        for term in all_vocab:
            # 해당 term이 나타난 문서 수 계산 (최소 1로 설정하여 분모 0 방지)
            doc_count = sum(1 for tokens in doc_tokens.values() if term in tokens)
            idf[term] = math.log((1 + num_docs) / (1 + doc_count)) + 1

        # 3. 문서 벡터 및 쿼리 벡터 구축
        doc_vectors = {}
        for doc_id, tokens in doc_tokens.items():
            # TF 계산 (단어 빈도)
            tf = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            
            # TF-IDF 값으로 벡터 매핑
            vector = {}
            for term in tokens:
                vector[term] = tf[term] * idf[term]
            doc_vectors[doc_id] = vector

        # 4. 쿼리 벡터 구축
        query_tf = {}
        for token in query_tokens:
            query_tf[token] = query_tf.get(token, 0) + 1
        
        query_vector = {}
        for term in query_tokens:
            query_vector[term] = query_tf[term] * idf[term]

        # 5. 코사인 유사도 계산
        scores = {}
        q_norm = math.sqrt(sum(v ** 2 for v in query_vector.values()))
        if q_norm == 0:
            return {doc['id']: 0.0 for doc in documents}

        for doc_id, doc_vec in doc_vectors.items():
            # 내적 계산
            dot_product = sum(query_vector[term] * doc_vec.get(term, 0.0) for term in query_vector)
            
            # 크기 계산
            d_norm = math.sqrt(sum(v ** 2 for v in doc_vec.values()))
            if d_norm == 0:
                scores[doc_id] = 0.0
            else:
                scores[doc_id] = dot_product / (q_norm * d_norm)

        return scores

    def hybrid_search(self, query, top_k=3):
        """
        SQLite FTS5 키워드 순위와 순수 파이썬 TF-IDF 유사도를 병합한 하이브리드 검색
        """
        all_docs = self.get_all_knowledge()
        if not all_docs:
            return []

        # 1. 시맨틱 유사도 채점 (TF-IDF 코사인 유사도)
        semantic_scores = self._calculate_tfidf(query, all_docs)

        # 2. SQLite FTS5 키워드 랭킹 매칭 수행 (FTS5 미지원 시 단순 Like 검색으로 백업)
        fts_rankings = {}
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            try:
                # FTS5 구문 파서 오류 예방을 위해 한글/알파벳/숫자 토큰만 안전하게 추출하여 OR 검색어 빌드
                tokens = [t for t in re.findall(r'[a-zA-Z0-9가-힣]+', query) if t]
                if tokens:
                    safe_fts_query = " OR ".join(f'"{t}"' for t in tokens)
                    
                    # FTS5 bm25 알고리즘 사용 (값이 작을수록 검색 연관성이 높음, 최상의 값이 음수)
                    cursor.execute("""
                    SELECT rowid, bm25(troubleshooting_knowledge_fts) as rank 
                    FROM troubleshooting_knowledge_fts 
                    WHERE troubleshooting_knowledge_fts MATCH ?
                    """, (safe_fts_query,))
                    for rowid, rank in cursor.fetchall():
                        # bm25 점수를 [0, 1] 범위의 유사도(양수)로 변환
                        fts_rankings[rowid] = 1.0 / (1.0 + exp_rank(rank))
            except Exception:
                # FTS5 검색 실패 시 백업 키워드 검색 (단순 LIKE 패턴 매칭 활용)
                for doc in all_docs:
                    match_count = 0
                    for q_part in query.split():
                        if q_part.lower() in f"{doc['issue_summary']} {doc['root_cause']} {doc['tags']}".lower():
                            match_count += 1
                    fts_rankings[doc['id']] = match_count / max(len(query.split()), 1)
        finally:
            conn.close()

        # 3. 하이브리드 가중치 결합 (Semantic TF-IDF: 60%, FTS5 Keyword: 40%)
        hybrid_results = []
        for doc in all_docs:
            doc_id = doc['id']
            s_score = semantic_scores.get(doc_id, 0.0)
            k_score = fts_rankings.get(doc_id, 0.0)
            
            # 최종 하이브리드 스코어 산출
            hybrid_score = (s_score * 0.6) + (k_score * 0.4)
            
            doc_with_score = doc.copy()
            doc_with_score['relevance_score'] = round(hybrid_score, 4)
            hybrid_results.append(doc_with_score)

        # 4. 높은 점수 순 정렬 후 top_k 반환
        hybrid_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return hybrid_results[:top_k]

def exp_rank(rank):
    """FTS5 bm25 순위의 음수 지수 스케일링용 보조 함수"""
    try:
        return math.exp(min(max(rank, -10), 10))
    except OverflowError:
        return 1.0

# =========================================================================
# CLI 인터페이스 핸들러
# =========================================================================
def main():
    parser = argparse.ArgumentParser(description="HHI Shipyard Offline Local RAG CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="실행할 명령어")

    # 1. 지식 등록 명령어
    parser_add = subparsers.add_parser("add", help="신규 트러블슈팅 지식 카드 추가")
    parser_add.add_argument("--category", "-c", required=True, help="카테고리 (예: Flutter, Gradle)")
    parser_add.add_argument("--issue", "-i", required=True, help="발생한 에러 현상 요약")
    parser_add.add_argument("--cause", "-r", required=False, default="", help="근본 원인 분석")
    parser_add.add_argument("--solution", "-s", required=True, help="검증된 소스코드 및 해결책 가이드")
    parser_add.add_argument("--tags", "-t", required=False, default="", help="콤마로 구분된 검색 키워드 태그")

    # 2. 하이브리드 RAG 검색 명령어
    parser_search = subparsers.add_parser("search", help="로컬 RAG 하이브리드 유사도 검색")
    parser_search.add_argument("query", help="검색할 질문 문장")
    parser_search.add_argument("--limit", "-l", type=int, default=3, help="출력할 결과 개수 (기본 3)")

    # 3. 전체 목록 보기 명령어
    subparsers.add_parser("list", help="저장된 전체 지식 인덱스 출력")

    args = parser.parse_args()
    engine = LocalRAGEngine()

    if args.command == "add":
        knowledge_id = engine.add_knowledge(
            category=args.category,
            issue_summary=args.issue,
            root_cause=args.cause,
            solution_code=args.solution,
            tags=args.tags
        )
        print(f"\n[성공] 로컬 RAG DB에 신규 지식 카드가 등록되었습니다. (ID: {knowledge_id})")
        print(f"- 카테고리: {args.category}")
        print(f"- 이슈 요약: {args.issue}")

    elif args.command == "search":
        print(f"\n🔍 [RAG Query]: '{args.query}' 검색 중...")
        results = engine.hybrid_search(args.query, top_k=args.limit)
        
        if not results:
            print("❌ 매칭되는 로컬 지식 카드가 존재하지 않습니다. 먼저 지식을 등록해 보세요.")
            return

        print(f"📌 최적의 해결 컨텍스트 검색 결과 (상위 {len(results)}개):")
        for i, res in enumerate(results, 1):
            # 유사도 스코어가 0.1 이상인 경우에만 의미 있는 매칭으로 판단
            print(f"\n-------------------------------------------------------------")
            print(f"[{i}] [{res['category']}] {res['issue_summary']} (유사도 점수: {res['relevance_score']})")
            if res['root_cause']:
                print(f"  👉 원인: {res['root_cause']}")
            print(f"  💡 검증된 해결책:\n{res['solution_code']}")
            if res['tags']:
                print(f"  🏷️ 태그: {res['tags']}")
            print(f"-------------------------------------------------------------")

    elif args.command == "list":
        knowledges = engine.get_all_knowledge()
        if not knowledges:
            print("\n📂 DB가 비어 있습니다. 첫 번째 지식 카드를 등록해 보세요.")
            return
        
        print(f"\n📂 저장된 전체 로컬 지식 카드 목록 (총 {len(knowledges)}개):")
        for k in knowledges:
            print(f"- [{k['id']}] [{k['category']}] {k['issue_summary']} ({k['created_at']})")

    else:
        parser.print_help()

if __name__ == "__main__":
    # 임베딩 데이터 샘플 초기 입력 (사용성 강화 목적)
    engine = LocalRAGEngine()
    if not engine.get_all_knowledge():
        # 기본 HHI 조선소 특화 오류 샘플 데이터 적재
        engine.add_knowledge(
            category="Gradle",
            issue_summary="HHI 사내 폐쇄망 환경에서 Gradle dependencies 빌드 다운로드 실패 에러",
            root_cause="조선소 내 사내망 프록시 및 외부 gradle 리포지토리 차단으로 빌드 타임아웃 발생",
            solution_code="flutter run --offline 옵션을 활용하고, build.gradle 파일 내 mavenLocal() 및 로컬 리포지토리를 참조하도록 repositories { flatDir { dirs 'libs' } } 정의 설정",
            tags="gradle, offline, mirror, proxy, shipyard"
        )
        engine.add_knowledge(
            category="Flutter",
            issue_summary="Flutter 위젯 트리 파싱 에러 및 중복 괄호(Bracket mismatch)로 인한 컴파일 붕괴",
            root_cause="코드 리팩토링 시 Scaffold 및 Multi-child 위젯 분리 과정에서 curly braces {}, () 매칭 유실",
            solution_code="Zero-Content-Loss 파서를 이용해 괄호 대칭성을 수치 계산한 후, UI 바디를 SafeArea로 감싸고 하단 컴포넌트를 BottomAppBar에 바인딩하여 복구함",
            tags="flutter, compiler, bracket, scaffold, safearea"
        )
        engine.add_knowledge(
            category="AdMob",
            issue_summary="Banner Ad 크기 불일치로 인한 광고 컴파일 및 렌더링 영역 침범 오류",
            root_cause="디바이스 크기 동적 연산 없이 고정 픽셀(320x50)을 Scaffold 높이에 강제 주입하여 UI 오버플로우 발생",
            solution_code="AdSize.getAnchoredAdaptiveBannerAdSize(Orientation.portrait, width) API를 사용해 동적 높이를 계산하고 AdWidget을 SizedBox로 감싸 렌더링 영역 보호",
            tags="admob, banner, alignment, overflow"
        )
    main()
