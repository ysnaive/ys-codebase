# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：file-space 與 ast 模組業務代碼五維度靜態診斷與重構審計  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_2133_file_space_and_ast_code_optimization_audit  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元與合約測試 | 驗證 `module:file-space` 拔除 `FileSpaceDef`、`FileFingerprint` 舊建構子別名、`BinarySnapshotManager.save/load`、6 個孤兒掃描方法與 `providers` 舊別名，並完成 `scanner <-> service` 單向匯入解耦、`_atomic_write_bytes` 收斂與 `load_spaces` / `scan_space` 階段拆解後，模組靜態檢查與 15 項合約及單元測試 100% 通過 | FR-01, FR-02, EC-02, EC-03 | `python yscb.py dev check file-space && python yscb.py dev test file-space` |
| **FT-02** | 單元與合約測試 | 驗證 `module:ast` 拔除頂層 8 個薄轉發函式、`formatter` 過渡包裝與常數、`OutlineNode.to_dict()` 重複 `"children"` 鍵、孤兒例外類別與死方法，並完成 `ASTEngine.outline` / `hot_patch_index` 階段拆解、`SpiceParser` 純函式外提與 `bundler` / `io_utils` / `cli` 收斂後，模組靜態檢查與 18 項合約及單元測試 100% 通過 | FR-03, FR-04, EC-01, EC-03 | `python yscb.py dev check ast && python yscb.py dev test ast` |
| **FT-03** | 跨模組回歸測試 | 驗證下游消費者 `module:knowledge-db`（含 `tests/test_file_space.py` 對齊至 `FileSpaceConfig`）與 `module:agents-workflow` 在熱部署安裝 `file-space@build`、`ast@build`、`knowledge-db@build` 後，全套 103 項與 141 項測試零回歸通過 | FR-01, FR-03, NFR-01 | `python yscb.py dev test knowledge-db && python yscb.py dev test agents-workflow` |
| **FT-04** | 結構量化與衛生驗證 | 驗證兩模組總業務代碼淨縮減（`file-space` `-219 LOC`、`ast` `-381 LOC`，合計 `-600 LOC`），核心巨型方法顯著收斂（`load_spaces` 123 $\to$ 21 LOC、`scan_space` 180 $\to$ 88 LOC、`ASTEngine.outline` 316 $\to$ 55 LOC、`hot_patch_index` 155 $\to$ 53 LOC），且源碼零殘留工單/審計代號與轉發空殼 | NFR-02 | 靜態行數統計與正則掃描 |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `dev check file-space` [PASS]；`dev test file-space` 15 Total, 15 Passed, 0 Failed (0.790s, 100% Ready)。 | 2026-11-02 |
| **FT-02** | `Passed` | `dev check ast` [PASS]；`dev test ast` 18 Total, 18 Passed, 0 Failed (2.240s, 100% Ready)。 | 2026-11-02 |
| **FT-03** | `Passed` | 已重新打包並安裝 `file-space@1.0.0.build`、`ast@1.0.0.build`、`knowledge-db@1.3.0.build`；`dev test knowledge-db` 103/103 Passed (7.293s)，`dev test agents-workflow` 141/141 Passed (15.440s)。 | 2026-11-02 |
| **FT-04** | `Passed` | 兩模組生產代碼總計淨減 **600 LOC**（`file-space`: 3,694 $\to$ 3,475 LOC；`ast`: 10,396 $\to$ 10,015 LOC）；`scanner.py -> service.py` 反向匯入降至 0；全模組源碼工單/審計標記掃描 0 殘留。 | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `module:file-space` 與 `module:ast` 之 `Mode A` 重構 Before / After 結構量化對照表，或於終端機抽測 `python yscb.py file-space status`、`python yscb.py ast outline ys_codebase/source/ast/ast_engine/engine.py`，確認重構後結構精簡且行為 100% 無損。 | `[測試通過]` | 開發者確認快速指令實測與量化對照驗收通過 |

