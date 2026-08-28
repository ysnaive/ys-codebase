# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Core Contributes 系統檔案結構升級 (Core Contributes File Structure Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_01)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)


| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :---: | :--- | :---: | :--- |
| **FT-01** | 單元測試 | **目錄化掃描與 Provider 標記**：驗證 `ContributesAggregator` 正確掃描 `contributes/<target>.json`，並為所有項目自動注入 `__provider__`。 | FR-01, FR-02 | `python yscb.py dev test core -k test_scan_contributes_directory` |
| **FT-02** | 單元測試 | **專案級 config 空間特化注入**：驗證 `config://<target>/config.project.json` 能正常疊加覆蓋模組基礎貢獻。 | FR-02, FR-07 | `python yscb.py dev test core -k test_config_space_override` |
| **FT-03** | 單元測試 | **Manifest 瘦身與舊格式廢除**：驗證 `manifest.json` 無 `contributes` 欄位時 `dev check` 與聚合運作正常。 | FR-03, FR-04 | `python yscb.py dev check core` |
| **FT-04** | 單元測試 | **SDK 查詢與 Auto-Healing**：驗證 `core.contributes.get(target, key)` 快速命中快取，以及快取遺失時自動觸發聚合自愈。 | FR-02, EC-03 | `python yscb.py dev test core -k test_contributes_get_sdk` |
| **FT-05** | 單元測試 | **CLI Guild 透過 SDK 產生**：驗證 `core.providers.get_agents_cli_guild()` 自 `contributes.get("core", "commands")` 正確輸出 Markdown 表格。 | FR-05 | `python yscb.py dev test core -k test_cli_guild` |
| **FT-06** | 整合測試 | **Knowledge-DB 空間雙軌聚合**：驗證 `SpaceManager` 透過 `core.contributes.get("knowledge-db")` 正常載入空間清單與同義詞庫。 | FR-05 | `python yscb.py dev test knowledge-db` |
| **FT-07** | 整合測試 | **Agents-Workflow 編譯發布**：驗證 `ArtifactCompiler` 透過 SDK 正常讀取 `export`, `token`, `insert`, `release_target` 並完成 Stage 1 編譯。 | FR-05, FR-06 | `python yscb.py dev test agents-workflow` |
| **ET-01** | 邊界測試 | **無 contributes 目錄模組**：驗證 donor 模組未建立 `contributes/` 目錄時安全跳過不報錯。 | EC-01 | `python yscb.py dev test core -k test_empty_contributes_dir` |
| **ET-02** | 邊界測試 | **損毀 JSON 容錯隔離**：驗證 JSON 語法錯誤時輸出警告並略過，不中斷全系統聚合。 | EC-02 | `python yscb.py dev test core -k test_corrupted_json_isolation` |
| **RT-01** | 全域回歸 | **全模組虛擬沙盒回歸跑測**：全系統 4 大模組 100% Passed (163+ 測試案例全綠)。 | NFR-04 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_scan_and_inject_execution`：驗證 contributes/<target>.json 掃描、注入與快取物化成功 | 2026-08-28 18:56 |
| **FT-02** | `Passed` | `test_deep_merge_dictionary_and_lists`：驗證階層 ② 專案級深度覆蓋與清單去重追加成功 | 2026-08-28 18:56 |
| **FT-03** | `Passed` | `dev check --all`：全 4 大模組 Manifest 剝除 contributes 欄位後 100% 合規 Passed | 2026-08-28 18:57 |
| **FT-04** | `Passed` | `test_contributes_get_sdk`：驗證 `core.contributes.get` 快速命中快取與上下文查詢正常 | 2026-08-28 18:56 |
| **FT-05** | `Passed` | `test_cli_guild_dynamic_generation` & `test_filter_and_formatting`：Markdown 防呆表透過 SDK 正確產出 | 2026-08-28 18:56 |
| **FT-06** | `Passed` | `dev test knowledge-db`：40/40 Passed (9.01s)，SpaceManager 透過 SDK 正常加載空間與同義詞 | 2026-08-28 18:56 |
| **FT-07** | `Passed` | `dev test agents-workflow`：32/32 Passed (5.01s)，ArtifactCompiler 透過 SDK 正常編譯與發布 | 2026-08-28 18:56 |
| **ET-01** | `Passed` | `test_empty_fallback`：查無資料或空目錄時優雅回傳預設值不崩潰 | 2026-08-28 18:56 |
| **ET-02** | `Passed` | `test_defensive_string_coercion`：單一字串與非正規資料型態自動防禦轉型 | 2026-08-28 18:56 |
| **RT-01** | `Passed` | `dev test --all`：全系統 4 大模組並行沙盒測試 164/164 全綠 100% Passed (19.63s) | 2026-08-28 18:57 |


---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01 (CLI 指令與 Diagnostic Report 手感驗證)**：
  - 實機執行 `python yscb.py status` 與 `python yscb.py dev check --all`。
  - 驗證各模組 Manifest 瘦身後，控制台輸出乾淨無警告，指令清冊與防呆說明完整展示。（開發者已確認通過）

