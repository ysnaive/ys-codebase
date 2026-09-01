# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_existing_injection_mode_optimization  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `release_target.agents_md` 宣告式欄位 | 擴充 `release_target` Schema，支援 `agents_md: str`（語意 URI 或空字串）。內建 Target 預設為：`antigravity` ➔ `"project://AGENTS.md"`、`claude` ➔ `"project://CLAUDE.md"`、`codex` ➔ `"project://AGENTS.md"`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-02** | `ReleasePublisher` 目標驅動軟合併 | 發布引擎遍歷 `active_targets`：若 Target 的 `agents_md` 存在且非空，以 `AgentsStandards.md` 內容對該路徑執行軟合併，並將該檔案納入該 Target 之雙軌 `published_files` 追蹤集合。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | 移除全域 `enable_agents_md` 組態 | 自 `config.project.json` 模板與預設組態中徹底移除 `enable_agents_md`，發布引擎完全移除該鍵之讀取邏輯。 | P0 | [P00:DR-01] |
| **FR-04** | 雙軌 Manifest 與 Pruning 整合 | 軟合併檔案納入 Manifest 追蹤；當停用特定 Target 且其 `agents_md` 檔案不再被其他啟用 Target 引用時，支援安全 Pruning 清理。 | P1 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 多個 Target 共享相同之 `agents_md` 目標路徑 (例 antigravity 與 codex 皆為 `project://AGENTS.md`) | 發布時執行去重與冪等合併（僅寫入一次）；任一 Target 停用但另一 Target 仍引用時，Pruning 不得誤刪共享檔案。 |
| **EC-02** | `agents_md` 設定為空字串 `""` 或未宣告 | 該 Target 完全跳過任何規範檔案的軟合併與落地輸出，不拋出異常。 |
| **EC-03** | `agents_md` 指定之路徑語意 URI 解析失敗或權限不足 | 記錄警告日誌並安全略過該 Target 之軟合併，不中斷其他 Target 與其他資產檔案的發布交易。 |
| **EC-04** | 所有啟用之 `active_targets` 皆設定 `agents_md: ""` | 正常輸出所有 `workflow`、`template`、`standard` 投影檔案，但不產生任何 `AGENTS.md` / `CLAUDE.md`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與指紋短路 | 雙軌 Stage 0 SHA-256 綜合指紋計算需納入各 Target 之 `agents_md` 配置；無變更時維持 0 I/O 短路（耗時 $\le 5\text{ms}$）。 |
| **NFR-02** | 換行一致性 | 軟合併輸出檔案強制採用 LF (`\n`) 換行符，符合全專案 Git 規範。 |
| **NFR-03** | 測試覆蓋率 | 單元測試 100% 覆蓋 `agents_md` 啟用、多 Target 共享、空字串跳過與 Pruning 清理情境。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` 軟合併標籤保護**：軟合併必須精確定位 `<!-- YSCB_AGENTS_BEGIN -->` 與 `<!-- YSCB_AGENTS_END -->` 區間，非 YSCB 區間（使用者自訂規格）必須 100% 原樣保留。
- **`[!WARNING]` 測試套件同步**：既有測試（如 `test_publisher.py`、`test_targets.py`）中可能包含對 `enable_agents_md` 的組態 mock，需同步更新為測試 `release_target.agents_md`。
