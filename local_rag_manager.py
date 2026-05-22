#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
⚡ Neo's Local RAG DB Manager & Desktop Shell (v2.0)
- HHI Shipyard Safe: 100% Offline, 외부 웹서버/포트 의존성 0%
- 주요 기능: 
  1. RAG DB 실시간 다이렉트 바인딩 및 총 지식 카드 개수 통계
  2. 🌌 로컬 지식 탐색 쉘 (하이브리드 키워드/태그 검색, Treeview 리스팅)
  3. ⚡ 프리미엄 다크 지식 카드 팝업뷰 & 원클릭 클립보드 복사 엔진
  4. 🚀 퀵 RAG 지식 직접 등록기 (Bento Input Form)
  5. 윈도우 시작 시 자동실행 레지스트리 자동화
  6. X 버튼 시 시스템 트레이 아이콘 은닉 (Tray minimize)
  7. 🖥 사용자 행동(Action) 및 에이전트 실시간 자율 학습(Self-Ingest) 터미널 로그 스트리밍
  8. 자체 비트맵 렌더러 기반 독립 아이콘 생성 (외부 이미지 파일 의존성 0%)
"""

import os
import sys
import threading
import time
import winreg
import atexit
import json
import socket
from datetime import datetime

# 🔒 중복 실행 방지를 위한 로컬 소켓 뮤텍스 락 (65432 포트 선점)
_instance_socket = None

def _ensure_single_instance():
    global _instance_socket
    try:
        _instance_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 로컬 루프백의 65432 포트를 점유하여 글로벌 락으로 사용
        _instance_socket.bind(('127.0.0.1', 65432))
        _instance_socket.listen(1)
    except socket.error:
        # 포트 점유 실패 시 이미 타 인스턴스가 구동 중인 상태이므로 즉각 셧다운
        root_temp = tk.Tk()
        root_temp.withdraw()
        messagebox.showwarning("중복 실행 방지", "⚡ Neo's Local RAG DB Manager가 이미 백그라운드에 구동 중입니다.\n기존에 실행된 프로그램을 이용해 주세요.")
        root_temp.destroy()
        sys.exit(0)

# Tkinter 내장 모듈 로드
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# 동적 임포트: 트레이 아이콘을 위한 라이브러리 검증 및 Fallback 준비
TRAY_SUPPORTED = False
try:
    from PIL import Image, ImageDraw
    import pystray
    from pystray import MenuItem as item
    TRAY_SUPPORTED = True
except ImportError:
    pass

# 경로 상수 정의
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "local_knowledge_rag.db")
ENGINE_SCRIPT = os.path.join(BASE_DIR, "local_rag_engine.py")
PENDING_FILE = os.path.join(BASE_DIR, "pending_ingestion.json")

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VAL_NAME = "NeosLocalRAGDBManager"

class RAGManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("⚡ Neo's Local RAG DB Manager & Desktop Shell")
        self.root.geometry("1180x800")
        self.root.minsize(1000, 700)
        
        self.tray_icon = None
        self.is_watching_files = True
        self.file_watcher_thread = None

        # 프리미엄 다크 테마 컬러 에스테틱 설정
        self.color_bg = "#0b0f19"         # 메인 다크 백그라운드
        self.color_panel = "#111827"      # 컨테이너 패널
        self.color_card = "#1f2937"       # 카드 배경
        self.color_text = "#f3f4f6"       # 기본 텍스트
        self.color_accent = "#6366f1"     # 인디고 액센트
        self.color_green = "#10b981"      # 성공/가동 그린
        self.color_red = "#ef4444"        # 정지/에러 레드
        self.color_gray = "#9ca3af"       # 보조 텍스트
        
        self.root.configure(bg=self.color_bg)
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # 로컬 RAG 엔진 초기화 및 다이렉트 링크
        sys.path.append(BASE_DIR)
        try:
            from local_rag_engine import LocalRAGEngine
            self.engine = LocalRAGEngine()
        except ImportError:
            self.engine = None
        
        self._setup_styles()
        self._build_ui()
        self._check_db_status()
        self._check_startup_registry()
        self.refresh_knowledge_list()
        self.refresh_token_usage()
        
        # 파일 기반 자가 학습 감시 루프 개시
        self.start_file_watcher()
        
        # 윈도우 시스템 트레이 지원 시 종료 이벤트 가로채기 재정의
        if TRAY_SUPPORTED:
            self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
            self._create_tray_icon()
            self.write_console_log("SYSTEM", "시스템 트레이 백그라운드 모듈 마운트 성공. (X 닫기 시 트레이로 숨김)")
        else:
            self.root.protocol("WM_DELETE_WINDOW", self.close_application)
            self.write_console_log("SYSTEM", "경고: pystray/pillow 미설치로 일반 창 닫기 모드로 구동됩니다.")

        # 메인 와이드 콘텐츠 좌우 3:7 비율 강제 싱크
        self.root.after(150, self._force_sash_ratio)

    def _setup_styles(self):
        """Ttk 컨트롤들을 위한 프리미엄 다크 테마 커스텀 스타일링"""
        self.style.configure(".", background=self.color_bg, foreground=self.color_text)
        self.style.configure("TFrame", background=self.color_bg)
        self.style.configure("Panel.TFrame", background=self.color_panel, relief="flat")
        
        # 버튼 스타일
        self.style.configure("Accent.TButton", 
                             background=self.color_accent, 
                             foreground=self.color_text, 
                             bordercolor=self.color_accent, 
                             font=("Segoe UI", 10, "bold"),
                             padding=8)
        self.style.map("Accent.TButton",
                       background=[("active", "#4f46e5"), ("pressed", "#4338ca")])

        self.style.configure("Stop.TButton", 
                             background=self.color_red, 
                             foreground=self.color_text, 
                             bordercolor=self.color_red, 
                             font=("Segoe UI", 10, "bold"),
                             padding=8)
        self.style.map("Stop.TButton",
                       background=[("active", "#dc2626"), ("pressed", "#b91c1c")])

        self.style.configure("Action.TButton", 
                             background="#1f2937", 
                             foreground=self.color_text, 
                             bordercolor="#374151", 
                             font=("Segoe UI", 9, "bold"),
                             padding=6)
        self.style.map("Action.TButton",
                       background=[("active", "#374151")])

        # 체크박스 및 콤보박스 스타일
        self.style.configure("TCheckbutton", 
                             background=self.color_panel, 
                             foreground=self.color_text, 
                             font=("Segoe UI", 9))
        
        self.style.configure("TCombobox", 
                             fieldbackground="#1f2937", 
                             background="#111827", 
                             foreground=self.color_text, 
                             darkcolor="#111827", 
                             lightcolor="#374151", 
                             arrowcolor=self.color_accent)

        # Treeview 다크 스타일
        self.style.configure("Treeview", 
                             background="#111827", 
                             foreground=self.color_text, 
                             fieldbackground="#111827", 
                             rowheight=26, 
                             font=("Segoe UI", 9))
        self.style.configure("Treeview.Heading", 
                             background="#1f2937", 
                             foreground=self.color_accent, 
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Treeview", 
                       background=[("selected", self.color_accent)], 
                       foreground=[("selected", "#ffffff")])

    def _build_ui(self):
        """다크 테마 벤토 스타일 레이아웃 구성 (RAG 대시보드 내장형)"""
        # 상단 헤더
        header_frame = ttk.Frame(self.root, style="TFrame")
        header_frame.pack(fill="x", padx=25, pady=15)
        
        title_label = tk.Label(header_frame, text="⚡ Neo's Local RAG DB Manager & Desktop Shell", 
                               font=("Outfit", 20, "bold"), bg=self.color_bg, fg="#a5b4fc")
                               
        title_label.pack(side="left")
        
        subtitle_label = tk.Label(header_frame, text="HHI Shipyard Desktop Agent v2.0", 
                                  font=("Segoe UI", 9), bg=self.color_bg, fg=self.color_gray)
        subtitle_label.pack(side="left", padx=15, pady=9)

        # 메인 와이드 컨텐트 팬 분할 (좌측 컨트롤러 / 우측 RAG 탐색 및 로그)
        main_paned = ttk.Panedwindow(self.root, orient="horizontal")
        main_paned.pack(fill="both", expand=True, padx=20, pady=5)
        self.main_paned = main_paned

        # ==========================================
        # [좌측 프레임] 지식 등록기 및 OS 설정 (380px 고정)
        # ==========================================
        left_frame = ttk.Frame(main_paned, style="Panel.TFrame", padding=15)
        main_paned.add(left_frame, weight=3)

        # 1구역: DB 현황 요약
        db_sec = tk.LabelFrame(left_frame, text=" RAG 데이터베이스 현황 ", 
                               font=("Segoe UI", 9, "bold"), bg=self.color_panel, fg="#818cf8", bd=1, relief="solid")
        db_sec.pack(fill="x", pady=5, ipady=5)
        
        self.lbl_db_status = tk.Label(db_sec, text="● 정상 연결 상태 검사 중...", 
                                      font=("Segoe UI", 9, "bold"), bg=self.color_panel, fg=self.color_text, anchor="w")
        self.lbl_db_status.pack(fill="x", padx=10, pady=4)

        self.lbl_db_count = tk.Label(db_sec, text="● 보관된 지식 카드 개수: 로딩 중...", 
                                     font=("Segoe UI", 9, "bold"), bg=self.color_panel, fg=self.color_green, anchor="w")
        self.lbl_db_count.pack(fill="x", padx=10, pady=4)

        btn_grid_frame = ttk.Frame(db_sec, style="Panel.TFrame")
        btn_grid_frame.pack(fill="x", padx=10, pady=5)

        btn_db_check = ttk.Button(btn_grid_frame, text="FTS5 자가검사", 
                                  style="Action.TButton", command=self.initialize_db)
        btn_db_check.pack(side="left", fill="x", expand=True, padx=(0, 2))

        btn_db_refresh = ttk.Button(btn_grid_frame, text="🔄 데이터 갱신", 
                                    style="Action.TButton", command=self.manual_refresh)
        btn_db_refresh.pack(side="left", fill="x", expand=True, padx=(2, 0))

        btn_action_frame = ttk.Frame(db_sec, style="Panel.TFrame")
        btn_action_frame.pack(fill="x", padx=10, pady=(2, 5))

        btn_db_restart = ttk.Button(btn_action_frame, text="⚡ 앱 재시작 (Restart)", 
                                    style="Accent.TButton", command=self.restart_application)
        btn_db_restart.pack(side="left", fill="x", expand=True, padx=(0, 2))

        btn_db_exit = ttk.Button(btn_action_frame, text="🔴 완전 종료 (Exit)", 
                                 style="Stop.TButton", command=self.close_application)
        btn_db_exit.pack(side="left", fill="x", expand=True, padx=(2, 0))

        # 1.5구역: 📊 AI 토큰 실시간 모니터링 & 제어 (Bento Panel)
        token_sec = tk.LabelFrame(left_frame, text=" 📊 AI 일일 토큰 제어기 (Double-Click) ", 
                                  font=("Segoe UI", 9, "bold"), bg=self.color_panel, fg="#a5b4fc", bd=1, relief="solid")
        token_sec.pack(fill="x", pady=6, ipady=5)

        token_tree_frame = ttk.Frame(token_sec, style="Panel.TFrame")
        token_tree_frame.pack(fill="x", padx=10, pady=4)

        token_cols = ("model", "used", "limit", "rate")
        self.token_tree = ttk.Treeview(token_tree_frame, columns=token_cols, show="headings", style="Treeview", height=4)
        self.token_tree.pack(side="left", fill="x", expand=True)

        self.token_tree.heading("model", text="AI 모델")
        self.token_tree.heading("used", text="사용량")
        self.token_tree.heading("limit", text="한도")
        self.token_tree.heading("rate", text="사용율")

        self.token_tree.column("model", width=120, anchor="w")
        self.token_tree.column("used", width=75, anchor="e")
        self.token_tree.column("limit", width=75, anchor="e")
        self.token_tree.column("rate", width=55, anchor="center")

        # 더블 클릭 시 상세 시간 분석 카드 팝업 바인딩
        self.token_tree.bind("<Double-1>", self.show_token_detail)

        # 2구역: ⚡ 퀵 RAG 지식 직접 등록기 (Bento Input Card)
        ingest_sec = tk.LabelFrame(left_frame, text=" ⚡ 퀵 RAG 지식 직접 등록기 ", 
                                   font=("Segoe UI", 9, "bold"), bg=self.color_panel, fg="#818cf8", bd=1, relief="solid")
        ingest_sec.pack(fill="both", expand=True, pady=10, ipady=5)

        # 카테고리
        tk.Label(ingest_sec, text="카테고리:", bg=self.color_panel, fg=self.color_gray, font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=2)
        self.cmb_cat = ttk.Combobox(ingest_sec, values=["Flutter", "Python", "Java", "Web", "RAG/MCP", "C#", "Docker", "Database", "General"], style="TCombobox")
        self.cmb_cat.pack(fill="x", padx=10, pady=2)
        self.cmb_cat.set("General")

        # 이슈 요약 현상
        tk.Label(ingest_sec, text="이슈 요약 현상:", bg=self.color_panel, fg=self.color_gray, font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=2)
        self.ent_issue = ttk.Entry(ingest_sec, font=("Segoe UI", 9))
        self.ent_issue.pack(fill="x", padx=10, pady=2)

        # 근본 원인 분석
        tk.Label(ingest_sec, text="근본 원인 분석 (옵션):", bg=self.color_panel, fg=self.color_gray, font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=2)
        self.ent_cause = ttk.Entry(ingest_sec, font=("Segoe UI", 9))
        self.ent_cause.pack(fill="x", padx=10, pady=2)

        # 최적 해결 코드
        tk.Label(ingest_sec, text="최적 해결 코드 / 명세 가이드:", bg=self.color_panel, fg=self.color_gray, font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=2)
        self.txt_sol = scrolledtext.ScrolledText(ingest_sec, height=7, width=35, bg="#030712", fg="#f3f4f6", 
                                                 insertbackground="#6366f1", font=("Consolas", 9), 
                                                 relief="flat", highlightthickness=1, 
                                                 highlightcolor=self.color_accent, highlightbackground="#374151")
        self.txt_sol.pack(fill="both", expand=True, padx=10, pady=2)

        # 검색 태그
        tk.Label(ingest_sec, text="검색 태그 (쉼표 구분):", bg=self.color_panel, fg=self.color_gray, font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=2)
        self.ent_tags = ttk.Entry(ingest_sec, font=("Segoe UI", 9))
        self.ent_tags.pack(fill="x", padx=10, pady=2)

        # 주입 버튼
        btn_ingest = ttk.Button(ingest_sec, text="🚀 RAG 지식 즉각 주입 (Direct Ingest)", 
                                style="Accent.TButton", command=self.manual_ingest)
        btn_ingest.pack(fill="x", padx=10, pady=8)

        # 3구역: OS 설정
        startup_sec = ttk.Frame(left_frame, style="Panel.TFrame")
        startup_sec.pack(fill="x", pady=5)

        self.startup_var = tk.BooleanVar(value=False)
        self.chk_startup = ttk.Checkbutton(startup_sec, text="윈도우 부팅 시 자동 시작", 
                                           variable=self.startup_var, command=self.toggle_startup_registry)
        self.chk_startup.pack(anchor="w", padx=5, pady=2)

        # ==========================================
        # [우측 프레임] RAG 탐색 쉘 및 터미널 로그 (나머지 영역)
        # ==========================================
        right_frame = ttk.Frame(main_paned, style="TFrame")
        main_paned.add(right_frame, weight=7)

        # 상단과 하단을 나누는 내부 PanedWindow
        right_paned = ttk.Panedwindow(right_frame, orient="vertical")
        right_paned.pack(fill="both", expand=True)

        # 1구역: 🌌 RAG 지식 탐색 쉘 (Knowledge Explorer)
        explorer_sec = ttk.Frame(right_paned, style="Panel.TFrame", padding=12)
        right_paned.add(explorer_sec, weight=3)

        # 검색 컨트롤 프레임
        search_frame = ttk.Frame(explorer_sec, style="Panel.TFrame")
        search_frame.pack(fill="x", pady=3)

        tk.Label(search_frame, text="🌌 RAG 지식 탐색 쉘:", font=("Segoe UI", 10, "bold"), bg=self.color_panel, fg="#a5b4fc").pack(side="left")
        
        self.ent_search = ttk.Entry(search_frame, font=("Segoe UI", 9), width=35)
        self.ent_search.pack(side="left", padx=10)
        self.ent_search.bind("<Return>", lambda e: self.search_knowledge())

        btn_search = ttk.Button(search_frame, text="🔍 지식 검색", style="Action.TButton", command=self.search_knowledge)
        btn_search.pack(side="left", padx=3)

        btn_reset = ttk.Button(search_frame, text="🔄 전체 보기", style="Action.TButton", command=self.refresh_knowledge_list)
        btn_reset.pack(side="left", padx=3)

        btn_delete = ttk.Button(search_frame, text="❌ 선택 소거", style="Stop.TButton", command=self.delete_selected_knowledge)
        btn_delete.pack(side="right", padx=3)

        # 지식 리스트 Treeview
        tree_frame = ttk.Frame(explorer_sec, style="Panel.TFrame")
        tree_frame.pack(fill="both", expand=True, pady=8)

        columns = ("id", "category", "issue", "created_at")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", style="Treeview")
        self.tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.heading("id", text="ID")
        self.tree.heading("category", text="카테고리")
        self.tree.heading("issue", text="이슈 요약 현상")
        self.tree.heading("created_at", text="등록일시")

        self.tree.column("id", width=50, anchor="center")
        self.tree.column("category", width=90, anchor="center")
        self.tree.column("issue", width=380, anchor="w")
        self.tree.column("created_at", width=120, anchor="center")

        # 더블 클릭 시 카드 팝업 보기
        self.tree.bind("<Double-1>", self.show_knowledge_detail)

        # 2구역: 🖥 RAG 실시간 자율 학습 및 액션 로그 모니터
        console_sec = ttk.Frame(right_paned, style="Panel.TFrame", padding=10)
        right_paned.add(console_sec, weight=2)

        log_header_frame = ttk.Frame(console_sec, style="Panel.TFrame")
        log_header_frame.pack(fill="x", pady=2)

        console_title = tk.Label(log_header_frame, text="🖥 RAG 실시간 자율 학습 및 액션 로그 모니터", 
                                 font=("Segoe UI", 9, "bold"), bg=self.color_panel, fg="#a5b4fc", anchor="w")
        console_title.pack(side="left")

        # 🧹 로그 소거 버튼 추가
        btn_clear_log = ttk.Button(log_header_frame, text="🧹 로그 소거 (Clear)", 
                                   style="Action.TButton", command=self.clear_console_log)
        btn_clear_log.pack(side="right", padx=3)

        self.txt_log = scrolledtext.ScrolledText(console_sec, bg="#030712", fg="#34d399", 
                                                 insertbackground="#34d399", font=("Consolas", 9), 
                                                 relief="flat", bd=0, highlightthickness=1, 
                                                 highlightcolor=self.color_accent, highlightbackground="#1f2937")
        self.txt_log.pack(fill="both", expand=True, pady=3)
        
        self.write_console_log("SYSTEM", "Neo's RAG 데스크톱 인텔리전트 쉘 구동 준비 완료.")

    # =========================================================================
    # 시스템 트레이 기능 구현 (pystray & PIL 동적 이미지 빌드)
    # =========================================================================
    def _create_tray_icon(self):
        """자체 드로잉 엔진을 이용해 외부 리소스에 의존하지 않고 트레이 아이콘 가동"""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        lightning_coords = [(35, 5), (10, 35), (30, 35), (25, 59), (54, 25), (32, 25)]
        draw.polygon(lightning_coords, fill="#6366f1", outline="#818cf8")
        
        menu = (
            item('메인 창 열기 (Show)', self.show_from_tray, default=True),
            item('프로그램 완전 종료 (Exit)', self.close_application)
        )
        
        self.tray_icon = pystray.Icon("RAG_DB_Manager", img, "Neo's Local RAG DB Manager", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self):
        self.root.withdraw()
        if TRAY_SUPPORTED:
            try:
                self.tray_icon.notify("RAG DB Manager가 백그라운드에 상주합니다.", "여기서 더블클릭 하거나 메뉴로 제어가 가능합니다.")
            except Exception:
                pass
        self.write_console_log("SYSTEM", "윈도우 최소화: 백그라운드 트레이 모드로 전환되었습니다.")

    def show_from_tray(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    # =========================================================================
    # 실시간 파일 폴링 기반 자가 학습 모듈 (Zero-Touch Ingestion)
    # =========================================================================
    def start_file_watcher(self):
        """임시 적재 파일 감시 데몬 스레드 가동 (절대 경로 추적 로깅 보강)"""
        self.is_watching_files = True
        self.file_watcher_thread = threading.Thread(target=self._watch_pending_ingestion, daemon=True)
        self.file_watcher_thread.start()
        self.write_console_log("SYSTEM", f"★ [감시자] 비동기 자가 학습 감시 데몬 기동 완료. (감시 파일 절대 경로: {PENDING_FILE})")

    def _watch_pending_ingestion(self):
        """1초 주기로 pending_ingestion.json 및 rag_mcp_traffic.log를 검출하여 UI 및 DB 동기화 (디버깅 로그 포함)"""
        traffic_log_path = os.path.join(BASE_DIR, "rag_mcp_traffic.log")
        debug_log_path = os.path.join(BASE_DIR, "rag_communication_debug.log")
        
        def write_debug(msg):
            try:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                with open(debug_log_path, "a", encoding="utf-8") as df:
                    df.write(f"[{ts}] [MANAGER_DEBUG] {msg}\n")
            except Exception:
                pass

        while self.is_watching_files:
            # 1. 에이전트 실시간 통신 트래픽 로그 감시
            if os.path.exists(traffic_log_path) and os.path.getsize(traffic_log_path) > 0:
                lines = []
                read_success = False
                
                # 락 우회하며 읽기 시도 (최대 5회)
                for attempt in range(5):
                    try:
                        with open(traffic_log_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        read_success = True
                        break
                    except PermissionError as pe:
                        write_debug(f"⚠️ [읽기 락 충돌] 시도 {attempt+1}/5 | PermissionError: {str(pe)}")
                        time.sleep(0.05 * (attempt + 1))
                    except Exception as e:
                        write_debug(f"❌ [읽기 일반 에러] {str(e)}")
                        break

                if read_success and lines:
                    write_debug(f"📖 [로그 읽기 성공] 읽어들인 라인 수: {len(lines)}")
                    processed_any = False
                    
                    for line in lines:
                        if line.strip():
                            try:
                                log_data = json.loads(line.strip())
                                sender = log_data.get("sender", "AGENT_MCP")
                                msg = log_data.get("message", "")
                                self.root.after(0, self.write_console_log, sender, msg)
                                processed_any = True
                                
                                # 토큰 에이전트 실시간 소모 기록 감지 시 화면의 토큰 리스트 즉각 갱신
                                if sender == "TOKEN_AGENT":
                                    write_debug(f"📊 [토큰 감지] 파싱 시도 메시지: {msg}")
                                    if "모델:" in msg:
                                        try:
                                            import re
                                            match = re.search(r"모델:\s*([^|]+?)\s*\|\s*Input:\s*(\d+)\s*\|\s*Output:\s*(\d+)", msg)
                                            if match and self.engine:
                                                model_name = match.group(1).strip()
                                                in_t = int(match.group(2))
                                                out_t = int(match.group(3))
                                                
                                                write_debug(f"💾 [DB 누적] 모델: {model_name} | In: {in_t} | Out: {out_t}")
                                                # DB에 실시간 누적 합산 적재
                                                self.engine.record_token_usage(model_name, in_t, out_t)
                                                write_debug("💾 [DB 누적 완료] 정상 반영 성공")
                                            else:
                                                write_debug("⚠️ [토큰 파싱 실패] 정규식 패턴 불일치")
                                        except Exception as de:
                                            write_debug(f"❌ [DB 누적 에러] {str(de)}")
                                            self.root.after(0, self.write_console_log, "SYSTEM_ERROR", f"토큰 로그 실시간 DB 적재 실패: {str(de)}")
                                    
                                    self.root.after(0, self.refresh_token_usage)
                            except Exception as le:
                                write_debug(f"❌ [라인 파싱 실패] JSON 에러: {str(le)}")
                                pass

                    if processed_any:
                        # 락 우회하며 파일 소거 시도 (최대 5회)
                        for attempt in range(5):
                            try:
                                with open(traffic_log_path, "w", encoding="utf-8") as f:
                                    f.truncate(0)
                                write_debug("🧹 [로그 소거 완료] rag_mcp_traffic.log 초기화 성공")
                                break
                            except PermissionError as pe:
                                write_debug(f"⚠️ [소거 락 충돌] 시도 {attempt+1}/5 | PermissionError: {str(pe)}")
                                time.sleep(0.05 * (attempt + 1))
                            except Exception as e:
                                write_debug(f"❌ [소거 일반 에러] {str(e)}")
                                break

            # 2. 임시 적재 JSON 파일 감시 (수동/동기화 누락 건 자동 적재)
            if os.path.exists(PENDING_FILE):
                try:
                    self.root.after(0, self.write_console_log, "SELF_LEARN", "임시 적재 파일 pending_ingestion.json 검출 완료! 락 안착 대기 가동 (0.5s)...")
                    time.sleep(0.5) # 파일 쓰기 락 경합 방지용 안착 대기
                    
                    self.root.after(0, self.write_console_log, "SELF_LEARN", "파일 버퍼 스트림 오픈 시도...")
                    with open(PENDING_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    self.root.after(0, self.write_console_log, "SELF_LEARN", f"JSON 파싱 성공! 데이터 규격: {list(data.keys())}")
                    
                    # 데이터 필수성 정합성 체크
                    has_category = "category" in data
                    has_issue = "issue_summary" in data
                    has_solution = "solution_code" in data
                    
                    if has_category and has_issue and has_solution:
                        self.root.after(0, self.write_console_log, "SELF_LEARN", "정합성 검증 통과! 로컬 RAG 인덱싱 엔진 마운트 중...")
                        
                        new_id = self.engine.add_knowledge(
                            category=data["category"],
                            issue_summary=data["issue_summary"],
                            root_cause=data.get("root_cause", ""),
                            solution_code=data["solution_code"],
                            tags=data.get("tags", "")
                        )
                        
                        log_msg = (
                            f"★실시간 자가 학습 인덱싱 감지 성공! (신규 지식 ID: {new_id})\n"
                            f"   [분류/카테고리] : {data['category']}\n"
                            f"   [이슈 요약 현상] : {data['issue_summary']}\n"
                            f"   [근본 원인 분석] : {data.get('root_cause', '')}\n"
                            f"   [최적 해결 코드] : {data['solution_code'][:150]}...\n"
                            f"   [관련 검색 태그] : {data.get('tags', '')}\n"
                            f"--------------------------------------------------------------------------"
                        )
                        self.root.after(0, self.write_console_log, "SELF_LEARN", log_msg)
                        self.root.after(0, self._check_db_status)
                        self.root.after(0, self.refresh_knowledge_list)
                        self.root.after(0, self.refresh_token_usage)
                    else:
                        err_details = f"필수 키 누락! (category={has_category}, issue_summary={has_issue}, solution_code={has_solution})"
                        self.root.after(0, self.write_console_log, "SELF_LEARN_ERR", f"⚠️ 데이터 정합성 실패: {err_details}\n수신 원본 데이터: {json.dumps(data, ensure_ascii=False)}")
                    
                    self.root.after(0, self.write_console_log, "SELF_LEARN", "임시 적재 파일 pending_ingestion.json 안전 소거 수행...")
                    os.remove(PENDING_FILE)
                    self.root.after(0, self.write_console_log, "SELF_LEARN", "임시 파일 소거 완료! 다음 감시 대기 모드로 복귀합니다.")
                    
                except json.JSONDecodeError as je:
                    self.root.after(0, self.write_console_log, "SELF_LEARN_ERR", f"JSON 파싱 실패 (포맷 손상): {str(je)}")
                    try:
                        os.remove(PENDING_FILE)
                        self.root.after(0, self.write_console_log, "SELF_LEARN", "손상된 임시 파일 강제 소거 완료.")
                    except Exception:
                        pass
                except Exception as e:
                    self.root.after(0, self.write_console_log, "SELF_LEARN_ERR", f"자동 학습 처리 중 예외 발생: {str(e)}")
                    try:
                        os.remove(PENDING_FILE)
                    except Exception:
                        pass
            time.sleep(1.0) # 감시 주기를 3초에서 1초로 단축하여 극단적인 실시간성 확보

    # =========================================================================
    # RAG 다이렉트 쿼리 연동 비즈니스 로직
    # =========================================================================
    def manual_refresh(self):
        """수동으로 RAG DB 현황 및 지식 리스트 동기화"""
        self._check_db_status()
        self.refresh_knowledge_list()
        self.refresh_token_usage()
        self.write_console_log("SYSTEM", "🔄 수동 데이터베이스 동기화 및 실시간 데이터 갱신 완료.")

    def refresh_token_usage(self):
        """SQLite DB에서 모델별 토큰 사용량 데이터를 가져와 리스트 갱신"""
        if not self.engine:
            return
        try:
            # Treeview 초기화
            for item in self.token_tree.get_children():
                self.token_tree.delete(item)
            
            usage_data = self.engine.get_all_token_usage()
            for u in usage_data:
                used = u["used_tokens_today"]
                limit = u["limit_tpd"]
                rate = (used / limit * 100) if limit > 0 else 0.0
                
                # 가독성 높은 쉼표 포맷팅
                used_str = f"{used:,}"
                limit_str = f"{limit:,}"
                rate_str = f"{rate:.1f}%"
                
                self.token_tree.insert("", "end", values=(u["model_name"], used_str, limit_str, rate_str))
        except Exception as e:
            self.write_console_log("SYSTEM_ERROR", f"토큰 사용 정보 로드 실패: {str(e)}")

    def show_token_detail(self, event):
        """더블 클릭 시 해당 AI 모델의 시작/마지막 대화 및 정밀 잔여 정보 상세 팝업"""
        selected = self.token_tree.selection()
        if not selected:
            return
        
        item_data = self.token_tree.item(selected[0])
        model_name = item_data["values"][0]
        
        try:
            usage_data = self.engine.get_all_token_usage()
            target = None
            for u in usage_data:
                if u["model_name"] == model_name:
                    target = u
                    break
            
            if not target:
                return
                
            used = target["used_tokens_today"]
            limit = target["limit_tpd"]
            left = max(limit - used, 0)
            first_chat = target["first_chat_today"] if target["first_chat_today"] else "기록 없음"
            last_chat = target["last_chat_today"] if target["last_chat_today"] else "기록 없음"
            
            # 고급스러운 팝업 모달 생성
            pop = tk.Toplevel(self.root)
            pop.title(f"📊 AI Token Analysis: {model_name}")
            pop.geometry("450x300")
            pop.configure(bg=self.color_panel)
            pop.transient(self.root)
            pop.grab_set()
            
            # 레이블 레이아웃
            tk.Label(pop, text=f"📊 {model_name} 토큰 정밀 모니터", font=("Outfit", 12, "bold"), bg=self.color_panel, fg=self.color_accent).pack(pady=15)
            
            info_frame = ttk.Frame(pop, style="Panel.TFrame")
            info_frame.pack(fill="both", expand=True, padx=25)
            
            details = [
                ("일일 제한 한도", f"{limit:,} tokens"),
                ("오늘 소모량", f"{used:,} tokens"),
                ("남은 사용 가능량", f"{left:,} tokens"),
                ("오늘 첫 대화 일시", first_chat),
                ("마지막 대화 일시", last_chat)
            ]
            
            for i, (label, val) in enumerate(details):
                lbl_color = self.color_gray if "일시" in label else self.color_text
                val_color = self.color_green if "남은" in label else (self.color_red if "소모" in label else self.color_text)
                
                tk.Label(info_frame, text=label, font=("Segoe UI", 9), bg=self.color_panel, fg=lbl_color).grid(row=i, column=0, sticky="w", pady=4)
                tk.Label(info_frame, text=val, font=("Segoe UI", 9, "bold"), bg=self.color_panel, fg=val_color).grid(row=i, column=1, sticky="e", pady=4)
                
            info_frame.grid_columnconfigure(0, weight=1)
            info_frame.grid_columnconfigure(1, weight=1)
            
            # 닫기 버튼
            ttk.Button(pop, text="닫기 (Close)", style="Action.TButton", command=pop.destroy).pack(pady=15)
            
        except Exception as e:
            self.write_console_log("SYSTEM_ERROR", f"토큰 상세 보기 실패: {str(e)}")

    def refresh_knowledge_list(self):
        """SQLite DB에서 전체 리스트를 즉각 다이렉트로 가져와 리스트 갱신"""
        if not self.engine:
            return
        
        try:
            # Treeview 초기화
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            records = self.engine.get_all_knowledge()
            for r in records:
                self.tree.insert("", "end", values=(r["id"], r["category"], r["issue_summary"], r["created_at"]))
            
            # DB 통계 업데이트
            self.lbl_db_count.configure(text=f"● 보관된 지식 카드 개수: {len(records)} 개", fg=self.color_green)
            
        except Exception as e:
            self.write_console_log("SYSTEM_ERROR", f"지식 카드 목록 로드 실패: {str(e)}")

    def search_knowledge(self):
        """하이브리드 키워드/태그 FTS5 검색 실행 및 액션 로그 스트리밍"""
        if not self.engine:
            return
        
        query = self.ent_search.get().strip()
        if not query:
            self.refresh_knowledge_list()
            return
        
        try:
            for item in self.tree.get_children():
                self.tree.delete(item)
                
            records = self.engine.hybrid_search(query)
            for r in records:
                self.tree.insert("", "end", values=(r["id"], r["category"], r["issue_summary"], r["created_at"]))
            
            log_msg = f"'{query}' 키워드로 RAG 하이브리드 검색을 수행했습니다. (검출된 지식 카드: {len(records)}개)"
            self.write_console_log("USER_ACTION", log_msg)
            
        except Exception as e:
            self.write_console_log("SYSTEM_ERROR", f"검색 수행 중 에러: {str(e)}")

    def manual_ingest(self):
        """수동 입력 폼에서 데이터 직접 DB 주입 완료 후 UI 즉각 동기화"""
        if not self.engine:
            messagebox.showerror("오류", "로컬 RAG 엔진이 정상적으로 로드되지 않았습니다.")
            return

        cat = self.cmb_cat.get().strip()
        issue = self.ent_issue.get().strip()
        cause = self.ent_cause.get().strip()
        sol = self.txt_sol.get("1.0", tk.END).strip()
        tags = self.ent_tags.get().strip()

        if not issue or not sol:
            messagebox.showwarning("입력 누락", "이슈 요약 현상과 최적 해결 코드는 필수적으로 입력하셔야 합니다.")
            return

        try:
            new_id = self.engine.add_knowledge(
                category=cat,
                issue_summary=issue,
                root_cause=cause,
                solution_code=sol,
                tags=tags
            )

            # 성공 로그 출력
            self.write_console_log("USER_ACTION", f"수동 지식 주입 성공! (신규 카드 ID: {new_id} / 분류: {cat})")
            
            # 입력 폼 청소
            self.ent_issue.delete(0, tk.END)
            self.ent_cause.delete(0, tk.END)
            self.txt_sol.delete("1.0", tk.END)
            self.ent_tags.delete(0, tk.END)

            # 대시보드 리스트 동기화
            self.refresh_knowledge_list()
            self._check_db_status()
            
            messagebox.showinfo("RAG 주입 완료", f"신규 지식 카드 #{new_id}가 RAG DB에 자율적으로 영구 적재되었습니다!")

        except Exception as e:
            self.write_console_log("USER_ACTION_ERR", f"수동 주입 실패: {str(e)}")
            messagebox.showerror("오류", f"RAG DB에 데이터를 직접 적재하는 도중 심각한 에러가 터졌습니다: {str(e)}")

    def delete_selected_knowledge(self):
        """선택한 지식 카드를 DB에서 안전 소거"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("선택 누락", "소거할 지식 카드를 리스트에서 먼저 선택하십시오.")
            return

        item_data = self.tree.item(selected[0])
        kb_id = item_data["values"][0]
        issue_name = item_data["values"][2]

        if not messagebox.askyesno("지식 카드 소거 확인", f"선택하신 지식 카드 #{kb_id}을 RAG DB에서 영구 소거하시겠습니까?\n\n이슈: {issue_name[:60]}..."):
            return

        try:
            self.engine.delete_knowledge(kb_id)
            self.write_console_log("USER_ACTION", f"선택 지식 소거 완료. (지식 ID: #{kb_id})")
            self.refresh_knowledge_list()
            self._check_db_status()
            messagebox.showinfo("소거 완료", f"지식 카드 #{kb_id}이 안전하게 소거되었습니다.")
        except Exception as e:
            self.write_console_log("SYSTEM_ERROR", f"소거 수행 실패: {str(e)}")
            messagebox.showerror("오류", f"지식 카드 소거 중 실패했습니다: {str(e)}")

    def show_knowledge_detail(self, event):
        """더블 클릭 시 극도로 고급스러운 다크 상세 지식 뷰 및 원클릭 복사 다이얼로그 팝업"""
        selected = self.tree.selection()
        if not selected:
            return

        item_data = self.tree.item(selected[0])
        kb_id = item_data["values"][0]

        try:
            # DB에서 상세 매핑 정보 획득
            records = self.engine.get_all_knowledge()
            target_record = None
            for r in records:
                if int(r["id"]) == int(kb_id):
                    target_record = r
                    break
            
            if not target_record:
                return

            self.write_console_log("USER_ACTION", f"지식 카드 #{kb_id} 더블클릭 상세조회 수행.")
            self._create_detail_popup(target_record)

        except Exception as e:
            self.write_console_log("SYSTEM_ERROR", f"상세 뷰어 생성 실패: {str(e)}")

    def _create_detail_popup(self, record):
        """다크 글래스모피즘 에스테틱 상세 지식 카드 팝업 다이얼로그"""
        pop = tk.Toplevel(self.root)
        pop.title(f"🌌 RAG Knowledge Card #{record['id']} [{record['category']}]")
        pop.geometry("820x650")
        pop.configure(bg=self.color_panel)
        pop.transient(self.root)
        pop.grab_set()

        # 헤더
        h_frame = ttk.Frame(pop, style="Panel.TFrame")
        h_frame.pack(fill="x", padx=20, pady=15)

        tk.Label(h_frame, text=f"🌌 RAG KNOWLEDGE CARD #{record['id']}", 
                 font=("Outfit", 14, "bold"), bg=self.color_panel, fg=self.color_accent).pack(side="left")
        
        tk.Label(h_frame, text=f"분류: {record['category']} | 등록일: {record['created_at']}", 
                 font=("Segoe UI", 9), bg=self.color_panel, fg=self.color_gray).pack(side="right", pady=3)

        # 내용 스크롤 프레임
        body_frame = ttk.Frame(pop, style="Panel.TFrame")
        body_frame.pack(fill="both", expand=True, padx=20, pady=5)

        # 이슈 요약
        tk.Label(body_frame, text="▶ 이슈 요약 현상", font=("Segoe UI", 10, "bold"), bg=self.color_panel, fg="#f3f4f6").pack(anchor="w", pady=2)
        lbl_issue = tk.Message(body_frame, text=record["issue_summary"], font=("Segoe UI", 9), bg="#1f2937", fg="#f3f4f6", width=760, relief="flat", bd=0, padx=10, pady=8)
        lbl_issue.pack(fill="x", pady=4)

        # 근본 원인
        if record.get("root_cause"):
            tk.Label(body_frame, text="▶ 근본 원인 분석", font=("Segoe UI", 10, "bold"), bg=self.color_panel, fg="#f3f4f6").pack(anchor="w", pady=2)
            lbl_ca
          use = tk.Message(body_frame, text=record["root_cause"], font=("Segoe UI", 9), bg="#1f2937", fg="#e5e7eb", width=760, relief="flat", bd=0, padx=10, pady=8)
            lbl_cause.pack(fill="x", pady=4)

        # 최적 해결 코드 블록 (ScrolledText)
        tk.Label(body_frame, text="▶ 최적 해결 코드 / 명세 가이드", font=("Segoe UI", 10, "bold"), bg=self.color_panel, fg=self.color_green).pack(anchor="w", pady=2)
        txt_code = scrolledtext.ScrolledText(body_frame, height=13, bg="#030712", fg="#34d399", 
                                             insertbackground="#34d399", font=("Consolas", 10), 
                                             relief="flat")
        txt_code.pack(fill="both", expand=True, pady=4)
        txt_code.insert(tk.END, record["solution_code"])
        txt_code.configure(state="disabled")

        # 클립보드 복사 액션 버튼
        def copy_code():
            self.root.clipboard_clear()
            self.root.clipboard_append(record["solution_code"])
            self.write_console_log("USER_ACTION", f"지식 카드 #{record['id']}의 최적 해결 코드를 클립보드로 전격 복사 완료!")
            messagebox.showinfo("복사 성공", "코드가 클립보드에 무결하게 안전 복사되었습니다!", parent=pop)

        btn_copy = ttk.Button(body_frame, text="⚡ 해결 코드 클립보드 원클릭 복사 (Copy to Clipboard)", 
                              style="Accent.TButton", command=copy_code)
        btn_copy.pack(fill="x", pady=12)

    # =========================================================================
    # 부속 상태 제어용 시스템 함수들
    # =========================================================================
    def clear_console_log(self):
        """실시간 콘솔 텍스트 위젯 로그를 깨끗하게 비웁니다."""
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.configure(state="disabled")
        self.write_console_log("SYSTEM", "🧹 콘솔 실시간 스트리밍 로그가 사용자에 의해 초기화되었습니다.")

    def write_console_log(self, sender, message):
        """타임스탬프 기반 스트리밍 터미널 출력기"""
        if not message:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] [{sender}] {message.strip()}\n"
        
        self.txt_log.configure(state="normal")
        self.txt_log.insert(tk.END, formatted)
        self.txt_log.configure(state="disabled")
        self.txt_log.see(tk.END)

    def _check_db_status(self):
        if os.path.exists(DB_FILE):
            db_size = os.path.getsize(DB_FILE) / 1024.0
            self.lbl_db_status.configure(text=f"● 정상 연결 (경로: {os.path.basename(DB_FILE)} / 용량: {db_size:.1f} KB)", fg=self.color_green)
            self.write_console_log("DATABASE", f"SQLite RAG DB 정상 바인딩 완료. (용량: {db_size:.1f} KB)")
        else:
            self.lbl_db_status.configure(text="● 데이터베이스 부재", fg=self.color_red)
            self.write_console_log("DATABASE", "경고: local_knowledge_rag.db 데이터베이스가 식별되지 않았습니다.")

    def initialize_db(self):
        try:
            self.write_console_log("DATABASE", "데이터베이스 FTS5 테이블 무결성 검증 착수...")
            if not self.engine:
                sys.path.append(BASE_DIR)
                from local_rag_engine import LocalRAGEngine
                self.engine = LocalRAGEngine()
            
            self._check_db_status()
            self.refresh_knowledge_list()
            messagebox.showinfo("무결성 검사 성공", "SQLite FTS5 RAG 데이터베이스를 성공적으로 검증 및 바인딩 완료했습니다!")
        except Exception as e:
            self.write_console_log("DATABASE_ERROR", f"DB 초기화 및 검증 실패: {str(e)}")
            messagebox.showerror("오류", f"데이터베이스 검증 과정에서 심각한 오류가 발생했습니다: {str(e)}")

    def _check_startup_registry(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ)
            value, reg_type = winreg.QueryValueEx(key, REG_VAL_NAME)
            winreg.CloseKey(key)
            self.startup_var.set(True)
            self.write_console_log("SYSTEM", "윈도우 시작 프로그램에 이미 등록되어 있습니다.")
        except FileNotFoundError:
            self.startup_var.set(False)
        except Exception as e:
            self.write_console_log("SYSTEM_ERROR", f"시작 프로그램 레지스트리 분석 실패: {str(e)}")

    def toggle_startup_registry(self):
        if self.startup_var.get():
            try:
                executable_path = sys.executable.replace("python.exe", "pythonw.exe")
                cmd_value = f'"{executable_path}" "{os.path.join(BASE_DIR, "local_rag_manager.py")}" --startup'
                
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_WRITE)
                winreg.SetValueEx(key, REG_VAL_NAME, 0, winreg.REG_SZ, cmd_value)
                winreg.CloseKey(key)
                
                self.write_console_log("SYSTEM", "성공: Windows 시작 프로그램 레지스트리에 RAG DB Manager를 추가 완료했습니다.")
            except Exception as e:
                self.startup_var.set(False)
                self.write_console_log("SYSTEM_ERROR", f"시작 프로그램 레지스트리 등록 실패: {str(e)}")
                messagebox.showerror("오류", f"레지스트리 쓰기 중 에러가 발생했습니다: {str(e)}")
        else:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_WRITE)
                winreg.DeleteValue(key, REG_VAL_NAME)
                winreg.CloseKey(key)
                self.write_console_log("SYSTEM", "성공: Windows 시작 프로그램 레지스트리에서 정상 제외되었습니다.")
            except FileNotFoundError:
                pass
            except Exception as e:
                self.write_console_log("SYSTEM_ERROR", f"레지스트리 키 삭제 실패: {str(e)}")
                messagebox.showerror("오류", f"레지스트리 값 해제 중 에러가 발생했습니다: {str(e)}")

    def restart_application(self):
        """현재 어플리케이션을 안전하게 셧다운하고 즉시 새 인스턴스로 핫 재시작"""
        self.is_watching_files = False
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()
        
        # 새 인스턴스를 띄우기 직전에 윈도우 타이틀 기준 좀비 및 다른 구버전 매니저 강제 셧다운
        import subprocess
        subprocess.run('taskkill /F /FI "WINDOWTITLE eq *Neo\'s Local RAG DB Manager*" /T', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 현재 실행중인 파이썬 및 파일 경로로 새 프로세스 가동
        subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "local_rag_manager.py")] + sys.argv[1:])
        sys.exit(0)

    def close_application(self):
        self.is_watching_files = False
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()
        
        # 나를 포함해 'Neo's Local RAG DB Manager' 창 타이틀을 가진 모든 프로세스를 윈도우 커널 수준에서 강제 완전 소거
        import subprocess
        subprocess.run('taskkill /F /FI "WINDOWTITLE eq *Neo\'s Local RAG DB Manager*" /T', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sys.exit(0)

    def _force_sash_ratio(self):
        """좌우 레이아웃 창 분할을 3:7 비율로 강제 정렬"""
        try:
            # 1180px 기준 30% 영역인 354px로 구분선 강제 이동
            self.main_paned.sashpos(0, 354)
        except Exception:
            pass

if __name__ == "__main__":
    _ensure_single_instance()  # 🔒 1순위: 중복 기동 방지를 위한 포트 뮤텍스 락 가동
    
    auto_start = len(sys.argv) > 1 and sys.argv[1] == "--startup"
    
    root = tk.Tk()
    app = RAGManagerApp(root)
    
    if auto_start:
        app.write_console_log("SYSTEM", "Windows 부팅 시작 매개변수를 인식하여 트레이 상주 기동 완료.")
        app.hide_to_tray()
        
    root.mainloop()
