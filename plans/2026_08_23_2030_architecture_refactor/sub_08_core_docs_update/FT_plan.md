# 快速通道開發計畫 (Fast Track Plan)

> 功能名稱：Core 與開發者工具鏈知識庫文檔綠地重建 (Core & Dev Toolchain Documentation Greenfield Update)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00：[P00_semantic_requirements.md](../P00_semantic_requirements.md)  
> 狀態：Draft  
> 擴充項目：none  
> 模板版本：v1.4  

---

## FT-1：變更說明

### P00 語意需求摘要（引用自 P00）

- **計畫類型**：Documentation / Greenfield Update
- **核心訴求**：在 `sub_02` ~ `sub_07` 完成超薄宿主、Core 微內核、Dev 工具鏈、測試引擎與持久化測試套件後，依據《知識庫維護規範 (DocumentationStandards.md)》的 7 大抽象維度，從零綠地重建全新的知識庫（`docs/`），使微內核架構、語意 URI 協議、命名空間 Hook、依賴注入快取與測試框架具備 100% 完整之文檔手冊。
- **P00 關鍵情境摘要**：
  > 「文檔更新：更新專案根目錄、`core` 與 `dev` 模組之規範文檔與 README。」（主計畫路線圖 § Ch.2 規劃目標）

### 修改動機

在 `sub_01` 階段，為防範歷史舊代碼與舊架構文檔誤導重構實作，歷史 `docs/` 已完整移至 `.quarantine/docs_legacy/` 封存。目前 `sub_02` ~ `sub_07` 已圓滿完成全量架構實作與 31/31 測試驗收，急需建立現代化、客觀、高專業度之知識庫（`docs/`）與專案首頁，為後續 `sub_09` 遷移業務模組（`agents-workflow`）提供唯一的標準真相來源 (SSOT)。

### 修改內容

遵循知識庫 7 大抽象維度標準，全面綠地撰寫下列知識庫文檔與手冊：
1. **全域知識地圖與架構導覽 ([`docs/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/README.md))**：
   - 繪製全系統分層架構圖（Host ➔ Core Microkernel ➔ Dev Toolchain ➔ Extension Modules）。
   - 建立全域知識地圖導覽索引（維度 1）。
2. **全專案工程規範與核心標準 ([`docs/_project/STANDARDS.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/_project/STANDARDS.md))**：
   - 記錄四大空間協議定義（`project://`, `yscb://`, `config://`, `cache://` 等）；
   - 記錄 2x2 組態矩陣邊界（`config.project.json` vs `config.local.json`）；
   - 記錄 Dogfooding 自引用三層空間邊界與四步閉環流水線（維度 2）。
3. **Core 微內核架構手冊 ([`docs/core/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/README.md))**：
   - 記錄 Core 架構、AtomicEngine 12 原子操作生命週期與 `core.uri` First-Class VFS SDK（維度 2）。
4. **語意 URI 協議與動態解析專題手冊 ([`docs/core/uri_protocols.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/uri_protocols.md))**：
   - 記錄 14 組自注入標準 URI 協議定義與 `contributes.merged.json` 中介快照載入機制；
   - 記錄 `project://` 嚴格顯式配置與零 Fallback 阻斷規範（維度 3）。
5. **命名空間 Hook 與生命週期事件手冊 ([`docs/core/lifecycle_and_hooks.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/lifecycle_and_hooks.md))**：
   - 記錄 `module.root://*/scripts/hook.{emit_module}.py` 對接規範、`ExecutionContext` 介面與 try-except 例外隔離（維度 3）。
6. **Core 設計決策與工程妥協 ([`docs/core/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/DESIGN_NOTES.md))**：
   - 登記 `DN-01` ~ `DN-04`（`project://` 零 Fallback、顯式 `config/`、`cache/` 中介層、例外隔離）（維度 5）。
7. **Dev 工具鏈架構手冊 ([`docs/dev/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/README.md))**：
   - 記錄 Scaffold 腳手架、Checker 靜態合規檢查器、Builder 純淨打包器（維度 2）。
8. **Dev 測試框架與沙盒指南 ([`docs/dev/testing_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/testing_guide.md))**：
   - 記錄 `YSCBTestCase` 沙盒生命週期、Auto-Contract 契約合成、兩階段測試與斷言輔助庫（維度 3）。
9. **Dev 設計決策與工程妥協 ([`docs/dev/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/DESIGN_NOTES.md))**：
   - 登記 `DN-DEV-01`（動態契約合成機制）等工程決策（維度 5）。
10. **專案首頁與快速上手手冊 ([`project://README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/README.md))**：
    - 更新專案根目錄之快速安裝、初始化、指令速查手冊。

### 受影響的檔案清單

| 檔案路徑 | 變更類型 | 說明 |
| :--- | :---: | :--- |
| [`docs/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/README.md) | NEW | 全域知識地圖與架構導覽 |
| [`docs/_project/STANDARDS.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/_project/STANDARDS.md) | NEW | 全專案工程規範與核心標準 |
| [`docs/core/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/README.md) | NEW | Core 微內核架構手冊 |
| [`docs/core/uri_protocols.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/uri_protocols.md) | NEW | 語意 URI 協議與動態解析專題手冊 |
| [`docs/core/lifecycle_and_hooks.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/lifecycle_and_hooks.md) | NEW | 命名空間 Hook 與生命週期事件手冊 |
| [`docs/core/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/DESIGN_NOTES.md) | NEW | Core 設計決策與工程妥協 (DN-01~04) |
| [`docs/dev/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/README.md) | NEW | Dev 工具鏈架構手冊 |
| [`docs/dev/testing_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/testing_guide.md) | NEW | Dev 測試框架與沙盒指南 |
| [`docs/dev/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/DESIGN_NOTES.md) | NEW | Dev 設計決策與工程妥協 |
| [`README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/README.md) | Modify | 專案根目錄快速上手與架構概述 |

### 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| sop_ext 清單 | on_demand | ❌ 排除 (Excluded) | 本子計畫專注於核心知識庫與規範文檔綠地重建，無特化擴充規則 |

### Decision Records

---

**[FT:DR-01] [NEW] 嚴格對齊知識庫 7 大抽象維度與事實與過程分離原則**
- 結論：所有新建文檔嚴格採用當前客觀事實陳述，不記錄歷史爭論過程；複雜協同主題強制拆分中觀專題手冊 (`docs/<Module>/[topic].md`)。
- 理由：確保知識庫文檔結構具備極致的可讀性、精準度與模組化獨立性。

**[FT:DR-02] [NEW] 設計決策顯式登錄 `DESIGN_NOTES.md`**
- 結論：凡涉及非直觀或具備安全防衛的設計（如 `project://` 零 Fallback 阻斷、中介層快照存於 `cache://`、Hook 例外隔離），強制登錄至相應模組的 `DESIGN_NOTES.md`。
- 理由：防止未來維護者與 Agent 誤修或破壞核心安全約束。

### 閉合確認 (Closing Confirmation)

- [x] 開發者已確認：目前討論已完整，無其他新議題

---

## FT-2：實作清單

- [x] **TASK-01**：建立全域地圖與專案規範
  - [x] 建立 [`docs/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/README.md)（系統全域知識地圖）
  - [x] 建立 [`docs/_project/STANDARDS.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/_project/STANDARDS.md)（核心工程規範、2x2 組態矩陣、Dogfooding 三層空間）
- [x] **TASK-02**：建立 Core 微內核知識庫文檔
  - [x] 建立 [`docs/core/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/README.md)（Core 架構、AtomicEngine 12 原子操作、VFS SDK）
  - [x] 建立 [`docs/core/uri_protocols.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/uri_protocols.md)（14 組 URI 協議、`project://` 零 Fallback、動態自注入解析）
  - [x] 建立 [`docs/core/lifecycle_and_hooks.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/lifecycle_and_hooks.md)（`hook.{emit_module}.py` 對接手冊、`ExecutionContext`、例外隔離）
  - [x] 建立 [`docs/core/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/DESIGN_NOTES.md)（登錄 `DN-01` ~ `DN-04`）
- [x] **TASK-03**：建立 Dev 開發者工具鏈知識庫文檔
  - [x] 建立 [`docs/dev/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/README.md)（Dev 架構、Scaffold, Checker, Builder 工具說明）
  - [x] 建立 [`docs/dev/testing_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/testing_guide.md)（`YSCBTestCase` 沙盒生命週期、Auto-Contract 動態契約合成、兩階段測試）
  - [x] 建立 [`docs/dev/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/DESIGN_NOTES.md)（登錄 `DN-DEV-01` 等）
- [x] **TASK-04**：更新專案根目錄指南
  - [x] 更新 [`README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/README.md)（專案首頁、快速安裝與指令速查）

---

## FT-3：測試與驗證計畫

### 測試項目與驗證方法

| 測試編號 | 測試項目 | 驗證目標 | 執行方式 | 預期結果 | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **DOC-01** | 文檔超連結與錨點完整性 | 驗證所有新建文檔內部相對路徑跳轉有效性 | 靜態巡檢 | 無任何死鏈或失效路徑 | ✅ Passed |
| **DOC-02** | 知識庫 7 大抽象維度合規性 | 驗證各文檔均具備明確主題、分層與程式碼範例 | 規範審查 | 100% 符合 DocumentationStandards | ✅ Passed |
| **DOC-03** | 程式碼範例可執行性 | 驗證文檔中所有 CLI 指令與 Python 代碼範例正確性 | 實機測試 | 所有範例指令與語法正確無誤 | ✅ Passed |
| **DOC-04** | 全量回歸測試守門 | 驗證更新文檔後既有代碼與測試不受任何影響 | `dev test --all` | 31/31 測試全數 Passed (0.438s) | ✅ Passed |
