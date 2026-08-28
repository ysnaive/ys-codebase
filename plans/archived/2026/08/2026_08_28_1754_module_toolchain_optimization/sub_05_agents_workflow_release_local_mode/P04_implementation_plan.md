# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Agents-Workflow Release 預設 Local 模式、Gitignore 軟合併同步與 Core Config 來源層級探測 (Release Local Mode, Gitignore Sync & Core Config Origin Inspection)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_05)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 API 規格書與架構設計中均有具體承接介面
- [x] **邊界防護**：EC-01 ~ EC-03 具備具體防禦處置（`.gitignore` 容錯、多層衝突去重、分層移除）
- [x] **依賴純淨**：符合 NFR-01~03 指標約束，維持純 Python 標準庫與 `core.config` SDK 邊界

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/core/README.md` | Modify | 增補 `core.config.get_raw()` 與 `core.config.inspect()` API 說明 |
| **維度 1** | `docs/agents-workflow/README.md` | Modify | 增補 `release-target --add / --remove` 預設 Local 模式與 `--proj` 旗標說明 |
| **維度 3** | `docs/agents-workflow/TOPICS/release_targets.md` | Modify | 更新多層 Target 解析與 `.gitignore` 軟合併機制說明 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者手動在 `project://.gitignore` 編輯規則，`ReleasePublisher` 執行軟合併時如何確保不會覆蓋或損壞手動規則？  
> 💡 **防護解法**：`sync_gitignore()` 採用明確的區塊邊界錨點（`# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===` 至 `# === YSCB AGENTS_WORKFLOW IGNORE END ===`），以正則表達式精確替換該區塊；若找不到錨點則在檔案末尾安全追加（並補齊必要換行），絕不全檔覆蓋。

> ❓ **尖銳問題 2**：若某個 Target 在 `config.project.json` 與 `config.local.json` 均被啟用，執行 `release-target --remove <target>`（無 `--proj`）時行為為何？  
> 💡 **防護解法**：預設操作 Local 組態，僅將該 Target 從 `config.local.json` 移除；由於 `config.project.json` 仍存在該 Target，狀態自動由 `[ENABLED (BOTH)]` 轉為 `[ENABLED (PROJECT)]`，發布時仍會保留物化，符合「局部操作不破壞專案共用設定」之原則。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (Core Config 來源層級探測 API 實作)**：
  - [ ] 在 `source/core/core/config.py` 中實作 `ConfigManager.get_raw()` 與 `ConfigManager.inspect()`。
  - [ ] 匯出頂層 Facade 函式 `get_raw` 與 `inspect`。
  - [ ] 在 `source/core/tests/test_config.py` 新增單元測試 (FT-01, FT-02)。
- [ ] **TASK-02 (ReleaseTargetManager 升級與來源標註)**：
  - [ ] 在 `source/agents-workflow/agents_workflow/targets.py` 升級 `add_target()` 與 `remove_target()` 預設 `is_project=False`（寫入 `config.local.json`），支援 `is_project=True`（寫入 `config.project.json`）。
  - [ ] 升級 `list_targets()` 透過 `core.config.get_raw()` 比對 Local 與 Project 組態，標註 `[ENABLED (LOCAL)]`、`[ENABLED (PROJECT)]`、`[ENABLED (BOTH)]`、`[DISABLED]`。
- [ ] **TASK-03 (ReleasePublisher 聯集發布與 .gitignore 軟合併)**：
  - [ ] 在 `source/agents-workflow/agents_workflow/publisher.py` 實作 `sync_gitignore()` 區塊軟合併邏輯。
  - [ ] 在 `release_all()` 發布交易中呼叫 `sync_gitignore()`。
- [ ] **TASK-04 (CLI release-target 指令與排版升級)**：
  - [ ] 在 `source/agents-workflow/scripts/cli.py` 升級 `cmd_release_target`，解析 `--proj` / `--project` 旗標並進行多層彩色排版輸出。
- [ ] **TASK-05 (單元測試與全生態系沙盒回歸)**：
  - [ ] 在 `source/agents-workflow/tests/test_targets.py` 新增/更新測試套件 (FT-03~08, ET-01~02)。
  - [ ] 執行 `python yscb.py dev test --all` 確保 4 大模組 100% Passed。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[sub_05:P04:DR-01] Local 預設與非侵入性多層架構**：確立所有個人開發工具偏好均預設留存於 `config.local.json`，配合 `.gitignore` 軟合併達成團隊協作零污染。
- **[sub_05:P04:DR-02] 微內核組態溯源 API 定稿**：確立 `core.config.get_raw()` 與 `inspect()` 作為全生態系組態診斷標準介面。
