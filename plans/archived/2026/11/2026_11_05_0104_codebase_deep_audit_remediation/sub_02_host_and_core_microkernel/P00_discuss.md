# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_host_and_core_microkernel  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Unknown  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：執行全倉深度審計分類型主計畫（`2026_11_05_0104_codebase_deep_audit_remediation`）之子計畫 `sub_02_host_and_core_microkernel`（宿主 yscb.py 與微內核 module:core 審計問題修復與執行緒安全加固）。
- **核心目標**：依據主計畫 `R01_codebase_deep_audit.md` 經盲眼反向查驗確認之問題清單與防回歸紅線，完成 `yscb.py 與 ys_codebase/source/core/` 範圍內所有確認缺陷之無損修復與單元測試驗證。
- **既有組件復用與查重 (Reuse Discovery)**：復用目標模組既有鎖機制、快取結構與 `YSCBTestCase` 隔離沙盒測試框架。
- **邊界排除 (Explicitly Excluded)**：嚴格限制寫入範圍於 `yscb.py 與 ys_codebase/source/core/`，不觸碰其他子計畫負責之模組目錄，且不修改 `R01_codebase_deep_audit.md` 已駁回之偽陽性項目。
- **架構影響範圍**：`yscb.py 與 ys_codebase/source/core/` 及對應 `tests/` 測試案例。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `core.uri` 執行緒本地化與子路徑安全邊界加固（`DEV-01` 根源修復, `U3-P0-01`, `U3-P1-02`）**：遵守紅線 6，將 `core/uri.py` 之 `_active_host_dir`、`_active_yscb_dir`、`_active_module_context` 與 `_reconciling_tokens` 遷移至 `threading.local()`，根除多執行緒平行沙盒 `host_scope`/`yscb_scope` 全域污染；遵守紅線 3，在解算出 `target_base` 後對非空子路徑 `rel` 攔截 `..` 逃逸與 Windows 磁碟機重置，於 `VFS.open()` 補齊 `assert_safe_path` 與寫入 `newline='\n'`；將 `contributes.py` 與 `update_checker.py` 對宿主設定檔之引用統一為 `yscb.host://yscb.config.json`（對標 `[DN-03]`）。
- **[P00:DR-02] Localhost IPC 無代理通道、重置異常判定與 Daemon 探針鎖保護（`U3-P0-02`, `U3-P1-05`, `U3-P1-06`）**：遵守紅線 4，於 `dispatcher.py` 與 `installer.py` 使用 `ProxyHandler({})` 繞過系統 `HTTP_PROXY`，在 `except urllib.error.URLError:` 分支將 `(TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError)` 判為 `accepted=True`；於 `_strict_hot_dispatch_or_block` 僅在 `accepted` 時跳出等待迴圈；為 Windows `taskkill` 補齊 `timeout` 與異常保護，並在 macOS 下支援 `ps -o stat=` 識別 Zombie。
- **[P00:DR-03] 快照回滾、套件還原、工作區快取鍵與驗證器/解析器細節收斂（`U3-P2-03` 已於 `2026_11_04_1739/sub_01` 修畢；聚焦剩餘 `U3-P1-01`, `U3-P1-03`, `U3-P1-04`, `U3-P2-01`~`02`, `U3-P2-04`, `U3-P3-01`~`02`）**：遵守紅線 5，於 `act_snapshot` 建立前清理同名舊快照、於 `cmd_rollback` 按 `(mtime, name)` 選取最新快照、於 `_restore_module_package` 先拷貝 `release/` 壓縮包至 `.mirror` 再驗 SHA256；將 `yscb_root` 納入 `ConfigManager`/`locale`/`symbols` 快取鍵並於 `act_reload` 連動失效（不對 `contributes.get` 無條件 `deepcopy`）；補齊 `_safe_copytree` 符號連結處理、`act_lock` 重入檢查、`validator.py` 略過 `dict` 之 `__provider__` 鍵、以及 `OptionResolver` 負數與 `config set` 浮點數解析。

---

## 3. 開放議題與確認紀錄

- **已確認事項**：子計畫範疇、防回歸紅線與修復方案已由主計畫 `R01_codebase_deep_audit.md` 定錨確認，可隨時啟動 Phase 01～07（或 `/auto`）推進實作。
