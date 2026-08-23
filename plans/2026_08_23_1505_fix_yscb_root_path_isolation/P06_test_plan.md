# 測試計畫 (Test Plan)

> 功能名稱：fix_yscb_root_path_isolation (Module 檔案系統、快取儲存與 yscb:// 統一路徑轉換器完備性架構)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Passed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.3  

---

## 1. 核心自動化測試矩陣 (Automated Test Matrix)

| ID | 類別 | 對應項目 | 測試描述與操作步驟 | 預期結果 | 實測狀態 |
|:---|:---:|:---|:---|:---|:---:|
| **FT-01** | 功能 | FR-01 | 配置 `paths.yscb_root = "./yscb_tools"`，執行 `installer install core` | 模組運行目錄位於 `./yscb_tools/modules/core/`，專案根目錄無 `./modules/` 殘留，達成 100% 空間隔離 | ✅ Passed |
| **FT-02** | 功能 | FR-02 | 調用 `ProjectContext.get_module_cache_dir("knowledge-db")` | 自動建立並回傳 `yscb://.yscb_cache/modules/knowledge-db/` 之絕對路徑 | ✅ Passed |
| **FT-03** | 功能 | FR-03 | 測試 `ProjectURI.resolve("cache://knowledge-db/index.json")` 與 `resolve("storage://knowledge-db/meta.db")` | 正確分流解析至 `yscb://.yscb_cache/modules/knowledge-db/index.json` 與 `project://.yscb_storage/knowledge-db/meta.db` | ✅ Passed |
| **FT-04** | 功能 | FR-04 | 測試 `ProjectURI.resolve()` 與 `ProjectURI.validate()` | 正規化路徑分隔符號，正常路徑通過校驗，返回校驗後絕對路徑 | ✅ Passed |
| **FT-05** | 功能 | FR-05 | 傳入位於 `docs/` 下的實體路徑至 `ProjectURI.to_uri(path)` | 依 LPM 演算法優先匹配 `docs://...` 而非 `project://docs/...`，精確返回最短語意 URI | ✅ Passed |
| **FT-06** | 功能 | FR-06 | 執行 `python yscb_cli.py cache clean knowledge-db`、`cache status` 與 `installer remove` | 1. 快取正確被清理<br>2. 狀態表格統計精準<br>3. 模組卸載時自動連動清理快取目錄 | ✅ Passed |
| **FT-07** | 功能 | FR-07 | 於 `.yscb_cache/` 建立舊版 `ide_manifest_antigravity.json`，觸發 `ide_sync.py` | 舊版檔案被自動移動平滑遷移至 `yscb://.yscb_cache/modules/agents-workflow/` | ✅ Passed |
| **FT-08** | 功能 | FR-08 | 模組設定檔內含有 `"plans_dir": "project://plans"`，執行 `ConfigManager.load()` | 字典值自動遞迴展開為實體絕對路徑 | ✅ Passed |
| **ET-01** | 邊界 | EC-01 | `paths.yscb_root` 設為多層未建立目錄（如 `./deep/nested/yscb`）並執行安裝 | Installer 自動遞迴 `mkdir -p`，安裝順暢完成不崩潰 | ✅ Passed |
| **ET-02** | 邊界 | EC-02 | 傳入 `docs:///sub//topic///doc.md` 與 `docs:\\sub\\doc.md` | 自動正規化為 `docs://sub/topic/doc.md` 與 `docs://sub/doc.md` 並精確解析 | ✅ Passed |
| **ET-03** | 邊界 | EC-03 | 傳入 `docs://../../secret.json` 進行解析與校驗 | `validate()` 判定不合法，`resolve()` 拋出 `SecurityError` 或回傳 `!undefined`，安全阻斷逃逸 | ✅ Passed |
| **ET-04** | 邊界 | EC-04 | 傳入缺少 Authority 的 `cache://` 或 `cache:///data.json` | 格式校驗失敗，安全回退不拋出未捕捉例外 | ✅ Passed |
| **ET-05** | 邊界 | EC-05 | 卸載未曾產生過快取之模組 | 快取清理靜默跳過，卸載事務正常完成 | ✅ Passed |
| **ET-06** | 邊界 | EC-06 | 傳入專案外部絕對路徑（如 `C:/Windows/temp`）至 `to_uri` | 安全回退回傳標準絕對路徑字串 | ✅ Passed |
| **ET-07** | 邊界 | EC-07 | `paths.yscb_root` 設為 `"."`（專案與工具庫同層） | `yscb://` 與 `project://` 平滑降級解析至同一根目錄，完全相容舊專案 | ✅ Passed |
| **RT-01** | 回歸 | 全域 | 實機執行全量回歸套件 `python test/run_regression.py` | 既有 60 項單元/整合測試與下游真實專案沙盒 E2E 100% Passed | ✅ Passed (77/77 + E2E) |
| **PT-01** | 效能 | NFR-02 | 執行 10,000 次 `ProjectURI.resolve()` 與 `validate()` 基準測試 | 總耗時 $\le$ 150ms（實測 38.16ms，平均單次解析 3.82µs） | ✅ Passed |

---

## 2. UX 與手動視覺互動驗證 (UX Validation)

| ID | 驗證主題 | 測試描述與操作路徑 | 開發者體驗與視覺反饋 | 驗證狀態 |
|:---|:---|:---|:---|:---:|
| **UX-01** | **CLI URI 診斷工具鏈體驗** | 執行 `python yscb_cli.py uri list` 與 `python yscb_cli.py uri check` | 協議矩陣排版整齊，狀態清晰顯示 `[ACTIVE]`、解析實體路徑與健康度檢查結果 | ✅ 通過 |
| **UX-02** | **CLI Cache 管理終端體驗** | 執行 `python yscb_cli.py cache status` 與 `python yscb_cli.py cache clean --all` | 終端以格式化表格列出各模組快取目錄、檔案數量與磁碟佔用，清理回饋簡潔明確 | ✅ 通過 |

---

## 3. Bug 修復記錄 (Defect Log)

> 僅在測試過程中發現缺陷時填寫，無則填「無」。

*（無缺陷紀錄）*

---

## 4. 測試結論與 Phase 6 Checkpoint

- [x] **Agent CLI 自動化測試**：已實機執行 `python test/run_regression.py` 與 `test_uri_completeness.py` 並全部通過（77/77 單元整合測試 + E2E Downstream Sandbox 100% Passed）
- [x] **Dogfooding 自引用流水線驗收**：已通過 Stage 1~4 閉環驗收，`version status` 顯示全模組 `[SYNCED]` (core v2.3.0, agents-workflow v1.2.0, installer v2.3.1)
- [x] **開發者 UX / 手動測試確認**：開發者已明確確認 UX / 手動驗證通過，正式推進至 Phase 7 結案審查與文檔交付。
