# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_skills_architecture  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `export.type = "skill"` 宣告支援 | `contributes.agents-workflow.export` 支援宣告 `type: "skill"`。`source` 支援指向 Skill 整體資料夾目錄（如 `module.root://assets/skills/knowledge-db`）或單檔路徑。 | P0 | [P00:DR-02] |
| **FR-02** | 編譯器目錄走訪與 Stage 1 快取 | `ArtifactCompiler` 檢測到 `source` 為目錄時，自動遞迴走訪其下所有檔案，對文字檔執行 Token 展開，保留相對目錄結構寫入 `cache://agents-workflow/resolved_contents/skills/<skill_name>/`。 | P0 | [P00:DR-03] |
| **FR-03** | 投影目錄巨集插值支援 | `ReleasePublisher.build_deployment_map` 支援解析 `target_dir` 中的 `{export.name}` / `{export.basename}` 巨集，將 Skill 內所有檔案映射至目標目錄。 | P0 | [P00:DR-04] |
| **FR-04** | 多檔案 Skill Stage 2 解析與落地 | `ReleasePublisher` 解算 Skill 內部所有文字檔之 `__#{...}__` 語意標籤，並以純 LF 格式落地輸出至目標路徑。 | P0 | [P00:DR-04] |
| **FR-05** | 雙軌 Manifest 追蹤與 Pruning | Skill 目錄下所有落地檔案皆登記於 `published_files`（Project 軌使用 `project://` 協議，Local 軌使用實體路徑），在檔案刪除或 Target 停用時精確 Pruning。 | P0 | [P00:DR-05] |
| **FR-06** | 內建 Release Targets 官方標準對齊 | 於 `agents-workflow.json` 為 `antigravity`、`claude`、`codex` 增補 `projections.skill`，並依官方標準修正 `codex` 專案路徑至 `project://.agents/`。 | P0 | [P00:DR-04] |
| **FR-07** | `.gitignore` 精確檔案忽略 | Skill 產物（如 `.agents/skills/<name>/SKILL.md`）自動納入 `.gitignore` 管理區塊，不整目錄忽略 `.agents/`，保護使用者自訂檔案。 | P1 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Skill 目錄為空或來源路徑不存在 | 編譯器發出警告日誌並跳過該 export，不 crash，不中斷其他 export 編譯。 |
| **EC-02** | Skill 目錄中包含二進位檔案或非 Markdown 資產 | 安全以二進位或純文字方式讀取與寫入，跳過佔位符替換，防止 UnicodeDecodeError。 |
| **EC-03** | Target 未宣告 `projections.skill` | 自動安全 fallback 至預設投影路徑 `project://.agents/skills/{export.name}`。 |
| **EC-04** | Skill 目錄包含多層深層子資料夾（如 `references/deep/sub.md`） | 編譯與發布管線完整保持其相對路徑與目錄層級。 |
| **EC-05** | 單一檔案 Skill (非目錄) 宣告（如 `source: ".../SKILL.md"`） | 自動相容處理，正確輸出至目標 Skill 資料夾下。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴 | 100% 使用 Python 標準庫 (`os`, `re`, `shutil`)，嚴禁引入第三方套件。 |
| **NFR-02** | 雙階 Diff 效能 | Skill 產物完整納入 Stage 0 指紋與 Stage 4 內容比對，無變更時 0 File I/O。 |
| **NFR-03** | 測試覆蓋與相容性 | 模組單元/邊界測試 100% 通過，全生態系 275+ 測試無回歸。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`**：
  - 發布 Skill 時目錄內可能包含 `SKILL.md` 以外的子文件（如 `references/*.md`），其內部亦可能包含語意 URI（如 `project://...` 或 `workflow.docs://...`），必須完整走過 Stage 2 解析，不能僅解析 `SKILL.md`。
  - `.gitignore` 同步時，嚴禁輸出 `/.agents/skills/` 整目錄忽略，必須以個別檔案為單位（如 `/.agents/skills/knowledge-db/SKILL.md`），以防使用者在專案自建之自訂 Skills 遭到 Git 誤忽略。
