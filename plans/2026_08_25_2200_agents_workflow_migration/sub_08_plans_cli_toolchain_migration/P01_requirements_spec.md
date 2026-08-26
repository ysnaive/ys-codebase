# 需求規格說明書 (Requirements Specification)

> 功能名稱：Plans CLI 工具鏈補齊與舊版功能遷移 (Plans CLI Toolchain Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 計畫安全歸檔工具 (`plan archive`) | 實作 `agents-workflow plan archive <plan_name> [--force]`（別名 `plan-archive`），將已完成計畫目錄由 `workflow.plans://` 安全搬移至 `workflow.archived://{YYYY}/{MM}/{plan_name}`；驗證完成度標記、全域 CHANGELOG 記載、自動清理 `handoff.md` 與目的地防衝突。支援 `--force` 跳過檢查。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-02** | 狀態矩陣掃描工具 (`plan status`) | 實作 `agents-workflow plan status`（別名 `plan-status`, `plans-status`），專注掃描 `workflow.plans://` 進行中計畫；識別 4 大 Track（Umbrella, Fast Track, Full Track, Phase 0）、當前 Phase 與 Paused 狀態；以 ASCII 樹狀縮排展示主/子計畫階層。明確不掃描歷史目錄。 | P0 | [P00:DR-02], [P00:DR-04] |
| **FR-03** | 歷史與決策檢索工具 (`plan search`) | 實作 `agents-workflow plan search <query> [--dr] [--year=YYYY] [--month=MM] [--limit=N]`（別名 `plan-search`）；跨 `workflow.plans://` 與 `workflow.archived://` 檢索。`--dr` 模式正則結構化擷取 `[{Phase}:DR-XX]` 與結論摘要去重展示；全文模式輸出匹配行號與前後上下文片段。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-04** | 計畫規範稽核工具 (`plan verify`) | 實作 `agents-workflow plan verify [plan_name] [--all]`（別名 `plan-verify`）；稽核 Markdown 文件是否殘留 `<!-- AGENT_GUIDANCE -->` 模板註解、檢查 Blockquote Header 元數據（`功能名稱`, `建立日期`, `狀態`）齊備性，並遞迴稽核子計畫目錄 `sub_*`。 | P0 | [P00:DR-02], [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 歸檔不存在之計畫目錄 | 當 `workflow.plans://{plan_name}` 不存在或非目錄時，輸出明確錯誤訊息 `[ERROR] 找不到指定的計畫目錄：{plan_name}` 並返回退出碼 1。 |
| **EC-02** | 歸檔名稱無效日期前綴 | 當 `<plan_name>` 未符合 `YYYY_MM_` 命名格式時，無法安全推斷歸檔年月目錄，輸出錯誤並阻斷歸檔操作。 |
| **EC-03** | 未完成或未記載 CHANGELOG 之歸檔攔截 | 當計畫未包含 `Completed` 狀態標記或全域 `project://CHANGELOG.md` 未記載該計畫名稱時，輸出警告並提示使用 `--force`，拒絕未授權搬移。 |
| **EC-04** | 歸檔目的地目錄已存在衝突 | 當 `workflow.archived://{YYYY}/{MM}/{plan_name}` 已存在同名歷史目錄時，拒絕覆蓋並阻斷，防止歷史產物被意外損毀。 |
| **EC-05** | 進行中目錄為空或無計畫 | 當 `workflow.plans://` 無任何進行中計畫時，`plan status` 優雅輸出 `[INFO] 目前無進行中的開發計畫。`，不拋出未捕獲例外。 |
| **EC-06** | 檢索或稽核遇到編碼異常或空檔案 | 讀取 Markdown 文件時使用 UTF-8 配合 `errors="ignore"`，遇到空檔案或無 Header 文件時安全略過或回報 WARN，保證稽核與檢索進程不中斷。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 語意 URI 一等公民與路徑解耦 | 所有路徑尋址（`workflow.plans://`, `workflow.archived://`, `project://`）100% 透過 `core.uri.resolve` 動態解算，嚴禁在程式碼中寫死任何本機絕對或硬編碼相對路徑。 |
| **NFR-02** | 跨平台與純標準庫無額外相依 | 採用 Python 標準庫（`pathlib`, `shutil`, `re`, `argparse`），嚴禁引入非必要之第三方套件，保證 Windows / Linux / macOS 跨平台一致性。 |
| **NFR-03** | 檢索與掃描效能約束 | 掃描與全文檢索採用串流式單遍讀取，在包含 50+ 個歷史計畫的專案中，`plan status` 與 `plan search` 執行時間應 $< 500\text{ms}$。 |

---

## 4. 決策紀錄 (Decision Records)

- **[P01:DR-01] 模組化封裝結構**：於 `source/agents-workflow/agents_workflow/plans/` 下建立專屬子套件（`archiver.py`, `scanner.py`, `searcher.py`, `verifier.py`），實現高內聚低耦合，`scripts/cli.py` 僅作為極簡 CLI 派發路由。

---

## 5. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：依據 `AGENTS.md` 規範，Agent 嚴禁主動執行 `archive` 歸檔操作，僅在開發者明確下達指令時方可調用。
- **`[!IMPORTANT]`**：`plan status` 依開發者指示排除歷史目錄掃描，專注於活躍進行中計畫掌控。
