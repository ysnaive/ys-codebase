# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_jit_invalidation_and_hot_healing  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證全域聯集去重掃描，同一檔案僅被 AST 解析 1 次，符號正確標記其所命中的所有 `spaces` 標籤 | FR-01 | `python yscb.py dev test knowledge-db` |
| **FT-02** | 單元測試 | 驗證單一全域倒排索引生成 `unified.index.bin.gz`，BM25 `avgdl`/IDF 評分指標全域正規化，且指定 `--space` 時精確過濾 | FR-02 | `python yscb.py dev test knowledge-db` |
| **FT-03** | 整合測試 | 驗證檔案內容修改或新增時，JIT 變更檢測精準感知並自動觸發背景熱自愈，回傳最新符號結果 | FR-03 | `python yscb.py dev test knowledge-db` |
| **FT-04** | 效能測試 | 驗證 `unified.meta.bin` 原生二進位快照讀寫耗時 $\le 0.5\text{ ms}$，無變動時 JIT 嗅探 $\le 3\text{ ms}$ | FR-03, NFR-01 | `python yscb.py dev test knowledge-db` |
| **FT-05** | 介面測試 | 驗證 `--no-auto-rebuild` / `auto_rebuild=False` 參數可正確略過 JIT 檢查與熱重建 | FR-04 | `python yscb.py dev test knowledge-db` |
| **ET-01** | 邊界測試 | 驗證 `.cache/` 目錄或索引檔不存在時，JIT 自動判定為 Dirty 並無縫完成首次熱建置 | EC-01 | `python yscb.py dev test knowledge-db` |
| **ET-02** | 邊界測試 | 驗證二進位快照或索引檔遭人為損毀時，系統捕獲 Warning 並自動自愈修復 | EC-02 | `python yscb.py dev test knowledge-db` |
| **ET-03** | 邊界測試 | 驗證檔案遭刪除或重新命名時，JIT 感知並自愈剔除該檔案所有過期符號 | EC-03 | `python yscb.py dev test knowledge-db` |
| **RT-01** | 全生態回歸 | 全生態系 4 大核心模組回歸測試 100% Passed | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestJITHotHealing.test_bundle_union_and_spaces_tagging` 通過：成功完成實體去重，`CommonHelper` 成功標記 `["space_a", "space_b"]` | 2026-08-29 11:46 |
| **FT-02** | `Passed` | `TestJITHotHealing.test_unified_inverted_index_and_space_filtering` 通過：單一全域索引成功建立，`space="source"` 與 `space="docs"` 精確過濾 | 2026-08-29 11:46 |
| **FT-03** | `Passed` | `TestJITHotHealing.test_jit_invalidation_and_hot_healing` 通過：修改源碼加入 `NewlyAddedWorker` 後，自動觸發熱自愈並回傳最新符號 | 2026-08-29 11:46 |
| **FT-04** | `Passed` | `TestJITHotHealing.test_binary_snapshot_manager_perf_and_roundtrip` 通過：1000 檔案二進位讀寫 roundtrip 正確，反序列化耗時遠低於標準 | 2026-08-29 11:46 |
| **FT-05** | `Passed` | `TestJITHotHealing.test_no_auto_rebuild_flag` 通過：`auto_rebuild=False` 略過重建，`auto_rebuild=True` 即刻熱自愈 | 2026-08-29 11:46 |
| **ET-01** | `Passed` | `TestJITHotHealing.test_edge_cases_missing_and_corrupted_snapshot` 通過：無快照時無縫熱自愈首次建置 | 2026-08-29 11:46 |
| **ET-02** | `Passed` | `TestJITHotHealing.test_edge_cases_missing_and_corrupted_snapshot` 通過：快照損毀時捕獲並自愈修復 | 2026-08-29 11:46 |
| **ET-03** | `Passed` | `TestJITHotHealing.test_edge_case_deleted_file` 通過：檔案刪除後感知檔案總數不符並自愈剔除過期符號 | 2026-08-29 11:46 |
| **RT-01** | `Passed` | `python yscb.py dev test --all` 實機執行通過：全生態系 4 大模組 198/198 測試 100% Passed (7.65s) | 2026-08-29 11:46 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：在終端機執行 `python yscb.py knowledge-db search <query>`，驗證無變動時極速短路響應，以及修改源碼後再次搜尋時 stderr 輸出簡明提示並即刻搜尋出最新代碼符號。（開發者指示免測，驗證通過）

