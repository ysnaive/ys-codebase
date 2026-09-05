# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge_db_cli_ux_flow_refactor_and_optimization  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 Local/Project Config 向量開關 (`enable_vector_search=false`) 正確跳過 FastEmbed 且以純 BM25 檢索 | FR-01, EC-04 | `test_cli_ux.py::test_enable_vector_search_config` |
| **FT-02** | 單元測試 | 驗證模型自訂配置 (`embedding_model`) 載入與白名單預檢，非法名稱平滑降級 | FR-02, EC-01 | `test_cli_ux.py::test_embedding_model_config_and_fallback` |
| **FT-03** | 單元測試 | 驗證模型切換時向量快取維度/名稱不符自動標記失效並降級 | EC-02 | `test_cli_ux.py::test_vector_index_model_mismatch_invalidation` |
| **FT-04** | 單元測試 | 驗證 JIT 10 符號動態探針推估與熔斷降級邏輯（模擬超時時安全降級純 BM25 並拋出提示） | FR-03, EC-03 | `test_cli_ux.py::test_jit_dynamic_probe_and_fuse` |
| **FT-05** | 單元測試 | 驗證手動 `index` 雙軌進度呈現與各階段耗時回呼 | FR-04 | `test_cli_ux.py::test_dual_track_progress_reporter` |
| **FT-06** | 單元測試 | 驗證 `knowledge-db --help` 包含 `index` 說明，且 `status` 能正確識別 `unified.index.bin.gz` | FR-05 | `test_cli_ux.py::test_help_and_status_recognition` |
| **FT-07** | 單元測試 | 驗證 HF Hub 警告屏蔽生效，且 `--json` 輸出時 stdout 為純淨 JSON | FR-06, EC-06 | `test_cli_ux.py::test_json_stdout_purity_and_hf_warning_suppression` |
| **FT-08** | 單元測試 | 驗證 ANSI 終端著色與 `NO_COLOR` / 非 TTY 自動去色機制 | FR-07, EC-05 | `test_cli_ux.py::test_terminal_styler_no_color` |
| **FT-09** | 單元測試 | 驗證 CPU 調用保護配置 (`max_threads` auto=cpu//2 及手動數值截斷) | FR-08, EC-07 | `test_cli_ux.py::test_cpu_max_threads_adaptation` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 向量開關 `enable_vector_search=false` 驗證成功，正確跳過向量化並以純 BM25 檢索 | 2026-09-05 |
| **FT-02** | `Passed` | 自訂模型配置解析與非法模型白名單回退驗證成功，支援清單查詢正常 | 2026-09-05 |
| **FT-03** | `Passed` | 向量快取檔頭名稱/維度不符時自動觸發不相容失效機制驗證成功 | 2026-09-05 |
| **FT-04** | `Passed` | JIT 10 符號動態探針與臨界值熔斷成功觸發，安全降級純 BM25 並產出 notice | 2026-09-05 |
| **FT-05** | `Passed` | 手動 index 雙軌 5 階段進度指示與耗時回呼機制驗證成功 | 2026-09-05 |
| **FT-06** | `Passed` | `--help` 成功包含 `index` 指令，`status` 精確判定二進位倒排索引已建立消除假警報 | 2026-09-05 |
| **FT-07** | `Passed` | HF Hub 警告成功屏蔽，`--json` 輸出時 stdout 100% 純淨且格式正確 | 2026-09-05 |
| **FT-08** | `Passed` | ANSI 色彩渲染、`NO_COLOR` 與非 TTY 管道去色過濾機制驗證成功 | 2026-09-05 |
| **FT-09** | `Passed` | CPU 調用保護 `max_threads="auto"` (cpu//2) 及無效值安全防呆回退驗證成功 | 2026-09-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py knowledge-db status` 驗證倒排索引正確顯示「已建立」且無 HF Hub 未認證警告 | `[測試通過]` | 實機輸出狀態精準識別二進位索引，無 HF Hub 警告雜音，開發者確認通過 |
| **UX-02** | 執行 `python yscb.py knowledge-db --help` 驗證清單中列出 `index` 子命令 | `[測試通過]` | Help 清單明確列出 `index` 子命令與功能說明，開發者確認通過 |
| **UX-03** | 執行 `python yscb.py knowledge-db index` 驗證顯示各階段進度指示與耗時報表 | `[測試通過]` | 雙軌進度條與統計報告正常輸出，文檔與 Term 計數正確，開發者確認通過 |
| **UX-04** | 執行 `python yscb.py knowledge-db search "test"` 驗證終端呈現 ANSI 階層色彩高亮且 JIT 提示正常 | `[測試通過]` | 樹狀階層、符號精確行號與色彩層次分明，自動熱重建流暢，開發者確認通過 |
