# 變更摘要 (Walkthrough)

> 功能名稱：Core 模組功能打磨 (Core Module Polish)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 變更概述

本子計畫（`sub_07`）完成了 Core 微內核核心機制與架構邊界的深度打磨與純淨化：
1. **`project://` 顯式配置與零 Fallback 鐵律**：`project://` 嚴格由 `yscb://config/core/config.project.json` 中配置的 `project_root` 解算；預設為 `!undefined`，未定義時精準拋出 `ValueError` 顯式阻斷，完全杜絕隱式猜測與跨環境路徑漂移。
2. **`config://` 顯式專案目錄協議**：將原 `.config/` 隱藏目錄導正為顯式之 `config/` 專案目錄（`config.root://` ➔ `yscb://config/`；`config://` ➔ `yscb://config/{module}/`），作為受 Git 追蹤之核心專案資產。
3. **依賴注入全面自宣告 (Self-Injection via Contributes)**：
   - `core` 於 `manifest.json` 自我宣告核心 10 組 URI 協議；
   - `dev` 於 `manifest.json` 宣告注入 4 組源碼/產物空間協議。
4. **中介層物化快照空間純淨化**：
   - `ContributesAggregator` 聚合結果導正輸出至 **`cache.root://{target}/contributes.merged.json`**（即 `yscb://.cache/`，受 Git 忽略）；
   - 實施**空檔抑制機制**，未接收注入之模組不落地空檔案，確保 `config/` 專案目錄 100% 維持純淨。
5. **模組預設組態自動分發與增量補齊 (Config Seeding & Auto-Fill)**：於安裝與重載時自動種入預設組態；已存在組態時採用原地遞迴鍵補齊，用戶既有之設定值 100% 保持不變。
6. **精準命名空間 Hook 對接與事件廣播 (`hook.{emit_module}.py`)**：接收端於自身 `scripts/` 下建立 `hook.{emit_module}.py` 對接發起端事件，Core 實施動態掃描、傳遞 `ExecutionContext` 並提供 try-except 例外隔離保護。
7. **套件產物空間追蹤與白皮書對齊**：`.gitignore` 追蹤 `ys_codebase/build/`，並全面回填更新主計畫 `R01` ~ `R04` 白皮書。

---

## 2. 變更檔案清單

| 檔案路徑 | 變更類型 | 說明 |
| :--- | :---: | :--- |
| [`source/core/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/manifest.json) | Modify | 自我宣告注入 10 組 Core 語意 URI 協議 (`yscb`, `mirror`, `temp`, `snapshot`, `module.root`, `module`, `config.root`, `config`, `cache.root`, `cache`) |
| [`source/dev/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/manifest.json) | Modify | 跨模組宣告注入 4 組 Dev 工具鏈空間 URI 協議 (`module.source.root`, `module.source`, `module.build.root`, `module.build`) |
| [`source/core/config.project.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/config.project.json) | Modify | 預設模板宣告 `project_root: "!undefined"` |
| [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py) | Modify | 實作 `ExecutionContext`、`project://` 零 Fallback 解析、動態載入 `.cache/core/contributes.merged.json` 中介快照並進行前綴解算與 `to_uri` 反查 |
| [`source/core/core/contributes.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/contributes.py) | Modify | 聚合結果導正輸出至 `cache.root://`，實施空檔抑制機制，並清除 `config/` 下歷史殘留 |
| [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | Modify | 實作 `_seed_or_update_config` 增量補齊演算法、`act_broadcast_event` 命名空間 Hook 調度與例外隔離、`act_init` 預設種入 `!undefined` |
| [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | Modify | 串接組態自動分發與生命週期事件廣播（`on_installed`, `on_update`, `on_remove`, `on_reload`） |
| [`.gitignore`](file:///h:/UseFolder/CodeRepo/ys_codebase/.gitignore) | Modify | 固化內部暫存 (`.temp`, `.mirror`, `.snapshots`, `.cache`) 忽略規則，保留 `build/` 受 Git 追蹤 |
| [`source/core/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/) | Modify | 全面覆蓋 `project://` 零 Fallback、`cache` 中介層物化、`config` 純淨性、Hook 例外隔離等 18 項測試 |
| [`plans/.../R01~R04`](file:///h:/UseFolder/CodeRepo/ys_codebase/plans/2026_08_23_2030_architecture_refactor/) | Modify | 全面回填 Hook 命名空間、顯式 config、無 Fallback 與自注入協議規範 |

---

## 3. 測試與品質驗證結果

- **自動化測試**：全量測試 100% 通過（共 31 項測試：6 項 Auto-Contract 契約測試 + 25 項持久化自訂測試，實測耗時 0.431s）
- **UX / 手動驗證**：開發者於控制台實機執行 `python yscb.py dev test --all --verbose` 驗收通過 (Status: PASSED 100% Ready)
- **偏差記錄**：
  1. `contributes.merged.json` 導正至 `cache://` 快取中介層，徹底清除 `config/` 空間中介衍生檔案。
  2. `project_root` 預設值明確規範為 `!undefined`，杜絕自舉階段任何隱式 Fallback。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

> 依據 P04 預排之文檔計畫，1:1 核對實際產出與更新的規範/規格文件：

| 規劃文檔路徑 | 交付狀態 | 實際修改章節 / 核心知識點 | 對應 P03/P05/P06 驗收錨點 |
| :--- | :---: | :--- | :--- |
| [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py) | ✅ 已交付 | `ExecutionContext` 介面、`project://` 零 Fallback 與動態載入 `.cache/` 中介層 | P03 §1.1, §1.2 / P06 FT-01, FT-02 |
| [`source/core/core/contributes.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/contributes.py) | ✅ 已交付 | 5 來源依賴注入級聯合併、`cache://` 輸出與空檔抑制機制 | P03 §1.5 / P06 FT-06 |
| [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | ✅ 已交付 | `_seed_or_update_config` 增量補齊與 `act_broadcast_event` 命名空間 Hook 調度 | P03 §1.3, §1.4 / P06 FT-03~05 |
| [`source/core/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/manifest.json) | ✅ 已交付 | 自宣告注入 10 組 Core URI 協議 | P03 §1.2 / P06 FT-02 |
| [`source/dev/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/manifest.json) | ✅ 已交付 | 跨模組宣告注入 4 組 Dev 工具鏈 URI 協議 | P03 §1.2 / P06 FT-02 |
| [`source/core/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/) | ✅ 已交付 | 全面更新測試案例矩陣（18 項持久化測試全數 Passed） | P03 §3 / P06 FT-01~06 |
| [`R01` ~ `R04` 白皮書](file:///h:/UseFolder/CodeRepo/ys_codebase/plans/2026_08_23_2030_architecture_refactor/) | ✅ 已同步 | 100% 同步回填主計畫調研報告（Hook 命名空間、顯式 config、無 Fallback） | NFR-04 |

---

## 5. 推薦 Commit 訊息

```text
feat(core): polish microkernel injection, namespaced hooks, and strict project_root resolution

- declare all core & dev URI schemes via self-injection in manifest.json
- persist dynamic contributes merged snapshots to cache:// (.cache/) with empty-file suppression
- enforce strict project:// resolution with default !undefined and zero fallback
- update config protocol to explicit non-hidden directory (yscb://config/)
- implement config seeding and recursive in-fill preserving user custom values
- implement namespaced hook dispatching (hook.{emit_module}.py) with exception isolation
- maintain yscb_codebase/build/ tracked in git repository
- achieve 31/31 automated tests passed (0.431s)
```
