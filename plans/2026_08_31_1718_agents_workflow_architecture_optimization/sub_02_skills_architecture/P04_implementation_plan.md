# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_skills_architecture  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書中均有具體承接介面。
- [x] **邊界防護**：EC-01 ~ EC-05 均有明確的目錄容錯、二進位跳過與 fallback 處理機制。
- [x] **依賴純淨**：100% 依賴 Python 標準庫，符合 NFR-01~03 指標。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 增補 `export.type: "skill"` 與 `projections.skill` 說明。 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 增補 Skills 目錄級導出、Release Target 映射與 Codex 官方路徑對齊說明。 |
| **規格手冊** | `source/agents-workflow/contributes.format.md` | Modify | 增補 `export.type: "skill"` 與 `projections.skill` 之 Schema 規範。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：如果一個 Skill Package 內有深層子目錄（如 `references/sub/deep.md`）且含有 `__#{...}__` 語意標籤，發布時會不會路徑錯亂或 Stage 2 遺漏？  
> 💡 **防護解法**：`_scan_directory_files` 保留正規化相對路徑 `rel_path`，Stage 1 快取與 Stage 2 解析皆以 `rel_path` 拼接，Stage 2 對所有 Skill 內的文字檔案逐一執行解析，確保深層文件內的語意標籤 100% 替換且落地目錄結構完整。

> ❓ **尖銳問題 2**：如果 Skill 目錄內有二進位檔案或大型資源（如圖片、可執行腳本），Stage 1 Token 展開會不會報錯？  
> 💡 **防護解法**：編譯器以 utf-8 安全讀取，若讀取失敗或檢測為二進位檔案，則保留原始 bytes / 內容原樣快取並原樣寫入，跳過正則 Token 展開，防止 `UnicodeDecodeError`。

> ❓ **尖銳問題 3**：若多個 Target 同時啟用（如 `antigravity` 與 `claude`），Skill 發布時各自落地不同目錄，Gitignore 如何處理？  
> 💡 **防護解法**：`sync_gitignore` 收集所有啟用 Target 的全部落地 Skill 檔案實體路徑，精確轉為相對專案路徑加入忽略清單，不使用萬用字元目錄忽略，精確且無漏。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：更新 `source/agents-workflow/contributes/agents-workflow.json` 與 `contributes.format.md`，為 `antigravity`、`claude`、`codex` 加入 `projections.skill` 宣告，並對齊 `codex` 專案路徑至 `project://.agents/`。
- [ ] **TASK-02**：擴充 `source/agents-workflow/agents_workflow/compiler.py`，實作 `_scan_directory_files`，支援目錄級 export 掃描與保留 `rel_path` 的 Stage 1 快取。
- [ ] **TASK-03**：擴充 `source/agents-workflow/agents_workflow/publisher.py`，支援 `projections.skill`、目錄巨集插值、多檔案 Stage 2 解析與 Gitignore 精確忽略。
- [ ] **TASK-04**：更新單元測試套件 `source/agents-workflow/tests/test_compiler.py`、`test_publisher.py`、`test_targets.py`，覆蓋 FT-01~07、ET-01~03。
- [ ] **TASK-DOC**：同步更新 `docs/agents-workflow/README.md` 與 `user_guide.md`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立 Skill 目錄級導出與投影流水線，將所有 Skill 內部檔案納入雙軌 Manifest 追蹤與 Pruning 管理。
