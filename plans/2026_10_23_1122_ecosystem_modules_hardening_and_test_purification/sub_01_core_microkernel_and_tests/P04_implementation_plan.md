# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_core_microkernel_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-10 在 API 規格書中有對應介面與契約
- [x] **邊界防護**：EC-01 ~ EC-07 有具體錯誤處理與降級策略
- [x] **依賴純淨**：符合 NFR-01 (100% Python 標準庫零依賴) 與 NFR-02 (20 檔 100% 通過且零殘留)

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 補充 `list --remote`、`config inspect` 與 `config unset` CLI 說明，更新微內核零依賴純淨承諾。 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-CORE-03]` 關於宣告式群組雙軌 Help 路由與 `contributes check` 專案覆寫剝殼之設計考量。 |
| **微觀註解** | `core/uri.py`, `core/commands/*.py` | Modify | 更新 `format_undefined_uri_hint`、`check_contributes`、`_try_hot_dispatch` 之 Docstring 與型別標註。 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 Stage 2 Global Step 3 `core` 微內核架構純化與測試集 28 檔收斂至 20 檔摘要。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：`dispatcher.py` 步驟 8 移除 `has_fn` 繞過是否會導致合法但動態傳遞的命令被誤殺？  
> [*] **防護解法**：僅在 `cmd_spec and cmd_spec.cmd and not cmd_spec.args` 為真（即明確定義了固定子命令樹且宣告不接受自由位置參數）時觸發未知子命令攔截，完全不影響宣告了 `args` 或非群組節點的常規指令。
>
> [?] **尖銳問題 2**：`core/tests/` 裁撤 8 個檔案後，是否可能遺漏既有測試覆蓋的邊界條件？  
> [*] **防護解法**：遵循「無損整併」原則，所有非死代碼、非跨模組無效 Mock 的有效案例逐一搬遷併入對應的子系統主檔（如 `test_uri.py`、`test_config.py`、`test_distribution_lifecycle.py` 等），併入後執行全量跑測確保總斷言量與覆蓋面實質提升。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 [微內核純化]**：修改 `core/providers.py`（移除 11 個 `get_phase*_cli_guide`）、`core/uri.py`（通用 URI hint）、`core/contributes.py`（移除 `print_global_help` 死代碼）。
2. **TASK-02 [CLI 與派發加固]**：修改 `core/commands/contributes_cmd.py`（支援 `config://` 與單檔剝殼）、`core/commands/dispatcher.py`（`_try_hot_dispatch` 陣列傳遞 + 步驟 8 建議）、`core/installer.py`（`cmd_list(remote=True)`）、`contributes/core.json` 與 `core/scripts/cli.py`（實作 `config_inspect`、`config_unset`、`config_list --local` 與群組 HelpRenderer 轉調）。
3. **TASK-03 [測試集去重與碎片收斂]**：刪除 `test_contributes_help.py`；將 7 個碎片測試檔依映射表無損整併至 `test_config.py`、`test_events_pipeline.py`、`test_uri.py`、`test_engine.py`、`test_distribution_lifecycle.py`、`test_installer.py`、`test_venv_core.py`，並清理舊檔與重複 `yscb.py` 載入邏輯。
4. **TASK-04 [測試虛假改寫、解耦與漏測補盲]**：實質改寫 5 處虛假測驗 (`T-01`)；移除跨模組 `patch`；補齊 `test_config.py` 沙盒 `@require` 與 `tearDown` 清理 (`T-05`)；新增 `contributes check` 負向與專案覆蓋測試、`_try_hot_dispatch` 串流測試、`OptionResolver` 與 `cmd_update` 測試 (`T-06`)。
5. **TASK-DOC [三層文檔與合規檢核]**：更新 `docs/core/README.md`、`docs/core/DESIGN_NOTES.md`，執行 `dev check core`、`dev test core` 與 `plan verify`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]**：確定實作順序為底層純化 $\to$ CLI 加固 $\to$ 測試集整併 $\to$ 補盲驗證 $\to$ 文檔結案。

