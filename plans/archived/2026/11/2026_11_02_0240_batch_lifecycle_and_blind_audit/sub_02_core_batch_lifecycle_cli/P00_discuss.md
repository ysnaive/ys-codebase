# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：core 模組生命週期 CLI 多模組批次操作與原子事務升級  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0240_batch_lifecycle_and_blind_audit / sub_02_core_batch_lifecycle_cli  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：對 `core` 中模組生命週期管理系列 CLI 進行升級，支援單次指令批次操作多個模組（`TODO-16`）；`rollback` 維持單一 `snapshot` 參數。
- **核心目標**：升級 `install`、`update`、`remove` 三大模組生命週期 CLI 指令與 `Installer` / `AtomicEngine` 內部管線，支援在單次命令列調用中傳入多個模組參數（如 `install a b@1.0.0 c@build`、`update a b`、`remove a b`），並將前置快照、跨進程鎖、常駐 Server 句柄釋放、依賴拓撲解析與下載準備、模組註冊／註銷、環境重載 (`act_reload`)、Python 虛擬環境依賴同步 (`sync_pip_dependencies`) 與事件廣播合併為**單次批次原子交易 (All-or-Nothing Batch Transaction)**。
- **既有組件復用與查重 (Reuse Discovery)**：直接擴充 `Installer.cmd_install` / `cmd_update` / `cmd_remove` 與 `AtomicEngine.act_solve_deps`，向後 100% 相容既有單一模組 `str` 呼叫簽名（支援傳入 `Union[str, Sequence[str]]` 或保留單一參數位置相容）。
- **邊界排除 (Explicitly Excluded)**：`rollback` 為環境級快照回滾（`snapshot://snap_xxx`），維持單一 `snapshot` 參數不變；`list`、`status`、`reload`、`restore` 維持既有語意不變。
- **架構影響範圍**：`ys_codebase/source/core/contributes/core.json`、`ys_codebase/source/core/scripts/cli.py`、`ys_codebase/source/core/core/installer.py`、`ys_codebase/source/core/core/engine.py`、`ys_codebase/source/core/tests/`、`docs/core/README.md`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] CLI 多模組參數解析與版本約束規則**：
  - `install <module...>`：支援傳入 1~N 個模組規格字串（每個規格可獨立帶 `@<version>` 或 `@build`，如 `install dev@build agents-workflow@build`）；若未帶 `@` 且指定了 `--version <ver>`，當僅傳入單一模組時套用該 `--version`，當傳入多個無 `@` 模組且同時帶單一 `--version` 時套用至未顯式帶 `@` 之模組。
  - `update [<module...>]`：未傳入任何模組參數時更新全部已安裝模組；傳入 1~N 個模組名稱時，依序去重並僅檢查與更新指定之已安裝模組（若包含未安裝模組則報錯返回非零狀態碼，不執行部分更新）。
  - `remove <module...>`：支援傳入 1~N 個已安裝模組名稱（去重）；拒絕包含 `core` 或未安裝模組。
- **[P00:DR-02] 批次依賴解析、逆向依賴聯集豁免與單次原子事務 (Batch Atomic Transaction)**：
  - **批次安裝 (`cmd_install`)**：單次 `act_snapshot` + 單次 `transaction_lock("install")` + 單次 `_notify_server_release_handles()`；對所有請求模組執行聯合拓撲依賴解析（若同一模組在批次中或跨依賴鏈出現衝突版本約束則立即拋出錯誤中止回滾），統一執行 `act_prepare`、批次 `act_register`、單次 `act_reload`、逐一執行需要升版遷移之 `act_migrate`、廣播 `on_installed`、最後執行 **1 次** `sync_pip_dependencies()`。
  - **批次移除 (`cmd_remove`)**：在檢查逆向依賴（`dependents`）時，將「本次一併列入移除批次之其他模組」自阻斷清單中豁免（即 `dependents = [m for m in all_dependents if m not in target_set]`），允許開發者不加 `--force` 一次乾淨移除具上下游關係的多個模組；單次 `act_snapshot` + 單次 `transaction_lock("remove")` + 批次 `act_unregister` & `act_delete` + 單次 `act_reload` & `sync_pip_dependencies()`。

---

## 3. 開放議題與確認紀錄

- [x] 已與開發者確認 `rollback` 維持單一 `snapshot` 參數，`install` / `update` / `remove` 升級為多模組批次原子交易。

