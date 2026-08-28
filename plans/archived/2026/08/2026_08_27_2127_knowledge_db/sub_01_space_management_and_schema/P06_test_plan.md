# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge-db 子計畫 01: 空間管理與資料架構 (Space Management & Data Schema)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Passed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `SymbolKind`、`LanguageType`、`SpaceOrigin` 列舉與 `MemberInfo` 之屬性、`to_dict()`、`from_dict()` 序列化無損一致性 | FR-02 | `test_schema.py:TestSchema.test_member_info_and_enums` |
| **FT-02** | 單元測試 | 驗證 `UnifiedSymbol` 不可變性 (`frozen=True`)、`compute_id` 演算法輸出 40 位 SHA1 雜湊唯一 ID、`to_dict()` / `from_dict()` 序列化 | FR-03 | `test_schema.py:TestSchema.test_unified_symbol_and_id_computation` |
| **FT-03** | 單元測試 | 驗證 `SpaceConfig` 與 `ThesaurusConfig` 模型、`file_patterns` 預設全包含 (include all) 與 Glob 匹配過濾邏輯 | FR-04, EC-01 | `test_schema.py:TestSchema.test_space_and_thesaurus_config` |
| **FT-04** | 單元測試 | 驗證 `SpaceManager` 雙軌聚合：載入模組 Contributes 空間與專案 Config 空間，並驗證 `Local` > `Project` > `Contributed` 覆蓋優先權 | FR-05, EC-07 | `test_space.py:TestSpaceManager.test_dual_track_aggregation_and_priority` |
| **FT-05** | 單元測試 | 驗證 `SpaceManager` 全空間聯集 (`get_union_spaces`)、`resolve_space_include` 語意 URI 解算及無效路徑過濾 | FR-06, EC-02 | `test_space.py:TestSpaceManager.test_union_spaces_and_uri_resolution` |
| **FT-06** | 單元測試 | 驗證 `FingerprintScanner` Stage 1 初篩：檔案未變更時依 `mtime`+`size` 判定 `UNCHANGED`，不觸發內容讀取與 SHA1 計算 | FR-07, NFR-02 | `test_scanner.py:TestScanner.test_stage_1_unchanged_fast_path` |
| **FT-07** | 單元測試 | 驗證 `FingerprintScanner` Stage 2 校驗：touch 檔案時比對 SHA1 一致僅更新快取 `mtime` 並標記 `UNCHANGED` | FR-07, EC-04 | `test_scanner.py:TestScanner.test_stage_2_touch_file_sha1_match` |
| **FT-08** | 單元測試 | 驗證 `FingerprintScanner` 檔案變更偵測：新增檔案標記 `ADDED`、修改檔案標記 `MODIFIED`、刪除檔案標記 `DELETED` | FR-07 | `test_scanner.py:TestScanner.test_diff_detection_added_modified_deleted` |
| **FT-09** | 單元測試 | 驗證 `scan_all_spaces` 全空間聯集掃描、指紋庫原子寫入與重新載入驗證 | FR-08, NFR-04 | `test_scanner.py:TestScanner.test_scan_all_spaces_and_atomic_save` |
| **ET-01** | 例外測試 | 驗證 `fingerprints.json` 損毀時自動發出 Warning 並自癒降級為全量掃描，寫入後修復損毀檔案 | FR-09, EC-03 | `test_scanner.py:TestScanner.test_corrupted_cache_self_healing` |
| **ET-02** | 例外測試 | 驗證查詢未註冊空間時拋出 `SpaceNotFoundError` 且包含明確錯誤訊息 | FR-09, EC-08 | `test_space.py:TestSpaceManager.test_space_not_found_error` |
| **ET-03** | 邊界測試 | 驗證包含不存在之來源路徑時記錄 Warning 並安全略過，維持正常掃描 | FR-09, EC-02 | `test_space.py:TestSpaceManager.test_invalid_source_path_warning_and_skip` |
| **RT-01** | 回歸測試 | 全模組單元測試回歸，執行 `python yscb.py dev test knowledge-db` 達成 100% Passed | NFR-01~04 | `python yscb.py dev test knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_01_member_info_and_enums`: 列舉與 MemberInfo 序列化/反序列化 100% 通過 | 2026-08-28 13:31 |
| **FT-02** | `Passed` | `test_ft_02_unified_symbol_and_id_computation`: SHA1 ID 演算法、不可變性與序列化 100% 通過 | 2026-08-28 13:31 |
| **FT-03** | `Passed` | `test_ft_03_space_and_thesaurus_config`: SpaceConfig/ThesaurusConfig 模型與 file_patterns 預設 include all 100% 通過 | 2026-08-28 13:31 |
| **FT-04** | `Passed` | `test_ft_04_dual_track_aggregation_and_priority`: 雙軌聚合與 Local > Project > Contributed 優先權覆蓋 100% 通過 | 2026-08-28 13:31 |
| **FT-05** | `Passed` | `test_ft_05_union_spaces_and_uri_resolution`: get_union_spaces 與 resolve_space_include 100% 通過 | 2026-08-28 13:31 |
| **FT-06** | `Passed` | `test_ft_06_stage_1_unchanged_fast_path`: Stage 1 初篩 (mtime+size) UNCHANGED 極速路徑 100% 通過 | 2026-08-28 13:31 |
| **FT-07** | `Passed` | `test_ft_07_stage_2_touch_file_sha1_match`: Stage 2 SHA1 校驗、touch 檔案更新快取 mtime 100% 通過 | 2026-08-28 13:31 |
| **FT-08** | `Passed` | `test_ft_08_diff_detection_added_modified_deleted`: ADDED / MODIFIED / DELETED 差異偵測 100% 通過 | 2026-08-28 13:31 |
| **FT-09** | `Passed` | `test_ft_09_scan_all_spaces_and_atomic_save`: scan_all_spaces 聯集掃描與原子寫入持久化 100% 通過 | 2026-08-28 13:31 |
| **ET-01** | `Passed` | `test_et_01_corrupted_cache_self_healing`: fingerprints.json 損毀自癒降級全量掃描與修復 100% 通過 | 2026-08-28 13:31 |
| **ET-02** | `Passed` | `test_et_02_space_not_found_error`: 查詢未註冊空間拋出 SpaceNotFoundError 100% 通過 | 2026-08-28 13:31 |
| **ET-03** | `Passed` | `test_et_03_invalid_source_path_warning_and_skip`: 來源目錄不存在安全略過且不中斷 100% 通過 | 2026-08-28 13:31 |
| **RT-01** | `Passed` | 實機執行 `python yscb.py dev test knowledge-db`，全套件 15/15 測試案例 100% Passed (3.400s) | 2026-08-28 13:31 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：開發者指示免測，自動化測試 15/15 100% Passed 通過。
