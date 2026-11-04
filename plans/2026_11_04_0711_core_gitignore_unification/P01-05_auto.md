# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：`core.gitignore` 統一忽略規則收斂引擎與跨模組遷移 (`core_gitignore_unification`)  
> 建立日期：2026-11-04  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core.gitignore` 單一託管引擎與語意 URI 轉換 | 建立 `core/gitignore.py`（並匯出至 `core/__init__.py`），統一維護根目錄單一 `project://.gitignore`。支援將語意 URI（如 `yscb://.venv/`、`project://.vscode/schemas/`）自動解析並轉換為相對於 `project://` 之標準 `/` 錨定路徑（子目錄拓撲下 `yscb://.venv/` 轉為 `/ys_codebase/.venv/`；同根拓撲下轉為 `/.venv/`）；一般 Glob 規則（如 `*.local.json`、`__pycache__/`）維持原貌。 | P0 | [P00:DR-01] |
| **FR-02** | `# [<module>]` 模組分組註解與單一託管區塊格式 | 託管區塊統一使用 `# === YSCB MANAGED GITIGNORE BEGIN ===` 與 `# === YSCB MANAGED GITIGNORE END ===` 包裹；區塊內部強制依模組來源輸出 `# [<module>]` 子標頭（排序：`core` 置頂，其餘模組按字母序，`project` 置底），各分組內規則去重並按字典序排列。 | P0 | [P00:DR-02] |
| **FR-03** | 舊版區塊無縫遷移與廢棄子目錄 `.gitignore` 清理 | 首次或日常同步 `project://.gitignore` 時，自動識別並移除舊版 `# === YSCB INTERNAL IGNORE BEGIN ===` ~ `END`、`# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===` ~ `END` 及 `# YS-Codebase Autonomous Internal Ignore Rules` 遺留自動生成行（完整保留使用者自訂行如 `ys_codebase/release/**/*.zip`、`!**/configurable/*.local.json`）；同時若 `yscb:// != project://` 且 `yscb://.gitignore` 僅含舊版 YSCB 託管規則，自動物理刪除 `yscb://.gitignore` 與 `project://.vscode/schemas/.gitignore`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-04** | 宣告式 `contributes` (`gitignore`) 與強制傳參之動態 SDK | 於 `core/contributes/_format.json` 新增 `"gitignore"` 擴充點（`list[str]! | extend`），利用 `contributes` 之 `__providers__` 自動歸屬至對應 `# [<module>]`；於 `core.gitignore` 提供 `register_dynamic(module: str, patterns: Iterable[str], sync_now: bool = True)` 與 `clear_dynamic(module: str, sync_now: bool = True)`（持久化於 `cache://core/gitignore_dynamic.json`），強制校驗 `module` 為非空字串。 | P0 | [P00:DR-02], [P00:DR-04] |
| **FR-05** | 跨模組全面遷移（`core`、`agents-workflow`、`vscode-support`）與卸載自癒 | ① `core` 於 `contributes/core.json` 宣告 `yscb://` 基礎忽略規則，並將 `installer.py` / `pip_manager.py` / `engine.py` 改為委派 `core.gitignore.sync()`；② `agents-workflow` 將 `ReleasePublisher.sync_gitignore` 改為計算動態忽略清單後呼叫 `core.gitignore.register_dynamic("agents-workflow", ...)`；③ `vscode-support` 於 `contributes/core.json` 宣告 `project://.vscode/schemas/`，並移除 `schema_compiler.py` 寫入 `.vscode/schemas/.gitignore` 之邏輯；④ `engine.act_delete(mod)` 與 `act_reload` 自動清理已移除模組之動態規則並重跑 `gitignore.sync()`。 | P0 | [P00:DR-03] |
| **FR-06** | `yscb.py gitignore <status\|sync>` CLI 與 `on_gitignore_synced` 事件 | 於 `core/contributes/core.json` 與 `core/scripts/cli.py` 註冊 `gitignore` 子命令群（`status [--json]` 檢視各模組靜態/動態規則與同步狀態、`sync [--json]` 手動強制收斂同步）及 `on_gitignore_synced` 事件。 | P1 | [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `yscb://` 與 `project://` 同根拓撲 (`yscb:// == project://`) | `yscb://.venv/` 相對於 `project://` 解析時 `relpath` 為 `.venv`，自動正規化為 `/.venv/`，絕不產生 `/.//` 或 `./.venv/` 畸形路徑；且同根時絕不誤刪 `project://.gitignore`。 |
| **EC-02** | SDK `register_dynamic` / `clear_dynamic` 傳入空白或非字串 `module` | 立即拋出 `ValueError("module name must be a non-empty string")`，防止產生匿名 `# []` 分組污染託管區塊。 |
| **EC-03** | `project://.gitignore` 尚不存在或無結尾換行 | 若不存在則原子建立新檔；若已存在且尾端無 `\n`，軟合併時自動補齊換行分隔，並保留託管區塊前後之使用者手寫內容。 |
| **EC-04** | Zero-Touch 冪等性與寫入原子性 | 當重算後之 `project://.gitignore` 內容與磁碟現有內容完全一致時，`sync()` 不觸發磁碟寫入（保持 `mtime` 不變並回傳 `updated=False`）；有變更時透過 `vfs.write_text(..., atomic=True)` 原子替換。 |
| **EC-05** | `yscb://.gitignore` 含有使用者自訂非託管規則 | 清理子目錄 `yscb://.gitignore` 時，先剝除 `# === YSCB INTERNAL IGNORE BEGIN ===` 區塊；若剝除後仍有非空之使用者自訂規則行，則僅更新移除託管區塊而保留該檔案，絕不盲目刪除使用者手寫規則。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴 | 100% 使用 Python 標準庫與 `core` 既有 `uri` / `vfs` / `contributes`，不呼叫外部 `git` 子進程，單次 `gitignore sync` 耗時 `< 20ms`。 |
| **NFR-02** | 向下相容性 | 保留 `installer.generate_internal_gitignore`、`pip_manager.ensure_yscb_gitignore` 與 `ReleasePublisher.sync_gitignore` 方法簽名作為輕量委派層，確保既有單元測試與外部呼叫零破壞。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `core.contributes` 在執行 `_deep_merge` 時，對 `list` 欄位會注入平行的 `__providers_<key>__` 或由各模組獨立檔案讀取來源；在 `core.gitignore` 收集靜態規則時，可直接遍歷已安裝模組之 `contributes/core.json`（及 `config://core/contribute.json`）或透過 `contributes` 來源映射精確歸屬每個 pattern 的 `# [<module>]` 群組。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Static Contributes]                           [Dynamic SDK Registry]
  ├── core/contributes/core.json                 ├── agents-workflow (ReleasePublisher)
  ├── vscode-support/contributes/core.json       └── future modules (e.g. gdrive)
  └── config://core/contribute.json                    │
            │                                          ▼
            │                               cache://core/gitignore_dynamic.json
            └──────────────────┬───────────────────────┘
                               ▼
                     ┌───────────────────┐
                     │  core.gitignore   │
                     │  - URI Resolution │
                     │  - # [mod] Group  │
                     │  - Legacy Cleanup │
                     └─────────┬─────────┘
                               ▼
              project://.gitignore (Single Root SSOT)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/gitignore.py` | New | 實作 `core.gitignore` 統一忽略規則收斂引擎、語意 URI 轉換、`# [<module>]` 分組合成、舊版區塊遷移、子目錄 `.gitignore` 清理與動態 SDK |
| `ys_codebase/source/core/core/__init__.py` | Modify | 匯出 `gitignore` 子模組 |
| `ys_codebase/source/core/contributes/_format.json` | Modify | 新增 `"gitignore"` 擴充點 Schema 定義 (`list[str]! \| extend`) |
| `ys_codebase/source/core/contributes/core.json` | Modify | 註冊 `core` 預設 `"gitignore"` 自貢獻規則、`gitignore <status\|sync>` CLI 指令與 `on_gitignore_synced` 事件 |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 新增 `gitignore` / `gitignore_status` / `gitignore_sync` CLI 路由處理器（支援 `status` 與 `sync` 及 `--json`） |
| `ys_codebase/source/core/core/installer.py` | Modify | 將 `generate_internal_gitignore` 委派至 `core.gitignore.sync()`（並同步承接 `pip_manager.ensure_yscb_gitignore`） |
| `ys_codebase/source/core/core/engine.py` | Modify | 於 `act_reload` Stage 4 與 `act_delete` 連動 `core.gitignore.clear_dynamic` / `sync` |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 重構 `ReleasePublisher.sync_gitignore` 委派 `core.gitignore.register_dynamic("agents-workflow", ...)` |
| `ys_codebase/source/vscode-support/contributes/core.json` | Modify | 新增 `"gitignore": ["project://.vscode/schemas/"]` 宣告 |
| `ys_codebase/source/vscode-support/vscode_support/schema_compiler.py` | Modify | 移除寫入 `.vscode/schemas/.gitignore` 邏輯，並於存在舊檔時自動清理 |
| `ys_codebase/source/core/tests/test_gitignore.py` | New | 測試 `core.gitignore` 靜態/動態合併、語意 URI 轉換、同根/子目錄拓撲、舊區塊遷移、SDK 強制傳參與 CLI 行為 |
| `ys_codebase/source/vscode-support/tests/test_vscode_support.py` | Modify | 對齊 `vscode-support` 改由 `contributes/core.json` 宣告忽略規則與清理 `.vscode/schemas/.gitignore` 之驗證 |
| `docs/core/README.md` | Modify | 補充 `core.gitignore` 與 `yscb gitignore` 指令說明 |
| `docs/core/DESIGN_NOTES.md` | Modify | 新增設計筆記 `[DN-17]` 說明根目錄單一 `.gitignore` 收斂與 `# [module]` 分組架構 |
| `docs/vscode-support/README.md` | Modify | 更新 `.vscode/schemas/` 由 `core.gitignore` 統一忽略之說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 靜態規則依模組精確歸屬策略**：
  - 為確保每個模組透過 `contributes/core.json` 貢獻之規則能精確歸入 `# [<module>]` 子標頭，Engine 直接掃描 `module://*/contributes/core.json`（及開發態 fallback）與 `config://core/contribute.json`（歸入 `# [project]`）收集各來源之 `"gitignore"` 列表，再合併 `cache://core/gitignore_dynamic.json` 中各模組註冊之動態規則，實現 100% 確定性的模組分組。
- **[P02:DR-02] 語意 URI 與目錄尾斜線正規化**：
  - 若規則包含 `://`（如 `yscb://.venv/` 或 `project://.vscode/schemas/`），透過 `uri.resolve()` 解析實體路徑並計算相對於 `project://` 之相對路徑；若原規則以 `/` 結尾則保留尾端 `/`，並統一加上前導 `/` 錨定於 `project://` 根目錄（如 `/ys_codebase/.venv/`）。若解析結果位於 `project://` 外部（`../`），則忽略該無效路徑以避免污染 `.gitignore`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/gitignore.py
from typing import Any, Dict, Iterable, List, Optional

GITIGNORE_BEGIN_MARKER = "# === YSCB MANAGED GITIGNORE BEGIN ==="
GITIGNORE_END_MARKER = "# === YSCB MANAGED GITIGNORE END ==="
DYNAMIC_CACHE_URI = "cache://core/gitignore_dynamic.json"

def normalize_pattern(
    raw_pattern: str,
    proj_root: str,
    yscb_root: Optional[str] = None,
) -> Optional[str]: ...

def collect_grouped_patterns(
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, List[str]]: ...

def register_dynamic(
    module: str,
    patterns: Iterable[str],
    *,
    sync_now: bool = True,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, Any]: ...

def clear_dynamic(
    module: str,
    *,
    sync_now: bool = True,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, Any]: ...

def sync(
    *,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
    emit_event: bool = True,
) -> Dict[str, Any]: ...

def status(
    *,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `register_dynamic` 與 `clear_dynamic`：當 `not isinstance(module, str) or not module.strip()` 時，強制拋出 `ValueError("module name must be a non-empty string")`。
  - `sync`：當磁碟寫入失敗時捕獲 `OSError` 並記錄於回傳字典 `{"updated": False, "created": False, "error": str(e), ...}`，不中斷宿主啟動流程。
- **階段決策紀錄**：`[P03:DR-01]` `sync()` 回傳結構相容既有 `ReleasePublisher.sync_gitignore` 之 `{"updated": bool, "created": bool, "patterns": List[str], "groups": Dict[str, List[str]], "target_path": str}`。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-06 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-05 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束（純標準庫 + `core` 內部模組）
- **靈魂拷問與防護解法**：
  - *問：當測試案例（如 `test_release_local_mode.py`）傳入自訂的臨時 `proj_root` 呼叫 `publisher.sync_gitignore(proj_root=tmp_dir)` 時，是否會誤改真實工作區的 `cache://core/gitignore_dynamic.json` 或真實 `.gitignore`？*
  - *答*：於 `register_dynamic` / `sync` 支援顯式傳入 `proj_root`；當呼叫端顯式傳入非預設 `proj_root`（如單元測試沙盒目錄）時，動態規則支援記憶體直通覆蓋或儲存於對應沙盒，不會污染宿主全域快取。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md`、`docs/vscode-support/README.md` | Modify | 補充 `core.gitignore` 機制與 `yscb gitignore` CLI 用法 |
| **專題手冊** | `docs/core/API_REFERENCE.md` | Modify | 新增 `core.gitignore` 公開 SDK 介面簽名與例外契約說明 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記根目錄單一 `.gitignore` 託管與 `# [module]` 分組設計筆記 `[DN-17]` |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新關鍵介面契約與模組 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本版本發布摘要（於 P07 執行） |

- **決策定稿**：**[P04:DR-01]** 確認採用單一根目錄 `project://.gitignore` 與 `# [<module>]` 分組架構推進實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：於 `core` 實作 `core/gitignore.py`、`contributes/_format.json`、`contributes/core.json`、`scripts/cli.py` 與 `installer.py` / `engine.py` 整合
- [x] **TASK-02**：重構 `agents-workflow` (`publisher.py`) 與 `vscode-support` (`contributes/core.json`、`schema_compiler.py`) 全面收斂至 `core.gitignore`
- [x] **TASK-03**：編寫 `core/tests/test_gitignore.py` 並更新 `vscode-support` 測試，執行全模組 `dev check`、`dev test` 與 `@build` 熱部署驗證
- [x] **TASK-DOC**：同步更新 `docs/core/` 與 `docs/vscode-support/` 文檔與微觀代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

