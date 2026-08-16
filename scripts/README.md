# 專案開發工具腳本庫 (.agents/scripts/)

本目錄存放用於處理定式作業 (Deterministic Tasks) 的專用工具腳本，旨在節省 Agent Context Token、提高執行可預測性並落實安全防護。

---

## 🛠️ 工具腳本列表與介面規範

### 1. `archive_plan.py` — Dev Plan 安全歸檔工具

- **用途**：將已完成的 Dev Plan 目錄安全搬移至 `.agents/dev_plans/history/YYYY/MM/`。
- **Agent 執行紀律**：⚠️ **絕對禁止 Agent 自動執行此腳本**。僅能在開發者明確下達歸檔指令（如：「請歸檔此計畫」）後方可呼叫。
- **命令列語法**：
  ```bash
  python .agents/scripts/archive_plan.py <plan_name> [--force]
  ```
- **執行邏輯**：
  1. 解析 `plan_name` 前綴 `YYYY_MM`。
  2. 檢查 `FT_plan.md`、`P07_walkthrough.md` 或 `umbrella_overview.md` 狀態是否為 `Completed`（未完成需加上 `--force`）。
  3. 檢查全域 `CHANGELOG.md` 是否已記載該 Plan 的變更摘要（未記載需加上 `--force`）。
  4. 自動建立 `.agents/dev_plans/history/YYYY/MM/` 並完成搬移。

---

### 2. `search_dev_plans.py` — 歷史計畫與 DR 決策檢索工具

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

### 3. `scan_plan_status.py` — 專案進度與狀態掃描工具

- **用途**：快速掃描 `.agents/dev_plans/` 中所有計畫的進度矩陣 (`Planning` / `Implementing` / `Completed`)。
- **Agent 執行紀律**：當執行 `/DevelopmentSOP_Continue` 接續中斷任務時，優先執行此腳本定位目標 Plan。
- **命令列語法**：
  ```bash
  # 僅掃描當前進行中 (Active) 計畫
  python .agents/scripts/scan_plan_status.py

  # 掃描包含已歸檔的全量計畫
  python .agents/scripts/scan_plan_status.py --all
  ```
