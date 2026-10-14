# 需求規格說明書 (Requirements Specification)

> 功能名稱：2026_10_14_1554_downstream_onboarding_and_ux_guidance  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **根目錄 `README.md` 與 `docs/README.md` 全景翻新** | 1. 補齊 5 大核心模組（`core`, `agents-workflow`, `knowledge-db`, `server`, `dev`）架構圖與職責表。<br/>2. 更新「3.1 基礎環境與宿主綁定」為 `python yscb.py init` 標準單檔自舉流程與 `config set core project_root ./`。<br/>3. 修正 `agents-workflow` 安裝教學為 `init --default` 與純 Skill 體系（`.agents/skills/`）。<br/>4. 修正 `knowledge-db` 安裝教學為 `spaces.source.include`、離線模型 `model download`（或純 BM25 降級）與一鍵 `index`（移除已刪除之 `scan`）。<br/>5. 新增 `server` 模組快速上手與 IDE Agent 常駐指引章節。 | P0 | [P00:DR-02] |
| **FR-02** | **5 大模組隨包 `source/<mod>/README.md` 實戰化升級** | 全面翻新 `ys_codebase/source/{core,dev,server,knowledge-db,agents-workflow}/README.md`（隨模組安裝分發至下游 `.modules/<mod>/README.md`）：<br/>1. 統一新增 **「快速上手 (5-Minute Quickstart)」** 章節。<br/>2. 對齊最新 15 項語意 URI 協議、正確組態設定路徑（`config/<mod>/config.project.json` 與 `config set <mod> ...`）及常見情境 Cookbook。 | P0 | [P00:DR-02] |
| **FR-03** | **`yscb.py init` 完成後之 `[Next Steps]` 互動引導** | 當執行 `python yscb.py init` 完成全新工作區自舉（非 `--fix` 模式）且 `core reload` 成功後，於終端輸出結構化 `[Next Steps]` 引導卡片，提示：<br/>1. 綁定宿主專案根目錄：`python yscb.py config set core project_root ./`<br/>2. 檢查 URI 健康狀態：`python yscb.py uri check`<br/>3. 安裝核心擴充模組：`python yscb.py install agents-workflow`、`knowledge-db`、`server`。 | P0 | [P00:DR-01] |
| **FR-04** | **`core:install` 宣告式模組 `[Next Steps]` Onboarding 引導** | 1. 在 5 大模組 `source/<mod>/manifest.json` 支援選填之 `"onboarding": ["...", ...]` 字串清單（並於 `dev` 之 `Checker._check_manifest` 校驗型別）。<br/>2. 於 `core.installer:Installer.cmd_install` 安裝模組成功後，呼叫 `_print_onboarding_guide(module_name)` 讀取 `manifest.json` 的 `onboarding` 清單，輸出結構化 `[*] Next Steps for '<module>':` 操作步驟與隨包手冊位置（`.modules/<module>/README.md`）。 | P0 | [P00:DR-01] |
| **FR-05** | **未定義語意協議 (`!undefined`) 自癒修復指令提示** | 1. 於 `core.uri.UndefinedURIError` 預設錯誤訊息中，動態注入可直接複製執行的一鍵修復 CLI 指令提示（若 `scheme == "project"` 提示 `python yscb.py config set core project_root ./`；若 `provider == "agents-workflow"` 提示 `python yscb.py agents-workflow init --default`；其餘提示 `python yscb.py config set <provider> <binding> <path>`）。<br/>2. 於 `core/scripts/cli.py:uri_check` 當發現 `UNDEFINED` 協議時，在報告底部列出對應之 `[Quick Fix]` 修復指令清單。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 第三方或舊版模組之 `manifest.json` 未宣告 `onboarding` 欄位，或欄位為空陣列 | `_print_onboarding_guide` 安全靜默略過，不拋出例外，不輸出空白區塊。 |
| **EC-02** | `manifest.json` 中 `onboarding` 欄位型別非 `List[str]`（例如寫成數字或空字串） | `dev` 之 `Checker._check_manifest` 精確攔截並報出 `MANIFEST` 類別之 `FAIL` 錯誤；`Installer._print_onboarding_guide` 執行期具備型別防禦忽略非字串項目。 |
| **EC-03** | 執行 `python yscb.py init --fix` 自癒修復既有環境 | 僅輸出修復完成訊息，不重複列印全新工作區之初次 Onboarding 卡片，避免干擾既有專案。 |
| **EC-04** | 既有單元測試（如 `test_uri.py`, `test_remote_zip_bootstrap.py`, `test_cli.py`）對 `UndefinedURIError` 或 CLI 輸出進行子字串斷言 | `UndefinedURIError` 保留原有全部錯誤前綴文字（`Semantic URI '...' is undefined (!undefined)...`），僅於尾部附加 `Quick fix:` 指引，100% 保持既有測試向後相容。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴與相容性 | 100% Python 標準庫實現，零第三方依賴；全終端輸出採純 ASCII 括弧標籤（`[*]`, `[+]`, `[!]`），杜絕 Windows CP950 編碼崩潰。 |
| **NFR-02** | 測試與合規守門 | 全生態系 5 大模組單元測試 100% 通過，`dev check --all` 0 Warnings / 0 Errors。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 依據 `[DN-06]` 與 `[DN-21]`，`UndefinedURIError` 訊息格式受 `test_uri.py` 驗證，擴充自癒指令時必須保留原訊息主幹不變。
- **`[!NOTE]`** 依據 `[DN-AW-14]`，`agents-workflow` 已全面除役 `workflow` 類型並統一為 `skill`，所有文檔與引導指令一律使用 `init --default` 與 `.agents/skills/`。

