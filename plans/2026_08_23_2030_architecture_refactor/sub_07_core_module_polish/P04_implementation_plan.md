# 實作計畫書 (Implementation Plan)

> 功能名稱：Core 模組功能打磨 (Core Module Polish)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據計畫：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md) / [P03_api_spec.md](./P03_api_spec.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 跨階段審查檢核表 (Cross-Verification Checklist)

- [x] **需求覆蓋**：P01 之 FR-01 ~ FR-06 在 P03 中均有明確之介面與函式簽名定義。
- [x] **邊界防禦**：EC-01 ~ EC-05 之例外防護已融入各 API 錯誤處理與 try-except 隔離設計。
- [x] **空間純淨**：`source/core/` 根目錄移除非標準 `config.project.json`，確立 `module://` 純淨發布包邊界。
- [x] **路徑確定**：`project://` 嚴格綁定 `config/core/config.project.json`，未定義時精準拋錯，零猜測。
- [x] **增量補齊**：既有組態採用原地鍵補齊（Recursive Key Infill），用戶值 100% 保持不變。
- [x] **白皮書對齊**：NFR-04 約束於本計畫完成時同步回填更新主計畫 `R01` ~ `R04` 調研報告。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

依據 7 大抽象知識維度投影，本子計畫將交付與更新以下知識庫文檔（於後續子計畫同步落地）：

| 維度 | 規劃文檔路徑 | 變更類型 | 核心內容與知識點 | 對應錨點 |
| :---: | :--- | :---: | :--- | :--- |
| **維度 1/2** | `docs/Core/README.md` | Modify | 模組架構總覽、`ExecutionContext` 介面與顯式 `config/` 說明 | P03 §1.1 |
| **維度 3** | `docs/Core/uri_protocol.md` | Modify | 語意 URI 協議手冊（`project://` 零 Fallback 與 `config://` 顯式解析） | P03 §1.2 |
| **維度 3** | `docs/Core/lifecycle_hooks.md` | Add | 命名空間 Hook 對接手冊（`hook.{emit_module}.py` 規範與事件派發） | P03 §1.3, §2.2 |
| **維度 5** | `docs/Core/DESIGN_NOTES.md` | Modify | 登記 `DN-01`（空間純淨）、`DN-02`（零 Fallback）、`DN-03`（Hook 動態載入隔離） | P01 §5 |
| **維度 7** | `R01` ~ `R04` 調研報告 | Modify | 主計畫全域白皮書對齊回填（Hook 命名空間、顯式 config、無 Fallback） | NFR-04 |

---

## 3. 架構審查靈魂拷問 (Stress Test & Architecture Defense)

> 🧐 **審查員提問**：
> 當第三方模組在 `hook.{emit_module}.py` 中執行耗時過長之阻塞 I/O 操作時，是否會拖慢或阻塞整個 CLI（如 `install` / `reload`）的主流程？Core 為何不採用非同步背景執行？

> 💡 **架構答辯與防護機制**：
> 1. **生命週期一致性優先 (Consistency First)**：模組生命週期 Hook（如 `on_installed`、`on_reload`）的定位是**保證各模組在環境刷新完成的那一刻已 100% 處於就緒狀態**（例如 IDE 配置重建完畢、記憶體快取刷新完成）。若採用非同步背景執行，會產生主流程已回報成功但下游模組尚未就緒的競態條件 (Race Condition)。
> 2. **例外隔離防護 (Exception Isolation)**：Core 在調度各模組 Hook 時全面實施 `try-except` 隔離，即使單一 Hook 崩潰亦不中斷主流程；
> 3. **規範約束**：生命週期 Hook 應專注於本地記憶體與輕量檔案同步，嚴禁塞入大型長耗時網路輪詢。

---

## 4. 實作任務工作細項 (Implementation Breakdown)

| 任務編號 | 實作檔案路徑 | 變更類型 | 核心實作內容 |
| :--- | :--- | :---: | :--- |
| **TASK-01** | [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py) | Modify | 1. 實作 `ExecutionContext` 凍結資料類別。<br/>2. 重構 `_find_host_config()` 與 `resolve()`：`project://` 嚴格讀取 `config/core/config.project.json` 之 `project_root`，未定義拋出 `ValueError`（零 Fallback）。<br/>3. 更新 `config.root://` ➔ `yscb://config/`，`config://` ➔ `yscb://config/{module}/`。<br/>4. 打通 `contributes.merged.json` 之 `type: "config"` 與動態佔位符 handler 解析。 |
| **TASK-02** | [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | Modify | 1. 實作 `_seed_or_update_config`：自動分發預設組態，已存在時遞迴比對補齊缺失條目（舊值不變）。<br/>2. 實作 `act_broadcast_event`：動態掃描 `module.root://*/scripts/hook.{emit_module}.py` 並調度執行，內建 try-except 例外隔離保護。 |
| **TASK-03** | [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | Modify | 1. 於 `cmd_install` / `cmd_update` / `cmd_reload` 流程串接組態自動分發與事件廣播。<br/>2. 移除 `source/core/config.project.json` 與 `modules/core/config.project.json`，維護模組空間純淨度。 |
| **TASK-04** | [`source/core/tests/...`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests) | Modify | 1. 更新 `test_uri.py`：驗證 `project://` 顯式解析與零 Fallback 阻斷、`config/` 新協議、動態佔位符。<br/>2. 更新 `test_engine.py`：驗證 `hook.{emit_module}.py` 命名空間事件廣播、例外隔離、組態增量補齊。<br/>3. 更新 `test_installer.py`：驗證安裝時組態自動種入與補齊。 |
| **TASK-05** | `R01 ~ R04 白皮書` | Modify | 全面回填對齊主計畫調研報告（`R01`~`R04`），同步 `hook.{emit_mod}.py`、`config/`、`project://` 零 Fallback 與增量補齊規範。 |

---

## 5. 本階段決策紀錄 (Phase 4 Decision Records)

- **[P04:DR-01] 全計畫雙重剛性定稿**：本實作計畫書與 `P06_test_plan.md` 經跨階段審查與靈魂拷問答辯，正式剛性定稿 (Confirmed)。
