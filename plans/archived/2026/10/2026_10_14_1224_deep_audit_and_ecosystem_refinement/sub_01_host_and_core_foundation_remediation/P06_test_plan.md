# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_host_and_core_foundation_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `ContributesAggregator` 生成 `__modules__` 且 `providers.get_agents_cli_guild` 獨立列出各模組 `status`/`list` | FR-01 | `python yscb.py dev test core -k test_contributes` |
| **FT-02** | 單元測試 | 驗證 `contributes list --module=core` 透過 `OptionResolver` 解析字串參數並回傳正確結果 | FR-02 | `python yscb.py dev test core -k test_contributes_cmd` |
| **FT-03** | 單元測試 | 驗證 `AtomicEngine.act_prepare` 正確檢查 `module.mirror://` 且重複定義方法已安全移除 | FR-03 | `python yscb.py dev test core -k test_engine` |
| **FT-04** | 單元測試 | 驗證 `PipManager` 與 `IdeProjector` 根目錄解析委派與 `.gitignore` 標記維護 | FR-04 | `python yscb.py dev test core -k test_pip_manager` |
| **FT-05** | 單元測試 | 驗證 `_maybe_auto_spawn_server` 支援本機 `config.local.json` 且相容 `tmp_dir` 測試 | FR-05 | `python yscb.py dev test core -k test_core_commands` |
| **FT-06** | 單元測試 | 驗證 `Installer.cmd_list`、`cmd_update` 與 `restore` 選項對齊 | FR-06 | `python yscb.py dev test core -k test_installer` |
| **FT-07** | 單元測試 | 驗證 `yscb.py` 之 `init` 與 `self-update` 空格傳參及無效來源防呆 | FR-07 | `python yscb.py dev test core -k test_remote_zip_bootstrap` |
| **FT-08** | 單元測試 | 驗證 `core.uri` 邊界防禦、反向轉換、快取命中與自動重載 | FR-08 | `python yscb.py dev test core -k test_uri` |
| **FT-09** | 單元測試 | 驗證 `_format.json` 與 `CommandsRegistry` 的 `required` 及 `choices` 對齊 | FR-09 | `python yscb.py dev test core -k test_validator` |
| **FT-10** | 單元測試 | 驗證 `core.__init__` 延遲載入映射與 `VersionTuple.__str__` 包含 `revision` | FR-10 | `python yscb.py dev test core -k test_semver` |
| **ET-01** | 邊界測試 | 驗證舊版平鋪結構 mock 在 `providers.py` 下仍能平滑退化相容 | EC-01 | `python yscb.py dev test core -k test_cli_router` |
| **ET-02** | 邊界測試 | 驗證同前綴兄弟目錄穿越攻擊在 `core.uri` 被精準攔截 | EC-05 | `python yscb.py dev test core -k test_uri` |
| **RT-01** | 全量回歸 | 驗證 `core` 模組全套測試 100% 通過（192+ Passed, 0 Failed） | NFR-02 | `python yscb.py dev test core` |
| **RT-02** | 生態系回歸 | 驗證全生態系 5 大模組測試 100% 通過（550+ Passed, 0 Failed） | NFR-02 | `python yscb.py dev test --all --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** ~ **FT-10** | `PASS` | `python yscb.py dev test core` 192 項單元測試全數通過 | 2026-10-14 13:24 |
| **ET-01** ~ **ET-02** | `PASS` | `test_cli_router` 平鋪相容與 `test_uri` 目錄穿越阻斷驗證通過 | 2026-10-14 13:24 |
| **RT-01** | `PASS` | `core` 模組全量測試：192 Total, 192 Passed, 0 Failed, 0 Skipped (18.58s) | 2026-10-14 13:24 |
| **RT-02** | `PASS` | 全生態系 5 大模組回歸：Pass: 550 (100.0%), Fail: 0, Skip: 0 | 2026-10-14 13:24 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py contributes list --module=core`，確認終端能正常印出 core 的貢獻點而非提示找不到模組 | `PASS` | 成功列出 uri_schemes, commands, events 共 3 大擴充點 |
| **UX-02** | 執行 `python yscb.py uri resolve config://core/config.project.json`，確認高頻解析正常且命中記憶體快取 | `PASS` | 成功解析為實體絕對路徑，反向 `to-uri` 亦通過 |
