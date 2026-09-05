# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_05_jit_self_healing_integration  
> 建立日期：2026-09-04  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 API 規格書 (`P03`) 與架構設計 (`P02`) 中具備 1:1 明確介面與資料流。
- [x] **邊界防護**：EC-01 ~ EC-05 在 `core.events.broadcast`、`yscb.py` 及模組 Hook 均有嚴格的 Fail-Safe 隔離防護。
- [x] **依賴純淨**：100% 維持純 Python 標準庫，零第三方 Pip 依賴，Clean 狀態延遲保證 $\le 5\text{ms}$。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **擴充手冊** | `source/core/contributes.format.md` | Modify | 補充 `events: list[{"<name>": "description"}]` 清單物件擴充格式規範 |
| **模組組態** | `source/core/contribute.json` | Modify | 宣告 `core` 模組派送之事件清冊中繼資料 |
| **微觀日誌** | `plans/.../sub_05_jit_self_healing_integration/changelog.md` | Modify | 記錄階段推進歷程、技術決策與測試驗證成果 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：在執行自舉（`init` / `restore` / `bootstrap`）或環境未初始化時執行 CLI，`pre_cli_dispatch` 廣播是否會因缺少 `core` 或 `.modules/` 拋出未捕獲例外？  
> 💡 **防護解法**：在 `yscb.py` 中，自舉命令顯式短路排除執行前置事件；若環境未初始化 (`load_config()` 無效)，直接短路返回，零副作用、零例外。

> ❓ **尖銳問題 2**：若某模組在 `hook.core.py` 執行 `on_pre_cli_dispatch` 時拋出權限錯誤或語法例外，是否會導致使用者指令無法執行？  
> 💡 **防護解法**：`core.events.broadcast` 對每個模組的 Hook 執行包裹獨立 `try...except Exception as e`，輸出結構化 Warning 日誌並將結果記錄為失敗，絕不向外拋出破壞主流程。

> ❓ **尖銳問題 3**：`agents-workflow` 的 JIT 自癒物化是否會在調用自身發布指令（如 `agents-workflow release`）時引發重入或死鎖？  
> 💡 **防護解法**：`ReleasePublisher.ensure_jit_release()` 內部依賴指紋比對；發布前若指紋已變更僅物化一次，且 `release_all` 具備狀態鎖與 mtime 短路，完全冪等無重入風險。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**: 實作 `ys_codebase/source/core/core/events.py`，提供 `broadcast()` 與 `get_contributed_events()`，並於 `core/__init__.py` 匯出。
- [ ] **TASK-02**: 重構 `ys_codebase/source/core/core/engine.py` 與 `installer.py`，移除 `Engine.act_broadcast_event` 舊門面，全面改調用 `core.events.broadcast`。
- [ ] **TASK-03**: 更新 `ys_codebase/source/core/contribute.json` 與 `contributes.format.md`，宣告 `events` 清單中繼資料。
- [ ] **TASK-04**: 重構 `ys_codebase/source/dev/dev/testing/sandbox.py`，移除自建之 `_dispatch_test_hooks`，改呼叫 `core.events.broadcast(..., emit_module="dev")`。
- [ ] **TASK-05**: 升級 `yscb.py`：
  - (a) 建立命令分發前置管線 `_ensure_jit_lifecycle_pre`（呼叫 `core.events.broadcast("pre_cli_dispatch")`）；
  - (b) 建立命令分發後置管線 `_ensure_jit_lifecycle_post`（呼叫 `core.events.broadcast("post_cli_dispatch")` 與 12hr 更新檢查）；
  - (c) 新增 `python yscb.py event list` CLI 指令與 `cmd_event()` 實作。
- [ ] **TASK-06**: 升級 `agents-workflow`：
  - (a) 於 `ys_codebase/source/agents-workflow/scripts/hook.core.py` 實作 `on_pre_cli_dispatch(ctx)`；
  - (b) 於 `ys_codebase/source/agents-workflow/scripts/cli.py` 徹底移除 Ad-hoc 的 `ensure_jit_release()` 攔截邏輯。
- [ ] **TASK-07**: 新增 `ys_codebase/source/core/tests/test_events_pipeline.py`，覆蓋 FT-01~08 與 ET-01~05。
- [ ] **TASK-08**: 執行全模組回歸跑測 (`python yscb.py dev test --all -q`) 與 Dogfooding 閉環驗收。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 8 大實作任務拓撲依賴定稿**：實作順序嚴格遵循微內核基礎設施 ➔ 核心解耦 ➔ 外部收斂 ➔ 宿主串聯 ➔ 業務模組對齊 ➔ 測試驗收。
- **[P04:DR-02] 測試計畫定稿 (P06 Confirmed)**：確立 `P06_test_plan.md` 狀態晉升為 `Confirmed`，包含 14 項自動化測試與 2 項 UX 實機檢核作為嚴格驗收關卡。
