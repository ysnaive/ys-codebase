# 變更摘要 (Walkthrough)

> 功能名稱：fix_yscb_root_path_isolation (Module 檔案系統、快取儲存與 yscb:// 統一路徑轉換器完備性架構)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Completed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 變更概述

本次開發徹底解決了 `paths.yscb_root` 自定義路徑下的檔案系統與專案空間隔離問題，並建立了統一、高效且安全防禦的五層語意 URI 協議體系（`ProjectURI`）與模組獨立快取/持久儲存體系。同時透過 Fast Track 子計畫 `sub_01_cache_mirror_isolation` 將遠端 Git 鏡像快取目錄隔離至 `yscb://.yscb_cache/mirror/`，消除 Git 同步失敗時誤刪使用者模組快取與快照備份的重大缺陷。

---

## 2. 變更檔案清單

| 檔案路徑 | 變更類型 | 說明 |
|---------|---------|------|
| [`ys_codebase/source/core/scripts/context.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/context.py) | Modify | 重構 `get_yscb_root`、`get_module_dir`、新增 `get_cache_root`、`get_module_cache_dir` 與 `get_module_storage_dir` |
| [`ys_codebase/source/core/scripts/uri.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/uri.py) | Modify | 實作五層語意 URI 協議、沙盒圍欄防護 (Chroot Guard)、LPM 反向轉換、高階 Direct I/O API、預編譯正則與快速通道 (3.8 µs) |
| [`ys_codebase/source/core/scripts/config.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/config.py) | Modify | 實作 `resolve_config_uris` 與 `load(resolve_uris=True)` 自動展開設定檔內之語意 URI |
| [`ys_codebase/yscb_installer.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_installer.py) | Modify | `yscb_root` 動態錨定、`GitRemoteClient.cache_dir` 隔離至 `mirror/`、`cache status / clean` CLI 工具與模組卸載連動清理快取 |
| [`ys_codebase/yscb_cli.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_cli.py) | Modify | 模組探索與執行器錨定 `get_yscb_root()`、擴充 `uri check / list` 診斷工具與 `cache` 轉接器 |
| [`ys_codebase/source/agents-workflow/scripts/ide_sync.py`](file:///d:/repos/ys_codebase/ys_codebase/source/agents-workflow/scripts/ide_sync.py) | Modify | 快取路徑升級為 `cache://agents-workflow/` 命名空間，支援舊版根目錄快取自動平滑遷移 |
| [`test/test_uri_completeness.py`](file:///d:/repos/ys_codebase/test/test_uri_completeness.py) | Add | 新增 16 項完備性測試（FT-01~08, ET-01~07, PT-01）覆蓋 URI 解析、邊界逃逸阻斷與效能基準 |
| [`test/test_installer.py`](file:///d:/repos/ys_codebase/test/test_installer.py) | Modify | 新增 `test_18_git_remote_mirror_isolation` 測試 |
| [`test/test_hardening.py`](file:///d:/repos/ys_codebase/test/test_hardening.py) | Modify | 更新 Hardening 測試中快取鏡像路徑斷言 |
| [`docs/Core/SEMANTIC_URI_SYSTEM.md`](file:///d:/repos/ys_codebase/docs/Core/SEMANTIC_URI_SYSTEM.md) | Add | 新建語意 URI 系統專題架構手冊（維度 3 Topic Manual） |
| [`docs/Core/README.md`](file:///d:/repos/ys_codebase/docs/Core/README.md) | Modify | 更新 Core SDK API 清單、類別總覽與模組結構 |
| [`docs/Installer/DESIGN_NOTES.md`](file:///d:/repos/ys_codebase/docs/Installer/DESIGN_NOTES.md) | Modify | 登記 `DN-09` (主執行器三位一體公理) 與 `DN-10` (Git 鏡像空間隔離) |
| [`docs/README.md`](file:///d:/repos/ys_codebase/docs/README.md) | Modify | 根層知識地圖加入語意 URI 系統快速索引連結 |
| [`CHANGELOG.md`](file:///d:/repos/ys_codebase/CHANGELOG.md) | Modify | 追加 `2026_08_23_1505_fix_yscb_root_path_isolation` 高階版本摘要 |

---

## 3. 測試與品質驗證結果

- **自動化測試**：全量回歸套件 100% 通過
  - 單元與整合測試：**77 / 77 Passed**
  - 下游真實專案沙盒端到端測試 (Downstream Sandbox E2E)：**100% Passed**
  - 效能基準測試 (PT-01)：10,000 次 URI 解析耗時 **38.16 ms**（平均單次 **3.82 µs**）
- **Dogfooding 自引用閉環**：
  - 模組版本矩陣：`core` v2.3.0 `[SYNCED]`、`agents-workflow` v1.2.0 `[SYNCED]`、`installer` v2.3.1 `[SYNCED]`
- **UX / 手動驗證**：開發者已實機確認 CLI `uri check`、`uri list`、`cache status` 與 `cache clean` 行為符合預期。
- **偏差記錄**：無非預期偏差；Phase 6 UX 驗證期間識別之 Git 鏡像快取混雜問題，已透過衍生子計畫 `sub_01_cache_mirror_isolation` 規範化結案。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 規劃文檔路徑 | 交付狀態 | 實際修改章節 / 核心知識點 | 對應 P03/P05/P06 驗收錨點 |
| :--- | :--- | :--- | :--- |
| [`docs/Core/README.md`](file:///d:/repos/ys_codebase/docs/Core/README.md) | ✅ 已更新 | 補齊 `ProjectContext` 快取 API、`ProjectURI` 門面與 v2.3.0 結構 | P03 API-01, API-02 |
| [`docs/Core/SEMANTIC_URI_SYSTEM.md`](file:///d:/repos/ys_codebase/docs/Core/SEMANTIC_URI_SYSTEM.md) | ✅ 已新建 | 完整記錄五層協議體系、沙盒圍欄 (Chroot Guard)、LPM 演算法與 Direct I/O | P05 Task 2, P06 FT-01~08 |
| [`docs/Installer/DESIGN_NOTES.md`](file:///d:/repos/ys_codebase/docs/Installer/DESIGN_NOTES.md) | ✅ 已登記 | 登記 `DN-09` (主執行器三位一體公理) 與 `DN-10` (Git 鏡像空間隔離) | P05 Task 4, Task 8, ARCH:DR-EXEC-01 |
| [`docs/README.md`](file:///d:/repos/ys_codebase/docs/README.md) | ✅ 已同步 | 根層知識地圖快速索引同步更新語意 URI 系統手冊 | 全域知識庫同步 |
| [`CHANGELOG.md`](file:///d:/repos/ys_codebase/CHANGELOG.md) | ✅ 已追加 | 追加 `2026_08_23_1505_fix_yscb_root_path_isolation` 發布日誌 | Phase 7 規範 |

---

## 5. 推薦 Commit 訊息

```text
feat(core,installer): complete semantic uri converter and yscb_root path isolation

- implement 5-tier semantic URI protocol (project://, yscb://, cache://, storage://, temp://)
- implement Chroot Guard sandbox escape protection and LPM reverse conversion
- achieve 3.8us per resolution via pure-python fast-path cache
- refactor ProjectContext to isolate runtime assets strictly under paths.yscb_root
- add CLI tools: yscb_cli.py uri check/list and cache status/clean
- isolate GitRemoteClient cache to .yscb_cache/mirror via sub_01_cache_mirror_isolation
- add comprehensive test suite (77/77 tests + downstream sandbox E2E 100% passed)
- bump versions: core v2.3.0, agents-workflow v1.2.0, installer v2.3.1
```
