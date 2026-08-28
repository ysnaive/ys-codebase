# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge-db 子計畫 04: CLI 工具鏈、統一門面 SDK、生態整合與本地端快取儲存遷移 (CLI, Unified SDK, Workflow Interlock & Local Cache Storage Migration)  
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
| **FT-01** | 單元測試 | 驗證 `KnowledgeEngine.status()` 回傳空間總數、指紋快取、同義詞與索引統計摘要 | FR-02 | `test_engine.py:TestEngine.test_engine_status_and_lifecycle` |
| **FT-02** | 單元測試 | 驗證 `KnowledgeEngine.scan()` 執行單一空間與全空間聯集增量掃描 | FR-03 | `test_engine.py:TestEngine.test_engine_status_and_lifecycle` |
| **FT-03** | 單元測試 | 驗證 `KnowledgeEngine.bundle()` 提取符號並輸出 SemanticBundle 發布包 | FR-04 | `test_engine.py:TestEngine.test_engine_status_and_lifecycle` |
| **FT-04** | 單元測試 | 驗證 `KnowledgeEngine.build_index()` 建立空間倒排索引並持久化快取至磁碟 | FR-05 | `test_engine.py:TestEngine.test_engine_status_and_lifecycle` |
| **FT-05** | 單元測試 | 驗證 `KnowledgeEngine.search()` 檢索能力與未建索引時自動觸發懶索引 (Lazy Indexing) | FR-06, EC-01 | `test_engine.py:TestEngine.test_engine_search_and_lazy_indexing` |
| **FT-06** | 單元測試 | 驗證 `KnowledgeEngine.clean()` 清理指定或全空間之指紋、Bundle 與索引快取檔案 | FR-07, EC-03 | `test_engine.py:TestEngine.test_engine_status_and_lifecycle` |
| **FT-07** | 單元測試 | 驗證 CLI 入口 6 大子指令 (`status`, `scan`, `bundle`, `index`, `search`, `clean`) 正確執行與返回碼 | FR-08, EC-06 | `test_cli.py:TestCLI.test_cli_all_commands` |
| **FT-08** | 單元測試 | 驗證模組自治 Hook `scripts/hook.dev.py` 鉤子生命週期回呼 | FR-09 | `test_cli.py:TestCLI.test_hook_lifecycle` |
| **FT-09** | 單元測試 | 驗證 Core 套件解析嚴格化：嘗試安裝未發布或不存在之模組時剛性拋出 `ModuleNotFoundError`，禁止 dummy fallback | FR-11, EC-09 | `source/core/tests/test_installer.py:TestCoreInstaller.test_install_unreleased_module_strict_error` |
| **FT-10** | 單元測試 | 驗證 Build 包物理隔離：常規安裝請求不得存取 `module.build://`，僅在版本為 `"build"` 或 `revision == "build"` 時允許觸發 | FR-12, EC-10 | `source/core/tests/test_installer.py:TestCoreInstaller.test_build_package_isolation` |
| **FT-11** | 單元測試 | 驗證資料庫預設存儲遷移至 `cache://knowledge-db/` (`.cache/knowledge-db/`)，杜絕 `storage/` 污染 | FR-13, EC-11 | `test_space.py:TestSpaceManager.test_ft_11_cache_storage_root_resolution` |
| **ET-01** | 例外測試 | 驗證操作不存在空間拋出 `SpaceNotFoundError` 且 CLI 回傳非 0 狀態碼 | FR-01, EC-02 | `test_engine.py:TestEngine.test_non_existent_space_error` |
| **RT-01** | 回歸測試 | 全模組單元測試回歸，執行 `python yscb.py dev test core` 與 `python yscb.py dev test knowledge-db` 達成 100% Passed | NFR-01~04 | `python yscb.py dev test` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_engine_status`: 空間總數、指紋快取、同義詞與索引統計摘要 100% 通過 | 2026-08-28 15:50 |
| **FT-02** | `Passed` | `test_engine_scan`: 空間增量/全量指紋比對與掃描結果摘要 100% 通過 | 2026-08-28 15:50 |
| **FT-03** | `Passed` | `test_engine_bundle`: 提取符號並導出 SemanticBundle 發布包 100% 通過 | 2026-08-28 15:50 |
| **FT-04** | `Passed` | `test_engine_build_index`: 倒排索引建立並原子持久化至磁碟快取 100% 通過 | 2026-08-28 15:50 |
| **FT-05** | `Passed` | `test_engine_search_and_lazy_indexing`: 檢索與未建索引時自動觸發懶索引 (Lazy Indexing) 100% 通過 | 2026-08-28 15:50 |
| **FT-06** | `Passed` | `test_engine_clean`: 清理指定或全空間指紋、Bundle 與索引快取 100% 通過 | 2026-08-28 15:50 |
| **FT-07** | `Passed` | `test_cli_all_commands`: CLI 6 大子指令 (status, scan, bundle, index, search, clean) 100% 通過 | 2026-08-28 15:50 |
| **FT-08** | `Passed` | `test_hook_lifecycle`: hook.dev.py 測試前置 setup 與後置 teardown 生命週期 100% 通過 | 2026-08-28 15:50 |
| **FT-09** | `Passed` | `test_install_unreleased_module_strict_error`: 嘗試安裝未發布模組拋出 ModuleNotFoundError 且 yscb.config.json 無幽靈模組 100% 通過 | 2026-08-28 15:50 |
| **FT-10** | `Passed` | `test_build_package_isolation`: 常規安裝阻斷 build 包挪用，顯式指定 build revision 正確安裝 100% 通過 | 2026-08-28 15:50 |
| **FT-11** | `Passed` | `test_ft_11_cache_storage_root_resolution`: 驗證 SpaceManager 預設路徑解析為 cache://knowledge-db/ (.cache/knowledge-db/) 100% 通過 | 2026-08-28 15:50 |
| **ET-01** | `Passed` | `test_non_existent_space_error`: 操作不存在空間拋出 SpaceNotFoundError 100% 通過 | 2026-08-28 15:50 |
| **RT-01** | `Passed` | 實機執行 `python yscb.py dev test core` (48/48 Passed) 與 `python yscb.py dev test knowledge-db` (38/38 Passed) 100% 通過 | 2026-08-28 15:50 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：Phase 6 CLI 自動化測試 100% Passed（Core: 48/48, Knowledge-DB: 38/38），呈遞測試報告等待開發者 UX 驗證確認。
