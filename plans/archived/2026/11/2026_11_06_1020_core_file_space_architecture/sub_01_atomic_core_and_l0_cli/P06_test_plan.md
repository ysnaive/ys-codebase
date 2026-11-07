# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_atomic_core_and_l0_cli  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `PresetDef` 與 `SpaceDef` Schema 定義、`SpaceConfig` 預設 `include: ["*"]` 與 `exclude` 優先於 `include` | FR-01 | `python yscb.py dev test core -k test_ft_01` |
| **FT-02** | 單元測試 | 驗證 `<module>/<name>` 與 `project/<name>` 命名空間隔離註冊、精準查詢與短名 `<name>` 自動聯集尋址（互不覆蓋、零載入順序相依） | FR-02 | `python yscb.py dev test core -k test_ft_02` |
| **FT-03** | 單元測試 | 驗證顯式 `presets` 展開（無隱式 `default_presets`）與內建 `"@gitignore"` 動態預設集開關控制 | FR-03 | `python yscb.py dev test core -k test_ft_03` |
| **FT-04** | 單元測試 | 驗證三座標相容匹配（語意 URI 前綴、`project_rel` 與 `entry_rel` 雙基準相對路徑、不含 `/` 檔名與目錄區段）與 `match_path` 解釋原語 | FR-04 | `python yscb.py dev test core -k test_ft_04` |
| **FT-05** | 單元測試 | 驗證 `iter_space_files` 零冗餘 `os.scandir` 目錄剪枝、單檔入口支援與跨入口/短名聯集實體路徑去重 | FR-05 | `python yscb.py dev test core -k test_ft_05` |
| **FT-06** | 單元測試 | 驗證 `compute_file_hash` 與 `hash_target` 在 `stat_only`、`adaptive`、`full_hash` 策略下之單檔指紋與空間決定性 `merkle_root` | FR-06 | `python yscb.py dev test core -k test_ft_06` |
| **FT-07** | 單元測試 | 驗證 L0 CLI (`core file-space` 與 `fs`) 五大子命令 (`spaces`, `presets`, `match`, `ls`, `hash`) 及 `dispatcher.py` 對同名外部模組優先避讓 | FR-07 | `python yscb.py dev test core -k test_ft_07` |
| **ET-01** | 邊界測試 | 驗證 `entries` 含不存在路徑時 `ls`/`hash` 安全靜默略過，且 `resolve_entries` 正確標註 `exists=False` | EC-01 | `python yscb.py dev test core -k test_et_01` |
| **ET-02** | 邊界測試 | 驗證 `entries` 指向 `project://` 外部目錄時，`rel_path` 自動退回相對於所屬 `entry` 表示，不拋出 `ValueError` | EC-02 | `python yscb.py dev test core -k test_et_02` |
| **ET-03** | 邊界測試 | 驗證 `presets` 引用不存在預設集時記錄於 `unresolved_presets` 警告清單且不崩潰 | EC-03 | `python yscb.py dev test core -k test_et_03` |
| **ET-04** | 邊界測試 | 驗證 `follow_symlinks=True` 下 `(st_dev, st_ino)` 阻斷符號連結循環（Symlink Loop）並安全略過懸空連結 | EC-04 | `python yscb.py dev test core -k test_et_04` |
| **ET-05** | 邊界測試 | 驗證查詢不存在之空間名稱時拋出 `SpaceNotFoundError` 且 CLI 返回 `exit code 1` | EC-05 | `python yscb.py dev test core -k test_et_05` |
| **ET-06** | 邊界測試 | 驗證 `@gitignore` 於無 `.gitignore` 時為空規則，且含 `!` 負向規則時可豁免前序 `.gitignore` 規則但不覆蓋 Space 自身 `exclude` | EC-06 | `python yscb.py dev test core -k test_et_06` |
| **PT-01** | 效能與規範測試 | 驗證 `core/space/` 100% 純標準庫零第三方依賴、POSIX 跨平台路徑正規化一致性與預編譯走訪效能 | NFR-01, NFR-02, NFR-03 | `python yscb.py dev test core -k test_pt_01` |
| **RT-01** | 回歸測試 | `module:core` 全量回歸測試套件與 `dev check core` 靜態檢核 | All | `python yscb.py dev test core -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-07** | `Passed` | `tests/test_space.py` 7 項功能測試案例 100% 通過 | 2026-11-06 |
| **ET-01 ~ ET-06** | `Passed` | `tests/test_space.py` 6 項邊界測試案例 100% 通過 | 2026-11-06 |
| **PT-01** | `Passed` | `tests/test_space.py` 純標準庫、POSIX 正規化與預編譯走訪測試 100% 通過 | 2026-11-06 |
| **RT-01** | `Passed` | `dev check core` [PASS]；`dev test core -q` 263/263 (100.0%) 全數通過 | 2026-11-06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於終端執行 `python yscb.py fs spaces`、`python yscb.py fs presets`、`python yscb.py fs ls`、`python yscb.py fs match yscb.py`、`python yscb.py fs hash`（或以 `python yscb.py core file-space <subcmd>` 呼叫），確認 L0 CLI 輸出與行為符合預期 | `[測試通過]` | 2026-11-06 實機完成 6 步端到端情境與雙空間聯集驗證，並通過 `/code-optimizer` 與 `/testing-sop` 雙盲審 (`PASSED`) |
