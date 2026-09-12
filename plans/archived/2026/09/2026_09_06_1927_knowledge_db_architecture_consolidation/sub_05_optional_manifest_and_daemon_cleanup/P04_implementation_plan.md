# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：optional_manifest_and_daemon_cleanup  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 API 規格書均具備明確簽名與責任類別
- [x] **邊界防護**：EC-01 ~ EC-04 涵蓋無 optional 向上相容、已安裝靜默跳過、結構防禦檢核與冷模式 100% 獨立運行
- [x] **依賴純淨**：`knowledge-db` 硬相依純化至僅依賴 `core`，符合 NFR-01~03

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 DN-22 (徹底廢除 daemon.py/hook.core.py，落實模組冷熱啟動零感知) |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 sub_05 變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當模組在 `manifest.json` 中宣告了不存在於生態系的 optional 模組，或者 optional 欄位格式被誤寫為 list 時，安裝器是否會拋出未捕獲例外導致安裝中斷？  
> 💡 **防護解法**：`_check_optional_dependencies` 內部以嚴格 `try...except` 包覆防禦，且先以 `isinstance(optional_dict, dict)` 嚴格守門；即使格式異常或發生非預期錯誤，僅印出除錯警告或靜默略過，絕不影響主模組已完成之安裝狀態。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：修改 `source/core/core/installer.py`，新增 `_check_optional_dependencies` 與單元測試 (FR-01, FR-02, FT-01, FT-02)
- [ ] **TASK-02**：修改 `source/dev/dev/checker.py`，擴充 `optional` 欄位靜態結構檢核與單元測試 (FR-03, FT-03, FT-04)
- [ ] **TASK-03**：刪除 `source/knowledge-db/knowledge_db/daemon.py` 與 `source/knowledge-db/scripts/hook.core.py` (FR-04, FR-05)
- [ ] **TASK-04**：修改 `source/knowledge-db/scripts/cli.py`，清理對 `daemon.py` 的引用與提示 (FR-05)
- [ ] **TASK-05**：修改 `source/knowledge-db/manifest.json`，將 `server` 移至 `optional` (FR-06, FT-06)
- [ ] **TASK-06**：執行 `knowledge-db` 與全生態系回歸驗證 (FT-05, FT-07)
- [ ] **TASK-07**：文檔同步交付 (`docs/knowledge-db/DESIGN_NOTES.md`, `CHANGELOG.md`)

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 確立擴充模組插槽化與領域模組清純化**：透過 manifest `optional` 與安裝提示機制，將非核心運行環境與擴充能力徹底插槽化；徹底移除 `daemon.py`，確立領域模組對冷熱啟動零感知的架構準則。
