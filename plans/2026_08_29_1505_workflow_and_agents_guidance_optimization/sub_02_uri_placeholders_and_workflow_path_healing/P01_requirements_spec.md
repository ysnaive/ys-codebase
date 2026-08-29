# 需求規格說明書 (Requirements Specification)

> 功能名稱：`sub_02_uri_placeholders_and_workflow_path_healing`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Stage 2 佔位符解析二分法 | 在 `compiler.py` 的 `resolve_stage2_uri` 中，精確區分純佔位符（Standalone）與行內穿插佔位符（Inline）。若 code span 為純佔位符，解算後完全替代並剝除外層反引號；若為行內穿插，解算後維持外層反引號。 | P0 | [P00:DR-01] |
| **FR-02** | 工作流讀檔動線全面改用 `__${...}__` | 將所有工作流資產（`ContextInit.md`、`Auto.md`、`Continue.md`、`Discuss.md`、`Idea.md`、`Pause.md`、`Research.md`、`Review.md`）及標準中供 Agent 於專案根目錄讀取/調用之檔案指引，全面切換為 `__${...}__` (Project Relative URI)，確保物化路徑相對於專案根目錄。 | P0 | [P00:DR-02] |
| **FR-03** | 語意協議前綴全量修復 | 修復資產中非標準協議前綴殘留：<br/>1. `DocumentationStandards.md:43`：`plans://` ➔ `workflow.plans://`<br/>2. `P07_walkthrough.md:07`：`plans://` ➔ `workflow.plans://`<br/>3. `umbrella_overview.md:08`：`archive://` ➔ `workflow.archived://` | P0 | [P00:DR-03] |
| **FR-04** | 確定性文檔讀取失效阻斷鐵律 | 於 `AgentsStandards.md` 注入剛性規範，嚴禁在讀取 SOP/指引明確指定之確定性檔案失敗時，自主發起同義詞或模糊搜尋來掩蓋路徑缺陷，必須立即停步向開發者呈報錯誤。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 佔位符前後帶微量空白（如 `` `__#{ uri }__` ``） | 使用精準正則 `re.fullmatch(r"__[@#\$]\{\s*[^}]+\s*\}__", inner.strip())` 容忍內部微量空格，依然精準判定為 Standalone 純佔位符。 |
| **EC-02** | 同一 code span 內含多個佔位符（如 `` `cmd __${a}__ --arg __${b}__` ``） | 判定為 Inline 穿插類型，逐一替換佔位符後，整體保留外層反引號。 |
| **EC-03** | 未知或無效 URI 協議 | 安全 fallback 返回原始 tag_uri，並輸出 `[compiler:warning]` 至 stderr，不中斷編譯流程。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 相容性與發布清單乾淨度 | 編譯與物化後產物不得破壞既有 Git Manifest 追蹤，全生態系單元測試 (208+ 測試) 100% Passed。 |
| **NFR-02** | Markdown 格式合法性 | 所有超連結物化後為合法的 CommonMark `[text](path)` 格式，0 反引號殘留。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` [DN-AW-04]**：佔位符在原始碼端一律以反引號包裹以支援 Markdown 編輯器可視化，編譯器在 Stage 1/Stage 2 物化時負責將 Standalone 佔位符完全替代為純文字。
- **`[!CAUTION]` Dogfooding 三層空間隔離**：所有代碼與資產修改必須 100% 發生在 `ys_codebase/source/` 空間，嚴禁直接修改消費空間 `.agents/` 或 `modules/`。
