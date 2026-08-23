# 最終實作計畫書 (Implementation Plan)

> 功能名稱：fix_yscb_root_path_isolation (Module 檔案系統、快取儲存與 yscb:// 統一路徑轉換器完備性架構)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 交叉驗證與架構檢核 (Cross-Verification Checklist)

- [x] **FR 對齊**：P01 每個功能需求 (FR-01 ~ FR-08) 在 P03 均有對應的介面與函式簽名
- [x] **EC 防護**：P01 每個 Edge Case (EC-01 ~ EC-07) 在 P03 均有明確的防禦、正規化與圍欄策略
- [x] **架構一致**：P02 變更清單與 P03 類別、命名空間一致且依賴拓撲（Core ➔ Installer ➔ CLI ➔ Workflow ➔ Tests）已驗證
- [x] **規範約束**：全專案 100% 使用純標準庫（零外部相依）、Windows UTF-8 控制台編碼防護、Python 3.8+ `_is_relative_to` 降級相容
- [x] **Extension 注入**：`dogfooding_pipeline_ext` 已實體注入實作拓撲 Stage 1~4 閉環任務中

---

## 2. 靈魂拷問與主執行器三位一體公理 (Stress Test & Invariant)

### Q1: 起手腳本自升級與 yscb_config 定位邊界定義
- **架構公理 [ARCH:DR-EXEC-01] 主執行器三位一體公理 (Triad Host Executor Axiom)**：
  - `yscb_config.json`、`yscb_installer.py` 與 `yscb_cli.py` 為本專案特殊之「主執行器 (Host Executor)」，**三者必須位於同一目錄下**。
  - `installer self-update` / `cli` 的自升級一律**以當前腳本所在實體位置為主**執行原子覆蓋。
  - **其餘所有資產**（`modules/`、`source/`、`build/`、`.yscb_cache/`、`docs/`、`plans/` 等）**100% 嚴格依照語意協定與 `yscb_config.json` 配置解析運行**。
- **開發者裁決結論**：確認採納三位一體公理，徹底釐清主執行器自身與受管理資產之邊界。

---

## 3. 實作順序 (按依賴拓撲排序)

| 順序 | 實作項目 | 變更檔案與目標 | 品質驗證方式 |
|:---:|:---|:---|:---|
| **1** | **Core SDK 路徑與快取 API 重構** | [`ys_codebase/source/core/scripts/context.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/context.py)<br>1. 修正 `get_yscb_root()` 正確解析 `paths.yscb_root`<br>2. 修正 `get_module_dir()` 自 `yscb_root` 查找，移除硬編碼 `"ys_codebase"`<br>3. 新增 `get_module_cache_dir(mod)`、`get_cache_root()`、`get_module_storage_dir(mod)` | 單元測試驗證路徑解析與目錄建立 |
| **2** | **語意 URI 統一轉換器升級與沙盒圍欄** | [`ys_codebase/source/core/scripts/uri.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/uri.py)<br>1. 擴充保留協議（含 `cache`, `storage`, `temp`）<br>2. `resolve()` 支援泛型 `cache://`、`storage://` 與 `_is_relative_to` 沙盒圍欄防護<br>3. 新增 `validate()` 完備度校驗<br>4. `to_uri()` 實作最長前綴匹配 (LPM) 演算法<br>5. 新增 `exists/is_file/is_dir/read_text/write_text/check_schemes` 門面 API | 單元測試驗證解析、驗證、越界阻斷與 LPM |
| **3** | **設定檔語意 URI 自動遞迴解析** | [`ys_codebase/source/core/scripts/config.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/config.py)<br>支援在 `load()` 時遞迴調用 `ProjectURI.resolve()` 展開設定值 | 單元測試驗證巢狀字典 URI 展開 |
| **4** | **Installer 安裝基底收斂與快取連動** | [`ys_codebase/yscb_installer.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_installer.py)<br>1. `ConfigManager.get_yscb_root()` 修正為動態解析 `paths.yscb_root`<br>2. `ModuleManager` 安裝、源碼、建置、快取與快照備份 100% 收斂至 `get_yscb_root()`<br>3. 模組卸載 `remove` 自動連動清理 `cache://<module>/`<br>4. 貫徹自更新以 `sys.argv[0]` 所在目錄為主執行器 | 整合測試驗證空間隔離與卸載清理 |
| **5** | **CLI 路由器擴充與診斷工具鏈** | [`ys_codebase/yscb_cli.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_cli.py)<br>1. 模組發現與 Core 探索改用 `ProjectContext.get_yscb_root()`<br>2. 新增 `cache clean [module] [--all]` 與 `cache status` 子指令<br>3. 擴充 `uri check` 一鍵健康度與越界診斷指令 | CLI 實機調度測試 |
| **6** | **`agents-workflow` 快取遷移** | [`ys_codebase/source/agents-workflow/scripts/ide_sync.py`](file:///d:/repos/ys_codebase/ys_codebase/source/agents-workflow/scripts/ide_sync.py)<br>快取改存至 `ProjectContext.get_module_cache_dir("agents-workflow")`，並執行舊版快取平滑自動遷移 | 驗證舊快取無損遷移至新命名空間 |
| **7** | **完備性全量測試套件編寫** | [`test/test_uri_completeness.py`](file:///d:/repos/ys_codebase/test/test_uri_completeness.py)<br>實作 FT-01~08、ET-01~07 與 PT-01 全量測試案例 | 執行 `python -m unittest test/test_uri_completeness.py` 全部通過 |
| **8** | **Dogfooding 閉環流水線執行** | 1. 遞進版本號：`core` v2.2.0 ➔ v2.3.0, `agents-workflow` v1.1.0 ➔ v1.2.0, `installer` v2.2.0 ➔ v2.3.0<br>2. `installer build --all`<br>3. `python test/run_regression.py` (全量 100% Passed)<br>4. 同步根目錄腳本與 `installer install --force` | 驗證 `version status` 顯示 `[SYNCED]` |

---

## 4. 📚 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 判定依據 (P03/P05/P06 錨點) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
|:---|:---|:---|:---|
| `P03: API / 介面變更` | 維度 2 (邊界與使用) | `docs/Core/README.md` | 補齊 `ProjectURI`（`resolve/validate/to_uri/read_text/write_text/check_schemes`）與 `ProjectContext`（`get_module_cache_dir/get_cache_root`）公開介面簽名與使用範例 |
| `P05: URI 協議體系與圍欄機制` | 維度 3 (中觀動態機制) | `docs/Core/SEMANTIC_URI_SYSTEM.md` | **[NEW]** 撰寫語意 URI 專題手冊：五層協議模型、Authority 命名空間分流、最長前綴匹配 (LPM) 演算法與沙盒圍欄防護時序 |
| `P05: 快取命名空間與路徑隔離` | 維度 5 (工程妥協) | `docs/Installer/DESIGN_NOTES.md` | 登記 `DN-09`（`yscb://` 空間隔離鐵律）與 `DN-10`（模組專屬快取命名空間與生命週期保護），標記 `[!CAUTION]` |
| `P03: CLI 指令擴充` | 維度 2 (邊界與使用) | `docs/Installer/README.md` 與 `docs/_project/CLI_SPECIFICATION.md` | 補齊 `python yscb_cli.py cache clean / status` 與 `python yscb_cli.py uri check` 指令手冊 |

---

## 5. 關鍵決策速查 (Decision Records Reference)

- **[ARCH:DR-EXEC-01] 主執行器三位一體公理**：`yscb_config.json`、`yscb_installer.py`、`yscb_cli.py` 必須同目錄共生，自更新以當前檔案位置為主，其餘全量依協定運作。
- **[ARCH:DR-URI-01] 統一路徑轉換器唯一入口鐵律**：全專案所有模組路徑存取 100% 透過 `ProjectURI` / `ProjectContext`，消除硬編碼。
- **[ARCH:DR-URI-02] 沙盒圍欄與完備度校驗**：`ProjectURI.resolve()` 內建路徑正規化與 `is_relative_to` 圍欄檢查，阻斷越界。
- **[ARCH:DR-URI-03] 泛型模組命名空間快取 (`cache://`)**：統一收斂至 `yscb://.yscb_cache/modules/<module>/` 並於卸載時自動清理。
- **[API:DR-01] `parse_uri` 三元元組契約**：回傳 `(scheme, subpath, authority)`，支援 authority 命名空間分流。
- **[API:DR-02] Python 3.8 `is_relative_to` 降級相容**：標準庫向後相容無損封裝。
