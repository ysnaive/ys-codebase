# 技術調研報告：agents-workflow 模組業務代碼五維度靜態診斷與重構處方箋 (R02_code_optimization_audit.md)

> 調研主題：agents-workflow 模組業務代碼五維度靜態診斷與結構收斂處方 (Module Scope × Mode A)  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

### 1.1 定錨基準與範圍摘要 (Scope & Lifecycle Anchor)
- **檢視範圍 (`Scope`)**：`Module Scope`（`ys_codebase/source/agents-workflow/` 全量業務生產源碼，排除 `tests/` 與靜態 Markdown 模板/技能資產；涵蓋 `agents_workflow/` 核心套件、`agents_workflow/plans/` 計畫工具鏈子套件、`scripts/` CLI 與微內核生命週期掛鉤，以及 `contributes/*.json` / `manifest.json` 宣告契約，共 19 個 Python 業務源碼檔案，總計約 6,290 LOC）。
- **生命週期模式 (`Lifecycle Mode`)**：`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`——強制單一正統入口（Single Canonical Entry），零容忍物理拔除過渡相容別名、薄轉發包裝方法（Pass-through Wrappers）、未綁定之冗餘參數與死代碼，並同步更新所有調用點。

### 1.2 核心問題與痛點
1. **高耦合與巨型檔案破窗 (`God File / Long Procedures`)**：
   - `publisher.py`（955 行）、`verifier.py`（935 行）、`_trace_parser.py`（898 行）、`session_trace.py`（868 行）、`roadmap.py`（859 行）、`compiler.py`（770 行）與 `scripts/cli.py`（748 行）共 7 個核心檔案超過 700~950 行。
   - 多個核心業務方法（如 `PlanVerifier._verify_markdown_file` 達 261 行、`SessionTraceEngine.analyze` 達 193 行、`ArtifactCompiler.resolve_single_artifact` 達 151 行、`PlanVerifier.verify_plan` 達 135 行、`SessionTraceEngine._analyze_telemetry` 達 153 行）混雜宏觀業務階段編排與底層正則解析、字串拼接及 I/O 細節，違反單一抽象層級原則（SLAP）。
2. **`Mode A` 下殘留大量薄轉發包裝層與相容別名 (`Pass-through Wrappers & Legacy Aliases`)**：
   - 先前將 `_verifier_specs.py`、`_verifier_healer.py`、`_trace_parser.py`、`_trace_renderer.py` 與 `_common.py` 拆分出去後，`PlanVerifier`、`PlanStatusResolver`、`SessionTraceEngine` 與 `_common.py` 內部仍留存 13 個僅做單行轉發的假性方法與別名（如 `_resolve_uri_path = resolve_plan_uri`、`PlanStatusResolver.parse_header_metadata`、`PlanVerifier._infer_deterministic_header_values` 等）。
3. **跨模組/跨檔案基礎設施重複造輪子 (`Infrastructure Duplication`)**：
   - 語意 URI 解析（`workflow.plans://`、`workflow.archived://`、`project://` 等）分別在 `plans/_common.py`（`resolve_plan_uri`）、`roadmap.py`（`_resolve_workflow_dir`）、`plans/session_trace.py`（`_resolve_uri_safe`）、`initializer.py`（`_resolve_physical_path`）與 `publisher.py` 中各自實作相似的 `try: from core import uri ... except: fallback` 邏輯。
   - `sys.path` 動態掛載 `core` 的啟動樣板在 `compiler.py:L15-L25`、`publisher.py:L21-L31` 與 `scripts/hook.core.py:L9-L25` 重複出現三次。
   - 計畫目錄與 `sub_XX` 子計畫路徑解析邏輯在 `PlanScanner.resolve_target_plan_dir`（`scanner.py:L235-L293`）與 `PlanVerifier.verify_plan`（`verifier.py:L801-L820`）中重複實作。

### 1.3 調研目標
1. 盤點 `agents-workflow` 在 `Mode A` 下的對外契約邊界、可物理拔除之相容別名/薄轉發層，以及需同步改寫之調用方座標。
2. 執行微觀（單檔方法級）至中觀（模組拓撲級）之 `D1~D5` 五維度靜態診斷並按 `P0 / P1 / P2` 定級。
3. 制定遵守「四大防過度設計紅線」的 `S1~S6` 外科手術無損重構處方箋。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 契約邊界與內部工具函式查驗表 (`Mode A` Convergence Audit)

#### (A) 對外公開與跨組件正統入口清單（Single Canonical Entries）
| 入口類別 | 正統檔案與符號 | 綁定來源 / 跨模組調用查驗 | `Mode A` 處置策略 |
| :--- | :--- | :--- | :--- |
| **CLI 命令入口** | `scripts/cli.py`：`plan` (`plan_archive`, `plan_status`, `plan_search`, `plan_verify`)、`release`、`release_target`、`compile`、`roadmap` (`roadmap_list`, `roadmap_promote`)、`todo` (`todo_add`, `todo_list`, `todo_promote`)、`tokens`、`list`、`init`、`session_trace` | `contributes/core.json` 宣告之 CLI 命令樹；由 `core` 命令分發器動態調用 | 維持命令簽名與退出碼契約；內部消除重複子命令分派樣板（`S3`/`S4`） |
| **微內核 Hook 入口** | `scripts/hook.core.py` (`on_reload`, `on_pre_cli_dispatch`)、`scripts/hook.dev.py` (`on_test_setup`, `on_test_teardown`) | `core` 生命週期與 `dev` 沙盒掛鉤動態調用 | 維持 Hook 函式簽名；清理 `hook.dev.py` 未使用之匯入與 `hook.core.py` 重複之 `sys.path` 探測 |
| **套件頂層匯出** | `agents_workflow/__init__.py`、`agents_workflow/plans/__init__.py` | 全空間 `knowledge-db callers` 查驗確認：`core`、`dev`、`server`、`knowledge-db` 均為 0 反向 Python import；所有調用皆在 `agents-workflow` 模組內部與測試集 | 收斂 `__all__`，物理移除 `_resolve_uri_path` 等廢棄轉發符號 |

#### (B) `Mode A` 強制物理拔除之相容別名、死代碼與薄轉發層清冊（Callers to Update）
| 序號 | 擬物理拔除之符號 / 結構 | 定義座標 | 內部生產調用方座標 (`Callers to Update`) | `Mode A` 收斂動作 |
| :---: | :--- | :--- | :--- | :--- |
| **1** | `_resolve_uri_path`（`resolve_plan_uri` 之舊別名） | `agents_workflow/plans/_common.py:L40`<br>`agents_workflow/plans/__init__.py:L8, L51` | 生產代碼 **0 調用** | 直接物理刪除別名定義與 `__init__.py` 匯出 |
| **2** | `from core import config`（未引用之死匯入） | `scripts/hook.dev.py:L6` | 生產代碼 **0 調用** | 直接刪除未使用之匯入 |
| **3** | `WorkflowInitializer.__init__(self, host_dir=None)` 空建構子 | `agents_workflow/initializer.py:L27-L28` | `scripts/cli.py:L439`（未傳參數） | 若保留 `host_dir` 則綁定 `self.host_dir = host_dir` 並用於 `_resolve_physical_path`，否則移除無意義空參數 |
| **4** | `PlanStatusResolver.parse_header_metadata` 薄轉發方法 | `agents_workflow/plans/status.py:L70-L81` | `status.py:L110` (`get_doc_header_status`)<br>`status.py:L198` (`get_doc_header_model`) | 刪除包裝方法，內部直接呼叫 `_common.parse_markdown_blockquote_headers` |
| **5** | `PlanVerifier.parse_plan_header` 薄轉發方法 | `agents_workflow/plans/verifier.py:L174-L177` | `verifier.py:L419` (`_verify_markdown_file`) | 刪除包裝方法，直接呼叫 `parse_markdown_blockquote_headers` |
| **6** | `PlanVerifier.normalize_header_title` 薄轉發方法 | `agents_workflow/plans/verifier.py:L179-L182` | `verifier.py:L407` (`_verify_markdown_file`) | 刪除包裝方法，直接呼叫 `_verifier_specs.normalize_header_title` |
| **7** | `PlanVerifier._is_header_match` 薄轉發方法 | `agents_workflow/plans/verifier.py:L194-L197` | `verifier.py:L412` (`_verify_markdown_file`) | 刪除包裝方法，直接呼叫 `_verifier_specs.is_header_match` |
| **8** | `PlanVerifier._map_file_to_template` 薄轉發方法 | `agents_workflow/plans/verifier.py:L199-L201` | `verifier.py:L397` (`_verify_markdown_file`) | 刪除包裝方法，直接呼叫 `map_file_to_template(rel_file_name, self.templates_dir)` |
| **9** | `PlanVerifier._infer_deterministic_header_values` 薄轉發方法 | `agents_workflow/plans/verifier.py:L322-L324` | `verifier.py:L460` (`_verify_markdown_file`) | 刪除包裝方法，直接呼叫 `_verifier_healer.infer_deterministic_header_values` |
| **10** | `PlanVerifier._auto_heal_deterministic_headers` 薄轉發方法 | `agents_workflow/plans/verifier.py:L326-L334` | `verifier.py:L446` (`_verify_markdown_file`) | 刪除包裝方法，直接呼叫 `_verifier_healer.auto_heal_deterministic_headers` |
| **11** | `PlanVerifier.extract_requirement_ids` 薄轉發方法 | `agents_workflow/plans/verifier.py:L598-L601` | `verifier.py:L701` (`_check_cross_file_and_traceability`) | 刪除包裝方法，直接呼叫 `_verifier_specs.extract_requirement_ids` |
| **12** | `PlanVerifier._resolve_effective_phase` 未被呼叫之轉發方法 | `agents_workflow/plans/verifier.py:L603-L606` | 生產代碼 **0 調用**（實際在 `_verifier_healer.py:L145` 內部直呼） | 直接物理刪除 `PlanVerifier._resolve_effective_phase` |
| **13** | `PlanVerifier._resolve_companion_model` 與 `_auto_heal_companions` 與 `append_changelog_entry` 薄轉發方法 | `agents_workflow/plans/verifier.py:L608-L625, L723-L731` | `verifier.py:L873, L919, L920`<br>`roadmap.py:L83-L89` (`_append_promoted_changelog`) | 刪除 `PlanVerifier` 內薄轉發，讓 `verifier.py` 與 `roadmap.py` 直接調用 `_verifier_healer` 之正統函式（解除 `roadmap.py -> PlanVerifier` 之重型耦合） |
| **14** | `SessionTraceEngine._parse_transcript_file` 與 `render_session_list_text` 薄轉發方法 | `agents_workflow/plans/session_trace.py:L278-L282, L670-L673` | `session_trace.py:L618, L697`<br>`scripts/cli.py:L723` | 刪除包裝方法，直接呼叫 `parse_transcript_file` 與 `render_session_list_text` |

---

### 2.2 重構候選方案對比

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：全量拆碎為微型類別與策略工廠** | 將每個檢核規則、每個 CLI 子命令、每個階段轉換拆分為獨立 Strategy Class 與 Factory | 單一檔案極小（$<150$ 行） | 嚴重違反「防過度設計紅線 ② & ③」，產生大量奈米類別與跨檔跳轉成本 | ⭐☆☆☆☆ (不採用) |
| **方案 B：外科手術階段管線化 (`S1~S5`) + 關鍵破窗物理拆檔 (`S6`) + `Mode A` 單一入口收斂** | 1. 拔除 14 處薄轉發與死代碼 (`Mode A`)；<br>2. 收斂共用 URI/Config/Markdown 基礎設施至 `_common.py`；<br>3. 將 `publisher.py`、`roadmap.py`、`verifier.py` 執行正交物理拆檔 (`S6`)；<br>4. 對超長方法執行業務階段拆解 (`S1`) 與無狀態純函式剝離 (`S2`) | • 徹底消滅 $>800$ 行破窗檔案<br>• 消除循環/交叉依賴與重複造輪子<br>• 100% 維持行為與錯誤語意等價 | 需同步更新模組內引用與對應測試匯入點（符合 `Mode A` 規範） | ⭐⭐⭐⭐⭐ (**推薦**) |
| **方案 C：僅做表層清理與註解打磨** | 僅刪除未使用變數與調整格式，不拆解長方法與大檔案 | 改動最小 | 無法解決 `P0/P1` 巨型方法混雜抽象層級與跨檔重複實作之結構腐化 | ⭐⭐☆☆☆ (不採用) |

### 3.1 `D1 ~ D5` 五維度分級靜態診斷矩陣

#### 維度總覽統計
- **`P0（高危破窗 / 巨型多職責檔案與架構耦合）`**：共 **4** 項
- **`P1（結構耦合 / 違反 SLAP / 假性實例方法 / 重複樣板 / 薄轉發殘留）`**：共 **12** 項
- **`P2（局部異味 / 魔術常數 / 段落註解與輕微冗餘）`**：共 **5** 項

#### 詳細病灶座標表 (`D1 ~ D5`)

| 編號 | 維度 | 嚴重度 | 檔案路徑與行號區間 | 具體結構病徵描述 | 對應處方 |
| :---: | :---: | :---: | :--- | :--- | :---: |
| **F-01** | `D1` | **`P0`** | `agents_workflow/publisher.py:L1-L955` | **巨型多職責破窗檔案 (955 LOC)**：`ReleasePublisher` 單一類別同時塞入來源檔案 SHA-1/SHA-256 雜湊快取計算（L61-L257）、Target 投影拓撲映射與 Header 巨集渲染（L259-L401）、`AGENTS.md` 與 `.gitignore` 軟合併/軟剝離字串演算法（L403-L449, L840-L942）以及 4 步原子發布交易編排（L450-L839），承載 4 個正交變更軸線。 | `S2`, `S6` |
| **F-02** | `D1` | **`P0`** | `agents_workflow/plans/verifier.py:L1-L935` | **巨型稽核類別與 261 行超長程序 (935 LOC)**：`PlanVerifier._verify_markdown_file`（L336-L596，共 261 行）與 `verify_plan`（L791-L925，共 135 行）將「程式碼區塊遮罩」、「HTML 註解檢查」、「佔位符正則掃描」、「動態模板章節比對與 TRIAGE 分級」、「Blockquote 標頭完整性與自癒觸發」、「Completed 狀態未勾選 Checkbox 掃描」及「P06/Revision 專屬 ID 矩陣驗證」全部塞在同一方法內，局部狀態交織嚴重。 | `S1`, `S2`, `S6` |
| **F-03** | `D1` | **`P0`** | `agents_workflow/roadmap.py:L1-L859` | **雙領域實體塞入單一巨型檔案 (859 LOC)**：同時承載 Tier 2 路線圖管理（`RoadmapItem`, `RoadmapManager` L98-L440）與 Tier 1 待辦帳本管理（`TodoItem`, `TodoManager` L112-L122, L443-L859）。且 `TodoManager.__init__`（L456）僅為取得 `roadmap_dir` 與 `plans_dir` 竟實例化整個 `RoadmapManager` 物件。 | `S2`, `S6` |
| **F-04** | `D2` | **`P0`** | `agents_workflow/publisher.py:L724`<br>`agents_workflow/targets.py:L138, L155`<br>`agents_workflow/roadmap.py:L46, L82`<br>`agents_workflow/plans/archiver.py:L80, L93`<br>`agents_workflow/plans/scanner.py:L40, L309` | **模組內雙向/交叉延遲匯入耦合 (Mutual Lazy-Import Cycles)**：<br>1. `targets.py` 匯入 `publisher.ReleasePublisher`，而 `publisher.py:L724` 又在方法內反向匯入 `targets.ReleaseTargetManager`；<br>2. `roadmap.py:L82` 為追加單行 `changelog.md`，竟反向匯入並實例化龐大的 `PlanVerifier(plans_dir)`，而實際邏輯早已在輕量模組 `_verifier_healer.append_changelog_entry` 中；<br>3. `scanner.py` 與 `status.py` 高度耦合但職責交錯。 | `S2`, `S6` |
| **F-05** | `D1` | **`P1`** | `agents_workflow/compiler.py:L352-L502`<br>`agents_workflow/compiler.py:L529-L630`<br>`agents_workflow/compiler.py:L642-L755` | **編譯器核心方法違反 SLAP 與閉包膨脹 (770 LOC)**：<br>1. `resolve_single_artifact`（151 行）混雜字面量遮罩、快照提取、3 種 insert 模式（`uri`/`computed`/`const` × `above`/`replace`/`below`）展開與殘留錨點清除；<br>2. `compile_stage1`（102 行）中「目錄型 Skill 項目」與「單檔型 Export 項目」存在高度重複的 `ExecutionContext` 建立、快取寫入與字典組裝邏輯；<br>3. `resolve_stage2_uri`（114 行）內部定義兩個龐大巢狀閉包 `_replace_in_fenced_block` 與 `_replace_in_code_span`，重複編寫 `__#{`、`__${`、`__%{` 三段替換與雙斜線清理邏輯。 | `S1`, `S3` |
| **F-06** | `D1` | **`P1`** | `agents_workflow/plans/session_trace.py:L158-L232, L429-L581, L675-L868` | **`SessionTraceEngine` 超長方法與假性實例方法 (868 LOC)**：<br>1. `analyze`（194 行）混雜 Transcript 定錨、計畫時間窗對齊、Telemetry 合併、Inferred CLI 補償、耗時計算與 50 行預設字典常數宣告（L767-L819）；<br>2. `_analyze_telemetry`（153 行）同時負責讀取過濾、Session 斷點切分、連續搜尋偵測、Gate 退件判定與統計彙總；<br>3. `_inspect_candidate_beacon`（75 行）與 `_parse_changelog_metadata`（36 行）未依賴可变實例狀態，可剝離為純函式。 | `S1`, `S2`, `S5` |
| **F-07** | `D1` | **`P1`** | `agents_workflow/plans/_trace_parser.py:L433-L537, L678-L898` | **Transcript 解析器長程序與多重職責 (898 LOC)**：`_process_tool_calls_in_step`（105 行）、`_compile_tier1_stats`（126 行）與 `parse_transcript_file`（93 行）過於龐大；單檔同時包含底層 `.jsonl` 跨宿主格式正規化、摩擦訊號狀態機與頂層 Token 報表彙編。 | `S1`, `S6` |
| **F-08** | `D2` | **`P1`** | `agents_workflow/plans/_common.py:L40`<br>`agents_workflow/plans/status.py:L70-L81`<br>`agents_workflow/plans/verifier.py:L174-L201, L322-L334, L598-L625, L723-L731`<br>`agents_workflow/plans/session_trace.py:L278-L282, L670-L673` | **`Mode A` 薄轉發包裝層與過渡別名殘留（共 14 處）**：詳見 §2.1 表 (B)。子模組拆分後於原類別保留的單行 Pass-through Wrappers 與 `_resolve_uri_path` 別名，在 `Mode A` 下屬零容忍冗餘代碼。 | `S2`, `S6` |
| **F-09** | `D3` | **`P1`** | `agents_workflow/plans/status.py:L69-L210`<br>`agents_workflow/plans/scanner.py:L30-L158` | **標頭文件讀取樣板重複與雙軌狀態推導重疊**：<br>1. `status.py` 中 `get_doc_header_status`（L94-L110）與 `get_doc_header_model`（L180-L198）重複編寫完全相同的 `Union[Path, str]` 判斷、檔案存在檢查、`read_text` 異常捕捉與前 35 行提取樣板；<br>2. `PlanScanner.get_plan_info`（`scanner.py:L30-L158`）與 `PlanStatusResolver.resolve_next_action`（`status.py:L212-L565`）各自維護一套 Track 判定順序（Umbrella -> Fast Track -> Full Track -> Revision -> Research -> P00 -> Seeded）。 | `S3`, `S4` |
| **F-10** | `D3` | **`P1`** | `agents_workflow/plans/scanner.py:L235-L293`<br>`agents_workflow/plans/verifier.py:L801-L820` | **目標計畫與 `sub_XX` 路徑解析邏輯重複**：`PlanVerifier.verify_plan` 自行硬編碼 20 行路徑解析與 `sub_XX` 唯一子計畫搜尋，與 `PlanScanner.resolve_target_plan_dir` 邏輯重複且缺少多同名 `sub_XX` 歧義攔截。 | `S3` |
| **F-11** | `D3` | **`P1`** | `scripts/cli.py:L275-L349, L560-L648` | **CLI 入口參數解析重複與長函式**：<br>1. `release_target`（L285-L329）中 `--add` 與 `--remove` 分支重複編寫複雜的三重 `or` 目標名稱提取邏輯；<br>2. `plan_verify`（89 行）混雜目標計畫自動定位與多層巢狀終端報表渲染。 | `S1`, `S3`, `S4` |
| **F-12** | `D3` | **`P1`** | `agents_workflow/plans/searcher.py:L51-L70`<br>`agents_workflow/plans/scanner.py:L173-L176`<br>`agents_workflow/plans/verifier.py:L930-L934` | **深層巢狀與計畫目錄枚舉重複 (Arrow Anti-pattern)**：`PlanSearcher.find_all_plans`（L62-L70）達 5 層 `for/if` 縮排；且「掃描 `plans_dir` 下符合 `^\d{4}_\d{2}_\d{2}` 之目錄」在 `searcher.py`、`scanner.py` 與 `verifier.py` 重複編寫。 | `S3`, `S4` |
| **F-13** | `D4` | **`P1`** | `agents_workflow/publisher.py:L450-L568, L616-L678` | **長參數列 (Long Parameter Lists, 9~10 個散裝參數)**：`ReleasePublisher._check_short_circuit`（10 個參數）、`_prepare_target_compilations`（5 個參數）、`_save_deployment_manifests`（10 個參數）跨階段傳遞大量散裝字典與清單，缺乏輕量上下文封裝。 | `S5` |
| **F-14** | `D4` | **`P1`** | `agents_workflow/initializer.py:L27-L28`<br>`agents_workflow/compiler.py:L233-L235`<br>`agents_workflow/publisher.py:L54-L56` | **建構子契約不一致 (`host_dir` 參數空置)**：`WorkflowInitializer.__init__(self, host_dir=None)` 接收 `host_dir` 卻直接 `pass` 丟棄；`ReleasePublisher.__init__` 儲存 `self.host_dir` 卻在 `release_all`（L716）與 `sync_gitignore`（L852）中直接呼叫 `os.getcwd()` 而忽略 `self.host_dir`。 | `S5` |
| **F-15** | `D5` | **`P1`** | `agents_workflow/compiler.py:L15-L25`<br>`agents_workflow/publisher.py:L21-L31`<br>`scripts/hook.core.py:L9-L25` | **跨檔案重複硬編碼 `sys.path` 探測樣板**：三個檔案頂部皆複製貼上相同的 `_this_dir / _pkg_root / _mods_root` 迴圈掛載 `core` 邏輯。 | `S3` |
| **F-16** | `D5` | **`P1`** | `agents_workflow/plans/_common.py:L15-L37`<br>`agents_workflow/roadmap.py:L18-L29, L136-L155`<br>`agents_workflow/plans/session_trace.py:L33-L44`<br>`agents_workflow/initializer.py:L45-L58` | **語意 URI 解析與退避機制各自為政**：4 處分別實作 `core.uri.resolve` 與本地退避邏輯，對 `!undefined` 判斷條件不一（`startswith("!undefined")` vs `startswith("!")`），且 `compiler.py:L175` 將 `workflow.archived://` 硬編碼退避為 `plans/archive`（少一個 `d`），與全系統標準 `plans/archived` 不一致！ | `S3`, `S5` |
| **F-17** | `D2` | **`P2`** | `scripts/hook.dev.py:L6` | **未使用之匯入**：`from core import config` 完全未被引用。 | `S2` |
| **F-18** | `D1` | **`P2`** | `agents_workflow/publisher.py:L259-L449`<br>`agents_workflow/targets.py:L18-L158` | **無狀態運算綁定於實例方法**：`ReleasePublisher.render_header`、`_soft_merge_agents_text`、`_soft_unmerge_agents_text`、`_to_project_uri`、`_resolve_project_uri` 完全不讀寫 `self` 狀態。 | `S2` |
| **F-19** | `D3` | **`P2`** | `agents_workflow/roadmap.py:L333-L440, L709-L859` | **`promote_roadmap`（108 行）與 `promote_todos`（151 行）長方法**：包含匹配驗證、目錄建立、檔案合併/搬移、Changelog 追加與長篇提示字串組裝。 | `S1` |
| **F-20** | `D5` | **`P2`** | `agents_workflow/plans/session_trace.py:L297, L477, L714`<br>`agents_workflow/plans/_trace_parser.py:L39, L189, L236, L314` | **散落魔術常數**：如 `1800.0`（30 分鐘 Session 閒置閾值）、`600.0`（歷史對齊容差）、`65536` / `196608`（Beacon 切片大小）、`160`（定點讀取行數上限）直接硬編碼於判斷式中。 | `S5` |
| **F-21** | `D3` | **`P2`** | `agents_workflow/plans/_verifier_healer.py:L177-L191, L271-L285` | **`changelog.md` 初始化樣板字串重複**：`auto_heal_companions` 與 `append_changelog_entry` 重複硬編碼完全相同的 15 行 `changelog.md` 初始 Markdown 結構。 | `S3` |

---

### 3.2 `S1 ~ S6` 外科手術重構處方箋 (Refactoring Blueprint)

#### 處方一：`S6` 正交職責之物理模組拆分與 `Mode A` 單一入口收斂
1. **統一基礎設施層 (`agents_workflow/_bootstrap.py` 或擴充 `agents_workflow/plans/_common.py`)**：
   - 收斂單一 `ensure_core_Importable()`（消除 `compiler.py`、`publisher.py`、`hook.core.py` 三處 `sys.path` 探測重複，`F-15`）。
   - 收斂統一的語意 URI 安全解析函式 `resolve_workflow_uri(uri_str, fallback_rel, host_dir=None)`，統一處理 `!undefined` / `!` 前綴與 `workflow.plans://`、`workflow.archived://`（修正 `compiler.py:L175` 誤寫為 `plans/archive` 之 Bug 隱患）、`workflow.docs://`、`workflow.roadmap://`、`project://` 退避邏輯（`F-16`）。
2. **拆分 `publisher.py` (955 行 $\to$ 雙模組正交分離，`F-01`, `F-18`)**：
   - 新增純運算輔助模組 `agents_workflow/_publisher_helpers.py`（或 `_merge_and_hash.py`）：下沉無狀態之 `_soft_merge_agents_text`、`_soft_unmerge_agents_text`、`render_header`、`_to_project_uri`、`_resolve_project_uri`、`.gitignore` 區塊合併純函式與檔案 SHA-1/SHA-256 計算邏輯。
   - `publisher.py` 專注於 `ReleasePublisher` 4 步原子交易編排與快取狀態管理，行數降至 $\le 480$ 行。
3. **拆分 `roadmap.py` (859 行 $\to$ 雙層儲備獨立或共用底層，`F-03`, `F-04`)**：
   - 將 Tier 1 待辦帳本（`TodoItem`, `TodoManager`）拆分為獨立模組 `agents_workflow/todo.py`（或 `agents_workflow/_todo_ledger.py`），並於 `agents_workflow/__init__.py` 維持匯出；`RoadmapManager` 與 `TodoManager` 共用 `_resolve_workflow_dir` 與 `_resolve_or_create_promoted_plan_dir`，徹底解除 `TodoManager.__init__` 實例化 `RoadmapManager` 的假性耦合。
   - `_append_promoted_changelog` 改為直接調用 `from .plans._verifier_healer import append_changelog_entry`，拔除對 `PlanVerifier` 的反向重型依賴（`F-04`）。
4. **解除 `targets.py` $\leftrightarrow$ `publisher.py` 雙向匯入 (`F-04`)**：
   - 將讀取 `config://agents-workflow` 之 `release_targets` 分類與聯集邏輯統一收斂於 `ReleaseTargetManager.get_classified_targets()`，`publisher.py` 頂層單向匯入 `ReleaseTargetManager`，或將純組態讀取下沉至共用 helper。
5. **`Mode A` 全面拔除 14 處薄轉發方法與廢棄別名 (`F-08`, `F-17`)**：
   - 依 §2.1 表 (B) 物理刪除 `_common._resolve_uri_path`、`hook.dev.config`、`PlanStatusResolver.parse_header_metadata`、`PlanVerifier` 內 9 個單行轉發方法與 `SessionTraceEngine` 內 2 個單行轉發方法，並同步更新模組內所有調用點。

#### 處方二：`S1` 業務階段拆解與主幹管線化 (SLAP)
1. **重構 `PlanVerifier._verify_markdown_file` (`verifier.py:L336-L596`，261 行 $\to$ 主幹 40 行 + 4 個具名階段函式，`F-02`)**：
   - `_strip_code_and_check_syntax(lines, rel_file_name, report) -> List[str]`：剝離 Fenced Code Blocks / Inline Code 並執行 HTML 註解與未替換佔位符檢核。
   - `_check_template_sections(lines, rel_file_name) -> Tuple[Optional[str], List[Tuple[str, str]], List[Tuple[str, str]]]`：比對動態模板章節標題。
   - `_verify_and_heal_headers(file_path, rel_file_name, lines, non_code_lines, is_sub_plan, missing_specs, enable_auto_heal, report)`：執行標頭欄位檢核、確定性標頭自癒與 Completed 狀態 Checkbox 檢查。
   - `_check_domain_id_matrix(lines, rel_file_name, report)`：執行 `P06_` (`FT/ET/RT-XX`) 與 `revision_log.md` (`[REV-XX]`) 專屬 ID 檢核。
2. **重構 `ArtifactCompiler` 核心管線 (`compiler.py`，`F-05`)**：
   - 於 `resolve_single_artifact` 中將「單一 Token 的 `matched_inserts` 內容解析與 `above/replace/below` 區塊組裝」提取為 `_evaluate_token_inserts(token_name, matched_inserts, context) -> Tuple[str, str]`。
   - 於 `compile_stage1` 提取 `_compile_and_cache_item(...)`，消除目錄型 Skill 與單檔型 Export 的重複迴圈體。
   - 於 `resolve_stage2_uri` 提取共用的 `_apply_stage2_tag_replacements(text, cur_dir, project_root, deployment_map, target_name, doc_basename)`，消除 `_replace_in_fenced_block` 與 `_replace_in_code_span` 之間 80% 重複的正則替換程式碼。
3. **重構 `SessionTraceEngine.analyze` 與 `_analyze_telemetry` (`session_trace.py`，`F-06`)**：
   - 將 `_analyze_telemetry` 拆解為 `_slice_session_telemetry_window(...)` 與 `_extract_telemetry_signals_and_stats(...)`。
   - 將 `analyze` 尾端 60 行之預設字典與 `session_stats` 組裝提取為 `_build_session_stats_payload(t1_stats, t2_stats, start_ts, end_ts)`。

#### 處方三：`S2` 無狀態邏輯剝離、`S3` 同構樣板聚合、`S4` 控制流扁平化与 `S5` 結構化契約
1. **聚合 Markdown 標頭讀取樣板 (`status.py`，`S3`，`F-09`)**：
   - 於 `PlanStatusResolver` 提取私有輔助方法 `_read_doc_headers(cls, doc_target: Union[Path, str]) -> Dict[str, str]`，集中處理 `Path | str` 讀取與前 35 行 Blockquote 解析，使 `get_doc_header_status` 與 `get_doc_header_model` 各縮減為 $\le 15$ 行。
2. **共用目標計畫目錄解析與活躍計畫列舉 (`scanner.py`, `verifier.py`, `searcher.py`，`S3`/`S4`，`F-10`, `F-12`)**：
   - 於 `_common.py` 提供 `iter_active_plan_dirs(plans_dir: Path) -> List[Path]`，統一 `^\d{4}_\d{2}_\d{2}` 過濾規則。
   - `PlanVerifier.verify_plan` 委派或共用路径解析輔助函式，消除與 `PlanScanner.resolve_target_plan_dir` 的重複邏輯。
   - 以衛語句（Guard Clauses）拉平 `PlanSearcher.find_all_plans` 與 `search_drs` 的 5 層縮排至 $\le 3$ 層。
3. **封裝發布上下文與常數集中化 (`publisher.py`, `session_trace.py`，`S5`，`F-13`, `F-14`, `F-20`)**：
   - 於 `publisher.py` 定義輕量 `@dataclass class _ReleaseContext`，封裝 `proj_root`、`proj_targets`、`local_targets`、`active_target_names`、`old_proj_manifest`、`old_local_manifest`、`proj_fingerprint`、`local_fingerprint`、`combined_fingerprint`，將 `_check_short_circuit` 與 `_save_deployment_manifests` 的 10 個散裝參數收斂為 `(self, ctx: _ReleaseContext, ...)`。
   - 修正 `WorkflowInitializer.__init__` 與 `ReleasePublisher` 中 `self.host_dir` 未傳遞之問題。
   - 將 `session_trace.py` 與 `_trace_parser.py` 中的魔術數字提取為模組頂層具名常數（如 `SESSION_IDLE_GAP_SEC = 1800.0`、`BEACON_CHUNK_BYTES = 65536`、`MAX_TARGETED_READ_LINES = 160`）。
4. **精簡 `_verifier_healer.py` 與 `scripts/cli.py` (`S3`/`S4`，`F-11`, `F-21`)**：
   - 於 `_verifier_healer.py` 提取 `_build_initial_changelog_content(plan_name, today_str, parent_name, model_val, first_type, first_summary)`，消除兩處 15 行重複字串模板。
   - 於 `scripts/cli.py` 提取 `_extract_release_target_arg(bags, opt_name, aliases)`，消除 `release_target` 中 `--add` 與 `--remove` 的重複參數解析分支。

---

### 3.3 預期 Before / After 結構量化指標預估

| 量化指標 (Metric) | 診斷前基線 (Before) | 預計重構後 (After) | 預期變化幅度 | 結構改善說明 |
| :--- | :---: | :---: | :---: | :--- |
| **超過 700 行之巨型檔案數** | `7 個` (最高 955 行) | `0 ~ 1 個` ($\le 600$ 行) | `-85%+` | 透過 `S6` 拆分 `publisher.py`、`roadmap.py` 並下沉 `verifier.py` 階段函式 |
| **最大單一函式行數 (Max Function LOC)** | `261 行` (`_verify_markdown_file`) | `$\le 65$ 行` | `-75%` | 透過 `S1` 業務階段拆解將頂層方法轉為高階編排器 |
| **最大控制流縮排深度 (Max Nesting Depth)** | `5 ~ 6 層` (`searcher.py` / `compiler.py`) | `$\le 3$ 層` | `-2 ~ 3 層` | 透過 `S4` 衛語句反轉與巢狀閉包提取扁平化 |
| **物理拔除之薄轉發層 / 廢棄別名 / 死匯入** | `14 處` | `0 處` | `-100%` | 嚴格執行 `Mode A` 單一正統入口收斂 |
| **重複之 URI 解析 / `sys.path` 啟動樣板** | `7 處` (4 處 URI + 3 處 `sys.path`) | `1 處 SSOT` | `-86%` | 收斂至模組共用基礎設施，並修復 `plans/archive` 拼字不一致隱患 |

---

## 3. 結論 (Conclusion)

### 3.1 推薦落地策略
- **採納「方案 B：外科手術階段管線化 (`S1~S5`) + 關鍵破窗物理拆檔 (`S6`) + `Mode A` 單一入口收斂」**。
- **建議實作分批順序（於子計畫 `P01~P07` 或 `Full Track` 中推進）**：
  1. **Step 1（基礎設施與 `Mode A` 清理）**：於 `_common.py` 建立統一 URI 解析與活躍計畫目錄列舉 SSOT，拔除 14 處薄轉發包裝方法與死匯入，並更新模組內與測試集之引用點。
  2. **Step 2（核心編譯與發布引擎重構）**：執行 `publisher.py` 之 `_ReleaseContext` 封裝（`S5`）與無狀態軟合併/雜湊輔助模組拆分（`S2`/`S6`），以及 `compiler.py` 之 Stage 1/Stage 2 重複樣板收斂（`S1`/`S3`）。
  3. **Step 3（Plans 工具鏈與 Roadmap/Todo 拆解）**：拆解 `PlanVerifier._verify_markdown_file`（`S1`）、聚合 `PlanStatusResolver._read_doc_headers`（`S3`）、拆分 `roadmap.py` 與 `todo.py`（`S6`）並精簡 `session_trace.py` / `scripts/cli.py`。
  4. **Step 4（全量沙盒驗證）**：執行 `python yscb.py dev check agents-workflow` 與 `python yscb.py dev test agents-workflow` 確保 100% 測試通過與零行為退化。

### 4.2 後續行動與流轉出口銜接
- **推薦流轉出口**：**出口 ① 立即原地升級實作**——因本子計畫涉及整個 `agents-workflow` 模組（19 個檔案）、`Mode A` 破壞性清理與 `S6` 物理拆檔，修改規模 $> 100$ 行，建議於主計畫 `2026_10_30_1641_code_optimize` 之子計畫 `sub_05_agents_workflow_code_optimization` 下以 **Full Track (`P01`~`P07`)** 推進實作與驗證。
