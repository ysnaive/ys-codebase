# 實作計畫與審查定稿 (Implementation Plan & Review)

> 功能名稱：agents-workflow 核心骨架與 SOP 本體遷移 (Core Skeleton & SOP Body Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據規格：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md)  
> 狀態：`Confirmed`  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 `P03_api_spec.md` 中皆有具體的類別方法與 CLI 進入點對應。
- [x] **邊界防護**：EC-01 ~ EC-04 在多輪遞迴狀態機演算法中皆有嚴密防護（無匹配清理、自指死鎖防禦、純淨環境合規、格式不全略過）。
- [x] **依賴純淨**：NFR-01 (100% Python 標準庫)、NFR-02 (耗時 $\le 100\text{ms}$)、NFR-03 (測試 100% 綠燈)。
- [x] **自注入閉環**：`PHASEXX_STANDARD_HEADER` 提取至 `templates/header.md`，並以 `replace` 模式自我閉環驗證。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

依據 7 大抽象知識維度投影，本次計畫預排交付與維護之 `docs/` 文件：

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/agents-workflow/README.md` | New | 模組概覽、核心職責、安裝與快速入門指令。 |
| **維度 3** | `docs/agents-workflow/FACTORY_PIPELINE.md` | New | 專題手冊：協議產物工廠化原理、`export`/`insert`/`token` Schema 與多輪遞迴解算狀態機。 |
| **維度 5** | `docs/agents-workflow/DESIGN_NOTES.md` | New | 登記 `[DN-AW-01]`（協議產物工廠化）與 `[DN-AW-02]`（自注入閉環與遞迴收斂防護）。 |
| **專案日誌** | `CHANGELOG.md` | Modify | 於根目錄追加 `agents-workflow` 核心骨架落地之高階紀錄。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若兩個第三方模組同時對同一個 Token（例如 `PHASEXX_STANDARD_HEADER`）宣告了 `mode: "replace"` 衝突時，系統如何判定勝負？  
> 💡 **防護解法**：依據依賴拓撲順序（Topological Order），後載入的模組之 `replace` 將在上一輪已替換的基礎上進行（若上一輪已將 Token 標籤替換消耗掉，則第二個模組的 replace 因找不到錨點標籤而安全跳過，由拓撲先後決定首個生效者；若希望多模組共同生效，模組應使用 `below` 或 `above` 模式）。
>
> ❓ **尖銳問題 2**：在執行 `yscb dev test agents-workflow` 時，沙盒內尚未執行 `reload` 前，測試如何讀取物化後的 `module://exports/`？  
> 💡 **防護解法**：測試套件在 `setUp` 或測試方法中主動呼叫 `ArtifactCompiler().compile_all()`，保證沙盒環境原地物化，達成 100% 自包含與隔離驗證。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (靜態資產建立)**：
  - 建立 `source/agents-workflow/standards/DocumentationStandards.md` 與 `DevelopmentStandards.md`。
  - 建立 `source/agents-workflow/workflows/ContextInit.md`。
  - 建立 `source/agents-workflow/templates/header.md` 與 13 大標準模板庫（P01~P07 頂部嵌入 `<!-- __PHASEXX_STANDARD_HEADER__ -->`）。
- [ ] **TASK-02 (核心工廠編譯器實作)**：
  - 建立 `source/agents-workflow/agents_workflow/__init__.py` 與 `compiler.py`。
  - 實作多輪遞迴狀態機（快照 ➔ 拓撲注入 ➔ 清理 ➔ 遞迴檢查 ➔ 分流儲存至 `module://exports/`）。
  - 實作 `get_registered_tokens()` 與 `get_exported_artifacts()` 自省查詢方法。
- [ ] **TASK-03 (CLI 進入點與 Hook 對接)**：
  - 實作 `source/agents-workflow/scripts/cli.py`（`compile`, `tokens`, `list` 處理器與表格排版）。
  - 實作 `source/agents-workflow/scripts/hook.core.py`（`on_reload` 事件自動物化）。
- [ ] **TASK-04 (宣告式 Manifest 綁定)**：
  - 建立 `source/agents-workflow/manifest.json`，宣告 16 項 `export`、`PHASEXX_STANDARD_HEADER` 之 `insert` (replace) 與 `token` 元數據。
- [ ] **TASK-05 (自動化測試套件與沙盒驗證)**：
  - 建立 `source/agents-workflow/tests/test_compiler.py`（覆蓋 FT-01~FT-06、ET-01~ET-04）。
  - 實機執行 `python yscb.py dev test agents-workflow` 與回歸測試 `python yscb.py dev test --all`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全流程剛性定稿**：本實作計畫與 `P06_test_plan.md` 經交叉審查無誤，剛性定稿進入 Phase 5 實作。
