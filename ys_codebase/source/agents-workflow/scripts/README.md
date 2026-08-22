# 專案開發工具腳本庫 (.agents/scripts/)

本目錄存放用於處理定式作業 (Deterministic Tasks) 的專用工具腳本，旨在節省 Agent Context Token、提高執行可預測性並落實安全防護。

---

## 🛠️ 工具腳本列表與介面規範

### 1. `verify_plan.py` — Dev Plan 合規性與 Extension 深度稽核工具 (NEW)

- **用途**：秒級自動驗證 Dev Plan 的 Header 元數據格式、佔位符、以及全量 `extensions/`（常態 always 與語意 on_demand）的落實情況。
- **Agent 執行紀律**：當執行 `/Review` 時，**必須優先呼叫此腳本**完成定式驗收。
- **命令列語法**：
  ```bash
  # 掃描所有進行中計畫
  python .agents/scripts/verify_plan.py

  # 掃描指定計畫
  python .agents/scripts/verify_plan.py 2026_08_16_1600_remove_centralized_auto_telemetry
  ```

---

### 3. `archive_plan.py` — Dev Plan 安全歸檔工具

- **用途**：將已完成的 Dev Plan 目錄安全搬移至 `.agents/dev_plans/history/YYYY/MM/`，並自動清理暫時性 `handoff.md`。
- **Agent 執行紀律**：⚠️ **絕對禁止 Agent 自動執行此腳本**。僅能在開發者明確下達歸檔指令（如：「請歸檔此計畫」）後方可呼叫。
- **命令列語法**：
  ```bash
  python .agents/scripts/archive_plan.py <plan_name> [--force]
  ```

---

### 4. `search_dev_plans.py` — 歷史計畫與 DR 決策檢索工具

- **用途**：精確搜尋 `.agents/dev_plans/` (含進行中與 history 歸檔) 下的 Dev Plan 內容與 Decision Records (DR)。
- **Agent 執行紀律**：當 Agent 需要檢索過去的架構決策或討論歷史時，**必須優先呼叫此腳本**，避免手動 grep 或大量讀取 Markdown 檔浪費 Context。
- **命令列語法**：
  ```bash
  # 全文關鍵字檢索 (附前後文片段)
  python .agents/scripts/search_dev_plans.py --query "Namespace"

  # 專用 DR 決策檢索 (精簡控制台表格輸出)
  python .agents/scripts/search_dev_plans.py --dr --query "camelCase"

  # 結合時間範圍篩選
  python .agents/scripts/search_dev_plans.py --dr --year 2026 --month 08
  ```

---

### 5. `scan_plan_status.py` — 專案進度與狀態掃描工具

- **用途**：快速掃描計畫目錄中所有計畫的進度矩陣 (`Planning` / `Implementing` / `Completed`)。
- **Agent 執行紀律**：當執行 `/Continue` 接續中斷任務時，優先執行此腳本定位目標 Plan。
- **命令列語法**：
  ```bash
  # 僅掃描當前進行中 (Active) 計畫
  python yscb_cli.py agents-workflow scan

  # 掃描包含已歸檔的全量計畫
  python yscb_cli.py agents-workflow scan --all
  ```

---

### 6. `_migration.py` — 模組跨版本遷移腳本 (Lifecycle Hook)

- **用途**：在模組升級覆寫時自動由 `yscb_installer.py` 調用，接收 `<old_version>` 與 `<new_version>` 兩參數，負責遷移本地 `config.json` 或更新相容性路徑。
- **命令列語法**：
  ```bash
  python modules/agents-workflow/scripts/_migration.py <old_version> <new_version>
  ```
