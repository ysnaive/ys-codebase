---
name: documentation
description: 定位、檢索、撰寫與審校 `__${workflow.docs://}__` 系統知識庫文檔 (ARCHITECTURE.md、模組 README.md、專題手冊、DESIGN_NOTES.md) 與原始碼 Docstring，落實 7 大知識維度歸屬與三層文檔交付對齊。觸發情境：查閱或更新 `__${workflow.docs://}__` 架構與防坑手冊、新增公開 API 註解、執行結案階段 (Phase 07 / FP-03) 三層文檔審查。排除情境：建立或管理 `__${workflow.plans://}__` 下之開發過程產物如 P00~P07、fast_track_plan 或 revision_log（改用 development-sop）。
---

# 專案知識庫架構與閱讀導引 (Documentation Standards - Reader's Guide)

本指南定義專案「系統知識庫（`__${workflow.docs://}__`）」與「開發過程紀錄（`__${workflow.plans://}__`）」的職責邊界、軟體工程 7 大抽象知識維度檢索地圖，以及撰寫／維護知識庫文檔時的標準作業程序。

---

## 1. 核心定位：兩套系統的職責劃分

專案嚴格區分「過程導向的計畫紀錄」與「狀態導向的系統知識庫」，切勿混用：

| 系統 | 語意定位 | 職責與生命週期 | 內容性質 |
| :--- | :--- | :--- | :--- |
| **開發過程紀錄** | `__${workflow.plans://}__` / `__${workflow.archived://}__` | 記錄探索、爭辯、任務與決策過程；**結案後永久凍結歸檔** | 過程導向、`DR` 決策脈絡、任務清單（由 [`development-sop`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`) 管轄） |
| **系統知識庫** | `__${workflow.docs://}__` | 記錄現況事實、架構拓撲與防坑邊界；**隨代碼持續演進更新** | 狀態導向、唯一現況真理（SSOT）、邊界合約（由本 `documentation` 技能管轄） |

> [!IMPORTANT]
> **知識庫只陳述客觀現狀與坑點，不記錄歷史爭辯過程。** 探索、爭辯與替代方案留於 `__${workflow.plans://}__`，`__${workflow.docs://}__` 專注於回答「現在是什麼架構」與「邊界條件/不變量」。

---

## 2. 軟體工程 7 大抽象知識維度（知識檢索地圖）

知識庫檔案按 `<Category>`（代表業務領域、架構子系統或多層命名空間，支援單層如 `core` 或多層如 `Render/Layout/FlexEngine`）進行組織：

| 維度 (Dimension) | 核心範疇 | 知識庫檔案位置 (Carrier) | 查閱與更新守門條件 |
| :--- | :--- | :--- | :--- |
| **① 領域概念模型** | 領域通用語言 (Ubiquitous Language)、實體與名詞定義 | `__${workflow.docs://_project/ARCHITECTURE.md}__`<br>`__${workflow.docs://}__/<Category>/README.md` | 理解全域與子系統業務實體概念；新增重大子系統或實體時更新 |
| **② 靜態邊界與拓撲** | 模組/子系統職責邊界（做什麼、不做什麼）、依賴方向 | `__${workflow.docs://_project/ARCHITECTURE.md}__`<br>`__${workflow.docs://}__/<Category>/README.md` | 確認架構邊界與模組依賴方向；變更模組核心職責時同步更新 |
| **③ 中觀動態機制** | 跨類別協同、資料流、狀態機 (FSM)、協議與生命週期 | `__${workflow.docs://}__/<Category>/[topic].md`<br>*(獨立專題手冊)* | 深入理解複雜控制流、資料管線與狀態轉換時查閱或獨立建檔 |
| **④ 介面合約與承諾** | 前置/後置條件、錯誤型態、輸入輸出 Schema | 程式碼 Docstrings / Public Headers | 修改 Public API 簽名、傳參、回傳值或例外時，隨源碼一併交付更新 |
| **⑤ 工程妥協與防坑** | 為效能/平台限制而採取的反直覺設計 (Non-obvious) | `__${workflow.docs://}__/<Category>/DESIGN_NOTES.md`<br>*(DN-XX + `[!CAUTION]`)* | 修改複雜模組前必讀！記錄反直覺設計與防坑設計，避免誤改破壞 |
| **⑥ 人因操作引導** | 快速上手、配置矩陣、典型範例 (Cookbook)、故障排查 | `__${workflow.docs://}__/<Category>/README.md`<br>`__${workflow.docs://_project/CLI_SPECIFICATION.md}__` | 查閱指令用法、配置參數與快速上手；新增或變更 CLI/組態時更新 |
| **⑦ 架構演進歷史** | 重大架構重構歷史（痛點 -> 改變 -> 參照 Plan） | `__${workflow.docs://}__/<Category>/CHANGELOG.md`<br>`__${project://CHANGELOG.md}__` | 每個開發計畫結案（`Phase 07` / `FP-03`）涉及架構演進時動態增補 |

---

## 3. 查閱與撰寫分流 SOP（按需載入作者指南）

- **情境 A：僅需「閱讀／檢索」既有知識庫**：
  1. 先讀 `__${workflow.docs://_project/ARCHITECTURE.md}__` 或目標模組之 `<Category>/README.md` 定位組件。
  2. 修改任何既有模組代碼前，**優先檢查該模組下是否存在 `DESIGN_NOTES.md`**，避免踩入已知的架構陷阱。
- **情境 B：需要「撰寫／新增／修改」知識庫文檔，或執行 `Phase 07` / `FP-03` 三層文檔審查**：
  - **[!] 強制按需載入**：在動筆修改任何 `__${workflow.docs://}__` 文檔前，**必須先讀取 [文檔撰寫與作者指引 (references/author_guide_and_checklist.md)](./references/author_guide_and_checklist.md)**，遵循其中的文檔歸屬判定決策樹、中觀專題手冊 5 大情境、三層交付閉環、寫作黃金三法則、YAML Frontmatter Schema 與作者自檢核對清單。

---

## 常見踩坑指南 (Gotchas)

- **嚴禁把「開發過程中的修訂流水帳」寫進 `__${workflow.docs://}__` 主文檔**：知識庫只描述「系統現在是什麼樣子（Status-Oriented）」，不要在 `README.md` 裡寫「我們在某年某月把 v1 改成了 v2」（歷史演進應寫在 `CHANGELOG.md` 或 `__${workflow.plans://}__`）。
- **嚴禁在知識庫複製貼上大段源碼實作**：實作細節以源碼為唯一真理（SSOT），文檔應使用表格或 Mermaid 圖描述架構與合約，避免代碼改動後文檔立刻過期。
