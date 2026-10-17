# 需求規格說明書 (Requirements Specification)

> 功能名稱：純淨安裝環境下游反饋 4 項缺陷修復與設定引導校準  
> 建立日期：2026-10-15  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `yscb.py` 宿主與套件 URL 職責分離 | 於 `yscb.py` 定義正交常數 `DEFAULT_PROVIDER_URL = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release"` 與 `DEFAULT_SELF_UPDATE_URL = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/yscb.py"`。`init` 使用 `DEFAULT_PROVIDER_URL`；`self-update` 預設直接使用 `DEFAULT_SELF_UPDATE_URL`，廢除 `/release` 字串推導並支援 `--url` 覆寫。 | P0 | [P00:DR-01] |
| **FR-02** | `release-target` CLI 雙向語法相容 | 修正 `agents-workflow/scripts/cli.py:release_target`，使選項語法（`--add <t> [--proj]`、`--remove <t> [--proj]`、`--list`）與位置子命令語法（`add <t> [--proj]`、`remove <t> [--proj]`、`list`）100% 互通。改用 `bags.get_option_value()` 提取目標名稱，徹底修復 `bags.args` 為空時被誤判為 `list` 之缺陷。 | P0 | [P00:DR-03] |
| **FR-03** | `release-target` 契約宣告補齊 | 於 `agents-workflow/contributes/core.json` 補齊 `release-target` 的 `--proj`（`alias: ["project"]`）選項宣告與子參數規格，使其符合 `core.commands` 剛性 Schema 校驗。 | P0 | [P00:DR-03] |
| **FR-04** | `knowledge-db` 空間設定指引校準 | 維持 `SpaceManager` 僅讀取 `contribute.json` 之架構設計（SSOT），全面修正根目錄 `README.md`、`source/knowledge-db/README.md`、`source/knowledge-db/manifest.json` (`onboarding`) 與 `docs/knowledge-db/contributes_guide.md`，指示專案自訂空間設定於 `config/knowledge-db/contribute.json`。 | P0 | [P00:DR-02] |
| **FR-05** | `AGENTS.md` 非破壞性軟剝離保護 | 於 `ReleasePublisher` 實作 `_cleanup_stale_file` 軟剝離安全機制。當發布清理舊檔案時，若檔案為 `agents_md` 且內含 `YSCB_AGENTS_BEGIN` 標記，僅剔除 YSCB 管理區塊與預設空殼段落；若仍有使用者自訂內容則原地保留該檔，僅當剝離後為全空白時才物理移除檔案。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `self-update` 指定自訂 `--url` | 優先使用 `--url` 指定之絕對路徑或 URL，不回退至 `DEFAULT_SELF_UPDATE_URL`。 |
| **EC-02** | `release-target` 缺少目標名稱 | 當執行 `release-target --add` 或 `add` 未提供目標時，輸出清楚 Usage 指引並返回狀態碼 1，不拋出非預期例外。 |
| **EC-03** | `AGENTS.md` 退出 Target 且無 YSCB 標記 | 若過期檔案清單包含 `AGENTS.md` 但該檔無 `YSCB_AGENTS_BEGIN` 標記（代表完全為使用者自建檔案），嚴格禁止刪除，安全略過並記錄 warning。 |
| **EC-04** | `AGENTS.md` 剝離後全為空白字符 | 若檔案原先 100% 由 YSCB 生成且使用者未添加任何自訂文字，軟剝離後檔案安全物理刪除，不留孤立空檔。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 核心相容性 | 100% Python 標準庫，零新增外部第三方相依。 |
| **NFR-02** | 測試與品質 | 全生態系現有測試 100% 通過（`Pass: 558, Fail: 0`），新增單元測試覆蓋率 100% 守門。 |
| **NFR-03** | 冪等性 | `release-target` 多次重複切換或發布，`AGENTS.md` 自訂內容無損保留。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：`ReleasePublisher` 在發布前會計算來源特徵指紋（Stage 0），修改 `publisher.py` 或 `manifest.json` 後需確保指紋連動更新並覆蓋測試。
- **`[!CAUTION]`**：切換 Target 時，`published_files` 記錄於 `storage://agents-workflow/release_manifest.json`，清理陳舊檔案前必須先比對檔案類型與標記，嚴禁無差別 `os.remove()`。

