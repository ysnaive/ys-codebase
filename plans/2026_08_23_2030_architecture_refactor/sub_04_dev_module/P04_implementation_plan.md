# 最終實作計畫書 (Implementation Plan)

> 功能名稱：開發者工具模組 (Dev Developer Tools Module)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 狀態：Confirmed
> 擴充項目：none
> 模板版本：v1.4

---

## 1. 交叉驗證與架構檢核 (Cross-Verification Checklist)

- [x] **FR 對齊**：P01 4 大功能需求 (`FR-01` scaffold/create, `FR-02` checker/check, `FR-03` builder/build, `FR-04` VFS 整合) 在 P03 均有對應模組與類別簽名
- [x] **EC 防護**：P01 4 大 Edge Cases (`EC-01` ~ `EC-04`) 在 P03 重複命名阻斷、合法識別碼校驗、AST 語法報錯與來源不存在檢查中均有明確防禦策略
- [x] **架構一致**：P02 模組劃分（`manifest.json`, `scaffold.py`, `checker.py`, `builder.py`, `cli.py`）與 P03 簽章 100% 一致
- [x] **規範約束**：100% 純 Python 3.8+ 標準庫（零第三方相依），所有檔案操作均透過 `core.uri` 一級 VFS，保證路徑無知性
- [x] **Test-First 剛性定稿**：`P06_test_plan.md` 測試矩陣已同步定稿為 `Confirmed`

---

## 2. 靈魂拷問 (Stress Test)

### Q1: `dev check` 進行 Python 語法與代碼檢查時，若模組頂層包含具備副作用的全局執行代碼，如何確保檢查過程絕對安全且不觸發執行？
**架構設計回答**：
1. **靜態 AST 解析 (Static AST Parsing)**：`Checker` 嚴禁使用 `importlib.import_module` 或 `exec()` 載入目標代碼，而是純粹讀取源碼字串並透過標準庫 `ast.parse(source_code)` 進行靜態抽象語法樹分析；
2. **零副作用保證**：即使模組代碼內部包含惡意指令或未定義依賴，靜態檢查均可在毫秒級完成語法驗證，絕不觸發任何運行期副作用。

### Q2: `dev build` 如何處理全域系統暫存快取與模組專屬自訂打包過濾清單？
**架構設計回答**：
1. **雙層過濾器架構 (Two-Layer Filter System)**：
   - **Layer 1 (全域系統預設黑名單)**：自動強制剃除所有底層暫存垃圾（`__pycache__`、`*.pyc`、`*.pyo`、`*.tmp`、`*.bak`、`.git*`、`.pytest_cache`、`.DS_Store` 等）；
   - **Layer 2 (模組專屬 `.yscbignore` 獨立過濾檔)**：模組若包含開發期測試或草稿，可在模組根目錄維護 `source/<module>/.yscbignore`（例如排除 `tests/`、`docs/`、`*.local.json` 等）。維持 `manifest.json` 純淨無污染；
2. **`fnmatch` 模式比對與產物自除**：建置器聚合 Layer 1 與 Layer 2 規則進行動態過濾複製，且 `.yscbignore` 檔案本體亦不會打包流入 `build/<module>/` 發布目錄。

---

## 3. 實作順序 (按依賴拓撲排序)

| 順序 | 實作項目 | 變更檔案與目標 | 品質驗證方式 |
| :---: | :--- | :--- | :--- |
| **1** | **模組元數據與依賴宣告** | `source/dev/manifest.json` | JSON Schema 與 `core` 依賴格式校驗 |
| **2** | **腳手架產生器** | `source/dev/dev/scaffold.py` (`Scaffolder`) | 模組建立、命名校驗與標準骨架完整性單元測試 |
| **3** | **規範合規檢查器** | `source/dev/dev/checker.py` (`Checker`) | `manifest`、進入點、AST 語法校驗與錯誤回報測試 |
| **4** | **純淨建置發布工具** | `source/dev/dev/builder.py` (`Builder`) | 純淨建置、快照垃圾過濾與 `--all` 批次建置測試 |
| **5** | **套件頂層匯出** | `source/dev/dev/__init__.py` | 匯出 `Scaffolder`, `Checker`, `Builder` |
| **6** | **模組對外 CLI 進入點** | `source/dev/scripts/cli.py` (`main`) | 命令列解析、參數分發與 Exit Code 返回測試 |

---

## 4. 📚 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 判定依據 (P03/P05/P06 錨點) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
| :--- | :--- | :--- | :--- |
| `P03: Scaffolder API` | 維度 2 (邊界與使用) | `docs/Dev/scaffold.md` (於 `sub_07` 建立) | 模組建立指南、標準 3 層源碼結構與腳手架自訂選項 |
| `P03: Checker & Builder API` | 維度 2 (邊界與使用) | `docs/Dev/checker_and_builder.md` (於 `sub_07` 建立) | 規範檢查清單、純淨建置發布流程與過濾規則 |
| `P06: 靜態過濾與安全檢查` | 維度 5 (工程妥協) | `docs/Dev/DESIGN_NOTES.md` (於 `sub_07` 建立) | 登記 AST 靜態解析零副作用與白名單建置防護坑點 |

---

## 5. 關鍵決策速查 (Decision Records Reference)

- **[P01:DR-01]** `dev` 模組宣告依賴 `core@>=1.0.0`，全面透過 `core.uri` 操作 VFS。
- **[P01:DR-02]** 純淨建置嚴格過濾 `__pycache__`、`*.pyc`、`*.tmp`、`*.bak`、`.git*`。
- **[P02:DR-01]** 全面透過 `module.source://` 與 `module.build://` 語意協議進行檔案定址。
- **[P02:DR-02]** `dev test` 測試執行引擎與沙盒基礎設施全量集中於 `sub_05` 打造。
- **[P03:DR-01]** `Builder.build_module` 前置強制調用 `Checker.check_module` 執行守門檢查。

- **[P04:DR-01]** 採用 `.yscbignore` 作為標準打包過濾機制：維持 `manifest.json`  чисто（純淨），將排除規則獨立於 `.yscbignore` 管理，與全域黑名單合併過濾且不打包進發布產物。