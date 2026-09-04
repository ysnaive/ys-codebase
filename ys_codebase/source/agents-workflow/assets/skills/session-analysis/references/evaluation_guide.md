# 對話歷程通用自檢與坑點防禦手冊 (Session Analysis & Pitfalls Guide)

本手冊為 `session-analysis` 技能之專屬參照手冊，定義非 Antigravity 環境下的通用手動評估方案，並闡述歷程分析中的四大核心坑點與防呆公理。

---

## 🧭 1. 通用降級手動評估方案 (Universal Fallback Protocol)

當在非 Antigravity 環境（如 Cursor, Windsurf, VS Code, Roo Code, 終端 CLI）執行分析工具腳本 `scripts/analyzer.py` 回報不支援時，Agent **必須依據本章節通則進行專案產物自檢**：

### 1.1 分析切片範圍鎖定鐵律
- **法定範圍**：**`上次分析後 (不包含) ~ 本次分析前 (不包含)`**。
- 若為 Session 首次分析，範圍為對話初始至本次指令前；若存在前次分析，嚴格排除前次分析之報告輸出與本次觸發分析之對話指令自身。

### 1.2 專案產物四步自檢法 (Git & Plan SSOT)
1. **變更邊界核驗 (Git Diff)**：
   - 執行 `git status -s` 與 `git diff --stat`，客觀統計本次任務涉及之修改檔案清單與代碼行數。
2. **計畫與歷程核驗 (Plan Changelog)**：
   - 檢查 `plans/<active_plan>/changelog.md`，核對階段流轉紀錄是否完整、決策標籤 (`[Phase:DR-XX]`) 是否依法登記。
3. **授權守門與紀律核驗 (Guardrails Audit)**：
   - 檢視終端執行歷程，確認是否有未授權調用 🔴 授權守門指令（如 `dev bump`、`dev release`、`remove`、`rollback`）。
   - 核對是否遵循「零臆測」、「SSOT 對話節流」、「單 Turn 邊界」三大核心原則。
4. **Context 視窗與資源定性估算**：
   - 依據當前活躍上下文與近期檔案讀取量，客觀推估活躍 Context 規模（通常約 30k ~ 100k Tokens），並明確標記 System Prompt 佔比。

---

## ⚠️ 2. 四大核心坑點與防禦公理 (The 4 Pitfalls & Guardrails)

### 坑點 1：誤將日誌行數或 Tool Output 視為 Steps 數
- **現象**：許多日誌或記錄中包含大量 Tool Output（如 `VIEW_FILE` 輸出、`RUN_COMMAND` 終端回傳）。若直接取日誌總行數作為 Steps，會把工具回傳誤當成模型重新發起 API 呼叫。
- **防禦公理**：
  > [!CAUTION]
  > **真實 Steps 嚴格僅限於模型實際推論輪次 (Planner Invocations)！**  
  > 工具回傳結果屬於執行負載，絕非獨立推論步驟。

---

### 坑點 2：系統固定上下文盲目乘算 (The Multi-Million Token Illusion)
- **現象**：系統前置上下文（原生工具 Schema、身分設定、行為準則）約 7,500 ~ 8,000 Tokens。若直接乘上幾百次 Steps，會得出「System Prompt 吃掉 600~800 萬 Token」的荒謬虛胖數字。
- **真相與快取機制**：
  - 純靜態 System Prompt 在現代 LLM（如 Gemini API / KV Cache）享有近乎 100% 的 Prompt Caching 命中率。
  - 後續模型調用根本不需要重新運算這 7.8k Tokens 的矩陣乘法，實際物理開銷與計費極低。
- **防禦公理**：
  > [!IMPORTANT]
  > **Token 呈現必須以「單輪實時 Context 視窗分佈」為主！**  
  > 呈現當前 Context（例如 50k）中 System Prompt 佔約 15%，並顯式註記 Prompt Cache 命中機制，嚴禁以單純累積乘算誤導使用者。

---

### 坑點 3：分析切片邊界混淆
- **現象**：將「上一次分析報告的輸出」或「本次正在執行分析的指令與對話」混入統計，導致重複計算或自我引用污染。
- **防禦公理**：
  > [!IMPORTANT]
  > **分析範圍強制雙端開區間：`上次分析後 (不包含) ~ 本次分析前 (不包含)`！**

---

### 坑點 4：主觀吹捧評語與情緒化形容詞
- **現象**：報告中出現「表現良好」、「非常精確」、「時機恰當」、「商業可用」等無意義主觀修飾詞。
- **防禦公理**：
  > [!WARNING]
  > **除最終「優化建議」外，全篇報告嚴禁一切主觀形容詞！**  
  > 僅允許純客觀統計數據、次數、百分比與客觀事實描述。
