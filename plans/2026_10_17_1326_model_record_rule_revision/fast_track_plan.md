# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：模型紀錄規則修訂 (Model Record Rule Revision)  
> 建立日期：2026-10-17  
> 所屬主計畫：無（獨立計畫，不隸屬 `2026_10_17_1133_workflow_optimization`）  
> 狀態：Completed  
> 模型：Claude Sonnet 5.5 (Medium)  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：生產碼 0 行；新增測試檔 118 行（有效行 95）。依 [FP-01:DR-07] 開發者裁定維持 Fast Track（測試不計入或以有效行計算，均未超標）。
- [x] **API 契約守門**：Public API 簽名契約 0 變更（`PlanVerifier` 等未改動）。
- [x] **依賴邊界守門**：零跨模組新依賴引入。
- [x] **既有測試守門**：`python yscb.py dev test agents-workflow -q` 共 100/100 通過（原 97 + 新增 3）。

### 1.2 核心需求與邊界
- **需求描述**：修正 `commit:cc94797c` 引入之模型紀錄規則在實戰中的缺陷（Gemini 4 Argon 於本機對話 `84facb53` 中，受專案檔案內他模型名稱汙染與壓縮摘要固化，連續 5 次將自身誤報為 `Claude Opus 5.5`；尾行 `> {model}` 無法定位且破壞表格）。調研依據：本機 `transcript.jsonl` 全量掃描與網路資料（LLM 無法由權重得知自身名稱，僅依 context 宣稱身分）。
- **決策紀錄**：
  - **[FP-01:DR-01]** 模型名稱唯一來源為**當輪平台／系統明確宣告**，原樣照抄、不改寫、不補全；無明確宣告或無法確認時填 `Unknown`；**嚴禁**從既有計畫檔、對話摘要、先前回覆或自身認知反推。
  - **[FP-01:DR-02]** 廢除對話首行 `> {model}` 與內文尾行 `> {model}` 兩項規則；模型紀錄只留在檔案內（開發者裁定）。
  - **[FP-01:DR-03]** 接手既有計畫時不得修改該檔既有 `> 模型：`；改於 `changelog.md` 新增事件列，並於新增之「模型」欄記錄當輪宣告模型（事件粒度歸屬）。
  - **[FP-01:DR-04]** 本期不做「來源」欄位、不做開發者宣告管道、不做平台探針擴充點（開發者裁定「先不要」）。
  - **[FP-01:DR-05]** 本計畫完成後**不歸檔**，保留於 `plans/` 作為紀錄；待下游實戰驗證一段時間無問題後再行歸檔（開發者裁定；歸檔屬授權守門，未獲指示不得執行）。
  - **[FP-01:DR-06]** 規則本體依既定草案置於 `AgentsStandards.md` 核心原則 2，取代原首行與尾行規則；`development-sop` 模板指針同步修正措辭。
  - **[FP-01:DR-07]** 修改行數守門之計數口徑：開發者裁定「維持 Fast Track」，不升級 Full Track（FP-02 實測生產碼 0 行、測試 118 行／有效 95 行）。
- **已確認之假設**（開發者於 FP-01 授權進入 FP-02 時確認）：
  - **A1**：模型名稱含推理強度後綴，例如 `Claude Sonnet 5.5 (Medium)`。
  - **A2**：規則細節全數置於核心原則 2，不另拆至 `development-sop`。
- **影響範圍**：
  - `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md`（取代 L16）
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md`（L86 措辭）
  - `ys_codebase/source/agents-workflow/assets/skills/pause/SKILL.md`（L26）、`research/SKILL.md`（L48~49）措辭對齊
  - `ys_codebase/source/agents-workflow/assets/templates/`：`header.md`、`handoff.md`、`roadmap.md`、`umbrella_overview.md`、`RXX_research_report.md` 佔位符；`changelog.md` 新增「模型」欄
  - `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`（新增）
  - 知識庫與日誌：`docs/agents-workflow/README.md`、`user_guide.md`、`DESIGN_NOTES.md`（登記 `[DN-AW-08]`）、根目錄 `CHANGELOG.md`
  - 不動：已封存與既有計畫檔案；`.agents/*` 物化產物已經 `@build` 同步
- **相容性邊界**：既有 3 欄 `changelog.md` 須持續通過 `plan verify`；`PlanVerifier` 僅檢查 `模型` 鍵存在（不驗證值），`Unknown` 可通過（FT-01、FT-02 已實證）。

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：`AgentsStandards.md` L16 改為模型紀錄規則（DR-01~DR-03）；`development-sop/SKILL.md` L86 措辭同步。
- [x] **TASK-02**：模板佔位符改為 `[平台宣告之模型名稱；無法確認填 Unknown]`（`header.md`、`handoff.md`、`roadmap.md`、`umbrella_overview.md`、`RXX_research_report.md`）；`changelog.md` 表頭改為 `日期時間｜類型｜模型｜摘要`。
- [x] **TASK-03**：`pause`、`research` 技能手冊相關措辭對齊。
- [x] **TASK-04**：新增 `tests/test_plans_model_record.py`（見下）。
- [x] **TASK-DOC**：`DESIGN_NOTES.md` 登記 `[DN-AW-08]`；`README.md`、`user_guide.md` 同步；根目錄 `CHANGELOG.md` 追加摘要。
- **測試案例清冊**：
  - [x] **FT-01**：`PlanVerifier` 接受 `> 模型：Unknown` 與 `> 模型：Claude Sonnet 5.5 (Medium)` 標頭，且未替換之新佔位符被攔截。
  - [x] **FT-02**：`PlanVerifier` 同時接受 4 欄（含「模型」）與既有 3 欄 `changelog.md`。
  - [x] **FT-03**：`AgentsStandards.md` 不再含首行／尾行 `> {model}` 規則，且含 `Unknown` 與嚴禁反推條款；`header.md`、`changelog.md` 模板已更新。
  - [x] **RT-01**：全模組既有單元測試 100% 回歸通過

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：
  - 規範與技能：`AgentsStandards.md`、`development-sop/SKILL.md`、`pause/SKILL.md`、`research/SKILL.md` 共 4 檔。
  - 模板：`header.md`、`handoff.md`、`roadmap.md`、`umbrella_overview.md`、`RXX_research_report.md`（佔位符）與 `changelog.md`（新增「模型」欄）共 6 檔。
  - 測試：新增 `test_plans_model_record.py`（118 行，FT-01 ~ FT-03）。
  - 知識庫：`README.md`、`user_guide.md`、`DESIGN_NOTES.md`；根目錄 `CHANGELOG.md`。
  - `PlanVerifier` 等生產碼 0 行變更。
- **實機測試日誌**：
  - `python yscb.py dev check agents-workflow`：PASSED
  - `python yscb.py dev test agents-workflow -q`：`Pass: 100 (100.0%), Fail: 0, Skip: 0`
  - `python yscb.py install agents-workflow@build --force`：成功安裝 `agents-workflow@1.1.0.build`，0 編譯告警；`AGENTS.md` 與 `.agents/.yscb/templates/changelog.md` 已確認物化新規則。
- **偏差紀錄**：測試行數 118 行高於預估 40 行；開發者裁定維持 Fast Track（[FP-01:DR-07]）。

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊——宏觀 `CHANGELOG.md`、中觀 `README.md` / `user_guide.md` / `DESIGN_NOTES.md`（`[DN-AW-08]`）、微觀測試 docstring；測試 100% 通過。
- [x] **日誌與發布交付**：已追加 `CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_10_17_1326_model_record_rule_revision` 驗證 100% Passed。
- [x] **標頭狀態更新**：頂部標頭已更新為 `Completed`；依 [FP-01:DR-05] **不執行歸檔**，保留待下游驗證。
