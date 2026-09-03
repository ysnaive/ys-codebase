# 需求規格說明書 (Requirements Specification)

> 功能名稱：modules_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 自動化內部 Git 忽略規範軟合併注入 | 於 `yscb.py` 內建之 `_generate_internal_gitignore(yscb_dir)` 函式中，新增 `/.modules/` 忽略宣告，並引入標記區塊軟合併機制（Soft Merge）。相容 `"yscb://" == "project://"` 拓撲，在調用 `init`、`restore` 或環境自檢時自動以非破壞性方式替換/追加 `yscb://.gitignore` 區塊，達成運行端產物與 Git 追蹤解耦且 100% 保留專案原有忽略規則。 | P0 | [P00:DR-01], [P00:DR-07] |
| **FR-02** | 語意協議路徑與運行端全面更名為 `.modules/` | 將 `module://` 與 `module.root://` 語意 URI 解析實體路徑由 `yscb://modules/` 正式更名為 `yscb://.modules/`。<br/>1. `core.contributes`: 更新 `contributes/core.json` 之 `module` 協議預設值為 `yscb://.modules/`；<br/>2. `core.uri`: 更新 `_BOOTSTRAP_FALLBACK_SCHEMES` 中 `module` 預設值為 `yscb://.modules/`；<br/>3. `yscb.py`: 宿主層所有路徑組裝直接切換為 `.modules`（`init` 建立 `.modules`、`dispatch_module` 與模組清查掃描 `.modules`）；<br/>4. 堅決不包含舊 `modules/` 之平滑相容、搬移或探測邏輯。 | P0 | [P00:DR-05] |
| **FR-03** | 宿主層原生 restore 冷啟動再生指令 | 在 `yscb.py` 宿主層提供原生 `restore` 子命令（`python yscb.py restore`，並提供 `bootstrap` 別名）。讀取 `yscb.config.json` 中的 `installed_modules` 清單，遍歷已登記模組與版本，依序從 `provider`（本地 `./ys_codebase/release`、本地 `build/`、`.mirror/` 或遠端 URL）解壓縮還原至 `yscb_root/.modules/<name>/`，並在完成後調用 `reload` 重聚 contributes。 | P0 | [P00:DR-02] |
| **FR-04** | JIT 模組同步感知與自動自愈守門 | 於 `yscb.py` 的命令調度分發入口（`dispatch_module` 前置）建立極速 JIT 模組感知守門。比對 `yscb.config.json` 的 `installed_modules` 與本機 `.modules/` 現況（目錄是否存在、`manifest.json` 之版本是否一致）。若偵測到缺失或版本不符，即刻自動觸發 JIT 原地還原同步與 reload，達成跨開發端 `git pull` 後零手動介入的自動自愈體驗。 | P0 | [P00:DR-06] |
| **FR-05** | 全專案最高工程規範 (STANDARDS.md) 空間協議更新 | 同步修訂 `docs/_project/STANDARDS.md` 第 1 節「語意空間協議清單」：將 `module.root://` 實體解析路徑更新為 `yscb://.modules/`，`module://` 更新為 `yscb://.modules/{module}/`，且 Git 追蹤政策由 `✅ 受追蹤` 正式變更為 `🚫 忽略`。 | P1 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `yscb.config.json` 缺失或 `installed_modules` 為空時執行 restore | 友善輸出提示「未找到任何已登記之安裝模組」，不拋出未捕獲例外，安全返回 0。 |
| **EC-02** | 某模組 provider 本地路徑或 zip 套件不存在/損毀 | 友好報錯並明確指出缺失之模組名稱與嘗試之路徑，避免未捕獲之崩潰，其他已找到模組仍正常還原。 |
| **EC-03** | 運行端 `.modules/` 已就緒且版本完全吻合 | JIT 嗅探以 $< 2\text{ms}$ 極速判定 Clean 並直接跳過還原流程，直接進入命令調度，零通訊阻塞與延遲。 |
| **EC-04** | 執行 restore 還原時目標模組目錄被暫存鎖占用或殘留舊檔 | 解壓還原時採用安全替換或乾淨清空重建單一模組目錄，避免檔案殘留產生髒狀態，並於完成後調用 `reload`。 |
| **EC-05** | 開發端僅配置純本地 `source/` 開發模組 (@build) | 若 `installed_modules` 登記版本為 `@build` 或包含本地 provider，restore 優先探測 `build/<mod>/<ver>.zip` 或 `build/<mod>` 進行本地快速還原。 |
| **EC-06** | "yscb://" == "project://" 拓撲（yscb_root 為 ./） | 生成/更新 `yscb://.gitignore` 時採用標記區塊軟合併，嚴禁整檔覆寫，精確替換或追加 BEGIN/END 標記區塊，完整保留專案根目錄自訂規則與其他模組之忽略宣告。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 延遲 | 在 Clean 狀態下，`yscb.py` 前置之 JIT 模組同步嗅探耗時 $\le 2\text{ms}$，保證全模組 CLI sub-100ms 執行基準不退化。 |
| **NFR-02** | 零外部依賴 | `yscb.py` 宿主層之 restore 與 JIT Auto-Sync 守門嚴格保持 100% Python 標準庫實作（`os`, `json`, `zipfile`, `urllib`, `shutil`），確保零第三方依賴與開箱即用。 |
| **NFR-03** | 測試覆蓋率 | 全生態系四大模組既有 292/292 單元測試 100% 通過，並為 restore 與 JIT Auto-Sync 提供專屬單元測試覆蓋。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：
  - **`yscb.config.json` 為唯一 SSOT**：任何新增、升級或移除模組的操作均必須同步更新 `yscb.config.json`，禁止將環境狀態散落至非 Git 追蹤檔案。
  - **零平滑遷移負擔**：遵循 `[P00:DR-05]`，核心邏輯不再維護歷史 `modules/` 目錄的向下相容或搬移邏輯，所有邏輯直接且唯一面向 `.modules/`。
