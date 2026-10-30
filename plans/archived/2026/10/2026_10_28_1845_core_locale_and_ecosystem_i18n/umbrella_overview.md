# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：核心多層次語系與宿主專有名詞引擎架構 (`core_locale_and_ecosystem_i18n`)  
> 建立日期：2026-10-28  
> 計畫狀態：Completed  
> Umbrella 模式：Incremental (增量演進型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  - 將多語系與宿主環境專有名詞（Dialect / Host Proper Nouns）治理定調為 **YSCB 微內核原語 (`core.locale`)**，而非下游專案通用 i18n 工具或會引發循環依賴的獨立外掛模組。
  - 建立支援 **多層優先級退避鏈（Multi-Layer Fallback Chain，如 `[nouns-antigravity|nouns-claude|nouns-codex] -> zh-TW -> zh -> en`）** 與 **遞迴專有名詞插值（Recursive Token Interpolation，如 `{tool.read_range}`）** 的輕量解析引擎。
  - 採用 **宣告式檔案指標 + 語意解釋契約（`"locales": {"definition": "locales/definition.json", "<lang-id>": "locales/<lang-id>.json"}`）** 設計，保持 `contributes/core.json` 極致精簡，並賦能 `contributes check` / `dev check` 執行 100% 確定性的孤兒鍵（Orphan Keys）、缺失鍵（Missing Keys）與變數佔位符（Placeholders）靜態契約校驗。
- **架構邊界**：
  - 本主計畫採 **Incremental（增量演進型）** 滾動推進：
    - **`sub_01_core_locale_engine`**：專注於 `core.locale` 核心解析引擎、`contributes/_format.json` 之 `locales` Schema 契約、基於 `definition` 的靜態校驗器擴充（`core.validator` / `dev.checker`）與 CLI 檢視/校驗指令實現（**嚴格排除各模組業務接入與字串遷移**）。
    - **後續子計畫（`sub_02+` 專注於宿主專有名詞接入 + `zh` 母語保底）**：現階段最終 Fallback 統一固定為開發團隊母語 `["zh"]`，暫不處理 `en` 等多語系翻譯（全系統 CLI、模板與文檔之多語系 `en` 支援已收斂至長期路線圖 [i18n_workflow_and_downstream_governance.md](file:///workspace/ys-codebase/plans/roadmap/i18n_workflow_and_downstream_governance.md)），專注於將宿主環境專有名詞（如 `{tool.read_range}` 等跨平台工具/概念代稱）透過 `[nouns-<host>, "zh"]` 優先級鏈接入 `knowledge-db` 與 `agents-workflow`。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_locale_engine` | Full Track | `Completed` | 實作 `core.locale` 多層 Fallback 與遞迴插值引擎、`contributes/core.json` 之 `locales` (`definition` + `<lang-id>`) 宣告式 Schema、聚合與靜態契約校驗機制（不含各模組業務接入） |
| **sub_02** | `sub_02_host_nouns_and_dogfooding` | Full Track | `Completed` | 於 `agents-workflow` 建立跨平台宿主環境專有名詞庫（`nouns-antigravity` / `nouns-claude` / `nouns-codex` + `zh` 母語保底），實作編譯期 Target 綁定與執行期呼叫端 IDE/Agent 環境變數自動嗅探前置 `nouns-<host>`，並於 `knowledge-db` 截斷提示完成首輪 Dogfooding 實機驗證 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 0（主計畫架構調研定調）**：完成 [R01_core_locale_declarative_architecture.md](R01_core_locale_declarative_architecture.md) 專題調研，確立 `core.locale` 內核定位、多層 Fallback 優先級鏈與 `definition` 語意契約設計。
- [x] **里程碑 1（`sub_01` 核心引擎與靜態校驗閉環）**：完成 `core.locale` 核心引擎、`locales` 擴充點 Schema 與 `definition` 靜態契約校驗實現及單元測試 100% 守門。
- [x] **里程碑 2（`sub_02` 宿主專有名詞庫與首輪 Dogfooding 實機驗證）**：完成 `agents-workflow` 之 `agent_tool.*` 宿主專有名詞庫、Stage 2 `` `__%{key}__` `` 投影、執行期多平台並發環境變數自動嗅探與 `knowledge-db` 截斷提示接入。

