# 需求討論與問題界定紀錄 (Phase 0: Discuss)

> 功能名稱：core 核心拓撲注入 (yscb_root) 與全庫 Fallback 剛性收斂  
> 建立日期：2026-08-30  
> 所屬計畫：2026_08_30_1928_core_topology_injection_and_zero_fallback  
> 狀態：Confirmed  

---

## 1. 原始需求陳述與問題背景

在排查測試沙盒生命週期鉤子 (`hook.dev.py`) 時，發現多進程並發建立沙盒會穿透寫入宿主 `config.project.json`。經全庫檢索，識別出 `core` 模組對 `host_dir` 已具備顯式注入能力，但對 `yscb_root` 仍依賴 `__file__` 向上推算，且 `core/config.py` 與 `agents-workflow` 殘留了多處 `while` 迴圈與 `os.getcwd()` 的隱式 Fallback 模糊猜測機制。

---

## 2. 全庫 Fallback 機制清冊與決策

- **[P00:DR-01]**：於 `core/uri.py` 補齊對稱之 `yscb_root` 記憶體與環境變數注入介面（`set_yscb_root`、`get_yscb_root`、`yscb_scope`、`YSCB_ROOT_DIR`），確立優先級：記憶體注入 > 環境變數 > 常數基準。
- **[P00:DR-02]**：徹底清除 `core/config.py` 中的 `while` 遞迴尋找 `yscb.py` 迴圈與 `os.getcwd()` 回退，貫徹零臆測原則。
- **[P00:DR-03]**：於 `dev/testing/sandbox.py` 之 `_dispatch_test_hooks` 同時包覆 `host_scope(ctx.host_dir)` 與 `yscb_scope(ctx.engine_dir)`，保證測試鉤子 100% 沙盒化。
- **[P00:DR-04]**：收斂 `agents-workflow` 內 `searcher.py`、`archiver.py` 等組件的路徑解算，消除 `archive_plans` 命名分歧。

---

## 3. 分流確認
- 涉及跨 3 大模組架構協同與 Public API 擴充，分流確立為 **Level 1 (Full Track)**。

