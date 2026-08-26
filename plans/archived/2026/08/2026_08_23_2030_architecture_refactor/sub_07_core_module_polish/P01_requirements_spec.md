# 需求規格書 (Requirements Specification)

> 功能名稱：Core 模組功能打磨 (Core Module Polish)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 系統功能需求 (Functional Requirements, FR)

| FR 編號 | 功能名稱 | 觸發時機 / 調用介面 | 核心行為與規則 | 驗收標準 (Acceptance Criteria) | 對應 P00 語意 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FR-01** | **`project://` 顯式配置與零 Fallback 解析** | `uri.resolve("project://...")` | 1. 讀取 `config/core/config.project.json` 之 `project_root` 進行解析。<br/>2. 若未配置或為 `undefined`，**立即拋出 ValueError 顯式例外，完全禁止猜測或 fallback**。 | 成功根據配置解析專案路徑；缺省時精準拋錯阻斷 | P00 §1.1, 情境 A |
| **FR-02** | **`config://` 顯式專案目錄協議** | `uri.resolve("config://...")`<br/>`uri.resolve("config.root://...")` | 1. `config.root://` 解算為 `yscb://config/`（非隱藏目錄，Git 追蹤資產）。<br/>2. `config://` 解算為 `yscb://config/{module}/`。 | 協議解析不再輸出 `.config/`，而精準指向 `config/` | P00 §1.2 |
| **FR-03** | **模組預設組態自動分發與增量補齊 (Config Seeding & Auto-Fill)** | `Installer.cmd_install`<br/>`AtomicEngine.act_reload` | 1. 模組物化時，探測其是否帶有預設 `config.project.json` / `config.local.json`。<br/>2. 若目標 `config://` 尚未存在該設定檔，**自動複製安裝至 `config://`**。<br/>3. **若已存在，自動遞迴比對分析缺失條目並自動補齊，既有用戶設定值剛性維持不變**。 | 初次安裝自動種入組態；既有組態自動增量補齊缺失鍵且保留用戶設定 | P00 §1.3, 情境 B |
| **FR-04** | **命名空間 Hook 對接與事件廣播** | `AtomicEngine.act_broadcast_event`<br/>`(emit_module, event_name, context)` | 1. 發起端調用廣播。<br/>2. Core 遍歷所有已安裝模組，探測 `module.root://{mod}/scripts/hook.{emit_module}.py`。<br/>3. 若存在同名函式 `{event_name}`，傳入 `ExecutionContext` 執行。<br/>4. **try-except 例外隔離保護**，單一模組失敗僅記錄 Warning，不阻斷主流程。 | 跨模組生命週期 hook 依命名空間精準派發與異常隔離 | P00 §1.4, 情境 C |
| **FR-05** | **語意 URI 動態協議與佔位符解算** | `uri.resolve` 與 `ExecutionContext` | 1. 支援 `type: "const"`（路徑模板）與 `type: "config"`（**僅讀取 `config://config.project.json`**）。<br/>2. 支援 `path_placeholders` 之動態 handler 函式調用解算。 | 完整解算動態 contributes 註冊之 URI 協議與自訂佔位符 | P00 §1.5 |
| **FR-06** | **模組空間純淨化與殘留清理** | `dev build` 與源碼空間檢查 | 1. 刪除 `source/core/config.project.json` 與 `modules/core/config.project.json`。<br/>2. 確立 `module://` 空間僅存放代碼與 manifest。 | `modules/core/` 根目錄無非標準設定檔殘留 | P00 §1.6 |

---

## 2. 邊界條件與例外處理 (Edge Cases & Exception Handling, EC)

| EC 編號 | 異常情境 | 防禦策略 | 預期系統行為 (降級/錯誤處理) | 對應 P00 語意 |
| :--- | :--- | :--- | :--- | :--- |
| **EC-01** | `project_root` 未配置或設定檔不存在 | 零臆測阻斷 | 拋出 `ValueError: 'project://' is undefined. Please configure 'project_root' in config://config.project.json (core)`。 | P00 限制 3.1 |
| **EC-02** | 接收端 Hook 函式執行過程拋出未捕獲例外 | 異常隔離防護 | 捕獲 Exception，輸出 Warning 日誌 `[core:events] Warning: Hook '{mod}:hook.{emit_mod}.py' failed: {e}`，繼續調度其餘模組。 | P00 情境 C |
| **EC-03** | 模組安裝時專案 `config/` 已存在自訂組態 | 增量補齊與保護 | 讀取既有組態，遞迴補齊預設範本中新增的鍵值，原有用戶值 100% 保留，更新寫回。 | P00 限制 3.4, FR-03 |
| **EC-04** | 動態佔位符 Handler 不存在或語法錯誤 | 動態載入防禦 | 拋出 `ImportError` 或 `AttributeError`，明確指明無法載入指定 handler。 | P00 情境 E |
| **EC-05** | Hook 檔案不存在或無目標 event 函式 | 靜默略過 | 忽略該模組，不拋錯，繼續處理下一模組。 | P00 情境 C |

---

## 3. 非功能需求 (Non-Functional Requirements, NFR)

| NFR 編號 | 質量維度 | 指標約束與目標 | 驗證方式 |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **零外部相依** | 100% 依賴 Python 3.8+ 標準庫（`importlib.util`, `json`, `os`, `shutil`），禁止引入任何第三方套件。 | 靜態代碼檢查與合規性掃描 |
| **NFR-02** | **極致效能** | 動態 URI 解算與單次事件全模組掃描開銷 $\le 5\text{ms}$。 | 計時斷言與基準測試 |
| **NFR-03** | **向下相容性** | 既有標準測試套件 (Core 15 + Dev 13) 100% 全數通過，無 Regression。 | `python yscb.py dev test --all` 回歸測試 |
| **NFR-04** | **主計畫白皮書對齊** | 同步更新主計畫調研報告（`R01`~`R04`），將最新之 `hook.{emit_module}.py`、`config/` 顯式協議、`project://` 顯式無 Fallback 與增量組態補齊規範 100% 回填至白皮書。 | 交叉核對與文檔稽核 |

---

## 4. 專案特化擴充判定矩陣 (Extension Specialization Matrix)

| 擴充功能名稱 (Extension Name) | 來源目錄 | 判定結果 | 評估理由與納入範圍 |
| :--- | :--- | :---: | :--- |
| **`sop_ext://` 專案擴充清單** | `extensions/` | **Excluded** | 本子計畫專注於 Core 微內核底層機制打磨，無額外專案特化擴充需求。 |

---

## 5. 知識庫防坑紀錄盤點 (Known Pitfalls & Design Notes)

- **[DN-01 空間純淨防線]**：`modules/{module}/` 為純淨發布包，嚴禁將用戶專案組態直接放在模組根目錄，必須一律安裝至 `yscb://config/{module}/`。
- **[DN-02 project:// 零猜測鐵律]**：絕對禁止在找不到 `project_root` 時自動 fallback 至 `os.getcwd()`，必須以顯式例外阻斷路徑漂移。
- **[DN-03 Hook 動態載入命名隔離]**：動態載入 `hook.{emit_module}.py` 時，必須指定唯一 module_name（如 `f"_yscb_hook_{receiver}_{emit_mod}"`）載入至 `sys.modules`，避免模組間快取碰撞。

---

## 6. 本階段決策紀錄 (Phase 1 Decision Records)

- **[P01:DR-01] 顯式 project_root 與無 Fallback 規範**：`project://` 嚴格綁定 `config/core/config.project.json`；未配置則拋錯。
- **[P01:DR-02] 顯式 config/ 目錄結構**：`config.root://` ➔ `yscb://config/`；`config://` ➔ `yscb://config/{module}/`。
- **[P01:DR-03] 命名空間 hook.{emit_module}.py**：接收端以 `hook.{emit_module}.py` 承接發起端事件，Core 負責動態掃描與例外隔離。
- **[P01:DR-04] 預設組態自動分發策略**：模組預設組態於安裝/reload 時部署至 `config://`，已存在則剛性保留。
