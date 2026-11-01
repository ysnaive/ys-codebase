# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_05_agents_workflow_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `Mode A` 編譯與發布器死代碼及過渡分支物理清除 (`M-01`, `M-02`) | 物理刪除 `compiler.py` 未引用正則 `TOKEN_ANCHOR_REGEX`/`URI_REF_REGEX`、未使用 `mod_order` 參數、`resolve_stage1_content`/`resolve_stage2_uris`/`compile_all` 薄包裝與舊版單檔 `workflow`/`workflows` 分支；物理刪除 `publisher.py` 之 `LEGACY_PROJECT_MANIFEST_STORAGE_URI`、`_migrate_legacy_storage_manifest()`、`get_registered_targets()`、`_soft_merge_agents_md`、未使用 `interactive` 參數與舊目錄過渡清理區塊。 | P0 | [P00:DR-01] |
| **FR-02** | `Mode A` 計畫驗證器、舊檔名分支、重複 CLI 與未引用匯入清除 (`M-03` ~ `M-06`) | 物理刪除 `verifier.py` 之 `PlanReport.__iter__/__getitem__`、`get_resolved_template_headers`、`_auto_heal_deterministic_headers(target_dir=...)` 與 `verify_all_plans(include_archived=...)` 未使用參數及 `PlanVerifier.verify()`；刪除 `archiver.py`、`scanner.py`、`status.py`、`verifier.py` 中 `FT_plan.md`/`P00_semantic_requirements.md`/`master_plan*.md` 舊檔名分支；刪除 `scripts/cli.py` 與 `contributes/core.json` 之 `plan_check` 重複命令及底部 11 個 `cmd_*` 舊轉發；刪除 `initializer.py` 死屬性 `host_dir`/`module_root` 與全模組 15 處未引用匯入。 | P0 | [P00:DR-01] |
| **FR-03** | `session_trace.py` 巨型單體模組三層拆解 (`F-01`) | 將 `plans/session_trace.py` (1,933 LOC) 拆分為：`plans/_trace_parser.py`（轉錄載入、Antigravity/Claude/Cursor/Codex 四種 IDE 專屬解析器與工具調用配對，單一函式 $\le 70$ LOC、巢狀 $\le 3$ 層）、`plans/_trace_renderer.py`（時間軸壓縮、敏感資訊遮罩與 Markdown 審計報告渲染）及 `plans/session_trace.py`（`SessionTraceExtractor` 門面與 IDE 轉錄探索）。 | P0 | [P00:DR-01] |
| **FR-04** | `verifier.py` 規格表、自癒器與驗證器三模組解耦 (`F-02`) | 將 `plans/verifier.py` (1,486 LOC) 拆分為：`plans/_verifier_specs.py`（`TEMPLATE_SPECS`、狀態機合法值表與正則常數）、`plans/_verifier_healer.py`（確定性標頭正規化自癒與 `changelog.md` 免讀盲寫追加）與 `plans/verifier.py`（將 `verify_plan` 拆為拓撲、標頭章節與跨文件追溯三階段驗證）。 | P0 | [P00:DR-01] |
| **FR-05** | `plans/_common.py` 共用基底建立与 PEP 562 延遲載入及雙向循環依賴斬斷 (`F-03`, `F-06`, `F-09`) | 建立 `plans/_common.py` 統一提供 `resolve_plan_uri(uri_key: str) -> str`（修正 `archiver.py` 的 `archive_plans` 拼字與退避不一致，統一使用 `"archived_plans"` 與 `"plans/archived"`）及 `parse_markdown_blockquote_headers(content: str) -> Dict[str, str]`；`plans/__init__.py` 改用 PEP 562 `__getattr__` 按需延遲載入子模組；`targets.py` 直接透過 `WorkflowCompiler.get_donor_contributions` 查詢 `contributes`，斬斷 `publisher <-> targets` 雙向循環依賴。 | P0 | [P00:DR-01] |
| **FR-06** | `publisher.release_all` 與 `compiler.resolve_stage2_uri` 階段聚合與去重 (`F-04`, `F-05`) | 將 `WorkflowPublisher.release_all` 拆解為 `_prepare_target_compilations`、`_detect_and_resolve_file_drifts`、`_materialize_target_files_and_agents_md`、`_prune_orphaned_managed_files`、`_save_deployment_manifests` 五個階段方法；將 `compiler.py:resolve_stage2_uri` 內部 7 個巢狀閉包提升為純函式並抽取 `_lookup_deployed_rel_path` 消除 3 處重複映射查找。 | P1 | [P00:DR-02] |
| **FR-07** | `status.py`、`scanner.py` 與 `roadmap.py` 拓撲判定及晉升管線合一 (`F-07`, `F-08`) | 由 `scanner.py` 統一產出計畫拓撲資訊供 `status.py` 消費，並將 `status.py:resolve_next_action` 拆分為 `_resolve_umbrella_next_action`、`_resolve_fast_track_next_action`、`_resolve_research_next_action`、`_resolve_full_track_next_action`；於 `roadmap.py` 抽取 `_initialize_promoted_plan_scaffold` 統一 `promote_roadmap` 與 `promote_todos` 立項建檔邏輯。 | P1 | [P00:DR-02] |
| **FR-08** | 全模組 `uri.<io>` 遷移至 `vfs.<io>` 與異常顯式處理 (`F-10`) | 將 `agents-workflow` 全模組內所有 `uri.exists`/`uri.read_text`/`uri.write_text` 等 `uri.<io>` 薄轉發調用 100% 遷移至 `vfs.<io>`；修復 `targets.py:save_tier_targets` 的空白 `except Exception: pass` 靜默吞錯並同步更新 `tests/` 測試夾具與斷言。 | P1 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `resolve_plan_uri("archived_plans")` 在無 `contributes` 配置時的退避路徑 | 統一退避至 `"project://plans/archived"`（修正原 `archiver.py` 誤查 `"archive_plans"` 並退避至 `"project://archive_plans"` 之缺陷）。 |
| **EC-02** | `targets.py:save_tier_targets` 寫入組態檔遭遇 I/O 或權限失敗 | 移除靜默 `except Exception: pass`，改為向上拋出 `OSError` / `WorkflowError` 或顯式傳遞錯誤，禁止靜默吞噬寫入失敗。 |
| **EC-03** | 轉錄檔 `_parse_transcript_file` 含有損毀 JSON 行或未知 IDE 事件結構 | `_load_raw_transcript_records` 對單行損毀 JSON 安全跳過並保留有效紀錄，未知事件欄位安全退避為空值而不中斷整體審計報告生成。 |
| **EC-04** | `plans/__init__.py` 存取不存在之屬性 | PEP 562 `__getattr__` 於未知屬性名稱時標準拋出 `AttributeError`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構與複雜度 | `_trace_parser.py` 單一解析函式行數 $\le 70$ LOC、巢狀深度 $\le 3$ 層；全模組消除 `publisher <-> targets` 雙向循環依賴。 |
| **NFR-02** | 依賴純淨度 | 100% 移除 `agents-workflow` 對 `core.uri` 檔案 I/O 薄轉發之呼叫，統一使用 `core.vfs`（僅保留純 URI 解析如 `uri.resolve` / `uri.parse` / `uri.to_path` 若屬 URI 語法層）。 |
| **NFR-03** | 行為相容與測試覆蓋 | 除 `Mode A` 明確刪除之廢棄別名與舊檔名外，所有正統 CLI 與 API 行為 100% 無損保持，`tests/` 同步更新後靜態編譯與驗證全數通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `plans/__init__.py` 改用 PEP 562 `__getattr__` 時，需維持 `__all__` 匯出清單（`PlanScanner`, `PlanStatusReporter`, `PlanVerifier`, `PlanReport`, `PlanArchiver`, `TodoManager`, `RoadmapManager`, `SessionTraceExtractor`），確保外部 `from agents_workflow.plans import ...` 100% 相容。
- **`[!CAUTION]`** 本子計畫嚴格限制寫入範圍於 `ys_codebase/source/agents-workflow/` 與本子計畫目錄，嚴禁觸碰 `.agents/` 二層物化空間或其他模組。
