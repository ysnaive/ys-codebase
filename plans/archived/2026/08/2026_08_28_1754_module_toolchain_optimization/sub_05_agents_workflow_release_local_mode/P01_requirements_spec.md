# 需求規格說明書 (Requirements Specification)

> 功能名稱：Agents-Workflow Release 預設 Local 模式、Gitignore 軟合併同步與 Core Config 來源層級探測 (Release Local Mode, Gitignore Sync & Core Config Origin Inspection)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_05)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Core Config 來源層級探測 API | 為 `core.config` 增補 `get_raw(module, key, local, default)` 與 `inspect(module, key)`，可精確讀取特定層級原始值並診斷有效值來源層級（`local`, `project`, `both`, `none`）與覆蓋狀態。 | P0 | [sub_05:P00:DR-04] |
| **FR-02** | ReleaseTargetManager 預設 Local 操作 | `ReleaseTargetManager.add_target()` 與 `remove_target()` 預設 `is_project=False`（寫入 `config.local.json`）；傳入 `is_project=True` 時寫入 `config.project.json`。 | P0 | [sub_05:P00:DR-01] |
| **FR-03** | ReleaseTargetManager 多層清單與來源標註 | `ReleaseTargetManager.list_targets()` 透過 `core.config` 同時比對 Local 與 Project 組態，標註來源狀態：`[ENABLED (LOCAL)]`、`[ENABLED (PROJECT)]`、`[ENABLED (BOTH)]`、`[DISABLED]`。 | P0 | [sub_05:P00:DR-02] |
| **FR-04** | CLI release-target 支援 `--proj` 旗標 | CLI `release-target --add <t> [--proj]` 與 `--remove <t> [--proj]` 支援透過 `--proj` 切換專案共用組態，預設操作本機私有組態；`--list` 彩色輸出層級。 | P0 | [sub_05:P00:DR-01], [sub_05:P00:DR-02] |
| **FR-05** | Gitignore 區塊非破壞性軟合併 | `ReleasePublisher.release_all()` 發布時自動於 `project://.gitignore` 軟合併維護 `# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===` 區塊，列出啟用 targets 之忽略規則；若檔案不存在則自動建立，外部規則 100% 保留。 | P0 | [sub_05:P00:DR-03] |
| **FR-06** | ReleasePublisher 複合來源 Targets 聯集發布 | 發布引擎解析 active targets 時，自動取得 Local 與 Project 之 `release_targets` 聯集清單，進行 4 步原子發布與檔案清理。 | P0 | [sub_05:P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `.gitignore` 檔案不存在或無結尾換行 | 若檔案不存在自動建立包含 Header 與標記區塊的新檔案；若存在但缺少結尾換行，自動補齊 `\n` 後追加/替換區塊，避免破壞末行規則。 |
| **EC-02** | 同一 Target 於 Local 與 Project 雙重啟用 | 若 Target 同時存在於兩層組態，`list_targets` 標註為 `[ENABLED (BOTH)]`，發布時去重正常處理。 |
| **EC-03** | 移除特定層級之 Target | 若 Target 在 Project 啟用，在 Local 執行 `--remove`（無 `--proj`），僅清理 Local 端的設定；若 Project 仍有，狀態降為 `[ENABLED (PROJECT)]`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 純淨標準庫與空間邊界 | 100% 依賴 Python 標準庫與 `core.config` SDK，嚴禁模組代碼直接硬編碼存取實體 JSON 裸檔。 |
| **NFR-02** | 效能指標 | `.gitignore` 軟合併解析與寫入耗時 $\le 10\text{ms}$，`inspect()` 查詢 $\le 1\text{ms}$。 |
| **NFR-03** | 向下相容性 | 既有未帶 `is_project` 參數的舊調用端自動採 Local 預設，發布行為 100% 相容。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：`core.config` 在執行 `set()` 或 `delete()` 後會自動觸發 `reload()` 熱自愈快取。
- **`[!CAUTION]`**：`.gitignore` 軟合併必須使用精確正則表達式定位 BEGIN / END 標記區塊，嚴禁以整檔覆蓋方式抹除用戶既有 ignore 規則。
