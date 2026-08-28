# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 子計畫 04: CLI 工具鏈、統一門面 SDK、生態整合與本地端快取儲存遷移 (CLI, Unified SDK, Workflow Interlock & Local Cache Storage Migration)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 依據 P03：[P03_api_spec.md](./P03_api_spec.md)  
> 測試計畫：[P06_test_plan.md](./P06_test_plan.md) (Confirmed)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-13 在 `P03_api_spec.md` 中均有對應 API 簽名與 CLI 指令。
- [x] **邊界防護**：EC-01 ~ EC-11 在本地快取自癒、不存在空間防護、安全清理、Core 嚴格拋錯與 Build 隔離中均有完整覆蓋。
- [x] **依賴純淨**：NFR-01 ~ NFR-04 承諾 100% Python 原生標準庫（Zero External Dependency）。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **維度 1 (概覽)** | `docs/knowledge-db/README.md` | **Modify** | 標記全子計畫 (sub_01~04) 完成，提供完整的模組手冊、CLI 6 大指令與 Python SDK 上手指南 |
| **維度 3 (架構)** | `docs/knowledge-db/architecture.md` | **Modify** | 更新全模組整合架構圖解，補充本地端快取 (`cache://`) 儲存拓撲與生態連動機制 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：將資料庫檔案遷移至 `cache://knowledge-db/` 後，若開發者執行 `git clean` 或手動刪除 `.cache/`，是否會導致系統報錯？**  
> 💡 **防護解法**：`KnowledgeEngine` 內建透明自癒機制，呼叫 `search()`、`scan()` 或 `build_index()` 時若發現 `.cache/` 不存在，自動呼叫 `mkdir(parents=True, exist_ok=True)` 重建目錄並重新生成指紋與索引，達到 100% 韌性。

> ❓ **尖銳問題 2：遷移至 `cache://knowledge-db/` 後，歷史建立於 `storage/knowledge-db/` 的舊檔案如何處置？**  
> 💡 **防護解法**：在本次 Phase 5 實作中主動清除 `ys_codebase/storage/knowledge-db/` 舊殘留目錄，並在 `hook.dev.py` 測試沙盒環境中全面統一為 `.cache/knowledge-db/`。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-00 (本地端快取儲存遷移)**：修改 `source/knowledge-db/knowledge_db/space.py`、`manifest.json`、`scripts/hook.dev.py`，將存儲根目錄全面切換至 `cache://knowledge-db/`，並清理舊 `storage/knowledge-db/`。
- [x] **TASK-01 (統一門面 SDK 實作)**：實作 `source/knowledge-db/knowledge_db/engine.py` (`KnowledgeEngine`)。
- [x] **TASK-02 (模組自治 Hook 實作)**：實作 `source/knowledge-db/scripts/hook.dev.py` (`on_test_setup`, `on_test_teardown`)。
- [x] **TASK-03 (CLI 完整指令與導出更新)**：更新 `source/knowledge-db/scripts/cli.py`（6 大指令）、`manifest.json` 與 `knowledge_db/__init__.py`。
- [ ] **TASK-04 (測試套件路徑更新與回歸驗證)**：更新 `test_space.py`、`test_cli.py` 等測試案例中路徑斷言，實機跑測 FT-01~11 與 RT-01。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿實作計畫與測試清單**：確認 Phase 1~3 規格與依賴拓撲無誤，同步定稿 `P06_test_plan.md` 為 `Confirmed`，進入 Phase 5 編碼實作。
