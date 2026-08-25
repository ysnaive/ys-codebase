# 實作計畫與定稿審查 (Implementation Plan & Review)

> 功能名稱：架構合規性缺陷修復與穩固性強化 (Architecture Compliance Bugfix & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01~P03：[P01](./P01_requirements_spec.md), [P02](./P02_architecture_plan.md), [P03](./P03_api_spec.md)  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 交叉審查核對清單 (Cross-Validation Checklist)

- [x] **FR 覆蓋完整性**：P01 中 FR-01 ~ FR-06 於 P03 API 規格書中皆有對應介面與簽名（`set_host_dir`, `_get_config`, `cmd_remove`, `_update_index_json`, `act_solve_deps`）。
- [x] **EC 錯誤處理對齊**：P01 中 EC-01 ~ EC-06 於 P02/P03 均具備顯式例外阻斷（`FileNotFoundError`, `ValueError`, Exit Code 1）。
- [x] **追溯鏈剛性對齊**：`P00 議題` ➔ `P01 (FR/EC)` ➔ `P02/P03 (API/DR)` ➔ `P06 (FT/RT)` 實現 100% 雙向追溯。
- [x] **零第三方依賴**：所有修改 100% 維持純 Python 3 標準庫實現。

---

## 2. 靈魂拷問 (Stress Test & Edge Case Scrutiny)

> **架構審查員提問**：  
> 「在自引用（Dogfooding）開發情境下，若開發者同時在 `source/core/` 編輯源碼並執行 `python yscb.py dev test --all`，`uri._get_yscb_root()` 在 `source/` 與 `modules/` 兩空間下是否能保證計算出的 `yscb_root` 絕對一致，且不會因目錄結構不同而發生錯置？」

**架構解析與防護回答**：
- 在源碼端：檔案路徑為 `<yscb_root>/source/core/core/uri.py`。
  `__file__` (uri.py) ➔ 上 1 層 (`source/core/core`) ➔ 上 2 層 (`source/core`) ➔ 上 3 層 (`yscb_root`)。
- 在運行端：檔案路徑為 `<yscb_root>/modules/core/core/uri.py`。
  `__file__` (uri.py) ➔ 上 1 層 (`modules/core/core`) ➔ 上 2 層 (`modules/core`) ➔ 上 3 層 (`yscb_root`)。
- 兩者在檔案樹深度上**完全對稱（均為剛好 3 層）**，因此在開發階段 (`source/`) 與運行階段 (`modules/`) 解析出來的 `yscb_root` 實體路徑 100% 完全相同，具備完美的對稱性與空間穩定性！

---

## 3. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

> 依據 7 大抽象知識維度，預排本次實作完成後需同步交付更新之文檔清單：

| 知識庫文檔路徑 | 知識維度 | 預排更新內容與主題 | 對應 P03/P06 驗收錨點 |
| :--- | :---: | :--- | :--- |
| [`docs/core/uri_protocols.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/uri_protocols.md) | 維度 3 | 更新 `yscb://` 代碼位置常數確定性自定位與 Host Context 注入機制說明 | P03 §1.1 / FT-02 |
| [`docs/core/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/DESIGN_NOTES.md) | 維度 5 | 登記 `DN-05`（宿主組態實體路徑解耦）與 `DN-06`（常數自定位與零猜測阻斷） | P01 DR-01, DR-02 |
| [`docs/dev/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/README.md) | 維度 2 | 補充 `Builder` 自動增量維護 `index.json` 之 Schema 與行為說明 | P03 §1.4 / FT-04 |
| [`source/dev/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/contributes.format.md) | 維度 4 | 新建 Dev 模組對外貢獻格式說明書（宣告 `module.source.*`, `module.build.*`） | FR-05 |

---

## 4. 實作任務清單 (Implementation Task Matrix)

| 任務編號 | 實作項目 | 目標檔案 | 對應 FR / EC | 依賴前置 |
| :--- | :--- | :--- | :--- | :---: |
| **TASK-01** | `core.uri` 定錨與 Context 注入重構 | `source/core/core/uri.py` | FR-02<br/>EC-02 | 無 |
| **TASK-02** | `core.engine` 宿主組態解耦與相依拓撲求解 | `source/core/core/engine.py` | FR-01, FR-05, FR-06<br/>EC-01, EC-06 | TASK-01 |
| **TASK-03** | `core.installer` 反向相依安全阻斷防護 | `source/core/core/installer.py` | FR-04<br/>EC-03, EC-04 | TASK-02 |
| **TASK-04** | `dev.builder` `index.json` 自動生成與維護 | `source/dev/dev/builder.py` | FR-03<br/>EC-05 | TASK-01 |
| **TASK-05** | `yscb.py` 宿主注入 `YSCB_HOST_DIR` 與 `cmd_init` 補齊 | `yscb.py` | FR-02, FR-05 | TASK-01 |
| **TASK-06** | 補齊 Dev 貢獻說明書與持久化測試套件 | `source/dev/contributes.format.md`<br/>`source/core/tests/`, `source/dev/tests/` | FT-01~FT-08<br/>RT-01 | TASK-01~05 |

---

## 5. 決策紀錄整合 (Decision Records Master List)

- `[P01:DR-01]`：宿主組態檔案操作與 `project://` 徹底隔離。
- `[P01:DR-02]`：`yscb://` 由代碼樹常數確定性定錨，廢除模糊爬目錄探測。
- `[P02:DR-01]`：宿主 Context 注入採用「環境變數傳遞 + API 設定」雙通道。
- `[P02:DR-02]`：`index.json` 採原地掃描增量維護。
- `[P03:DR-01]`：統一以 `_find_host_config()` 作為宿主組態單一真相入口。

---

## 6. 閉合確認 (Closing Confirmation)

- [x] 開發者已確認：Phase 4 實作計畫定稿與靈魂拷問審查無誤，指示進入 Phase 5 開始實作
