# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_core_microkernel_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 微內核跨模組耦合純化 (`C-01`) | 自 `core/providers.py` 移除專屬 `agents-workflow` 階段的 11 個 `get_phase*_cli_guide` 函式；自 `core/uri.py:format_undefined_uri_hint` 移除 `agents-workflow` 硬編碼分支並統一以通用提示格式輸出；純 `core` 環境單元測試不依賴外部模組。 | P0 | [P00:DR-01] |
| **FR-02** | 專案級 `contribute.json` 驗證與剝殼 (`C-02`) | `core/commands/contributes_cmd.py:check_contributes()` 單檔模式遇到 `contribute.json` 時自動取父目錄名作為 `target_mod`，並支援外層包含 `<target_mod>` 物件時自動剝殼；全量與單模組模式自動檢查 `config://<target>/contribute.json`。 | P0 | [P00:DR-02] |
| **FR-03** | 多層子指令熱派發參數修復 (`C-03`) | `core/commands/dispatcher.py:_try_hot_dispatch` 接收 `cmd_path: List[str]`，發送之 HTTP Payload 中 `"args"` 完整保留子命令陣列 `list(cmd_path) + list(args)`，常駐 Server 正確路由。 | P0 | [P00:DR-01] |
| **FR-04** | 實作 `list --remote` 套件清冊查詢 (`C-04`) | `core/installer.py:cmd_list(remote=True, provider=...)` 探測本地或遠端 Provider 之套件索引，正確列出可用套件、最新版本與本地安裝狀態標籤（`Installed (vX.Y.Z)` vs. `Available`）。 | P1 | [P00:DR-01] |
| **FR-05** | 補齊 `config list --local`、`inspect` 與 `unset` (`C-05`) | 於 `core/scripts/cli.py` 打通 `config list --local` 過濾本機覆蓋項；於 `contributes/core.json` 與 `core/scripts/cli.py` 新增並實作 `config_inspect` 與 `config_unset` 頂層葉節點函式。 | P0 | [P00:DR-03] |
| **FR-06** | 宣告式群組節點 Help 渲染與未知子命令攔截 (`C-06`) | `dispatcher.py` 步驟 8 針對 `cmd_spec.cmd and not cmd_spec.args` 節點移除 `has_fn` 繞過，未知子命令強制呼叫 `_suggest_command` 報錯回傳 1；步驟 7 保留跨模組預設行為，並更新 `core/scripts/cli.py` 四大群組函式無參數 fallback 調用 `HelpRenderer`。 | P0 | [P00:DR-01] |
| **FR-07** | 測試集 28 $\to$ 20 檔子系統 1:1 對齊收斂 (`T-02`, `T-03`) | 移除 `core/contributes.py:print_global_help` 死代碼與 `test_contributes_help.py`；按映射表裁撤 8 個歷史碎片測試檔並無損整併入對應主測試檔，維持 20 個高內聚測試檔。 | P0 | [P00:DR-04] |
| **FR-08** | 5 處虛假測驗實質化改寫 (`T-01`) | 實質改寫 `sync_pip_dependencies` 呼叫斷言、非 Zip 亂碼與損毀防護、`act_migrate` 遷移階梯順序追蹤及 `cmd_status` 雙分支診斷，消除無意義放行。 | P0 | [P00:DR-04] |
| **FR-09** | 測試跨模組解耦、`yscb.py` 載入收斂與沙盒零殘留 (`T-04`, `T-05`) | 移除跨模組 `patch` 與外部目錄讀取；收斂 `_load_yscb_script()`；為 `test_config.py` 補齊 `@require(ENV | ISOLATED_SANDBOX)` 與 `tearDown`，對 `config://` 寫入 100% 包入 `try...finally`。 | P0 | [P00:DR-04] |
| **FR-10** | 4 大高風險漏測路徑補盲 (`T-06`) | 補齊 `contributes check` 負向與專案級覆寫測試、`_try_hot_dispatch` 串流與參數測試、`OptionResolver` `--` 與布林解析測試，以及 `cmd_update` 升級與 Major Lock 測試。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `contribute.json` 頂層未包裝 `<target_mod>` 鍵直接為設定字典 | `ContributesValidator` 能容忍未剝殼或已剝殼型態，不拋出 KeyError，若格式非法回傳非 0 且輸出 Schema 錯誤。 |
| **EC-02** | 執行 `contributes check` 指定不存在之路徑或模組 | 輸出明確錯誤提示並回傳 Exit Code 1，不發生 Unhandled Exception。 |
| **EC-03** | `_try_hot_dispatch` 常駐 Server 連線超時或連線失敗 | 自動安全回退為本地直接派發執行，印出除錯日誌不中斷使用者指令。 |
| **EC-04** | `list --remote` 指定不存在的 Provider 或遠端無 `index.json` | 輸出錯誤提示並優雅回傳 1，不崩潰。 |
| **EC-05** | `config unset` 指定不存在的 key 或 module | 輸出未找到提示並回傳 1，若成功刪除則輸出確認並回傳 0。 |
| **EC-06** | `config inspect` 查詢未設定之鍵值 | 輸出 `source: none` 與 `effective: None`，回傳 0（或依 `--json` 格式化）。 |
| **EC-07** | 群組節點輸入未知子指令（如 `yscb uri checkk`） | 輸出 `Unknown command 'uri checkk'. Did you mean 'uri check'?` 並回傳 1。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零相依 (Zero Dependencies) | `core` 模組維持 100% Python 標準庫零第三方依賴。 |
| **NFR-02** | 測試與品質 (Test Quality) | `python yscb.py dev test core` 20 個測試檔全部通過（100% Passed），測試後工作區零殘留（`git status` 無新增未追蹤檔案）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：`agents-workflow plan`、`roadmap`、`todo` 在未帶子命令時具備預設動作（如 `plan_status`、`list`），`dispatcher.py` 步驟 7 必須保留 `if not has_fn:` 分支，嚴禁一刀切強制覆蓋所有模組的預設行為。
- **`[!CAUTION]`**：測試清理必須採用 `try...finally` 或 `tearDown`，避免斷言中途失敗導致 `config://` 或 `module://` 留下幽靈目錄。

