# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Core Contributes 系統檔案結構升級 (Core Contributes File Structure Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_01)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書與架構設計中皆有具體介面與資料流承接。
- [x] **邊界防護**：EC-01 ~ EC-05 之各類異常（無 contributes 目錄、JSON 損毀、快取自愈、去重）皆有專屬錯誤處理防線。
- [x] **依賴純淨**：100% 使用 Python 3 原生標準庫，零外部第三方依賴 (NFR-01)。
- [x] **三層空間恪守**：模組內部嚴格拘束於 `module://`，徹底清除任何 `module.source://` 穿透代碼。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `source/core/contributes.format.md` | Update | 更新為最新 `contributes/<target>.json` 目錄化規格與宣告手冊 |
| **維度 2** | `source/knowledge-db/contributes.format.md` | Update | 更新為 `contributes/knowledge-db.json` 標準規格 |
| **維度 3** | `source/agents-workflow/contributes.format.md` | Update | 更新為 `contributes/agents-workflow.json` 標準規格 |
| **維度 4** | `source/dev/contributes.format.md` | Update | 更新為 `contributes/core.json` 與 `contributes/agents-workflow.json` 標準規格 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若某個 donor 模組在 `contributes/` 下建立了不存在於當前系統已安裝清單的 `target.json`（例如 `contributes/future-plugin.json`），系統是否會崩潰？  
> 💡 **防護解法**：`ContributesAggregator` 在掃描時，以掃描到的所有 targets 作為鍵值物化快取至 `cache://<target>/contributes.merged.json`，即使目標模組尚未安裝，資料安全留存於快取中，目標模組安裝後立即可被 SDK 查詢，零崩潰且具備未來擴充韌性。

> ❓ **尖銳問題 2**：若下游專案在 `config.project.json` 中自訂同名 command 或 space，是否會被 donor 模組的更新衝掉？  
> 💡 **防護解法**：`ContributesAggregator` 採用兩階段合併順序：階層 ① 模組貢獻 ➔ 階層 ② 專案組態。專案級組態在最後執行 `_deep_merge` 疊加覆蓋，保證專案特化宣告擁有絕對最高優先權。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (資產分拆)**：為 4 大核心模組建立 `contributes/<target>.json` 檔案：
  - `source/core/contributes/{core.json, agents-workflow.json}`
  - `source/dev/contributes/{core.json, agents-workflow.json}`
  - `source/knowledge-db/contributes/core.json`
  - `source/agents-workflow/contributes/{core.json, agents-workflow.json}`
- [ ] **TASK-02 (Manifest 瘦身)**：自 4 大核心模組之 `manifest.json` 徹底移除 `"contributes"` 物件。
- [ ] **TASK-03 (Core 聚合引擎重構)**：改寫 `source/core/core/contributes.py`，僅掃描 `contributes/<target>.json` 與 `config://`，升級 `_tag_provider` 與 `scan_and_inject`。
- [ ] **TASK-04 (Core 消費端收斂)**：
  - 改寫 `source/core/core/providers.py`：移除 `module.source://` 探針，改呼叫 `core.contributes.get("core", "commands")`。
  - 改寫 `source/core/core/engine.py`：`act_get_installed_commands_summary` 改呼叫 `core.contributes.get("core", "commands")`。
- [ ] **TASK-05 (Knowledge-DB 消費端收斂)**：改寫 `source/knowledge-db/knowledge_db/space.py`，廢除手寫遍歷與 `origin`，改呼叫 `core.contributes.get("knowledge-db")`。
- [ ] **TASK-06 (Agents-Workflow 消費端收斂)**：改寫 `source/agents-workflow/agents_workflow/compiler.py`，廢除手寫遍歷與 `module.source://` 探針，改呼叫 `core.contributes.get("agents-workflow")`。
- [ ] **TASK-07 (單元測試與全系統驗證)**：更新 `source/core/tests/test_contributes.py`，實機執行 `python yscb.py dev test --all`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[sub_01:P04:DR-01] 剛性定稿 7 大 TASK 實作清單與 P06 測試計畫**：確定依序實作，並在全系統回歸通過後於 Phase 6 進入 UX 驗證關卡。
