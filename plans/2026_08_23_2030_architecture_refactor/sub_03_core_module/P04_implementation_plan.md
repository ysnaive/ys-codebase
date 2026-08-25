# 最終實作計畫書 (Implementation Plan)

> 功能名稱：核心微內核基礎設施模組 (Core Infrastructure Module)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 狀態：Confirmed
> 擴充項目：none
> 模板版本：v1.4

---

## 1. 交叉驗證與架構檢核 (Cross-Verification Checklist)

- [x] **FR 對齊**：P01 5 大功能需求 (`FR-01` uri/VFS, `FR-02` 12大原子操作, `FR-03` 7大Installer指令, `FR-04` contributes注入, `FR-05` ExecutionContext) 在 P03 均有對應模組與類別簽名
- [x] **EC 防護**：P01 6 大 Edge Cases (`EC-01` ~ `EC-06`) 在 P03 拓撲求解器、反向相依檢查、VFS 協議校驗與快照自癒邏輯中均有明確防禦策略
- [x] **架構一致**：P02 模組劃分（`context.py`, `uri.py`, `contributes.py`, `engine.py`, `installer.py`, `cli.py`）與 P03 簽章 100% 一致
- [x] **規範約束**：100% 純 Python 3.8+ 標準庫（零第三方相依），所有檔案操作均透過 `core.uri` 一級 VFS，保證路徑無知性與編碼安全
- [x] **Test-First 剛性定稿**：`P06_test_plan.md` 測試矩陣已同步定稿為 `Confirmed`

---

## 2. 靈魂拷問 (Stress Test)

### Q1: `RELOAD` 階段一自 `mirror://` 物化至 `modules/` 時，若模組中存在由前次運行生成的動態臨時檔案或髒注入狀態，如何確保 100% 徹底清除？
**架構設計回答**：
1. **清冊驅動全量純淨物化**：`act_reload` 在階段一不採增量比對，而是先完整刪除運行端目標目錄（`core.uri.rmtree('module.root://<module>/')`），再自 `mirror://<module>/<version>/` 進行純淨目錄複製；
2. **幽靈模組清理**：遍歷 `module.root://` 下所有子目錄，凡未在 `yscb.config.json` 清冊中登記之模組資料夾一律強制刪除，徹底杜絕幽靈模組；
3. **純淨基底再注入**：確保階段二的 contributes 注入永遠基於 100% 純淨的 build 鏡像源檔案之上執行。

### Q2: 模組在呼叫 `core.uri` 讀寫檔案時，若未傳入 `current_module`，如何精確解析帶有 `{module}` 佔位符的協議（如 `module://`）？
**架構設計回答**：
1. **自動上下文探測**：`core.uri` 內部維護一個線程安全（或當前進程）之當前模組上下文指標，呼叫端若為特定模組 script 執行環境，自動根據當前工作模組名稱解算 `{module}`；
2. **明確參數優先**：若呼叫端明確指定 `current_module='linter'`，則優先代換為該指定模組；
3. **未定義阻斷**：若無法推斷且未指定，`core.uri` 拋出明確 `ValueError: Cannot resolve placeholder {module} without active module context`，防止路徑發散至錯誤目錄。

---

## 3. 實作順序 (按依賴拓撲排序)

| 順序 | 實作項目 | 變更檔案與目標 | 品質驗證方式 |
| :---: | :--- | :--- | :--- |
| **1** | **模組元數據與能力宣告** | `source/core/manifest.json` | JSON Schema 與必要欄位格式校驗 |
| **2** | **極簡上下文介面** | `source/core/core/context.py` (`ExecutionContext`) | 資料結構定義與 3 欄位約束檢查 |
| **3** | **語意 URI 與一級 VFS 檔案系統** | `source/core/core/uri.py` (`core.uri`) | 9 大協議雙向對映、佔位符代換與 VFS I/O 方法單元測試 |
| **4** | **Contributes 聚合與注入引擎** | `source/core/core/contributes.py` (`ContributesAggregator`) | 5 大來源掃描、相依拓撲排序與注入合併測試 |
| **5** | **12 大原子操作引擎** | `source/core/core/engine.py` (`AtomicEngine`) | 下載、清冊註冊、Kahn 相依求解、兩階段重載與快照測試 |
| **6** | **7 大套件管理子指令** | `source/core/core/installer.py` (`Installer`) | `install`, `update`, `remove`, `list`, `status`, `rollback`, `reload` 管線測試 |
| **7** | **模組對外 CLI 進入點** | `source/core/scripts/cli.py` (`main`) | 命令列解析、參數分發與 Exit Code 返回測試 |
| **8** | **套件頂層匯出** | `source/core/core/__init__.py` | 匯出 `uri`, `ExecutionContext`, `AtomicEngine`, `Installer` |

---

## 4. 📚 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 判定依據 (P03/P05/P06 錨點) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
| :--- | :--- | :--- | :--- |
| `P03: core.uri VFS API` | 維度 2 (邊界與使用) | `docs/Core/uri_vfs.md` (於 `sub_07` 建立) | 詳述 9 大語意協議、佔位符與 VFS 讀寫方法操作指南 |
| `P05: 12大原子操作與生命週期` | 維度 3 (中觀動態機制) | `docs/Core/atomic_engine.md` (於 `sub_07` 建立) | 繪製 12 大原子操作流向、兩階段 RELOAD 與快照災難還原機制 |
| `P05: Contributes 聚合與注入` | 維度 3 (中觀動態機制) | `docs/Core/contributes_injection.md` (於 `sub_07` 建立) | 詳解 5 大來源 contributes 宣告格式、優先級與衝突處理 |
| `P06: 循環相依與邊界防護` | 維度 5 (工程妥協) | `docs/Core/DESIGN_NOTES.md` (於 `sub_07` 建立) | 登記 Kahn 拓撲環路攔截、Windows 檔案鎖與純淨物化防護坑點 |

---

## 5. 關鍵決策速查 (Decision Records Reference)

- **[P01:DR-01]** 微內核源碼放置於 `source/core/`，遵循標準模組化開發架構。
- **[P01:DR-02]** `RELOAD` 強制分為「階段一：純淨物化」與「階段二：依賴注入與廣播」。
- **[P01:DR-03]** `core.uri` 直接升級為一級 VFS 檔案系統介面，業務模組直接使用 URI 進行 I/O。
- **[P02:DR-01]** `core.uri` 採用模組級純函式（便於隨處呼叫），`AtomicEngine` 與 `Installer` 採用物件導向類別封裝。
- **[P03:DR-01]** 100% 依賴純 Python 標準庫，零外部 Package。
