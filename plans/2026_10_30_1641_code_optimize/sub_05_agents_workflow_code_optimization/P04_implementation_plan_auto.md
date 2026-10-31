# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_05_agents_workflow_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-08 在 API 規格書中有對應介面
- [x] **邊界防護**：EC-01 ~ EC-04 有具體錯誤處理策略
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/agents-workflow/README.md` | Modify | 確認 CLI 命令說明無殘留 `plan check`（於 Phase 7 結案階段檢視） |
| **專題手冊** | `docs/agents-workflow/README.md` | Modify | 同步更新 `plans` 內部子模組架構說明（於 Phase 7 結案階段檢視） |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 記錄 Mode A 清除舊檔名相容分支與拆解巨型模組決策（於 Phase 7 結案階段檢視） |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新拆分後各模組與公開方法之 Docstring |
| **發布日誌** | CHANGELOG.md | Modify | 記錄 `sub_05` 重構摘要（於主計畫 Phase 7 結案階段統一更新） |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：將 `session_trace.py` 與 `verifier.py` 拆分為多個內部子模組後，若既有測試或外部模組直接從 `session_trace` 或 `verifier` 匯入 `TEMPLATE_SPECS` 等常數或輔助方法，是否會引發 `ImportError`？  
> [*] **防護解法**：在 `verifier.py` 中顯式匯入 `TEMPLATE_SPECS`（`from ._verifier_specs import TEMPLATE_SPECS`），並在 `SessionTraceExtractor` 上保留既有公開與受測介面委派，同時清查 `tests/` 確保匯入路徑 100% 對齊。

> [?] **尖銳問題 2**：`plans/__init__.py` 改用 PEP 562 `__getattr__` 後，型別檢查器或 `from agents_workflow.plans import *` 是否能正常運作？  
> [*] **防護解法**：在 `plans/__init__.py` 中完整保留 `__all__` 清單與 `TYPE_CHECKING` 靜態匯入區塊，兼具執行期零飢渴載入與靜態型別推導支援。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：建立 `plans/_common.py`（統一 `resolve_plan_uri` 與 `parse_markdown_blockquote_headers`）並將 `plans/__init__.py` 改為 PEP 562 `__getattr__` 延遲載入（對應 `FR-05`, `EC-01`, `EC-04`）。
2. **TASK-02**：重構 `compiler.py`、`targets.py`、`publisher.py`、`initializer.py`、`hooks.py`，清除 `M-01`/`M-02`/`M-06` 死代碼、斬斷 `publisher <-> targets` 雙向循環、拆解 `release_all` 與 `resolve_stage2_uri`，並全數遷移 `uri.<io>` 至 `vfs.<io>`（對應 `FR-01`, `FR-05`, `FR-06`, `FR-08`, `EC-02`）。
3. **TASK-03**：拆分 `plans/verifier.py` 為 `_verifier_specs.py`、`_verifier_healer.py` 與 `verifier.py`，清除 `M-03`/`M-04` 廢棄方法與舊檔名分支並遷移至 `vfs.<io>`（對應 `FR-02`, `FR-04`, `FR-08`）。
4. **TASK-04**：拆分 `plans/session_trace.py` 為 `_trace_parser.py`、`_trace_renderer.py` 與 `session_trace.py`，壓降單一解析函式至 $\le 70$ LOC 與巢狀 $\le 3$ 層並遷移至 `vfs.<io>`（對應 `FR-03`, `FR-08`, `EC-03`, `NFR-01`）。
5. **TASK-05**：重構 `scanner.py`、`status.py`、`archiver.py`、`roadmap.py`、`todo.py`、`scripts/cli.py` 與 `contributes/core.json`，移除 `M-04`/`M-05` 舊檔名與 `plan_check`/`cmd_*`，合一拓撲判定與晉升管線，並更新 `tests/` 測試夾具與通過 `py_compile` 靜態檢查（對應 `FR-02`, `FR-07`, `FR-08`, `NFR-02`, `NFR-03`）。
6. **TASK-06（R02 二次深層掃描收斂）**：修復 `compiler.py:175` 之 `workflow.archived://` fallback 拼字錯誤（`"plans/archive"` -> `"plans/archived"`）、補齊 `initializer.py` 與 `publisher.py` 之 `self.host_dir` 儲存與傳遞、移除 `scripts/hook.dev.py` 未使用匯入，並全面移除 `_common.py`/`__init__.py`、`status.py`、`verifier.py`（11 個單行轉發包裝）、`session_trace.py`（2 個單行轉發包裝）共 14 處 Mode A 殘留單行轉發與測試對齊（對應 `FR-01` ~ `FR-05`, `NFR-02`, `NFR-03`）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認依循 `TASK-01` ~ `TASK-05` 拓撲順序直接於 `ys_codebase/source/agents-workflow/` 完成源碼與測試無損重構，並於子代理階段以 `python -m py_compile` 與 `plan verify` 執行靜態與結構守門。
