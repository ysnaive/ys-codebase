# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：於 session-audit 技能引入盲眼子代理客觀審計機制  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0240_batch_lifecycle_and_blind_audit / sub_01_session_audit_blind_subagent  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Revision  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：於 `session-audit` 技能引入盲眼子代理 (`blind-subagent`) 執行客觀審計，防範主代理認知偏差與自我辯護（`TODO-17`）。
- **核心目標**：在 `/session-audit` 工作流中，將原本由當事主代理直接自行解讀 `session-trace` 的模式，升級為「主代理提取 `session-trace` 結構化鐵證 $\to$ 強制委派無歷史對話包袱之盲眼 Subagent（依 `BlindSubagentStandards.md`）執行步驟 2~3 五大摩擦訊號核對與 A/B/C/D 四象限根因解剖 $\to$ 主代理彙整輸出診斷報告」，彻底切斷當事主代理因敘事慣性將 `Type D（模型注意力滑脫／規則未遵循）` 防衛性合理化為 `Type C（任務本質的不可知探索）` 之認知偏誤。
- **既有組件復用與查重 (Reuse Discovery)**：直接復用 `ys_codebase/source/agents-workflow/assets/standards/BlindSubagentStandards.md` 之去錨定三原則（`§4.1`）、黑盒隔離（`§4.2`）、誠實收斂（`§4.3`）與 `§5.2` 盲眼專用派發模板，不重複發明子代理規範。
- **邊界排除 (Explicitly Excluded)**：不修改 `session_trace.py` 底層 Python 軌跡提取引擎邏輯；純屬技能工作流與規範修訂（`Revision Plan`）。
- **架構影響範圍**：`ys_codebase/source/agents-workflow/assets/skills/session-audit/SKILL.md`、`docs/agents-workflow/README.md`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 盲眼子代理審計分工與去錨定鐵律**：
  - 步驟 1 由主代理執行 `session-trace --json` 提取結構化統計、五大摩擦訊號與關鍵 Step `<thinking>` 切片（若輸出較大可存於暫存檔或傳遞提取結果路徑／JSON 切片座標）。
  - 步驟 2 & 3 預設強制讀取 `BlindSubagentStandards.md` 並套用 `§5.2` 盲眼專用派發模板（原型 ② 基準對齊冷眼靜態審查），委派唯讀盲眼 Subagent 進行五大摩擦訊號核對與 A/B/C/D 四象限歸因；主代理派發時**嚴禁附帶任何主視窗的事後解釋、心路歷程辯護或誘導性歸類傾向**，並於驗收基準強制注入「嚴格防範將明文規則已載之 `Type D` 滑脫誤判為 `Type C` 健康試錯」之審計判準。
- **[P00:DR-02] 零摩擦快速放行與無 Subagent 環境降級**：
  - 若 `session-trace` 提取結果為 **0 摩擦訊號 (`friction_signals` 為空) 且 0 錯誤步數 (`error_steps == 0`)**，允許免派發 Subagent 直接輸出零摩擦報告（遵循 `BlindSubagentStandards.md` 零硬傷誠實放行與節約冷啟動 Token 原則）。
  - 若處於不支援 Subagent 工具之宿主環境（或屬 `Tier 3` 無 `.jsonl` 僅能依主視窗記憶逆向自白），自動降級由主代理 Inline 執行，並於報告頂部觀測層級顯式標註 `[Inline Fallback]`。

---

## 3. 開放議題與確認紀錄

- [x] 已與開發者確認採用 `Umbrella Plan` 統籌 `sub_01`（`Revision Plan`）與 `sub_02`（`Full Track`），並確認 `sub_01` 盲眼審計流程與降級規則。

