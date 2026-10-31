# 技術調研報告：`agents-workflow` 模組五維度靜態診斷與 Mode A 無損重構處方 (R01_code_optimization_audit.md)

> 調研主題：sub_05_agents_workflow_code_optimization (`agents-workflow` 模組五維度靜態診斷與 Mode A 無損重構處方)  
> 建立日期：2026-10-30  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  1. **巨型單體檔案與極端深層巢狀（`D1` / `D3` — `P0`）**：`ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py`（1,933 LOC）將「IDE 日誌探索、Antigravity/Claude/Cursor/Codex 四種異質 JSONL 轉錄解析、工具調用配對、異常壓縮與 Markdown 報告渲染」全部塞入單一檔案，其中 `_parse_transcript_file`（`L345-1126`）單一函式長達 **782 LOC**、巢狀深度達 **11~12 層**；`verifier.py`（1,486 LOC）則將 16 類計畫模板規格表、標頭正規化自癒、跨文件追溯驗證与 `changelog.md` 盲寫耦合於單一類別。
  2. **雙向循環依賴與飢渴匯入（`D2` — `P0/P1`）**：`publisher.py` 頂層匯入 `targets.py`（`L21`），而 `targets.py` 又在函式內反向匯入 `publisher.WorkflowPublisher`（`L98`），形成 `publisher <-> targets` 雙向循環；`plans/__init__.py` 頂層飢渴匯入全部 7 個子模組，而 `archiver.py`、`status.py`、`roadmap.py` 又在函式內延遲互相匯入，形成隱性網狀耦合。
  3. **多處重複解析器與路徑退避不一致（`D3` / `D5`）**：`compiler.py:resolve_stage2_uri`（254 LOC）在單一方法內定義 7 個巢狀閉包並連續 3 次複製貼上相同的 `deployment_map` 字典查找；`scanner.py:get_plan_info` 與 `status.py:resolve_next_action` 重複實作 7 大計畫模式檔案拓撲嗅探；`archiver.py`、`scanner.py`、`status.py`、`verifier.py` 各自實作語意 URI 解析與 Markdown `> Key：Value` 標頭解析，且 `archiver.py:67` 將封存 URI 預設寫成 `archive_plans`（實際正統名稱為 `archived_plans`）與 fallback `"archive_plans"`（其他模組皆為 `"plans/archived"`）。
  4. **歷史過渡分支、廢棄別名與雙重複製命令（`D2` / `D5`）**：殘留 `compiler.py` 的 `resolve_stage1_content`/`resolve_stage2_uris`/`compile_all` 與舊版單檔 `workflow`/`workflows` 分支、`publisher.py` 的 `LEGACY_PROJECT_MANIFEST_STORAGE_URI` 遷移與 `_soft_merge_agents_md` 0 調用方法、`verifier.py` 的 `PlanReport.__iter__/__getitem__` 與 `PlanVerifier.verify()`、4 支檔案內的 `FT_plan.md`/`P00_semantic_requirements.md`/`master_plan_*.md` 舊檔名相容分支，以及 `scripts/cli.py` 的 `plan_check` 重複命令與底部 11 個 `cmd_*` 舊測試轉發。
- **調研目標**：
  - 鎖定 **範圍 = 單一模組（`ys_codebase/source/agents-workflow/`，含 `agents_workflow/` 15 檔與 `scripts/cli.py` 1 檔，共 16 檔 / 8,847 LOC）** 與 **生命週期 = `Mode A：新功能收斂期（Convergence Mode / 可破壞性變更）`**。
  - 融合雙子代理（Auditor A / Auditor B）獨立盲測共識，產出完整基線盤點、`Mode A` 破壞性清除清冊（19 項）、`D1~D5` 分級問題單（`P0/P1/P2`）與 `S1~S6` 無損重構處方。

### 1.1 `agents-workflow` 模組基線盤點表 (16 檔 / 8,847 LOC)

| 檔案路徑 (`ys_codebase/source/agents-workflow/...`) | 行數 (LOC) | 核心職責與主要類別/函式 | 入向耦合 (`aw` 內 / 跨模組) | 診斷熱點等級 |
| :--- | :---: | :--- | :--- | :---: |
| `agents_workflow/plans/session_trace.py` | 1,933 | `SessionTraceExtractor`：跨平台 AI IDE 對話轉錄探索、解析與審計報告生成 | `cli`、`tests/` | **P0** |
| `agents_workflow/plans/verifier.py` | 1,486 | `PlanVerifier`、`PlanReport`：計畫結構校驗、確定性標頭自癒與 `changelog` 盲寫 | `status`、`roadmap`、`cli`、`tests/` | **P0 / P1** |
| `agents_workflow/compiler.py` | 886 | `WorkflowCompiler`：Stage 1 Token 錨點展開與 Stage 2 語意 URI 編譯 | `publisher`、`verifier`、`cli`、`tests/` | **P0 / P1** |
| `agents_workflow/publisher.py` | 875 | `WorkflowPublisher`：二層物化發布、Drift 衝突檢測、`AGENTS.md` 軟合併與清理 | `targets`、`initializer`、`cli`、`tests/` | **P0 / P1** |
| `scripts/cli.py` | 801 | `agents-workflow` CLI 路由入口（`release`/`target`/`plan`/`todo`/`roadmap`/`session`） | `core.dispatcher`、`tests/` | **P1** |
| `agents_workflow/plans/roadmap.py` | 730 | `RoadmapManager`：路線圖盤點、立項推薦與 `roadmap`/`todo` Consume-on-Promote | `cli`、`tests/` | **P1** |
| `agents_workflow/plans/status.py` | 599 | `PlanStatusReporter`：7 大計畫軌道階段推導、下一步建議與儀表板渲染 | `archiver`、`cli`、`tests/` | **P1** |
| `agents_workflow/plans/todo.py` | 489 | `TodoManager`：`TODO.md` 免讀盲寫追加、過濾檢索與項目移除 | `roadmap`、`cli`、`tests/` | **P1 / P2** |
| `agents_workflow/plans/archiver.py` | 396 | `PlanArchiver`：結案計畫合規守門與按年月歸檔搬移 | `cli`、`tests/` | **P1** |
| `agents_workflow/plans/scanner.py` | 251 | `PlanScanner`：活躍與封存計畫目錄走訪及模式分類 | `status`、`archiver`、`verifier`、`roadmap` | **P1** |
| `agents_workflow/targets.py` | 172 | 多發布目標（`antigravity`/`claude-code` 等）雙層配置讀寫與啟用解析 | `publisher`、`compiler`、`cli`、`tests/` | **P1** |
| `agents_workflow/initializer.py` | 145 | `WorkflowInitializer`：首次安裝引導與工作流組態初始化 | `cli`、`tests/` | **P2** |
| `agents_workflow/hooks.py` | 46 | 模組安裝/移除/重載生命週期 Hook | `core.engine` | **P2** |
| `agents_workflow/plans/__init__.py` | 29 | `plans` 子套件門面 | `cli`、`tests/` | **P1** |
| `agents_workflow/__init__.py` & `exceptions.py` | 9 | 頂層套件標記與 `WorkflowError` 例外 | `agents_workflow` | Clean |

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：`Mode A` 全面破壞性收斂 + 巨型模組拆解 + 單向依賴純化**<br/>*(Recommended — Full Track)* | 徹底移除 19 項舊版別名、單檔 `workflows` 分支、`FT_plan.md`/`master_plan` 舊檔名分支、`plan check` 重複命令與 11 個 `cmd_*` 轉發；將 `session_trace.py` (1,933 LOC) 與 `verifier.py` (1,486 LOC) 拆分為職責單一之子模組；抽取 `plans/_common.py` 統一語意 URI 與標頭解析並斬斷循環依賴；將全模組 43 處 `uri.<io>` 遷移至 `vfs.<io>`。 | 預計淨減 **750~950 LOC**，將 `_parse_transcript_file` 782 行巨函式拆解為清晰解析器，達成 100% 單向無環依賴。 | 需同步更新 `agents-workflow/tests/` 中使用舊檔名（如 `P00_semantic_requirements.md`、`FT_plan.md`）或舊轉發方法之測試夾具。 | ⭐⭐⭐⭐⭐ **(推薦)** |
| **方案 B：僅做內部私有函式提取（保留所有歷史相容分支）** | 保留 `FT_plan.md`、`workflows`、`compile_all`、`PlanVerifier.verify()` 與 `cmd_*`。 | 不需調整測試夾具。 | 4 處重複的舊檔名退避與冗餘包裝持續污染核心邏輯。 | ⭐⭐ |

### 3.1 `Mode A` 公開入口收斂、薄轉發層、相容別名與死代碼清除清冊 (`S5`)

| 編號 | 檔案與行號座標 | 冗餘轉發 / 相容別名 / 死代碼 | 調用方盤點（`aw` 內部 / 跨模組 / `tests/`） | `Mode A` 物理清除與收斂處方 (`S5`) |
| :---: | :--- | :--- | :--- | :--- |
| **M-01** | `agents_workflow/compiler.py:49-50, 219, 371-373, 431-433, 452-475, 797, 799-808` | 未引用正則常數 `TOKEN_ANCHOR_REGEX`/`URI_REF_REGEX`；`get_donor_contributions(mod_order=None)` 與 `compile_target(mod_order=None)` 未使用參數；`resolve_stage1_content` 與 `resolve_stage2_uris` 1 行薄包裝；`compile_all()` 舊版單目標包裝；以及 `L452-475` 舊版單檔 `workflow`/`workflows` 掃描分支 | 生產代碼均走 `compile_all_targets()` 與 `skills` 目錄；僅 `tests/test_compiler.py` 呼叫舊包裝 | 物理刪除 2 個死正則、移除 `mod_order` 未使用參數、刪除 `resolve_stage1_content`/`resolve_stage2_uris`/`compile_all` 與 `workflow`/`workflows` 舊分支，更新 `test_compiler.py`。 |
| **M-02** | `agents_workflow/publisher.py:43, 115-121, 134-151, 291-293, 501-532, 534, 572-585, 768-791` | `LEGACY_PROJECT_MANIFEST_STORAGE_URI` 與 `_migrate_legacy_storage_manifest()` 舊路徑遷移；`get_registered_targets()` 0 調用包裝；`_soft_merge_agents_md` 0 調用死方法（已被 `_soft_merge_agents_text` 取代）；`release_all(interactive=False)` 未使用參數；以及清理舊 `.agents/workflows` / `.claude/commands` 之過渡代碼 | 生產代碼 **0 callers** | 物理刪除上述所有歷史遷移方法、死方法 `_soft_merge_agents_md`、未使用參數 `interactive` 與舊目錄過渡清理區塊。 |
| **M-03** | `agents_workflow/plans/verifier.py:95-105, 321-327, 533, 1443, 1455-1486` | `PlanReport.__iter__`/`__getitem__` 舊版字典相容魔術方法；`get_resolved_template_headers` 0 調用方法；`_auto_heal_deterministic_headers(target_dir=...)` 與 `verify_all_plans(include_archived=...)` 未使用參數；以及尾部 `PlanVerifier.verify()` 舊版 tuple 回傳包裝方法 | 生產代碼均使用 `verify_plan()` / `verify_all_plans()`；僅 `test_plans.py` 1 處呼叫 `.verify()` | 物理刪除 `PlanReport` 魔術方法、`get_resolved_template_headers`、`PlanVerifier.verify()` 與 2 個未使用參數，更新 `test_plans.py`。 |
| **M-04** | `archiver.py:99, 105`<br/>`scanner.py:43-55, 77, 146`<br/>`status.py:253, 268, 291, 546`<br/>`verifier.py:337-339, 356` | 4 支模組內針對舊版計畫檔名之相容分支：`FT_plan.md`（現為 `fast_track_plan.md`）、`P00_semantic_requirements.md`（現為 `P00_discuss.md`）、`master_plan*.md`（現為 `umbrella_overview.md`） | 生產環境活躍與封存計畫已 100% 採用新標準檔名；僅 `test_plans.py` 與 `test_cli_dispatch.py` 夾具使用舊名 | 物理刪除 4 支檔案中所有 `FT_plan.md`、`P00_semantic_requirements.md`、`master_plan*.md` 分支，並將測試夾具同步改為正統檔名。 |
| **M-05** | `scripts/cli.py:654-656, 757-800`<br/>`contributes/core.json:220-254` | `plan_check`（`yscb agents-workflow plan check`，僅 `return plan_verify(cmd_bags)` 之重複命令）與 `scripts/cli.py` 底部 11 個 `cmd_*` 舊版平鋪測試轉發函式 | 全倉 Skill 與 CLI 均使用 `plan verify`；底部 `cmd_*` 僅 `test_cli_dispatch.py` 引用 | 物理刪除 `plan_check`（含 `contributes/core.json` 宣告）與底部 11 個 `cmd_*` 轉發函式，測試統一改測正統入口。 |
| **M-06** | `agents_workflow/initializer.py:28-31`<br/>7 支檔案未引用 `import` | `WorkflowInitializer.host_dir` 與 `module_root` 0 引用死屬性；以及 `compiler.py`、`publisher.py`、`archiver.py`、`roadmap.py`、`status.py`、`verifier.py`、`session_trace.py` 共 15 處未引用匯入 | **0 references** | 物理清除死屬性與全部 15 處未引用匯入。 |

---

### 3.2 五維度靜態診斷問題單 (`D1~D5` × `P0/P1/P2`)

| 編號 | 維度 | 嚴重度 | 座標 (`file:line`) | 病徵描述與根因剖析 | 對應重構策略 |
| :---: | :---: | :---: | :--- | :--- | :---: |
| **F-01** | **D1 / D3** | **P0** | `plans/session_trace.py:345-1126` (全檔 1,933 LOC) | **`_parse_transcript_file` 782 行極端巨函式與 12 層深層巢狀**：單一方法內混雜 JSON/JSONL 雙格式串流讀取、4 大 IDE（Antigravity/Claude/Cursor/Codex）異質 Schema 欄位嗅探、工具調用/結果跨步配對、系統噪音過濾與時間戳正規化，圈複雜度破百。 | **S1 + S2 + S3**（拆分為 3 個子模組與各 IDE 專屬解析器，詳見 §3.3） |
| **F-02** | **D1 / D3** | **P0** | `plans/verifier.py:1-1486` | **`verifier.py` (1,486 LOC) 規格表、自癒器與驗證器高度耦合**：`TEMPLATE_SPECS` 靜態規格定義（~210 LOC）、確定性標頭正規化自癒（`_auto_heal_deterministic_headers` 176 LOC）、單一計畫校驗（`verify_plan` 244 LOC）與跨文件追溯矩陣全部擠在同一類別。 | **S1 + S2**（拆分為 `_verifier_specs.py`、`_verifier_healer.py` 與 `verifier.py`） |
| **F-03** | **D2** | **P0** | `publisher.py:21` <-> `targets.py:98`<br/>`plans/__init__.py` <-> `plans/*.py` | **模組間雙向循環依賴與頂層飢渴載入**：`publisher.py` 頂層匯入 `targets.py`，`targets.py:get_enabled_targets` 又反向匯入 `WorkflowPublisher`；`plans/__init__.py` 頂層飢渴載入全部 7 個子模組（含 1,933 行的 `session_trace` 與 1,486 行的 `verifier`），拖慢所有輕量 CLI 子命令（如 `todo list`）並引發子模組間函式內延遲匯入。 | **S2 + S5**（抽取共用常數/基底並改用 PEP 562 `__getattr__` 延遲載入） |
| **F-04** | **D1 / D3** | **P0** | `publisher.py:534-874` | **`WorkflowPublisher.release_all` 341 行巨型發布編排器**：單一方法內混雜專案角色保護、多目標編譯、Drift 雜湊比對、互動式衝突詢問、`AGENTS.md` 軟合併、孤兒檔案清理與 Manifest 持久化，巢狀達 8 層。 | **S1 + S2**（拆解為 5 個具名業務階段方法） |
| **F-05** | **D1 / D3** | **P1** | `compiler.py:542-795` | **`resolve_stage2_uri` 254 行與 7 個內部巢狀閉包及 3 處重複查找**：在方法內部定義 `_normalize_rel`、`_resolve_target_path` 等 7 個閉包，且在處理 Markdown 連結、反引號路徑與純文字 URI 時連續 3 次複製貼上相同的 `deployment_map` 映射查找邏輯。 | **S1 + S2 + S3**（提升閉包為純函式並抽取 `_lookup_deployed_rel_path`） |
| **F-06** | **D3 / D5** | **P1** | `archiver.py:28-72`、`scanner.py:16-39`、`status.py:66-76`、`verifier.py:296-308` | **4 處重複實作語意 URI 解析且 `archiver.py` 預設鍵名不一致**：4 支模組各自呼叫 `WorkflowCompiler.get_donor_contributions` 解析 `active_plans`/`archived_plans`；且 `archiver.py:67` 誤查 `"archive_plans"`（漏 `d`）並退避至 `"archive_plans"`（其他 3 處皆為 `"plans/archived"`）。 | **S3 + S5**（統一收斂至 `plans/_common.py:resolve_plan_uri`） |
| **F-07** | **D3** | **P1** | `scanner.py:39-174`<br/>`status.py:182-557` | **`scanner.py` 與 `status.py` 重複實作 7 大計畫模式檔案拓撲判定**：`get_plan_info` (135 LOC) 與 `resolve_next_action` (376 LOC) 各自掃描 `umbrella_overview.md`、`fast_track_plan.md`、`revision_log.md`、`R*.md`、`P00~P07` 推導計畫型態與進度。 | **S1 + S3**（由 `scanner.py` 統一產出結構化快照供 `status.py` 消費） |
| **F-08** | **D3** | **P1** | `plans/roadmap.py:394-662` | **`promote_roadmap` (134 LOC) 與 `promote_todos` (135 LOC) 高度同構**：兩方法超過 75% 邏輯相同（驗證目標模式、渲染 `P00`/`fast_track_plan`/`revision_log` 模板、初始化 `changelog.md`、執行 Consume-on-Promote 回寫）。 | **S1 + S3**（抽取共用 `_initialize_promoted_plan_scaffold`） |
| **F-09** | **D3** | **P1** | `status.py:128-149`、`roadmap.py:114-142`、`verifier.py:533-570` | **3 處重複實作 Markdown `> Key：Value` 標頭解析器**：3 支模組各自用正則解析計畫與路線圖頂部 Metadata 區塊。 | **S3**（統一收斂至 `plans/_common.py:parse_markdown_blockquote_headers`） |
| **F-10** | **D4** | **P1** | `targets.py:73-74`<br/>全模組 43 處 `uri.<io>` | **`targets.py:save_tier_targets` 以 `except Exception: pass` 靜默吞噬組態寫入失敗**；且全模組有 43 處呼叫 `uri.exists`/`uri.read_text` 等薄轉發函式。 | **S4 + S5**（改用 `vfs.<io>` 並顯式拋出或記錄寫入錯誤） |

---

### 3.3 `S1` 業務階段邏輯聚合與 `S2` 無狀態邏輯剝離藍圖（7 大核心檔案）

#### 1. `agents_workflow/plans/session_trace.py` (1,933 LOC $\to$ 拆分為 3 個職責單一模組)
* **`S1 + S2` 模組與階段拆解**：
  1. `plans/_trace_parser.py` (~650 LOC)：將原 782 行的 `_parse_transcript_file` 拆解為 `_load_raw_transcript_records`、`_parse_antigravity_event`、`_parse_claude_code_event`、`_parse_cursor_event`、`_parse_codex_event` 與 `_correlate_tool_calls_and_results`，將最大函式行數壓降至 $\le 70$ LOC、巢狀壓降至 $\le 3$ 層。
  2. `plans/_trace_renderer.py` (~450 LOC)：將 `_build_markdown_report` (230 LOC)、`_compress_timeline_events` (165 LOC) 與敏感資訊遮罩 (`_redact_text`) 剝離為無狀態純函式模組。
  3. `plans/session_trace.py` (~420 LOC)：僅保留 `SessionTraceExtractor` 門面、跨平台 IDE 轉錄目錄探索與檔案匹配評分。

#### 2. `agents_workflow/plans/verifier.py` (1,486 LOC $\to$ 拆分為 3 個職責單一模組)
* **`S1 + S2` 模組與階段拆解**：
  1. `plans/_verifier_specs.py` (~260 LOC)：存放 `TEMPLATE_SPECS`、狀態機合法值表與預編譯正則常數。
  2. `plans/_verifier_healer.py` (~280 LOC)：封裝確定性標頭正規化自癒（`_auto_heal_deterministic_headers`）與 `changelog.md` 免讀盲寫追加邏輯。
  3. `plans/verifier.py` (~580 LOC)：專注於 `PlanVerifier.verify_plan`（拆為 `_verify_plan_topology`、`_verify_document_headers_and_sections`、`_verify_cross_doc_traceability` 三階段）與 `verify_all_plans`。

#### 3. 新增共用基底 `agents_workflow/plans/_common.py` (~120 LOC) 與 `plans/__init__.py` 延遲載入
* **`S2 + S3 + S5` 破除循環依賴與統一原語**：
  - 建立 `plans/_common.py`，提供單一正統之 `resolve_plan_uri(uri_key: str) -> str`（修正 `archiver.py` 的 `"archive_plans"` 拼字與退避不一致）與 `parse_markdown_blockquote_headers(content: str) -> Dict[str, str]`。
  - `plans/__init__.py` 與 `scripts/cli.py` 改用 PEP 562 `__getattr__` 按需匯入子模組，徹底消除頂層飢渴載入與子模組間循環依賴。

#### 4. `agents_workflow/publisher.py` (875 LOC $\to$ 預估 ~540 LOC) & `targets.py` (172 LOC)
* **`S1 + S2` 階段拆解與單向依賴**：
  - 將 `targets.py` 所需的 `contributes` target 查詢直接委派給 `WorkflowCompiler.get_donor_contributions`，斬斷 `targets.py -> publisher.py` 反向匯入。
  - `WorkflowPublisher.release_all`（原 341 LOC）拆為 `_prepare_target_compilations`、`_detect_and_resolve_file_drifts`、`_materialize_target_files_and_agents_md`、`_prune_orphaned_managed_files`、`_save_deployment_manifests` 五個階段方法。

#### 5. `agents_workflow/compiler.py` (886 LOC $\to$ 預估 ~580 LOC)
* **`S1 + S2 + S3` 消除巢狀閉包與重複查找**：
  - 將 `resolve_stage2_uri`（原 254 LOC）內部的 7 個巢狀閉包提升為模組級純函式，並抽取 `_lookup_deployed_rel_path(uri_str, deployment_map)` 消除 3 處複製貼上的映射查找區塊。

#### 6. `agents_workflow/plans/status.py` (599 LOC) & `roadmap.py` (730 LOC)
* **`S1 + S3` 拓撲判定與晉升管線合一**：
  - `status.py:resolve_next_action`（376 LOC）按 7 大計畫軌道拆分為 `_resolve_umbrella_next_action`、`_resolve_fast_track_next_action`、`_resolve_research_next_action`、`_resolve_full_track_next_action` 分派表。
  - `roadmap.py` 抽取 `_initialize_promoted_plan_scaffold(target_mode, plan_name, title, ...)`，消除 `promote_roadmap` 與 `promote_todos` 之間 ~100 行的重複立項建檔邏輯。

---

## 3. 結論 (Conclusion)

- **推薦落地策略**：
  - 採納 **方案 A（`Mode A` 全面破壞性收斂 + 巨型模組拆解 + 單向依賴純化）**，於後續啟動實作時將本子計畫 `sub_05_agents_workflow_code_optimization` 原地升級為 **標準開發計畫 (`Full Track`, `P01~P07`)**。
  - **預估量化收益**：
    1. 物理清除 **19 項歷史過渡別名、單檔 `workflows` 分支、`FT_plan.md`/`master_plan` 舊檔名分支、`plan check` 重複命令與 11 個 `cmd_*` 舊轉發**，並消除 4 處語意 URI 解析、3 處標頭解析與雙晉升管線重複，預計淨減 **800~950 LOC**。
    2. 將全倉最大單一函式 `session_trace.py:_parse_transcript_file`（**782 LOC，12 層巢狀**）拆解為獨立解析模組（單一函式 $\le 70$ LOC，巢狀 $\le 3$ 層），並將 `verifier.py`（1,486 LOC）解耦為規格、自癒與驗證三模組。
    3. 徹底斬斷 `publisher <-> targets` 雙向循環依賴，並修復 `archiver.py` 的 `archive_plans` 鍵名拼字偏差与 `targets.py` 靜默吞錯問題。
- **後續行動與 P00 銜接（Step 3 三大流轉出口）**：
  1. **出口 ① 立即/後續升級實作（推薦）**：將 `R01_code_optimization_audit.md` 標記為 `Concluded`，並於 `sub_05_agents_workflow_code_optimization` 原地追加 `P01~P07` 升級為 `Full Track` 實作計畫。
  2. **出口 ② 轉入長期技術儲備**：轉入 `/roadmap` 或 `/todo` 分批排程。
  3. **出口 ③ 結案存檔**：僅保留調研診斷報告備查。
