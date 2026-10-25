# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：專案特化技能建置與 Layer 2 宣告式擴充引導工作流 (sub_05_skill_creator_extension_workflow)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Medium)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：`FR-01` ~ `FR-05` 在 `P03_api_spec.md` 與實作任務中皆有 1:1 對應介面與檔案變更。
- [x] **邊界防護**：`EC-01` ~ `EC-05` 皆具備具體防呆設計與邊界測試（`ET-01` ~ `ET-03`）覆蓋。
- [x] **依賴純淨**：符合 `NFR-01`（`SKILL.md` $\le 180$ 行，單層 `references/extension-guide.md` 附 TOC）與 `NFR-02`（零特化污染、零母倉 dummy 組態殘留）。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **隨包手冊** | `ys_codebase/source/agents-workflow/README.md` | Modify | 更新內建純 Skill 技能包數量（17 個，新增 `skill-creator`）與 Token 錨點表（新增 `SKILL_CREATOR_STANDARDS`） |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 同步更新系統知識庫之 17 大內建技能總覽表與宣告式擴充引導說明 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 於指令與技能速查表補充 `/skill-creator` 三軌擴充引導與使用時機 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 更新 `last_updated` 並於設計決策補充 `/skill-creator` 三軌擴充與編譯器正則豁免防呆要點 |
| **微觀註解** | `contributes/_manifest.md` & 測試方法 Docstrings | Modify | 同步更新 `_manifest.md` 匯出清冊（17 大技能）與 `test_ft_11` 追溯註解 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時追加 `sub_05_skill_creator_extension_workflow` 完成摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：`skill-creator/SKILL.md` 與 `references/extension-guide.md` 本身就是專門教導 Agent 如何使用語意 URI 與 Token 錨點的文檔，內文勢必包含大量語法範例；如何確保在執行 `agents-workflow compile` 與 `release` 時，編譯器不會將教學範例誤判為「未包覆反引號之裸標籤 (`Unenclosed placeholder tag`)」或「無法解析之語意 URI (`Unresolved semantic URI tag`)」？  
> [*] **防護解法**：嚴格執行 `[P02:DR-02]` 雙軌編譯器豁免設計：
> 1. 於 `ArtifactCompiler` (`compiler.py`) 引入 `LITERAL_FENCED_BLOCK_REGEX`：凡在 Fenced Code Block 首行標註 `<!-- yscb:literal -->` 者，在 Stage 1 (`resolve_single_artifact`) 與 Stage 2 (`resolve_stage2_uri`) 均先抽離保護，待佔位符解算完畢後於 Stage 2 剝除首行 `<!-- yscb:literal -->` 標記並原樣還原字面量內容。因此，所有展示 `__@{...}__`、`__#{...}__`、`__${...}__` 教學語法與正反對照表之代碼塊一律首行標註 `<!-- yscb:literal -->`，確保物化產物保留 100% 原始教學語法且零警告。
> 2. 凡出現在散文或 Markdown 表格內部需實際轉譯的 Inline Code Span 語意標籤，一律使用穿插型真實已註冊語意 URI（如 `` `__${config://agents-workflow}__/contribute.json` ``、`` [`new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) ``）或真實錨點（如尾部獨立行 `` `__@{SKILL_CREATOR_STANDARDS}__` ``）。

> [?] **尖銳問題 2**：`test_ft_08` 對所有技能目錄下的 `*.md` 設有嚴格的雙軌 Frontmatter 斷言與禁字掃描，新增 `skill-creator` 時如何確保不破壞既有契約？  
> [*] **防護解法**：
> 1. 將 `"skill-creator"` 同時加入 `test_ft_08` 的 `expected_skills` 與 `command_driven_skills` 集合。
> 2. `skill-creator/SKILL.md` 前 4 行 Frontmatter 嚴格包含 `僅於顯式輸入` 且不含 `(或 /` 大小寫變體，文末包含 `## 常見踩坑指南 (Gotchas)`。
> 3. 全文絕不出現 `test_ft_08` 禁止之詞彙。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01（模組組態與 Token 註冊）**：
   - 修改 `ys_codebase/source/agents-workflow/contributes/agents-workflow.json`，註冊 `skill-creator` 技能 `export` 與 `SKILL_CREATOR_STANDARDS` `token`。
   - 修改 `ys_codebase/source/agents-workflow/contributes/_manifest.md`，更新導出技能數為 17 大技能。
2. **TASK-02（建立單層擴充參考手冊 `references/extension-guide.md`）**：
   - 建立 `ys_codebase/source/agents-workflow/assets/skills/skill-creator/references/extension-guide.md`，頂部配置 `## 目錄 (Contents)`，完整收錄全系統 22 個 Stage 1 Token 錨點地圖（含宿主檔案、獨立區塊 vs. 表格行結構屬性、注入時機）、Stage 2 語意 URI 轉換規則與單反引號防呆正反對照、以及軌跡 ①/②/③ 之 `contribute.json` 最小增量範本。
3. **TASK-03（建立 `/skill-creator` 技能主檔與中樞互指導流）**：
   - 建立 `ys_codebase/source/agents-workflow/assets/skills/skill-creator/SKILL.md`（控制在 $\le 180$ 行），實作主動指令型 Frontmatter、四步檢核表、三軌擴充判定矩陣、步驟 2 CLI 探索與「🛠️ /SkillCreator 專案擴充藍圖確認卡」、步驟 3 扁平路徑與雙軌連結分流、步驟 4 三步編譯驗證守門、尾部 `` `__@{SKILL_CREATOR_STANDARDS}__` `` 錨點與 `## 常見踩坑指南 (Gotchas)`。
   - 修改 `development-sop/SKILL.md` 與 `skill-optimizer/SKILL.md` 補齊 `/skill-creator` 雙向導流。
4. **TASK-04（單元測試擴充與三層文檔同步）**：
   - 修改 `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`，更新 `test_ft_08` 並新增 `test_ft_11_sub05_skill_creator_extension_workflow`。
   - 同步更新 `ys_codebase/source/agents-workflow/README.md` 與 `docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}`。
   - 執行 `dev check`、`dev test`、`install agents-workflow@build --force` 與 `agents-workflow release` 驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **`[P04:DR-01]` 測試歸戶與實機編譯雙重斷言**：遵循 `testing-sop` 鐵律 1 與鐵律 3，不新建計畫名碎片測試檔，直接於既有 `tests/test_plans_model_record.py` 擴充 `test_ft_11_sub05_skill_creator_extension_workflow`，並在測試內實機調用 `ArtifactCompiler().compile_stage1()` 與 `check_unenclosed_tags()` 驗證 0 Error / 0 Warning。

