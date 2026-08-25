# Phase 1: 需求規格說明書 (Requirements Spec) - agents-workflow 配置治理與一鍵初始化

> 計畫名稱：`sub_04_agents_workflow_injection_config_and_init_default`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據語意需求：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 當前狀態：`Confirmed` (Phase 1 規格審查確認完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格說明 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: |
| **FR-01** | **4 大 Workflow URI 協議註冊** | `manifest.json` 在 `contributes.core.uri` 中宣告 `workflow.plans`, `workflow.archived`, `workflow.ext`, `workflow.docs`，對應至 `config://agents-workflow/config.project.json` 之 `paths.*` 鍵值。 | `[P00:DR-01]` |
| **FR-02** | **組態模板與 `!undefined` 剛性預設** | 提供 `config.project.json` 模板，`paths` 內 4 大鍵值預設剛性為 `"!undefined"`，並宣告 `ide: []`, `enable_agents_md: true`, `enable_project_changelog: true` 3 大保留欄位。 | `[P00:DR-01]`, `[P00:DR-02]` |
| **FR-03** | **`--init-default` 一鍵初始化指令** | 提供 `python yscb.py agents-workflow --init-default` 指令，攜帶預設推薦路徑：`plans="project://.agent_workflow/plans"`, `archived="project://.agent_workflow/plans/archived"`, `ext="project://.agent_workflow/extensions"`, `docs="project://docs"`。 | `[P00:DR-03]` |
| **FR-04** | **實體路徑探測與已存在提醒** | 執行 `--init-default` 時實體探測目標目錄是否已存在，若已存在則輸出提醒訊息：`[提示] 目錄 <path> 已存在，確認要自動綁定在該路徑嗎?`。 | `[P00:DR-03]` |
| **FR-05** | **互動確認與目錄自動建立** | 依次條列即將綁定與建立之目錄清單，提示 `將建立以下資料夾 [-y / -n]`。使用者確認後自動調用 `os.makedirs` 建立缺失目錄。 | `[P00:DR-03]` |
| **FR-06** | **組態原子寫入與快取自愈** | 使用者確認後，將路徑值寫回 `config/agents-workflow/config.project.json`（取代 `"!undefined"`）並通知 Core URI 模組刷新快取。 | `[P00:DR-03]` |
| **FR-07** | **`--path-*` 變種覆蓋參數** | 支援 `--path-plans="<path>"`, `--path-archived="<path>"`, `--path-ext="<path>"`, `--path-docs="<path>"` 自訂覆蓋推薦路徑，並支援 `-y`/`--yes` 無提示自動同意模式。 | `[P00:DR-04]` |

---

## 2. 邊界與例外清單 (Edge Cases & Exceptions)

| 例外編號 | 情境名稱 | 觸發條件與防禦策略 | 預期行為 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- | :---: |
| **EC-01** | **`project://` 未定義引導** | 執行 `--init-default` 時若宿主 `project://` 尚未配置（為 `!undefined`）。 | 自動觸發 Core 的 JIT 補齊或提示使用者先指定 `project_root`，防止產生相對路徑漂移。 | `[P00:DR-03]` |
| **EC-02** | **使用者拒絕互動 (`-n`)** | 使用者在提示時輸入 `n` 或 `no`。 | 優雅退出指令，不建立任何實體目錄，亦不修改 `config.project.json`。 | `[P00:DR-03]` |
| **EC-03** | **無效路徑參數** | `--path-*` 傳入空字串或包含無效非法字元。 | 輸出錯誤訊息並中斷執行，保持現有組態不變。 | `[P00:DR-04]` |
| **EC-04** | **混合存在性情境** | 4 個路徑中部分目錄已存在，部分不存在。 | 僅對缺失目錄調用建立，對已存在目錄僅做提醒與綁定，全部正確寫入組態。 | `[P00:DR-03]` |

---

## 3. 非功能性需求 (Non-Functional Requirements)

- **NFR-01 (零臆測原則)**：靜態模板嚴禁預設實體路徑，除使用者明確執行 `--init-default` 外，全系統嚴格維持 `"!undefined"` 阻斷。
- **NFR-02 (原子寫入安全性)**：寫入 `config.project.json` 採用暫存檔原子覆蓋，防止寫入中斷造成 JSON 損毀。
- **NFR-03 (回歸與沙盒驗證)**：在 `dev test` 沙盒微型虛擬環境中完整驗證 `--init-default` 互動與非互動行為，全系統 100% Passed。

---

## 4. 當前階段確認狀態

- **當前狀態**：`Draft` (Phase 1 規格草擬完成)  
- **推進關卡**：請開發者審查本規格說明書，若確認無誤，請明確指示「**確認無誤，推進至 Phase 2**」！
