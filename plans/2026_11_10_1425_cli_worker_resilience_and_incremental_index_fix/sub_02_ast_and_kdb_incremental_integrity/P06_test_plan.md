# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：AST 與 Knowledge-DB 增量更新一致性與鎖競爭修復  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `SpaceScanner.diff()` 在修改空間 `exclude` 規則（`config_hash` 改變）時正確將被排除檔案列入 `deleted`，且 `GrammarProvisioner._provision_lock` 正確傳遞 `timeout_sec` 並阻擋未獲鎖並發安裝 | FR-01 | `python3 yscb.py dev test core --no-build && python3 yscb.py dev test ast --no-build` |
| **FT-02** | 整合測試 | 驗證 `hot_patch_index` 後首次 `callers` 水合 `workspace_graph` 即寫回磁碟（第 2 次免重建）、`ast_config_hash` 變更自動重建、CoW 無鎖迭代安全及刪檔不模糊誤連 | FR-02, EC-01, EC-02, NFR-01 | `python3 yscb.py dev test ast --no-build` |
| **FT-03** | 整合測試 | 驗證同行號修改 Docstring 在兩階段同步下必更新向量、頂部插入空行平移未改函式時 0 次重算 ONNX 向量，以及倒排索引刪除舊詞無幽靈命中且 `field_avgdl` 精確 | FR-03, EC-01, NFR-01 | `python3 yscb.py dev test knowledge-db --no-build` |
| **FT-04** | 整合測試 | 驗證 `reconfigure_model` 無變更免鎖返回、`yielded_to_foreground` 殘缺向量自動降級 `lexical_bm25`、跨空間同名 `scripts/cli.py` 修改不誤刪他空間符號，以及 `space_weights` 組態變更自動生效 | FR-04, EC-02 | `python3 yscb.py dev test knowledge-db --no-build` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `core` 303/303、`ast` 57/57 (`0 ResourceWarning`)：`SpaceScanner.diff` 組態變更刪檔保留、跨進程 `InterProcessLock` 逾時阻擋與鎖內重檢磁碟負快取驗證通過 | 2026-11-10 |
| **FT-02** | `Passed` | `ast` 57/57 (`0 ResourceWarning`)：水合圖譜雙檔 `st_mtime` 守衛落盤、`CallGraphIndex` `call_sites` CoW 深拷貝與 `ast_generation` 校驗、`--space` 查詢不覆寫多空間索引、刪檔防模糊誤連驗證通過 | 2026-11-10 |
| **FT-03** | `Passed` | `knowledge-db` 124/124 (`0 ResourceWarning`)：`doc_text_hashes` 同行號改內文重算（含探針逾時熔斷淘汰舊向量）、行號平移零推論重用、`_InternTables` 強引用解耦零洩漏與倒排舊詞清除驗證通過 | 2026-11-10 |
| **FT-04** | `Passed` | `knowledge-db` 124/124 (`0 ResourceWarning`)：鎖外 ONNX 推論與 `working_idx` 原子發佈、`yielded_to_foreground` 降級、雙前綴去重與跨空間後綴隔離、`get_engine()` 動態刷新驗證通過 | 2026-11-10 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於本地執行 `python yscb.py gdrive pull` 後測試單檔編輯下之 `ast callers` 與 `kdb search` 增量同步速度與檢索準確度 | `[跳過/免測]` | 雲端 VM 已完成自動化與新環境模擬驗證，交由本地發布前例行驗收 |
