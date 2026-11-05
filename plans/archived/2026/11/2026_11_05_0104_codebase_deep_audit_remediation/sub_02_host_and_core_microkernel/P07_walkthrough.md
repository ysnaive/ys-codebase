# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_02_host_and_core_microkernel  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：完成 `yscb.py` 宿主與 `module:core` 13 項深度審計問題修復及 `DEV-01` 根源 TLS 化：將 `core/uri.py` 全域狀態（`active_host_dir`/`active_yscb_dir`/`active_module_context`/`reconciling_tokens`）遷移至 `threading.local()`；於 `uri.resolve` 補齊子路徑 `..` 逃逸與磁碟機重置攔截、`VFS.open` 安全邊界守衛與 `newline="\n"` 及 `OSBackend.copy(symlinks=True)` (`U3-P0-01`)；為 Localhost IPC 綁定 `ProxyHandler({})` 與 `ConnectionResetError`/`BrokenPipeError` 重置判定 (`U3-P0-02`)；對齊 `yscb.host://yscb.config.json` (`U3-P1-02`)、`act_snapshot` 清理同名舊快照與 `cmd_rollback` mtime 排序 (`U3-P1-03`)、無 `/proc` 環境 `ps` 殭屍進程檢測 (`U3-P1-01`)、`.mirror` 備份先於 SHA-256 校驗 (`U3-P1-05`)、負數 CLI 參數解析 (`U3-P1-06`) 與多 `yscb_root` 快取隔離 (`U3-P2-01`~`04`/`U3-P3-01`~`02`)。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 修正 `_atomic_write_bytes` 失敗時於 `except` 區塊清理遺留 `.tmp` 暫存檔 (`U3-P3-01`) |
| `ys_codebase/source/core/core/uri.py` | Modify | 遷移 `_URI_TLS` 執行緒本地儲存並實作 `_ensure_safe_subpath` 子路徑逃逸攔截 (`DEV-01`, `U3-P0-01`) |
| `ys_codebase/source/core/core/vfs.py` | Modify | `VFS.open` 補齊 `assert_safe_path` 與預設 `newline="\n"`，`OSBackend.copy` 啟用 `symlinks=True` (`U3-P0-01`, `U3-P1-04`, `U3-P2-02`) |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | Localhost IPC 綁定 `ProxyHandler({})`、重置異常歸類 `accepted=True` 與 `_GLOBAL_REGISTRY_ROOT` 隔離 (`U3-P0-02`, `U3-P2-01`) |
| `ys_codebase/source/core/core/commands/resolver.py` | Modify | `_is_negative_number_token` 放行負數位置與帶值選項參數 (`U3-P1-06`) |
| `ys_codebase/source/core/core/platform/process.py` | Modify | 補齊 `ps -o stat=` 殭屍進程識別與 `daemon_probe` 跨進程鎖保護 (`U3-P1-01`, `U3-P2-04`) |
| `ys_codebase/source/core/core/contributes.py` | Modify | `_get_installed_modules_state` 改讀 `yscb.host://yscb.config.json` (`U3-P1-02`) |
| `ys_codebase/source/core/core/update_checker.py` | Modify | `_run_update_check_worker` 改讀 `yscb.host://yscb.config.json` (`U3-P1-02`) |
| `ys_codebase/source/core/core/engine.py` | Modify | `act_snapshot` 清理同名舊快照、`act_lock` 同操作名重入保護 (`U3-P1-03`, `U3-P3-02`) |
| `ys_codebase/source/core/core/installer.py` | Modify | `cmd_rollback` 按 `mtime` 降序選取最新快照、`_restore_module_package` 先鏡像再驗 SHA-256 (`U3-P1-03`, `U3-P1-05`) |
| `ys_codebase/source/core/core/{config,locale,symbols,validator,cli}.py` | Modify | 以 `yscb_root` 隔離快取、正負號數值解析與忽略 `__*__` 元數據鍵 (`U3-P2-01`, `U3-P3-01`~`02`) |
| `ys_codebase/source/core/tests/test_*.py` | Modify | 新增與擴充 12 個測試檔覆蓋全數修復點 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：100% 通過（`core`: 256/256 Pass），`dev check core` 100% Passed。
- **實機 UX / 人工驗證**：已通過盲眼子代理審查（`REVIEW_STATUS: PASSED`）與主代理 P06 統一沙盒測試驗收並同步安裝 `core@1.2.7.build`。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已更新 | 已於根目錄 `CHANGELOG.md` 記錄 `sub_02` 完整修復與微內核加固摘要 |
| **中觀 (Meso)** | `docs/core/README.md` | 免更 | 內部安全守衛與 TLS 實作加固，對外 SDK 簽名與架構保持相容 |
| **中觀 (Meso)** | `docs/core/[topic].md` | 免更 | 未新增獨立專題手冊 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | 免更 | 對齊既有 `[DN-03]` 與 `[DN-07]` 規範，無新增反直覺設計妥協 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已更新 | `uri.py`、`vfs.py`、`dispatcher.py`、`installer.py` 等公開與內部函式註解完整且無工單編號污染 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(core,host): isolate uri scopes in thread-local storage and harden vfs/ipc/installer guards
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_05_0104_codebase_deep_audit_remediation/sub_02_host_and_core_microkernel` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

