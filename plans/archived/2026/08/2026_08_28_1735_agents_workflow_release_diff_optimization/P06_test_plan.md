# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：agents-workflow 發布引擎來源 Diff 檢測與無效 File IO 優化 (agents-workflow Release Diff Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Testing  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 首次發布成功物化檔案，`storage://release_manifest.json` 正確記錄指紋、目標與發布檔案清冊。 | FR-01, FR-02 | `test_publisher.py::test_ft_01_initial_release_persists_fingerprint` |
| **FT-02** | 單元測試 | 二次發布在無異動情況下觸發 Stage 0 短路 (`short_circuited=True`, `written_count=0`, `skipped_count > 0`)。 | FR-01, NFR-01 | `test_publisher.py::test_ft_02_short_circuit_when_no_change` |
| **FT-03** | 單元測試 | 單一來源檔案修改時，指紋變更並觸發增量寫入（僅該目標檔案寫入，其餘目標檔案略過）。 | FR-01, FR-02 | `test_publisher.py::test_ft_03_incremental_write_on_partial_change` |
| **FT-04** | 單元測試 | 傳入 `force=True` 時強制跳過短路與略過邏輯，執行全量重新編譯與覆寫 (`written_count == published_count`)。 | FR-04 | `test_publisher.py::test_ft_04_forced_release_overwrites_all` |
| **FT-05** | 單元測試 | `AGENTS.md` 軟合併在注入內容未變更時跳過磁碟寫入，有變更時正確寫入更新。 | FR-03 | `test_publisher.py::test_ft_05_agents_md_soft_merge_diff` |
| **FT-06** | CLI 測試 | CLI `python yscb.py agents-workflow release --force` 成功解析參數並執行強制發布。 | FR-04, FR-05 | `test_publisher.py::test_ft_06_cli_release_with_force_flag` |
| **ET-01** | 邊界測試 | 已發布檔案遭外部刪除時，即使來源指紋未變仍自動失效短路，平滑修復補齊遺失檔案。 | EC-01 | `test_publisher.py::test_et_01_short_circuit_invalidated_when_file_missing` |
| **ET-02** | 邊界測試 | `release_targets` 配置增減時觸發指紋變更，正確物化新 Target 並清理過往孤立檔案。 | EC-02 | `test_publisher.py::test_et_02_target_configuration_change_triggers_republish` |
| **ET-03** | 邊界測試 | `storage://` 中之 `release_manifest.json` 遺失或格式損毀時，安全降級全量發布並修復 manifest。 | EC-03 | `test_publisher.py::test_et_03_corrupted_or_missing_manifest_fallback` |
| **RT-01** | 回歸測試 | 全系統各模組（agents-workflow, core, dev, knowledge-db）回歸測試 100% Passed。 | NFR-04 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 首次發布成功生成 fingerprint (64 hex)，manifest 寫入正確 | 2026-08-28 17:44 |
| **FT-02** | `Passed` | Stage 0 短路命中，written_count=0, skipped_count=published_count | 2026-08-28 17:44 |
| **FT-03** | `Passed` | 局部變更檔案 written_count=1, 其餘檔案 skipped 跳過磁碟寫入 | 2026-08-28 17:44 |
| **FT-04** | `Passed` | force=True 強制全量寫入，written_count=published_count | 2026-08-28 17:44 |
| **FT-05** | `Passed` | AGENTS.md 軟合併在內容一致時 written=False，內容相異時 written=True | 2026-08-28 17:44 |
| **FT-06** | `Passed` | CLI 指令無參數短路，`--force` 強制全量發布，返回碼 0 | 2026-08-28 17:44 |
| **ET-01** | `Passed` | 檔案手動刪除後短路自動失效，只寫入缺失之檔案 (written_count=1) | 2026-08-28 17:44 |
| **ET-02** | `Passed` | 指紋計算具備高度敏感性與環境重現一致性 | 2026-08-28 17:44 |
| **ET-03** | `Passed` | Manifest 損毀或缺失時安全降級為全量物化並自癒寫入新 manifest | 2026-08-28 17:44 |
| **RT-01** | `Passed` | 全系統 4 大模組 163/163 測試案例 100% Passed (10.409s) | 2026-08-28 17:44 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：在專案根目錄實機調用 `python yscb.py reload`，觀察控制台輸出 `[agents-workflow:hook] Auto-release skipped on reload (no changes detected, N files up to date).`，驗證無多餘磁碟寫入。
