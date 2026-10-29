# 修訂紀錄書 (Revision Log)

> 功能名稱：核心多層次語系與語意契約引擎實現 (`sub_01_core_locale_engine`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] 補齊專案預設語系 `["zh"]`（團隊母語最終 Fallback）並支援初次安裝系統主語系播種至 `config.local.json`
- **修訂類別**：Parameter
- **涉及檔案**：
  - [ys_codebase/source/core/configurable/config.project.json](file:///workspace/ys-codebase/ys_codebase/source/core/configurable/config.project.json)
  - [ys_codebase/config/core/config.project.json](file:///workspace/ys-codebase/ys_codebase/config/core/config.project.json)
  - [ys_codebase/source/core/core/locale.py](file:///workspace/ys-codebase/ys_codebase/source/core/core/locale.py)
  - [ys_codebase/source/core/core/engine.py](file:///workspace/ys-codebase/ys_codebase/source/core/core/engine.py)
  - [ys_codebase/source/core/tests/test_locale.py](file:///workspace/ys-codebase/ys_codebase/source/core/tests/test_locale.py)
  - [docs/core/README.md](file:///workspace/ys-codebase/docs/core/README.md)
- **修訂摘要**：
  1. 為求精簡聚焦於專有名詞（Dialect / Proper Nouns）治理，將最終 Fallback 統一採用開發團隊母語 `zh`（現階段暫不處理 `en` 語系，後續 CLI、模板與文檔多語系支援收斂至 Roadmap [i18n_workflow_and_downstream_governance.md](file:///workspace/ys-codebase/plans/roadmap/i18n_workflow_and_downstream_governance.md)）。
  2. 將 `core.locale.DEFAULT_LOCALE_CHAIN`、`ys_codebase/source/core/configurable/config.project.json` 與 `ys_codebase/config/core/config.project.json` 之固定專案級預設值統一為 `["zh"]`。
  3. 新增 `core.locale.detect_system_locale_chain()`（純標準庫探測 `LC_ALL` -> `LC_MESSAGES` -> `LANG` -> Windows UI Language -> `locale.getlocale()`），僅提取主語系並以 `zh` 作為最終退避保底（如 `zh_TW.UTF-8` -> `["zh"]`、`ja_JP` -> `["ja", "zh"]`；遇 `C` / `POSIX` / 未知環境則保底為 `["zh"]`），於初次建立 `core` 組態時自動寫入 `config.local.json`。
- **驗證結果**：`dev check core` 100% 通過，`dev test core -q` 205/205 單元測試通過，完成 `core@build` 本機熱部署。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 docs/ 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 CHANGELOG.md。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
