# 需求規格說明書 (Requirements Specification)

> 功能名稱：core 核心拓撲注入 (yscb_root) 與全庫 Fallback 剛性收斂  
> 建立日期：2026-08-30  
> 所屬計畫：2026_08_30_1928_core_topology_injection_and_zero_fallback  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `yscb_root` 顯式注入介面 | 於 `core.uri` 提供 `set_yscb_root(path)`、`get_yscb_root()`、`yscb_scope(path)` 與 `YSCB_ROOT_DIR` 環境變數讀取支援。 | P0 | [P00:DR-01] |
| **FR-02** | 核心自省優先級三級階梯 | `_get_yscb_root()` 依序求值：`_active_yscb_dir` (記憶體) $\rightarrow$ `YSCB_ROOT_DIR` (環境變數) $\rightarrow$ `__file__` 向上 3 層 (常數基準)，若皆無效拋出異常。 | P0 | [P00:DR-01] |
| **FR-03** | 移除 `core.config` while 迴圈 | 徹底移除 `ConfigManager._get_yscb_root()` 中的 `while` 遞迴搜尋與 `os.getcwd()` fallback，100% 委任 `uri._get_yscb_root()`。 | P0 | [P00:DR-02] |
| **FR-04** | 沙盒生命週期雙軌作用域 | `SandboxProvisioner._dispatch_test_hooks` 同時包覆 `uri.host_scope(ctx.host_dir)` 與 `uri.yscb_scope(ctx.engine_dir)`。 | P0 | [P00:DR-03] |
| **FR-05** | 工作流路徑與歸檔目錄收斂 | 統一 `agents-workflow` 各元件預設歸檔目錄為 `plans/archived`，消除 `archive_plans` 命名不一致。 | P1 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `set_yscb_root(None)` 或傳入空字串 | 自動清空記憶體全域快取 `_active_yscb_dir = None`，不拋出錯誤。 |
| **EC-02** | `YSCB_ROOT_DIR` 指向不存在之路徑 | `get_yscb_root()` 忽略無效路徑並退回 `__file__` 常數基準，杜絕崩潰。 |
| **EC-03** | 巢狀呼叫 `yscb_scope()` 與異常退出 | 以 `try...finally` 100% 保證還原前一次的作用域狀態，防止測試間互相污染。 |
| **EC-04** | 多進程/多執行緒並發呼叫 `_dispatch_test_hooks` | 各執行緒在各自的 `yscb_scope` 與 `host_scope` 內獨立解算 URI，100% 隔離實體檔案存取。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴約束 | 100% 採用純 Python 原生標準庫（Zero External Dependency）。 |
| **NFR-02** | 效能指標 | `get_yscb_root()` 記憶體快取讀取延遲 $\le 0.05\mu\text{s}$。 |
| **NFR-03** | 相容與守門 | 全生態系 248+ 套測試案例 100% Passed，`dev check` 合規性 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!IMPORTANT]`**：`yscb_scope` 與 `host_scope` 必須對稱管理全域狀態，在單元測試中使用 `@contextmanager` 確保 finally 還原。
- **`[!CAUTION]`**：嚴禁在 `_get_yscb_root` 再次引入 `os.getcwd()` 隱式回退，必須貫徹物理拓撲不變性。

