# 技術路線圖：跨語系工作流體驗與下游國際化工程治理藍圖 (Roadmap)

> 主題：跨語系工作流體驗與下游國際化工程治理藍圖 (`i18n_workflow_and_downstream_governance`)  
> 歸檔日期：2026-10-29  
> 狀態：Backlog  
> 目標範疇：`agents-workflow`、`core`、`knowledge-db`、`dev`、`server`、`module:i18n`（獨立擴充模組）  
> 前置解鎖條件：完成 `2026_10_28_1845_core_locale_and_ecosystem_i18n`（`core.locale` 內核引擎與宿主專有名詞優先級鏈穩定落地）及 `declarative_track_schema_and_domain_packs`  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
- **當前階段策略聚焦於專有名詞（Dialect / Host Proper Nouns）與母語 `zh` 最終保底**：在 `2026_10_28_1845_core_locale_and_ecosystem_i18n` 中，`core.locale` 已完成多層優先級退避鏈與二階遞迴專有名詞插值引擎，並策略性收斂為「最終 Fallback 固定採用開發團隊母語 `["zh"]`、優先服務各宿主環境專有名詞（如 `nouns-antigravity`、`nouns-claude`、`nouns-codex`）」，暫不散射處理 `en` 等多語系文本翻譯。
- **非繁體中文開發者之母語閱讀門檻與驗證耦合**：目前各模組 CLI 提示、`P00`~`P07` 模板與 `PlanVerifier` 標頭檢核預設以繁體中文 (`zh`) 為主；未來若跨國團隊希望切換為 `en` 或 `ja` 語系撰寫開發計畫與檢視 CLI，尚待補齊各模組 `en.json` 語系包與語系無關檢核機制。
- **多語系文檔維護成本與 Token 壓縮需求**：在國際開源推廣或追求極致 Context Window 空間（英文 Token 消耗較繁體中文少約 25%~40%）時，若人工全量翻譯 `README.md`、`docs/` 與 `SKILL.md`，不僅成本高昂，且易誤傷 `__@{...}__`、HTML 託管註解與語義 URI。
- **下游多語系業務專案缺乏自動化語系包契約檢查**：開發多語系產品時，常發生語系檔漏 Key、廢棄 Key（Orphan Keys）或格式化變數佔位符不一致導致執行期崩潰（母倉內建模組已可透過 `core.locale.validate_module_locales` 與 `dev check` 校驗 `locales/definition.json`，下游通用專案工具箱則待封裝）。

### 1.2 現況與影響範圍評估
- `agents-workflow` 的 `verifier.py` 與模板目前綁定單一語系標頭格式。
- 系統尚無 2x2 組態矩陣中的 `locale`（專案產出語系）與 `interaction_locale`（個人互動語系）錨點定義。

### 1.3 核心根因
1. `PlanVerifier` 尚未將標頭欄位與章節比對抽離為語系無關之 Canonical Keys 或動態語系模板映射。
2. 缺乏具備 YSCB 語法保護罩（Syntax & Token Guard）與 SHA-256 段落指紋比對的增量文檔翻譯輔助管線。
3. 缺乏服務下游專案的確定性語系包結構與佔位符契約檢查器（`check-locales`）。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：將跨語系混入核心重構主線同步全量改寫** | 在重構 `agents-workflow` 狀態機的同時，直接將所有核心模組字串改為傳統 `gettext` 字典查找 | 一次到位 | 嚴重分散核心架構演進注意力，造成多維度變數干擾與維護複雜度暴增 | ⭐️⭐️ |
| **方案 2：與核心主線完全脫鉤，採「人機雙軌分層 + 增量保護編譯 + 獨立 `module:i18n`」漸進實施** | 將 `i18n` 列為正交支線：對內先解耦 `verifier.py` 語系錨點與 `locale` 組態（ACI 機器輸出鎖定標準化代號、Human UX 輕量映射），再按需擴充增量文檔同步與下游 `check-locales` 工具箱 | 100% 不干擾核心主線、執行期 0 額外 Token 成本、嚴格保護 `<yscb-token>` 與 URI 語法安全 | 分階段推進，需待 `TrackSpec` 穩定後啟動 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（核心主線全量字典化） | 方案 2（正交分層架構 + 獨立 `module:i18n`） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 低（極易破壞 ACI 機器解析穩定度） | 高（人機通道分離，ACI 維持 100% 穩定） |
| **後續維護難度 (Maintenance)** | 極高 | 低（SHA-256 增量指紋僅處理變更段落） |
| **可靠性 (Reliability)** | 低（翻譯易破壞語義佔位符） | 高（內建 AST / Regex 語法保護罩強制校驗） |
| **落地難度 (Implementation)** | 高 | 中（可依需求分三階段獨立交付） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# Phase 1（核心工作流語系破冰）：
# - 於 config.project.json / config.local.json 支援 locale 與 interaction_locale
# - 解除 verifier.py 對硬編碼中文字串之依賴（支援 Canonical Key 雙軌或依 locale 載入對應模板標頭）
# - 透過 Computed Token 向 AGENTS.md 注入語系守則，並支援 Lean English Skill 投影選項

# Phase 2（生態系文檔增量同步與雙軌 CLI 輸出）：
# - 實作 `yscb i18n sync-docs`：以 SHA-256 計算 Markdown 段落差異，鎖定保護 `__@{...}__`、HTML 託管區塊與語義 URI，交由宿主 Agent 翻譯後執行語法完整性驗證
# - ACI 輸出（--json、驗證器結構化報錯）固定維持標準格式；Human UX 輸出（status, help, list）支援輕量語系映射

# Phase 3（下游專案 i18n 工程治理套件）：
# - 實作確定性 `yscb i18n check-locales`：檢查多語系 JSON/YAML/PO 之 Missing/Orphan Keys、變數佔位符與 HTML 標籤一致性、UI 長度溢位預警
# - 視下游業務剛需評估基於 AST 與領域 Glossary 之進階掃描輔助
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 貫徹「關注點單一化（Single Focus）」原則，在 Stage 1 ~ Stage 3 核心工作流演進完成前維持 `Backlog` 凍結狀態，待開源推廣或跨語系專案需求浮現時按階段啟動。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1（工作流語系脫鉤 MVP）**：完成 `verifier.py` 語系無關化、2x2 `locale` 組態讀取與英文版 `P00`~`P07` / `SKILL.md` 投影支援。
2. **Stage 2（增量文檔編譯器與雙軌 CLI）**：實作帶 `<yscb-token>` 保護罩之 `sync-docs` 差異提取與驗證管線，並為人類高頻 CLI 加上輕量語系表。
   - **⚠️ `server` 等模組擴充在地化之相依版本約束提醒**：`server` 目前尚未宣告 `locales` 故維持 `"core": ">=1.1.0"`；當未來於 Stage 2 為 `server`（或任何新模組）新增 `locales/` 並於 `contributes/core.json` 註冊 `"locales"` 時，**必須同步將其 `manifest.json` 之 `dependencies.core` 調升為 `">=1.2.0"`**（`dev check` 已同步配置靜態攔截守門）。
3. **Stage 3（下游業務 `module:i18n` 工具箱發布）**：封裝 `check-locales` 多語系包契約檢查器與專屬 `i18n-sop` 技能。

