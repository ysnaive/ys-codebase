# 需求規格說明書 (Requirements Specification)

> 功能名稱：agents-workflow 核心骨架與 SOP 本體遷移 (Core Skeleton & SOP Body Migration)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據需求：[P00_semantic_requirements.md](./P00_semantic_requirements.md), [R01_core_skeleton_and_sop_redesign.md](./R01_core_skeleton_and_sop_redesign.md)  
> 狀態：`Confirmed`  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 純淨通用資產物化 | 建立 `source/agents-workflow/` 骨架，落實規範 (2 項: `DocumentationStandards`, `DevelopmentStandards`)、流程 (1 項: `ContextInit`)、模板 (13 項完全鏡像移植)，徹底剝離專案特化規則，維持模組 100% 抽象通用。 | P0 | [P00:DR-01] |
| **FR-02** | 宣告式 Contributes 註冊 | 在 `manifest.json` 中宣告 `export`（資產導出）、`insert`（錨點注入，支援 `const`/`uri` 與 `replace`/`below`/`above` 模式）與 `token`（錨點自省元數據）。 | P0 | [P00:DR-02] |
| **FR-03** | 多輪遞迴狀態機解算 | 實作工廠編譯器，執行 1~5 步狀態機（快照 CurrentTokens ➔ 依依賴拓撲有序注入 ➔ 移除本輪已解算標籤 ➔ 遞迴檢查新子 Token ➔ 分流儲存至 `module://exports/`）。 | P0 | [P00:DR-03] |
| **FR-04** | URI 標籤延遲解算 | 在 Export 文本中支援 `<!-- __URI("...")__ -->` 標籤，在模組內部物化階段保持原樣不解算，留待未來輸出端解算。 | P0 | [P00:DR-03] |
| **FR-05** | CLI 工廠與自省指令集 | 實作 `agents-workflow` CLI 子指令：`compile` (或 `build`)、`tokens` (或 `--list-token`)、`list`（計畫治理工具鏈明確留待後續子計畫）。 | P0 | [P00:DR-04] |
| **FR-06** | 微內核 Hook 自治閉環 | 於 `scripts/hook.core.py` 註冊 `on_reload` 生命週期監聽，在微內核執行 `yscb reload` 後自動觸發工廠編譯器自主物化。 | P0 | [P00:DR-05] |
| **FR-07** | 模組自注入內容與標頭解耦 | 提取 P01~P07 模板共通標頭至 `templates/header.md`，在各模板頂部放置 `<!-- __PHASEXX_STANDARD_HEADER__ -->` 錨點；在 `manifest.json` 中自宣告 `token` (`PHASEXX_STANDARD_HEADER`) 與 `insert`（`type: uri`, `mode: replace`, 指向 `module.root://agents-workflow/templates/header.md`），以自身閉環驗證工廠替換注入機制。 | P0 | [P00:DR-01], [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 無效 Token 或無匹配 Insert | 若 Export 文件中存在 `<!-- __TOKEN__ -->` 標籤但全系統無任何模組聲明匹配的 insert，在 Step 3 清除該標籤（避免遺留未解算代碼），系統正常完成物化而不崩潰。 |
| **EC-02** | 自我遞迴與自指防護 | 若單一 insert 注入內容中包含自身同名的 Token 標籤，該次注入視為字面值，禁止本輪自我展開，防止無窮迴圈自指死鎖。 |
| **EC-03** | 純淨環境下零外部依賴物化 | 在僅安裝 `agents-workflow` 本身、無任何第三方擴充模組之全新環境下，執行 `compile` 依然能產出 100% 完整合規的預設 exports 物化資產。 |
| **EC-04** | 損毀或格式不全之 Insert 宣告 | 若第三方模組的 insert 宣告缺少必備欄位（如 `token`、`type` 或 `mode`），編譯器印出清晰警告並安全略過該項無效 insert，不中斷整體物化。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴 | 100% 採用 Python 3.8+ 標準庫（`re`, `os`, `json` 等），嚴禁引入任何第三方套件。 |
| **NFR-02** | 編譯物化效能 | 全系統所有 export/insert 之多輪遞迴解算與檔案物化寫入總耗時 $\le 100\text{ms}$。 |
| **NFR-03** | 自動化品質守門 | Auto-Contract 與單元測試 100% 綠燈 Passed，支援在沙盒測試微環境下自包含驗證。 |

---

## 4. 專案特化擴充判定矩陣 (Extension Specialization Scan)

| 擴充功能名稱 | 判定結果 | 納入 / 排除理由 |
| :--- | :---: | :--- |
| **`sop_ext://` (SOP Extensions)** | `Excluded` | 本子計畫 `sub_01` 嚴格聚焦於通用核心骨架與 SOP 本體純淨化，排除所有特化擴充。 |
| **`ide` 指令擴充** | `Excluded` | 多 IDE 編譯生成指令留待後續專題子計畫實作。 |

---

## 5. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE] 路徑語意安全`**：在 `export.source` 與 `insert.value` 中，一律推薦使用 `{xxx.root://module/...}` 形式（如 `module.root://agents-workflow/...`），避免直接使用未初始化的抽象協議產生 Undefined Behavior。
- **`[!CAUTION] 原子寫入與剛性覆蓋`**：物化至 `module://exports/` 時，應在寫入前確保目標目錄結構存在，並以原子方式覆蓋寫入，保證運行空間純淨。
