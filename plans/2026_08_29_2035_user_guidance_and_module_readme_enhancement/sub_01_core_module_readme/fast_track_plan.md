# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：`sub_01_core_module_readme`  
> 建立日期：2026-08-29  
> 所屬主計畫：`user_guidance_and_module_readme_enhancement`  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  站在**純用戶與模組 Release 消費者視角**（專案由 `python yscb.py install` 下載安裝模組，環境中僅有該模組 Release 產物，無專案內部 `docs/` 知識庫），於模組源碼目錄撰寫 100% 自包含 (Self-Contained) 的 `core` 模組導引手冊 [`source/core/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/README.md)。
  涵蓋：
  1. **模組角色與核心功能**：微核心架構定位、套件生命週期管理、語意空間協議 VFS、2x2 組態矩陣。
  2. **純用戶 CLI 指令大全與範例**：
     - 套件管理：`install`, `update`, `remove`, `list`, `status`, `rollback`, `reload`
     - 組態管理：`config list`, `config get`, `config set`, `config reload`（含 `--local` 本機覆蓋）
     - 語意 URI 虛擬檔案系統：`uri list`, `uri resolve`, `uri to-uri`, `uri check`
  3. **語意空間協議說明**：純用戶如何透過 URI 解耦路徑 (`project://`, `yscb://`, `module://`, `config://`, `cache://`)。
  4. **組態檔配置實務**：`config.project.json` 與 `config.local.json` 的運作機制。
  5. **公開 Python API 速查**：下游開發者直接引用 `core.config`、`core.uri`、`core.semver` 之常用函式範例（微觀規格自包含於 README，不依賴外部文檔）。
- **影響範圍**：
  - 新增：[`source/core/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/README.md)（隨模組發布打包分發給所有下游用戶）
- **Fast Track 4 維度確認**：
  - [x] 修改行數預估 $\le 100$ 行 (文檔型任務)
  - [x] Public API 契約 0 變更
  - [x] 架構自包含、零外部 `docs/` 依賴
  - [x] 既有測試/CLI 可 100% 驗證指令正確性

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：撰寫並交付 100% 自包含的 [`source/core/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/README.md)。
- **測試案例**：
  - `FT-01`：驗證文檔內所有示範之 `python yscb.py` CLI 指令均能在真實環境中無誤解析與執行。
  - `FT-02`：驗證 `source/core/README.md` 完全無損自包含，無指向專案內部 `docs/` 的外部斷鏈。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - 已於 `source/core/README.md` 產出完整自包含說明文檔，包含架構 Mermaid 圖、語意 URI 表格、2x2 組態矩陣、全量 CLI 指令範例、Python SDK 常用範例及 3 大 Cookbook 情境。
- **實機測試日誌**：
  - `dev test core`：59/59 測試全數通過（3 契約測試 + 56 自訂單元測試，耗時 5.51s）。
  - CLI 指令驗證（`list`, `status`, `uri check`, `uri list`, `uri resolve`, `config list`）：100% 成功執行無報錯。
  - `dev check core`：合規檢查 100% Passed。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_08_29_2035_user_guidance_and_module_readme_enhancement/sub_01_core_module_readme` 驗證 100% Passed。
- **結案狀態**：`Completed`
