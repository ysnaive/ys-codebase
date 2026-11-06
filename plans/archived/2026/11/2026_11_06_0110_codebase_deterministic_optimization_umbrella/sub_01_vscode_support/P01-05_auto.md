# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：vscode-support 模組業務與測試代碼確定性優化 (vscode-support Deterministic Optimization)
> 建立日期：2026-11-06
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella
> 狀態：Completed
> 模型：Unknown
> 依據 P00：[P00_discuss.md](./P00_discuss.md)
> 模板版本：v1.0

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :---: | :--- | :--- | :---: | :---: |
| **FR-01** | `projector.py` 單趟 `strip_jsonc` 與設定讀取收斂 (`OPT-01~05`) | 移除無效引入與 `_resolve_yscb_root` 轉發殼；`strip_jsonc` 收斂為單趟原地掃描；提取 `_load_settings_jsonc`、`_is_under_yscb_venv` 與 `_set_or_pop_list`。 | P1 | [P00:DR-01] |
| **FR-02** | `schema_compiler.py` 鏡像檢索去重與階段拆解 (`OPT-02, 06, 07`) | 移除 `_rule_str_to_json_schema` 轉發殼；提取 `_is_valid_semver` 並單次傳遞 `latest_zip`；提取 `_compile_type_defs`、`_write_and_track_schema`、`_append_contributed_schema_bindings` 與 `_cleanup_orphan_schemas`。 | P1 | [P00:DR-01] |
| **FR-03** | `cli.py` 與 `hook.core.py` 啟動上下文收斂 (`OPT-01, 08`) | 提取 `_init_cli_context` 與 `_get_workspace_projector` 共用啟動樣板。 | P2 | [P00:DR-01] |
| **FR-04** | `test_vscode_support.py` 六維度測試病灶純化 (`AUD-01~07`) | 消除 broken symlink 隱蔽吞錯與 `on_remove` 虛假 stub；改為精確數量斷言；拆解為 15 個單一職責語意化測試並補齊 PEP 562、CLI 人類可讀模式與非 dict JSON/JSONC 防護測試。 | P1 | [P00:DR-01] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :---: | :--- | :--- |
| **EC-01** | `settings.json` 為非 `dict` 之合法 JSON 或合法 JSONC（如陣列 `[1, 2]`） | `_load_settings_jsonc` 回傳 `(None, False, None)`，安全略過且不誤建 `.bak` 或誤印語法錯誤警告。 |
| **EC-02** | 已安裝模組無 `.mirror/<mod>/*.zip` 歸檔包 | `_sync_all_schemas_impl` 傳入 `latest_zip=""` 避免 `_load_module_config_*` 重複呼叫 `_select_latest_mirror_zip`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :---: | :---: | :--- |
| **NFR-01** | 行為等價性 | 對外 SDK 與 CLI 維持 100% Mode B 向下相容，業務代碼淨減 102 行（-6.1%）。 |
| **NFR-02** | 零工單註解 | 全模組業務與測試代碼達成 0 工單/審計編號殘留。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **[!NOTE] PEP 562 延遲載入測試**：測試 `vscode_support.__getattr__` 時須先暫時彈出 `vscode_support.__dict__` 內已快取之屬性並於 `finally` 還原。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

維持 `SettingsProjector`、`SchemaCompiler` 與 CLI / Lifecycle Hooks 原有架構拓撲，透過內部階段輔助函式消除重複 I/O 與重複狀態機。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/vscode-support/vscode_support/projector.py` | Modify | 單趟 `strip_jsonc`、提取 `_load_settings_jsonc`、`_is_under_yscb_venv`、`_set_or_pop_list` |
| `ys_codebase/source/vscode-support/vscode_support/schema_compiler.py` | Modify | 提取 `_compile_type_defs`、`_write_and_track_schema`、`_append_contributed_schema_bindings`、`_cleanup_orphan_schemas` 與 `latest_zip` 復用 |
| `ys_codebase/source/vscode-support/scripts/cli.py` | Modify | 提取 `_init_cli_context` 並移除未使用 `import os` |
| `ys_codebase/source/vscode-support/scripts/hook.core.py` | Modify | 提取 `_get_workspace_projector` 共用工作區投影器初始化 |
| `ys_codebase/source/vscode-support/tests/test_vscode_support.py` | Modify | 純化並擴充為 15 個單一職責語意化測試案例 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 原業務設計疏失隔離**：`ISS-01 ~ ISS-08` 統一紀錄於 `issue_report.md`，重構過程維持 100% 行為無損。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
class SettingsProjector:
    @staticmethod
    def _load_settings_jsonc(settings_path: str) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str]]: ...
    @staticmethod
    def _set_or_pop_list(settings: Dict[str, Any], key: str, items: List[Any]) -> None: ...
    def _is_under_yscb_venv(self, cand_path: str, proj_root: str, allow_root: bool = False) -> bool: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：維持所有公開 API 與 CLI 返回碼契約 100% 不變。
- **階段決策紀錄**：[P03:DR-01] `_load_module_config_format` 與 `_load_module_config_template` 新增選填預設參數 `latest_zip: Optional[str] = None`。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- **需求對齊**：FR-01 ~ FR-04 與 EC-01 ~ EC-02 皆已完整落實。
- **邊界防護**：經盲眼子代理 B、D、E 三重核驗無誤。
- **依賴純淨**：100% Python 標準庫實作。
- **靈魂拷問與防護解法**：
  - *問：非 dict 之合法 JSONC 是否會誤觸 `.bak` 備份？*
  - *答*：已由子代理 D 修正 `_load_settings_jsonc`，僅於語法解析失敗時才標記 `had_jsonc=True` 觸發 `.bak` 備份。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **模組手冊** | `docs/vscode-support/README.md` | N/A | 內部確定性結構重構，無公開介面異動 |
| **微觀註解** | `vscode-support` 源碼與測試檔 | Modify | 清理所有工單編號並補齊清晰 Docstring |

- **決策定稿**：**[P04:DR-01]** 通過五步盲眼閉環驗證並完成雲端交付。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 Loop 1 Step 1~2 盲眼子代理 A 初審與子代理 B 反向查證，登錄 `ISS-01 ~ ISS-08` 至 `issue_report.md`
- [x] **TASK-02**：完成 Loop 1 Step 3 子代理 C 實作 `OPT-01 ~ OPT-08` 與 `AUD-01 ~ AUD-07`
- [x] **TASK-03**：完成 Loop 1 Step 4 盲眼子代理 D 驗收與 3 項邊界修正，並完成雲端受控 CoW 同步
- [x] **TASK-04**：完成 Loop 1 Step 5 盲眼子代理 E 二次零錨定分析（P0=0, P1=0, P2=0）並觸發熔斷結案

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
