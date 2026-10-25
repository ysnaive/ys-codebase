# 測試驗證計畫書 (Test Plan & Verification)

> 功能名稱：sub_01_core_microkernel_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Passed  
> 模型：Gemini 3.8 Flash (Medium)  

> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 模板版本：v1.4  

---

## 1. 測試案例清單 (Test Cases Inventory)

| 案例編號 | 類型 | 測試目標與驗證邏輯 (涵蓋正向副作用與負向異常) | 對應需求 | 預期結果 |
| :--- | :---: | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 `core/providers.py` 移除 `get_phase*_cli_guide` 後僅保留通用 `get_agents_cli_guide`，且 `format_undefined_uri_hint` 輸出通用提示不含 `agents-workflow` | FR-01 | 通用提示正確，純 `core` 不拋 ModuleNotFoundError |
| **FT-02** | 整合測試 | 驗證 `check_contributes` 單檔模式能自動識別 `config://agents-workflow/contribute.json` 之父目錄為目標模組，並正確執行剝殼驗證 | FR-02 | 回傳 0，若格式錯誤回傳 1 且輸出欄位錯誤 |
| **FT-03** | 整合測試 | 驗證 `_try_hot_dispatch` 接收 `["uri", "resolve"]` 時發送包含完備子命令陣列之 HTTP JSON Payload | FR-03 | 串流正常接收，正確回傳 Exit Code |
| **FT-04** | 整合測試 | 驗證 `Installer.cmd_list(remote=True)` 能夠讀取 Provider 索引並格式化印出 `Installed` 與 `Available` 狀態 | FR-04 | 終端輸出包含可用套件與版本清冊 |
| **FT-05** | 單元測試 | 驗證 `config list --local` 僅列印本機覆蓋設定；`config_inspect` 與 `config_unset` 正確調用底層 SDK 並回傳 0 | FR-05 | 覆蓋資訊與刪除結果正確呈現 |
| **FT-06** | 整合測試 | 驗證群組節點如 `uri checkk` 觸發未知子指令攔截與拼寫建議；無參數時正確輸出 `HelpRenderer` | FR-06 | 未知子指令回傳 1 且印出建議；無參數印出標準 Help |
| **FT-07** | 體檢去重 | 驗證 `test_contributes_help.py` 刪除，8 碎片檔無損併入對應主檔，`core/tests/` 總檔數收斂 | FR-07 | 測試集檔數精確收斂，無遺留碎片 |
| **FT-08** | 實質斷言 | 驗證 `sync_pip_dependencies`、損毀 Zip、`act_migrate` 與 `cmd_status` 實質執行與雙分支斷言 | FR-08 | 消除空殼 patch 與 leniency 放行 |
| **FT-09** | 沙盒隔離 | 驗證 `test_config.py` 補齊 `@require` 與 `tearDown`，執行後工作區無任何 `test_mod_*` 殘留目錄 | FR-09 | 測試後 `config://` 完全乾淨 |
| **FT-10** | 漏測補盲 | 驗證 `contributes check` 負向攔截、`OptionResolver` `--` 與布林解析、`cmd_update` 遷移階梯與 Major Lock | FR-10 | 邊界條件 100% 覆蓋通過 |
| **ET-01** | 邊界測試 | `contribute.json` 頂層未包裝 `<target_mod>` 鍵直接為設定字典時之相容驗證 | EC-01 | 正確解析或輸出明確 Schema 錯誤，不崩潰 |
| **ET-02** | 邊界測試 | 執行 `contributes check` 指定不存在之路徑或模組 | EC-02 | 輸出錯誤提示並回傳 1 |
| **ET-03** | 邊界測試 | `_try_hot_dispatch` 連線失敗降級本地派發 | EC-03 | 自動本地執行，指令不中斷 |
| **ET-04** | 邊界測試 | `list --remote` 查詢無效 Provider | EC-04 | 提示錯誤並優雅回傳 1 |
| **ET-05** | 邊界測試 | `config unset` 指定不存在之鍵值 | EC-05 | 提示未找到並回傳 1 |
| **ET-06** | 邊界測試 | `config inspect` 查詢未設定之鍵值 | EC-06 | 輸出 `source: none` 與 `effective: None` |
| **ET-07** | 邊界測試 | 群組指令輸入未知子指令模糊拼寫建議 | EC-07 | 輸出 Did you mean 建議並回傳 1 |
| **PT-01** | 效能測試 | `core` 微內核維持零第三方相依且單元測試執行快速穩定 | NFR-01 | 滿足 NFR-01 與 NFR-02 |
| **RT-01** | 全量回歸 | 執行 `python yscb.py dev test core` 確保 100% 通過 | NFR-02 | 193 Passed (100%), 0 Fail, 環境零殘留 |

---

## 2. 自動化測試案例清單 (Automated Tests Summary)

- 測試指令：`python yscb.py dev test core -q`
- 涵蓋範圍：`ys_codebase/source/core/tests/`
- 執行結果：193 Passed, 0 Fail, 0 Skip (100% 綠燈通過)

---

## 3. 測試執行紀錄表 (Test Execution Records)

| 測試編號 | 執行日期 | 執行環境 | 測試結果 | 備註 / 失敗原因分析 |
| :--- | :---: | :---: | :---: | :--- |
| **FT-01 ~ FT-10** | 2026-10-24 | 沙盒環境 | 通過 | 全部實質斷言與反向複查補齊驗證通過 |
| **ET-01 ~ ET-07** | 2026-10-24 | 沙盒環境 | 通過 | 邊界防禦與降級機制驗證通過 |
| **PT-01, RT-01** | 2026-10-24 | 沙盒環境 | 通過 | 193 個測試 100% 通過，工作區零殘留 |

---

## 4. 人工 / UX 驗證 Checkpoint (Manual & UX Verification)

- **UX-01**：在終端機手動執行 `python yscb.py list --remote` 與 `python yscb.py config inspect core project_root`，驗證命令列輸出格式美觀清晰且直觀。
