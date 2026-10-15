# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：純淨安裝環境下游反饋 4 項缺陷修復與設定引導校準  
> 建立日期：2026-10-15  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 均在 P03 API 規格書中有對應之常數、函式與方法簽名。
- [x] **邊界防護**：EC-01 ~ EC-04 均有定義具體防禦（如 `--url` 覆寫優先、缺少目標回報用法、軟剝離自訂內容判定與空檔判定）。
- [x] **依賴純淨**：全數使用 Python 3.9+ 原生標準庫（`os`, `re`, `sys`, `urllib`），零新增第三方套件依賴，符合 NFR-01。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **快速入門** | `README.md` | Modify | 校準 3.3 節 `knowledge-db` 空間設定教學為 `config/knowledge-db/contribute.json` |
| **模組手冊** | `ys_codebase/source/knowledge-db/README.md` | Modify | 校準快速上手步驟 1 與自訂空間說明為 `contribute.json` |
| **模組清單** | `ys_codebase/source/knowledge-db/manifest.json` | Modify | 校準 `onboarding` 第一條引導為更新 `contribute.json` |
| **專題指南** | `docs/knowledge-db/contributes_guide.md` | Modify | 校準空間覆蓋合併機制說明為 `config/knowledge-db/contribute.json` |
| **核心決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登錄 `[DN-28]` 宿主自更新 URL 與套件 Provider URL 職責分離決策 |
| **工作流決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登錄 `[DN-AW-16]` 根目錄規範入口檔軟剝離 (Soft-Unmerge) 保護決策 |
| **專案日誌** | `CHANGELOG.md` | Modify | 記錄本修復計畫高階成果（結案階段追加） |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若開發者手動在 `AGENTS.md` 加入公司內部規範，然後執行 `release-target --remove antigravity --proj`，會發生什麼事？  
> [*] **防護解法**：`_soft_unmerge_agents_text` 僅精準移除 `<!-- YSCB_AGENTS_BEGIN --> ... <!-- YSCB_AGENTS_END -->` 標記段落，保留開發者自訂的全部內容與檔案實體，絕不觸發 `os.remove`！

> [?] **尖銳問題 2**：若使用者在本地搭建私有 Provider 鏡像測試，執行 `self-update --url ...`，是否會被 `DEFAULT_SELF_UPDATE_URL` 覆蓋？  
> [*] **防護解法**：`_resolve_self_update_target_url` 嚴格將 `custom_url`（`--url`）排在最高優先順序，直接返回自訂 URL。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01**：重構 `yscb.py` 常數與自更新解算函式（FR-01, EC-01）。
- [x] **TASK-02**：補齊 `agents-workflow/contributes/core.json` 契約並改寫 `scripts/cli.py:release_target`（FR-02, FR-03, EC-02）。
- [x] **TASK-03**：於 `agents-workflow/agents_workflow/publisher.py` 實作 `_soft_unmerge_agents_text` 與陳舊 `agents_md` 檔案軟剝離保護（FR-05, EC-03, EC-04）。
- [x] **TASK-04**：修正 `README.md`、`source/knowledge-db/README.md`、`source/knowledge-db/manifest.json` 與 `docs/knowledge-db/contributes_guide.md`（FR-04）。
- [x] **TASK-05**：新增並執行單元測試（`test_cli_router.py`, `test_cli.py`, `test_release_publisher.py`），驗證 FT-01 ~ FT-06 與全庫回歸 RT-01。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 正式確立方案 C：`yscb.py` 拆分獨立常數 `DEFAULT_PROVIDER_URL` 與 `DEFAULT_SELF_UPDATE_URL`。
- **[P04:DR-02]** `release-target` 兼顧 `--add` / `add` 雙向相容性，`CmdBags` 存取統一對齊 `get_option_value()`。
- **[P04:DR-03]** `AGENTS.md` / `CLAUDE.md` 建立軟剝離防線，杜絕 Target 變更時誤刪使用者檔案。

