# 技術調研報告：YSCB 核心多層次語系與宿主專有名詞宣告式架構 (R01_core_locale_declarative_architecture.md)

> 調研主題：YSCB 核心多層次語系與宿主專有名詞宣告式架構 (`core_locale_declarative_architecture`)  
> 建立日期：2026-10-28  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  1. **宿主環境專有名詞耦合（Host Dialect Coupling）**：在跨平台 AI Agent 協作中，不同宿主環境（如 `antigravity`、`claude`、`codex`）擁有各自的原生工具名稱與參數語意（例如 Antigravity 的 `read_file` (`StartLine`/`EndLine`) vs. 其他環境的範圍讀檔工具）。若在 CLI 輸出（如 `knowledge-db` 的切片截斷提示）或技能模板中硬編碼單一宿主工具名，將違反跨平台通用性；若全面改寫為抽象通用詞，又會降低特定宿主下 Agent 的第一反射精準度。
  2. **YSCB i18n 定位重塑**：原先路線圖 `i18n_workflow_and_downstream_governance.md` 傾向建立服務下游業務專案的通用 i18n 工具。然而下游業務專案通常已有成熟的專屬 i18n 框架；YSCB 作為「AI Agent Codebase 管理工具基座」，真正的剛需是 **「YSCB 自身各模組（`core`、`dev`、`server`、`knowledge-db`、`agents-workflow`）的宿主方言（Nouns）映射與多語系（`zh-TW`、`zh`、`en`）訊息管理」**。
  3. **模組職責與相依邊界**：由於 `knowledge-db`、`server`、`agents-workflow` 乃至最底層的 `core` 本身都會使用語系與名詞映射，若將其設計為外部獨立模組（`module:locale`），將導致 `core` 反向依賴上層模組的循環相依。
- **調研目標**：
  1. 確立 `locale` 在 YSCB 微內核中的模組歸屬（獨立模組 vs. `core.locale` 內核原語）。
  2. 設計現代化多層優先級退避鏈（Multi-Layer Priority Fallback Chain），同時滿足「宿主專有名詞覆寫（Dialect Overlay）」與「多語系退避（Regional -> Base -> Default Language）」。
  3. 制定各模組透過 `contributes/core.json` 註冊語系資產的宣告式結構，兼顧 `core.json` 檔案精簡度、AI 翻譯語境理解與 100% 確定性靜態校驗。

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：獨立外掛模組 (`module:i18n` / `module:locale`)** | 建立獨立於 `core` 之外的擴充模組，提供 CLI 與 API 供其他模組調用 | 模組職責物理隔離 | `core`、`dev`、`server` 若需使用多語系或名詞解析，會產生對外掛模組的反向或循環相依；未安裝該模組時核心無法運作 | ⭐️⭐️ |
| **方案 B：`core.locale` 內核原語 + `contributes/core.json` 內聯字典** | 直接內建於 `core.locale`，各模組於 `contributes/core.json` 直接內聯宣告所有語系之 `key: value` 字串字典 | 零循環依賴，單檔可見 | 隨著翻譯鍵與語系增加，`contributes/core.json` 迅速膨脹數百行，污染指令樹宣告，且缺乏每個 Key 的語意說明供 AI 參考与校驗 | ⭐️⭐️⭐️ |
| **方案 C（推薦）：`core.locale` 內核原語 + `"locales"` 檔案指標與 `"definition"` 語意解釋契約** | 擴充 `core.locale` 為微內核基礎設施；`contributes/core.json` 僅宣告 `"locales"` 相對檔案路徑映射，並以 `"definition"` 指向語意解釋與佔位符契約檔，其餘 `"<lang-id>"` 指向各語系/方言 JSON 檔 | 1. 解決 `core` 與全模組共用之相依基底問題<br/>2. `contributes/core.json` 保持極致輕量<br/>3. `definition` 同時作為 AI 翻譯上下文 SSOT 與 `contributes check` / `dev check` 靜態契約校驗基準 | 需於 `core` 實作檔案指標解析、多層退避聚合與 `definition` 結構校驗器 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 多層優先級退避鏈 (Multi-Layer Fallback Chain) 與遞迴名詞插值

借鑒現代化 i18n（BCP 47 / ICU Locale Fallback）並結合 YSCB 的 AI 宿主方言需求，`core.locale` 支援配置任意長度的優先級退避鏈：

$$\texttt{[nouns-antigravity | nouns-claude | nouns-codex]} \;\longrightarrow\; \texttt{zh-TW} \;\longrightarrow\; \texttt{zh} \;\longrightarrow\; \texttt{en}$$

- **二階複合解析（Two-Stage Recursive Resolution）**：
  1. **主鍵查找**：當模組請求 `t("knowledge-db:cli.snippet.truncated_hint", rem=50, start=10, end=60)` 時，依優先級鏈查找，於 `zh-TW` 命中模板字串：`"... (+{rem} lines truncated, use {tool.read_range} on lines {start}-{end})"`。
  2. **專有名詞遞迴插值**：解析器識別出佔位符 `{tool.read_range}` 未在呼叫端 `kwargs` 直接傳入（或屬於名詞鍵引用），自動沿**同一條優先級鏈**查找 `tool.read_range`：
     - 若當前環境掛載了 `nouns-antigravity`（第 1 優先級），命中 `` "`read_file` (`StartLine`/`EndLine`)" ``。
     - 若未掛載特定宿主方言，自動 Fallback 至 `zh-TW` 的通用表述 `"宿主範圍讀檔工具（指定起訖行號）"` 或 `en` 的 `"host line-range read tool"`。

### 3.2 宣告式貢獻結構（`"locales"` File-Pointer + `"definition"` Contract）

各模組在 `contributes/core.json` 中僅宣告語系檔案路徑（相對於該模組根目錄，支援自動解析 `module://<mod>/` 與 `module.source://<mod>/`）：

```json
{
  "locales": {
    "definition": "locales/definition.json",
    "nouns-antigravity": "locales/nouns-antigravity.json",
    "nouns-claude": "locales/nouns-claude.json",
    "nouns-codex": "locales/nouns-codex.json",
    "zh-TW": "locales/zh-TW.json",
    "zh": "locales/zh.json",
    "en": "locales/en.json"
  }
}
```

#### ① 語意解釋與契約檔 (`locales/definition.json`)
定義該模組所有合法的語系 Key、語意用途說明（供人類與 AI Agent 理解上下文）與必備插值佔位符清單：

```json
{
  "cli.snippet.truncated_hint": {
    "description": "當 AST 代碼切片超過 --max-snippet-lines 時，附加於切片尾端的截斷提示，引導 Agent 改用宿主範圍讀檔工具。",
    "placeholders": ["rem", "start", "end", "tool.read_range"]
  },
  "tool.read_range": {
    "description": "宿主環境中支援指定行號區間讀取檔案的原生工具專有名詞。",
    "placeholders": []
  }
}
```

#### ② 稀疏方言覆寫檔 (`locales/nouns-antigravity.json`) 與語系檔 (`locales/zh-TW.json`)
- 方言檔（`nouns-*`）與區域變體檔（如 `zh-TW`）允許**稀疏定義（Sparse Override）**，僅需填寫需要覆寫的 Key。
- 靜態校驗器（`contributes check` / `dev check`）依據 `definition.json` 執行三項確定性檢查：
  1. **嚴禁未定義孤兒鍵（No Orphan Keys）**：任何 `<lang-id>.json` 中出現的 Key 必須 100% 存在於 `definition.json`。
  2. **佔位符契約一致性（Placeholder Integrity）**：任何語系字串中使用的 `{var}` 必須與 `definition.json` 宣告的 `placeholders` 一致（防止翻譯時遺漏或拼錯變數名導致執行期 `KeyError`）。
  3. **結構與檔案存在性**：`contributes/core.json` 中 `"locales"` 必須包含 `"definition"` 鍵，且所有指向的 JSON 檔案必須真實存在且語法合法。

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：採納 **方案 C**，以增量演進型主計畫（`2026_10_28_1845_core_locale_and_ecosystem_i18n`）統籌推進。
- **後續行動與 P00 銜接**：
  - **第一階段（`sub_01_core_locale_engine`）**：專注於實現 `core.locale` 核心解析引擎、`contributes/_format.json` 的 `locales` Schema 擴充、`ContributesAggregator` 語系聚合快取，以及基於 `definition` 的靜態校驗器（**不包含各模組實際業務字串遷移接入**）。
  - **後續階段（`sub_02+`）**：待 `sub_01` 基底穩定並驗收後，再逐一開立子計畫將 `knowledge-db`、`agents-workflow`、`dev`、`server` 接入 `core.locale`。

