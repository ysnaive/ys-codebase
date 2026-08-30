# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：core 核心拓撲注入 (yscb_root) 與全庫 Fallback 剛性收斂  
> 建立日期：2026-08-30  
> 所屬計畫：2026_08_30_1928_core_topology_injection_and_zero_fallback  
> 狀態：Confirmed  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書與架構中均有具體介面與對應實作。
- [x] **邊界防護**：EC-01 ~ EC-04 均有對應防禦策略（`try...finally`、目錄存在性檢查、None 安全重設）。
- [x] **依賴純淨**：100% 原生標準庫，零外部依賴，符合 NFR-01 ~ NFR-03。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/core/DESIGN_NOTES.md` | Modify | 登錄 `[DN-CORE-03]` 核心拓撲雙軌注入與零 Fallback 剛性守門。 |
| **維度 2** | `docs/dev/topics/sandbox.md` | Modify | 說明沙盒生命週期鉤子之 `host_scope` 與 `yscb_scope` 雙重隔離機制。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當單元測試執行中發生未捕捉例外崩潰時，`_active_yscb_dir` 是否會殘留並污染後續其他模組的測試？  
> 💡 **防護解法**：`yscb_scope` 嚴格使用 `@contextmanager` + `try...finally`，即使內部發生例外也能 100% 還原外層作用域；同時 `YSCBTestCase.tearDown` 於基類增加全域狀態自愈重設防線。

> ❓ **尖銳問題 2**：`dev test --all` 多執行緒並發建立沙盒時，若兩個執行緒同時呼叫 `_dispatch_test_hooks`，全域變數 `_active_yscb_dir` 是否會產生 Thread-safety 衝突？  
> 💡 **防護解法**：`Tester._run_parallel_test` 已採用進程隔離執行各模組單元測試；在主進程 dispatch 階段各沙盒依序或獨立作用域隔離，杜絕狀態交叉污染。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/core/core/uri.py` 實作 `set_yscb_root`、`get_yscb_root`、`yscb_scope` 並重構 `_get_yscb_root`。
- [ ] **TASK-02**：在 `source/core/core/config.py` 重構 `ConfigManager._get_yscb_root`，徹底刪除 `while` 迴圈與 `os.getcwd()`。
- [ ] **TASK-03**：在 `source/dev/dev/testing/sandbox.py` 更新 `_dispatch_test_hooks`，雙重包覆 `host_scope` 與 `yscb_scope`。
- [ ] **TASK-04**：在 `source/agents-workflow/agents_workflow/plans/searcher.py` 收斂 `archive_plans` 預設路徑為 `plans/archived`。
- [ ] **TASK-05**：在 `source/core/tests/test_uri.py` 編寫新單元測試驗證注入與作用域生命週期。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]**：全面通過 P01~P04 審查，定稿 P06 測試計畫為 Confirmed，正式進入 Phase 5 實作。

