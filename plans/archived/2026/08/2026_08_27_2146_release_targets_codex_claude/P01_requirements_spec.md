<!--

Phase 1 執行指引：
1. 目標：將 P00 語意需求 1:1 轉譯為可驗收的功能需求 (FR)、邊界條件 (EC) 與非功能需求 (NFR)。嚴禁在 P00 範疇之外新增未經討論的臆測功能。
2. 規格轉譯：FR 表格中的每一項必須明確追溯至 P00 的具體使用情境或決策紀錄 [P00:DR-XX]。
3. 邊界與防禦：列出極限輸入、異常狀態 (EC) 與預期防禦處理行為。
4. 踩坑防護：主動查閱相關模組在 docs/ 與 DESIGN_NOTES 中的 [!CAUTION] 與 [!WARNING]。
5. Checkpoint 等待關卡：等待開發者明確確認 P01 內容（狀態更新為 Confirmed）後推進至 Phase 2。

-->

# 需求規格說明書 (Requirements Specification)

> 功能名稱：agents-workflow 添加 codex 與 claude code release targets  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `claude` Release Target 宣告與投影 | 於 `manifest.json` 宣告 `claude` release_target，將 workflows 投影至 `project://.claude/commands`、templates 投影至 `project://.claude/.yscb/templates`、standards 投影至 `project://.claude/.yscb/standards`，並支援 YAML Frontmatter 標頭注入。 | P0 | [P00:DR-02] |
| **FR-02** | `codex` Release Target 宣告與投影 | 於 `manifest.json` 宣告 `codex` release_target，將 workflows 投影至 `project://.codex/workflows`、templates 投影至 `project://.codex/.yscb/templates`、standards 投影至 `project://.codex/.yscb/standards`，並支援 YAML Frontmatter 標頭注入。 | P0 | [P00:DR-03] |
| **FR-03** | `ReleasePublisher` 多 Target 映射支援 | 發布引擎支援同時或依組態啟用 `antigravity`、`claude`、`codex` 多目標發布，精準解算各目標的相對路徑與 YAML 標頭。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-04** | CLI `release-target` 管理相容性 | `python yscb.py agents-workflow release-target <list|add|remove>` 能正確辨識並管理 `claude` 與 `codex` 目標狀態。 | P1 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 目標目錄（如 `.claude/` 或 `.codex/`）尚未建立 | `ReleasePublisher` 在寫入檔案前自動遞迴建立目標父目錄 (`os.makedirs(..., exist_ok=True)`)。 |
| **EC-02** | Target 被移除 (`remove_target`) 時殘留檔案 | 發布流水線比對 `storage://agents-workflow/release_manifest.json`，自動清理已停用 Target 之歷史檔案。 |
| **EC-03** | 同時啟用多個 Target 時之 Header 渲染 | 各 Target 獨立依照自身 projection header 規則進行渲染，互不干擾。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構相容性 | 100% 採用 Python 標準庫，零第三方依賴。 |
| **NFR-02** | 發布效能 | 多目標發布耗時維持在毫秒級，不增加額外 I/O 阻塞。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `manifest.json` 中各 `release_target` 的 projections 鍵值必須與 `contributes.export` 中的 `type`（`workflow`, `template`, `standard`）精準對齊，`ArtifactCompiler` 與 `ReleasePublisher` 會自動處理單複數容錯。
