# 實作任務清單 (Task List)

> 功能名稱：fix_yscb_root_path_isolation (Module 檔案系統、快取儲存與 yscb:// 統一路徑轉換器完備性架構)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Completed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.2  

---

## 1. 核心任務清單 (TODO Checklist)

- [x] **Task 1: Core SDK 路徑與快取 API 重構** ([`ys_codebase/source/core/scripts/context.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/context.py))
  - [x] 修正 `get_yscb_root()` 正確解析 `paths.yscb_root` 相對路徑
  - [x] 修正 `get_module_dir()` 移除硬編碼 `"ys_codebase"`，改自 `get_yscb_root()` 查找
  - [x] 新增 `get_module_cache_dir(mod)` 自動建立並回傳 `yscb://.yscb_cache/modules/<mod>/`
  - [x] 新增 `get_cache_root()` 回傳 `yscb://.yscb_cache`
  - [x] 新增 `get_module_storage_dir(mod)` 回傳 `project://.yscb_storage/<mod>/`
- [x] **Task 2: 語意 URI 統一轉換器升級與沙盒圍欄防護** ([`ys_codebase/source/core/scripts/uri.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/uri.py))
  - [x] 擴充保留協議 `RESERVED_SCHEMES`（含 `cache`, `storage`, `temp`）
  - [x] `parse_uri()` 支援三元元組回傳 `(scheme, subpath, authority)`
  - [x] `resolve()` 支援泛型 `cache://`、`storage://` 與 `_is_relative_to` 沙盒圍欄防護
  - [x] 新增 `validate()` 完備度校驗接口
  - [x] `to_uri()` 實作最長前綴匹配 (LPM) 演算法與優先級消歧
  - [x] 新增 `exists / is_file / is_dir / read_text / write_text / check_schemes` 門面 API
- [x] **Task 3: 設定檔語意 URI 自動遞迴解析** ([`ys_codebase/source/core/scripts/config.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/config.py))
  - [x] `load()` 時支援自動遞迴解析設定值中的語意 URI
- [x] **Task 4: Installer 安裝基底收斂與快取連動** ([`ys_codebase/yscb_installer.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_installer.py))
  - [x] `ConfigManager.get_yscb_root()` 修正為動態解析 `paths.yscb_root`
  - [x] `ModuleManager` 安裝、源碼、建置、快取與快照備份 100% 收斂至 `get_yscb_root()`
  - [x] 模組卸載 `remove` 自動連動清理 `cache://<module>/`
  - [x] 貫徹自更新以主執行器所在實體目錄為準 ([ARCH:DR-EXEC-01])
- [x] **Task 5: CLI 路由器擴充與診斷工具鏈** ([`ys_codebase/yscb_cli.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_cli.py))
  - [x] 模組發現與 Core 探索改用 `ProjectContext.get_yscb_root()`，移除硬編碼
  - [x] 新增 `cache clean [module] [--all]` 與 `cache status` 子指令
  - [x] 擴充 `uri check` 一鍵健康度與越界診斷指令
- [x] **Task 6: `agents-workflow` 快取遷移** ([`ys_codebase/source/agents-workflow/scripts/ide_sync.py`](file:///d:/repos/ys_codebase/ys_codebase/source/agents-workflow/scripts/ide_sync.py))
  - [x] 快取改存至 `ProjectContext.get_module_cache_dir("agents-workflow")`
  - [x] 執行舊版快取檔案自動平滑遷移至新命名空間
- [x] **Task 7: 完備性全量測試套件編寫** ([`test/test_uri_completeness.py`](file:///d:/repos/ys_codebase/test/test_uri_completeness.py))
  - [x] 實作 FT-01~08 功能測試
  - [x] 實作 ET-01~07 邊界與安全測試
  - [x] 實作 PT-01 效能基準測試
- [x] **Task 8: Dogfooding 閉環流水線執行**
  - [x] 遞進版本號（`core` v2.3.0, `agents-workflow` v1.2.0, `installer` v2.3.0）
  - [x] `python yscb_cli.py installer build --all`
  - [x] `python test/run_regression.py` (全量測試 100% Passed)
  - [x] 同步根目錄起手腳本與 `installer install --force` 自引用部署

---

## 2. 實作偏差記錄 (Deviation Log)

| 偏差 ID | 等級 | 涉及檔案 | 偏差描述 | 處置方式 |
|:---|:---:|:---|:---|:---|
| *(無實作偏差)* | - | - | 實作完全對齊 P02/P03/P04 規格書 | - |
