# 需求規格說明書 (Requirements Specification)

> 功能名稱：2026_10_30_1605_code_optimizer_skill  
> 建立日期：2026-10-30  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (High)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `code-optimizer` 純手動觸發與前置雙維度定錨（範圍 × 生命週期） | 1. 建立 `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md`，Frontmatter `description` 嚴格遵循主動指令型極簡契約（`針對既有業務程式碼執行五維度靜態診斷、業務階段邏輯聚合與行為無損重構。僅於顯式輸入 /code-optimizer 時觸發，嚴禁主動觸發。`），不掛載於 `AGENTS_SKILL_ROUTING` 被動路由表。<br>2. 步驟 1 強制規範：若開發者呼叫時未同時明確指定「檢視範圍」與「生命週期模式」，必須先向開發者詢問確認並等待回覆，嚴禁 Agent 自行猜測。<br>3. 檢視範圍採**包含式階層（`全專案 ⊃ 單一模組 ⊃ 單一檔案`）**，大範圍完整包含小範圍之微觀結構分析（`S1` 業務階段拆解、`S2` 無狀態邏輯剝離、`S3~S6`）。<br>4. 生命週期模式由開發者顯式指定為 `Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)` 或 `Mode B：維護期 / 嚴守向下相容 (Compatibility Mode)`；且於 `Mode B` 明確規定：對外公開入口與插件契約維持 100% 門面相容，但**若經嚴格查驗確認純屬內部工具函式（非公開匯出/註冊契約且 0 外部跨模組調用），同樣直接執行破壞性變更與收斂**。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | 調研計畫立項 (`R01`) 與三大流轉出口裁決閉環 | 1. 步驟 1 獲開發者確認範圍與 `Mode A/B` 後，依 JIT 原則於 `__${project://plans}__/` 建立調研計畫目錄（`P00_discuss.md` + `R01_code_optimization_audit.md` + `changelog.md`）。<br>2. 步驟 2 執行環境感知探索與五維度（`D1`~`D5`）靜態診斷、擬定六大策略（`S1`~`S6`）重構處方箋，正式落檔於 `R01_code_optimization_audit.md`。<br>3. 步驟 3 呈遞極簡調研診斷卡並強制 End Turn，向開發者詢問三大流轉出口：① 立即原地升級實作（依範圍與規模轉入 `Fast Track`、`Full Track` 或 `Umbrella`）、② 轉入技術儲備（`/roadmap` 或 `/todo`）、③ 維持現狀結案（`Concluded`）。<br>4. 步驟 4（當選擇出口 ① 時）按需讀取 `references/refactoring-playbook.md` 執行外科手術式無損重構、回歸測試與 Before/After 結構量化對照。 | P0 | [P00:DR-03] |
| **FR-03** | 三大漸進式揭露參考手冊 (`references/`) 與子代理委派契約 | 1. `references/exploration-and-delegation.md`：定義環境感知探索協議、支柱一唯讀探索子代理量化觸發門檻（單檔 $> 400$ 行、$\ge 3$ 檔或跨模組多階調用追蹤時派發）、開發者已拍板 `Mode A/B` 傳入約束（子代理不自行猜測 `Mode A/B`，改依指定模式盤點需同步改寫之調用點或需保護之公開門面 + 可直接破壞性收斂之 0 外部調用內部工具函式），以及 $\le 400$ Tokens 高密度回傳契約（0 原始碼傾倒）。<br>2. `references/diagnostic-matrix.md`：定義跨語言五維度靜態診斷矩陣（`D1` 職責內聚與抽象層級、`D2` 調用耦合與拓撲健康度、`D3` 控制流與認知複雜度、`D4` 介面契約與資源生命週期、`D5` 架構邊界與專案慣例）及 `P0 / P1 / P2` 嚴重度判準。<br>3. `references/refactoring-playbook.md`：定義六大通用軟工重構策略（`S1` 業務階段拆解與主幹管線化、`S2` 狀態依賴分析與無狀態邏輯剝離、`S3` 跨方法同構模式聚合、`S4` 控制流扁平化與表驅動分派、`S5` 資料團塊封裝與結構化契約、`S6` 正交職責之物理模組拆分）與 `Mode A / Mode B` 處置指引。 | P0 | [P00:DR-02], [P00:DR-03], [P00:DR-04] |
| **FR-04** | 防過度設計四大紅線與跨語言工具自適應規範 | 1. 於 `code-optimizer/SKILL.md` 內嵌 `D1~D5` 與 `S1~S6` 速查表及四條防過度設計紅線：① 禁止教條式套用設計模式（No Pattern Mania）、② 禁止碎紙機式過度拆分（No Nano-Functions / Fragmentation）、③ 禁止竄改錯誤與邊界語意（Preserve Error Semantics）、④ 自我解釋優先於廢話註解（Self-Documenting over Noise Comments）。<br>2. 內文工具名稱全面採用 Stage 2 宿主專有名詞佔位符（`` `__%{agent_tool.file_read_range}__` ``、`` `__%{agent_tool.file_edit}__` ``、`` `__%{agent_tool.shell_exec}__` `` 等），跨技能與模板連結全面採用單反引號包覆之 Stage 2 語意 URI（`` `__#{...}__` ``、`` `__${...}__` ``）。 | P0 | [P00:DR-04] |
| **FR-05** | `CODE_OPTIMIZER_STANDARDS` 錨點註冊、生態系連動與測試覆蓋 | 1. 於 `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` 與 `_manifest.md` 註冊 `code-optimizer` 技能（內建純 Skill 擴充至 19 個）與 `CODE_OPTIMIZER_STANDARDS` Token（本模組 23 個、全系統標準錨點 24 個）。<br>2. 同步更新 `development-sop/SKILL.md` §1 生命週期工作流中樞分流、`how-to-yscb/SKILL.md`、以及 `skill-creator/SKILL.md` 與 `skill-creator/references/extension-guide.md` 之全系統 Stage 1 錨點地圖（補入 `CODE_OPTIMIZER_STANDARDS`）。<br>3. 於 `ys_codebase/source/agents-workflow/tests/test_compiler.py` 擴充自動化測試並更新既有技能/Token 集合斷言，同步更新 `docs/agents-workflow/{README.md,user_guide.md}`。 | P0 | [P00:DR-01], [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 開發者輸入 `/code-optimizer` 時未指定目標範圍或未指定 `Mode A / Mode B` 生命週期模式 | 嚴禁 Agent 自行猜測模組是否已釋出或擅自掃描全專案；強制於步驟 1 先向開發者提問確認「檢視範圍（全專案 / 單一模組 / 單一檔案）」與「生命週期模式（`Mode A` 收斂期 vs. `Mode B` 維護期）」後再建檔推進。 |
| **EC-02** | `Mode B（維護期）` 下遭遇內部輔助函式或私有方法腐化 | 若經全空間調用圖譜（如 `callers`）與匯出宣告（如 `__all__` / `export` / `contributes`）**嚴格查驗確認 0 外部跨模組調用且非對外公開契約**，強制直接執行破壞性收斂與重構（同步更新模組內調用點），嚴禁為純內部工具函式留下多餘的相容轉發層。 |
| **EC-03** | 單一中小型檔案（$\le 400$ 行且單檔範圍）優化時之子代理過度派發風險 | 依量化規模門檻短路：單一中小型檔案由主代理直接以二階段漏斗檢索內聯完成，免除無謂的子代理冷啟動開銷；僅於 $\ge 3$ 檔、單檔 $> 400$ 行或跨模組多階調用追蹤時委派唯讀探索子代理。 |
| **EC-04** | 將業務程式碼重構錯誤導向 `Revision Plan` 或未經出口確認即直接修改業務代碼 | 於 `SKILL.md` 明確禁止將業務邏輯重構分流至 `Revision Plan`（僅允許轉入 `Fast Track`、`Full Track` 或 `Umbrella`），且在 `R01` 調研診斷卡未獲開發者拍板選擇「出口 ① 立即實作」前，嚴禁修改任何業務原始碼。 |
| **EC-05** | Stage 1 / Stage 2 語意標籤未包覆反引號或宿主專有名詞拼寫錯誤導致編譯警告 | 所有跨空間語意標籤（`` `__@{...}__` ``、`` `__#{...}__` ``、`` `__${...}__` ``、`` `__%{...}__` ``）強制以單反引號包覆，並通過 `contributes check` 與 `agents-workflow compile` 零錯誤、零 `[compiler:warning]` 驗證。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 上下文經濟與行數預算 | `code-optimizer/SKILL.md` 主體嚴格控制在 $\le 180$ 行；附屬 `references/*.md` 皆維持單層深度（1-level deep），超過 100 行之參考檔頂部必須附帶 `## 目錄 (Contents)`。 |
| **NFR-02** | 零第三方依賴與跨平台投影合規 | 100% 相容 `antigravity`、`claude`、`codex` 三大 `release_target` 投影；`dev check agents-workflow` 與 `dev test agents-workflow -q` 100% 通過且沙盒零殘留。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` 雙軌 `description` 與全技能集合測試同步**：`ys_codebase/source/agents-workflow/tests/test_compiler.py` 中之 `test_ft_08` 與 `test_ft_11` 對內建技能集合（`expected_skills`、`command_driven_skills`）與 Stage 1 Token 數量（原 22 個模組內建 / 23 個全系統）設有精確集合斷言，新增 `code-optimizer` 與 `CODE_OPTIMIZER_STANDARDS` 時必須同步更新 `skill-creator/references/extension-guide.md` 與對應測試集合斷言。
- **`[!NOTE]` 同技能相對路徑 vs. 跨空間語意 URI**：依 `[DN-AW-14]`，`code-optimizer/SKILL.md` 引用同目錄下 `./references/*.md` 一律使用標準相對路徑，引用其他技能或模板則使用單反引號包覆之 `` `__#{module://agents-workflow/...}__` ``。

