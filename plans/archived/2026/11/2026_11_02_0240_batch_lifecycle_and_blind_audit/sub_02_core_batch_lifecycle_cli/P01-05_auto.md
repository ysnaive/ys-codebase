# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：core 模組生命週期 CLI 多模組批次操作與原子事務升級  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0240_batch_lifecycle_and_blind_audit / sub_02_core_batch_lifecycle_cli  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `install <module...>` 多模組批次安裝與單次原子事務 | 支援 CLI 傳入 1~N 個模組規格（如 `install a b@1.0.0 c@build`），或 API 傳入 `Union[str, Sequence[str]]`；執行單次前置快照 (`act_snapshot`)、單次跨進程鎖 (`transaction_lock("install")`)、單次 `_notify_server_release_handles()`、聯合拓撲依賴解析、批次準備 (`act_prepare`) 與註冊 (`act_register`)、單次環境重載 (`act_reload`)、逐一遷移 (`act_migrate`)、廣播 `on_installed` 及單次 Python 虛擬環境依賴同步 (`sync_pip_dependencies`) | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | `update [<module...>]` 多模組指定批次更新 | CLI 支援傳入 0~N 個模組名稱（API 支援 `Union[str, Sequence[str], None]`）；未傳入時更新全部已安裝模組；傳入 1~N 個模組時依序去重並僅檢查與更新指定之已安裝模組，並透過單次批次原子安裝管線執行更新 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | `remove <module...>` 多模組批次移除與逆向依賴聯集豁免 | CLI 支援傳入 1~N 個已安裝模組名稱（API 支援 `Union[str, Sequence[str]]`），依序去重；檢查逆向依賴（`dependents`）時，將「本次一併列入移除批次之其他模組」自阻斷清單中豁免（`dependents = [m for m in all_dependents if m not in target_set]`），允許不加 `--force` 一次移除具上下游依賴的多個模組，並在單次 `act_snapshot` + `transaction_lock("remove")` + `act_reload` + `sync_pip_dependencies` 中完成 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-04** | `contributes/core.json` 與 `scripts/cli.py` 參數對稱升級 | 更新 `ys_codebase/source/core/contributes/core.json` 中 `install`、`update`、`remove` 的位置參數宣告（支援 `nargs: "+"` 或 `nargs: "*"` 多值收集），並於 `scripts/cli.py` 對應解包轉發至 `Installer` | P0 | [P00:DR-01] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `install` 批次中或跨依賴鏈對同一模組出現不相容/衝突之版本約束（如 `install a@1.0.0 a@2.0.0` 或依賴鏈衝突） | 於聯合拓撲解析階段立即偵測衝突並拋出例外/錯誤訊息，中止交易並回滾，確保 All-or-Nothing |
| **EC-02** | `install` 多模組時顯式帶 `@<ver>` 與全域 `--version <ver>` 混用 | 個別帶 `@<ver>` 之規格優先使用其內嵌版本；未帶 `@` 之模組若指定了 `--version` 則套用該 `--version` |
| **EC-03** | `update` 傳入包含未安裝之模組名稱 | 在進入更新前預先驗證所有目標模組皆已安裝；若包含未安裝模組則報錯返回 `False`（CLI 返回非零狀態碼），不執行部分更新 |
| **EC-04** | `remove` 批次中包含 `core` 基座模組或未安裝之模組 | 在執行任何刪除動作前攔截並報錯返回 `False`，拒絕移除 `core` 或未安裝模組，確保零部分破壞 |
| **EC-05** | `remove` 批次模組被「不在本次移除批次中」的其他已安裝模組依賴且未加 `--force` | 精準列出批次外之阻斷依賴模組並拒絕移除返回 `False` |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 向後相容性 | `Installer.cmd_install` / `cmd_update` / `cmd_remove` 與 `AtomicEngine.act_solve_deps` 100% 相容既有單一字串 (`str`) 位置參數呼叫與單元素 `list[str]` 呼叫 |
| **NFR-02** | 原子性與 I/O 收斂 | 單次 `cmd_install` / `cmd_remove` 批次操作最多僅觸發 1 次 `act_snapshot`、1 次 `transaction_lock`、1 次 `act_reload` 與 1 次 `sync_pip_dependencies` |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `core.json` 的 CLI 參數宣告與 `scripts/cli.py` 必須遵守 `yscb-module-dev` 的對稱性規範；`CmdBags` 對 `nargs: "+"` / `nargs: "*"` 的取值型別需與單值/多值相容處理。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
CLI Args (install/update/remove <module...>)
  │
  ▼
ys_codebase/source/core/contributes/core.json (nargs: "+" / "*")
  │
  ▼
ys_codebase/source/core/scripts/cli.py (Normalize str | list[str])
  │
  ▼
Installer.cmd_install / cmd_update / cmd_remove (Union[str, Sequence[str]])
  ├── Pre-validation (installed check, core protection, reverse-deps union exemption)
  ├── Single act_snapshot + Single transaction_lock + Single _notify_server_release_handles
  ├── AtomicEngine.act_solve_deps (Multi-root topological sort & conflict detection)
  ├── Batch act_prepare -> Batch act_register / act_unregister & act_delete
  └── Single act_reload -> Batch act_migrate / Event emit -> Single sync_pip_dependencies
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/contributes/core.json` | Modify | 升級 `install`、`update`、`remove` 指令之 `module` 參數定義支援多值輸入 (`nargs`) |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 升級 `install`、`update`、`remove` 入口函式以接收並正規化多模組參數轉發至 `Installer` |
| `ys_codebase/source/core/core/engine.py` | Modify | 擴充 `AtomicEngine.act_solve_deps` 支援多根節點聯合拓撲解析與版本約束衝突檢測 |
| `ys_codebase/source/core/core/installer.py` | Modify | 升級 `cmd_install`、`cmd_update`、`cmd_remove` 支援 `Union[str, Sequence[str]]` 批次原子交易與逆向依賴聯集豁免 |
| `ys_codebase/source/core/tests/test_installer.py` | Modify | 新增多模組批次 `install`、`update`、`remove`、逆向依賴聯集豁免與異常邊界單元測試 |
| `ys_codebase/source/core/tests/test_core_commands.py` | Modify | 新增 CLI 層多模組參數解析與轉發測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** `Installer.cmd_install`、`cmd_update`、`cmd_remove` 第一個參數維持原參數名（或相容位置呼叫），型別放寬為 `Union[str, Sequence[str]]`（`cmd_update` 為 `Optional[Union[str, Sequence[str]]] = None`），內部統一透過輔助函式正規化為去重保序之 `list[str]`，確保既有程式碼與測試以單一字串呼叫時 100% 無損相容。
- **[P02:DR-02]** `AtomicEngine.act_solve_deps` 支援單一根模組或多個根模組規格序列輸入，於同一個 `visited` / `visiting` 拓撲圖與約束表中聯合解析，若發現同一模組在批次中或跨依賴鏈存在不相容版本約束，立即拋出 `ValueError` / `RuntimeError` 阻斷交易。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
from typing import Optional, Sequence, Union, List, Tuple

class AtomicEngine:
    def act_solve_deps(
        self,
        module_id: Union[str, Sequence[Tuple[str, Optional[str]]]],
        version_constraint: Optional[str] = None,
        force: bool = False,
    ) -> List[Tuple[str, str, dict]]: ...

class Installer:
    def cmd_install(
        self,
        module_id: Union[str, Sequence[str]],
        version_constraint: Optional[str] = None,
        force: bool = False,
    ) -> bool: ...

    def cmd_update(
        self,
        module_id: Optional[Union[str, Sequence[str]]] = None,
        check_only: bool = False,
    ) -> bool: ...

    def cmd_remove(
        self,
        module_id: Union[str, Sequence[str]],
        force: bool = False,
        purge: bool = False,
    ) -> bool: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `act_solve_deps`：當批次內或跨依賴鏈出現版本約束衝突、循環依賴或找不到滿足約束之版本時，拋出例外或返回失敗並由 `Installer` 捕獲觸發快照回滾與返回 `False`。
  - `cmd_install` / `cmd_update` / `cmd_remove`：任一前置校驗失敗（如包含未安裝模組、嘗試移除 `core`、存在批次外逆向依賴且無 `--force`）或準備階段失敗時，確保環境狀態回滾並返回 `False`。
- **階段決策紀錄**：`[P03:DR-01]` 保持參數名稱 `module_id` 不變以相容具名關鍵字參數呼叫 (`cmd_install(module_id="foo")`)，同時支援傳入字串序列 (`cmd_install(["foo", "bar@build"])`)。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-05 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：若使用者執行 `install a@build b@build`，且 `b` 依賴 `a`，聯合拓撲解析會不會重複處理或覆蓋 `@build` 約束？*
  - *答*：在聯合解析時，先收集所有顯式請求之根模組約束作為強約束基準；當依賴鏈再次遇到已在根模組指定 `@build`（或特定版本）之模組時，驗證其相容性並保留顯式請求之目標版本與順序，確保不會重複加入安裝佇列或遺失 `@build` 標記。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 於主計畫收尾階段統一同步 `install`/`update`/`remove` 多模組批次語法說明 |
| **專題手冊** | `docs/core/[topic].md` | N/A | 無專題手冊結構變更 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | N/A | 無新增工程妥協 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `Installer`、`AtomicEngine` 與 `cli.py` 關鍵介面契約 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於主計畫 Phase 7 結案時記錄本版本發布摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `core` 批次生命週期升級範疇與單次原子交易管線設計定案，進入實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：升級 `ys_codebase/source/core/contributes/core.json` 與 `ys_codebase/source/core/scripts/cli.py` 支援 `install`、`update`、`remove` 多模組位置參數解析
- [x] **TASK-02**：升級 `ys_codebase/source/core/core/engine.py` 與 `ys_codebase/source/core/core/installer.py` 實作多模組聯合拓撲解析、單次批次原子安裝/更新/移除與逆向依賴聯集豁免
- [x] **TASK-03**：於 `ys_codebase/source/core/tests/test_installer.py` 與 `test_core_commands.py` 編寫正向批次操作與負向邊界攔截單元測試，並通過 `dev check core` 與 `dev test core -q`
- [x] **TASK-DOC**：同步更新 `core` 源碼檔案之公開 API Docstrings（`docs/core/README.md` 列入跨邊界交接由主代理統籌）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
