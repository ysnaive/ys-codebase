<!-- YSCB_AGENTS_BEGIN -->
# Agent 專案行為準則與防呆紀律規範 (Agents Standards)

本文件定義 Agent 在專案內執行任務時**必須強制遵守**的通用硬性核心原則、防呆紀律與工程規範。

---

## 1. 核心原則與防呆紀律 (Core Principles & Guardrails)

### 📌 核心三大原則 (Core Axioms)
1. **零臆測 (Zero Speculation)**：任何不確定的技術細節，必須與開發者釐清後才能推進。嚴禁自行假設需求、猜測 API 行為或臆測解法。
2. **剛性追溯 (Traceability)**：從需求到程式碼的每一步決策，必須 100% 具備文件記錄可回溯（`P00 語意` ➔ `FR/EC` ➔ `[{Phase}:DR-XX]` ➔ `API 簽名` ➔ `程式碼` ➔ `測試`）。
3. **分級管控 (Graduated Control)**：依三大分流層級選擇 Level 0 (Fast Track)、Level 1 (Full Track) 或 Level 2 (Umbrella 主計畫模式)。

### 🚨 執行與推進紀律（絕對禁止條款）
- **嚴禁連發**：一次回應 (Turn) **最多只能執行一個 Phase 或一個獨立動作**。產出階段文件後，必須以明確文字詢問開發者並**立即 End Turn** 等待回覆。
- **Checkpoint 強制等待**：產出 Phase 文件後，必須等待開發者明確給予推進指示，絕對禁止 Agent 自行假設通過並推進下一個 Phase。
- **「問答 $\neq$ 推進」防呆條款 (Clarification $\neq$ Advancement Disambiguation)**：
  - **回覆意圖二分法**：Agent 必須嚴格區分開發者的回覆類型：
    - **類型 A：局部解答 / 意見回饋**（例：解答提問、提供特定參數、修改某欄位）➔ Agent **僅可更新當前 Phase 文件**，呈遞更新摘要與變更處，並明確詢問「已為您更新 [項目]，請問本階段內容是否確認無誤，可指示推進至下一階段？」並**立即 End Turn 等待**，**絕對禁止直接跨入下一 Phase**！
    - **類型 B：推進 / 定稿指令**（例：「確認」、「通過」、「進入 Phase X」、「沒有其他問題了」）➔ 只有接收到此類明確信號，Agent 才能標記當前 Phase 為 `Confirmed` / `Passed` 並推進。
  - **嚴禁複合推論**：絕對禁止 Agent 自行假設「因為開發者解答了疑問 ➔ 代表整份文件無其他問題 ➔ 自動推進」。
  - **更新後二次確認 (Update & Re-confirm Loop)**：文件修訂後必須重新呈遞修改摘要，並重新等待開發者明確給出類型 B 指令。
- **嚴禁空降實作**：未經規劃定稿並獲得開發者確認前，**絕對禁止直接編寫或修改原始碼**。
- **確定性文檔讀取失效阻斷鐵律 (Deterministic Document Read & Anti-Fuzzy Fallback Guardrail)**：
  - **確定性內容定義**：指 SOP 工作流、規範手冊、註冊協議或指引中**顯式指定之實體文檔或標準檔案路徑**（例：`AGENTS.md`、`AgentsCliGuild.md`、`CHANGELOG.md`、`STANDARDS.md`、指定 Phase 模板等）。
  - **🚨 絕對禁止同義詞搜尋與模糊探勘**：當讀取指定文檔發生失敗或無法定位時（如 404 FileNotFound / 路徑解析錯誤），**絕對禁止** Agent 自主發起 `knowledge-db search`、同義詞搜尋、全專案模糊搜尋或遍歷目錄來「擅自隱藏缺陷並猜測替代檔案」！
  - **即時呈報與阻斷**：必須立即停止動作，向開發者明確呈遞：「指定文檔路徑 `[檔案路徑]` 讀取失敗，無法定位」，直接暴露底層路徑缺陷與真實報錯，等待開發者指示或修正。

### 🛡️ 除錯排查與範疇保護鐵律 (Scope-Bound Debugging & Anti-Drift Guardrails)
- **「由近及遠、本體優先」排查階層 (Local-First Hierarchy)**：遇到錯誤或異常時，Agent **必須優先徹底排查當前組件本體內部邏輯與呼叫端傳參配置**。在未 100% 排除自身問題前，**絕對禁止直接跨模組深入下游/外部模組進行修改**。
- **修改範疇越界阻斷 (Out-of-Scope Modification Gate)**：若排查發現問題似乎位於超出本次 Dev Plan 承諾範圍的外部模組，**Agent 絕對禁止擅自修改外部代碼**！必須立即發起 `/Discuss` 向開發者呈遞調用證據，由開發者判定。
- **阻斷盲目淺層修補 (Anti-Trial-and-Error Loop)**：同一問題**連續 2 次修復失敗**，或修復將破壞既有架構/API 簽名時，必須強制停手發起 `/Discuss` 進行 5-Whys 根因分析。

### ⚙️ 工具調度與 CLI 守門鐵律 (Tool Execution & Safety Guardrails)
- **CLI 指令 Default-Deny 守門**：
  - **查表比對**：Agent 在欲調用 `python yscb.py` 宿主或子模組指令前，必須先比對 `AgentsCliGuild.md`。僅在當前情境 100% 符合 `✅ 推薦/適用情境` 時方可執行。
  - **Default-Deny 閉環**：若欲執行之指令或參數組合未列於表、無對應推薦欄位、或命中 `🚨 絕對禁止/不適用情境`（例：跑測前手動 build、未授權 bump 版本、日常跑 test --all、調用內部 op-test 等），**絕對禁止擅自執行**！必須向開發者確認意圖與預期指令，獲明確授權後方可執行。
- **目錄歸檔紀律與 CLI 調度優先**：所有計畫預設留存原位（plans），**嚴禁 Agent 主動歸檔**，僅在開發者明確下達歸檔指令時才執行歸檔工具。

---

### 🏛️ 模組開發與 Dogfooding 自引用空間閉環鐵律 (Module Dev & Dogfooding Axiom)

本模組提供本地擴充模組開發與測試設施。凡安裝 `dev` 模組之專案，Agent 進行生態系模組開發時**必須強制遵守**以下三大空間隔離與雙軌標準閉環流水線：

#### 1. 三層空間權限矩陣
- **空間 ① 源碼開發空間 (`source/<module>/`)**：【唯一源碼來源 (SSOT)】所有代碼、腳本、工作流修改 **100% 必須在此空間進行**。
- **空間 ② 測試驗證空間 (`cache://dev/sandbox/`)**：【品質守門閘門】所有自動化測試在獨立隔離沙盒中執行（`python yscb.py dev test <module>` 或 `python yscb.py dev test --all`），未 100% 通過前嚴禁放行更新自引用產物。
- **空間 ③ 自引用運行消費空間 (`modules/<module>/` 與 `.mirror/`)**：【部署運行產物】視為編譯產物，**嚴禁手動直接修改**，一律由 CLI 同步物化。

#### 2. 雙軌開發與發布閉環流水線 (Dual-Track Development & Release Pipeline)

- **軌道 A：日常開發與本地自引用調試 (Dogfooding Track)**（未晉升版本之日常修改與調試）：
  1. `Step 1 (Source)`：編輯 `source/<module>/...` (唯一 SSOT)。
  2. `Step 2 (Build/Check)`：`python yscb.py dev check <module>` 靜態稽核，或 `python yscb.py dev build <module>` 產出本機開發包。
  3. `Step 3 (Regression)`：實機執行 `python yscb.py dev test <module>` 100% Passed。
  4. `Step 4 (Dogfooding Sync)`：透過 `@build` 直裝通道部署至 `modules/`：`python yscb.py install <module>@build --force`。

- **軌道 B：版本晉升與正式發布交付 (Release & Bump Track)**（獲指示進行 bump、release 或結案交付）：
  1. `Step 1 (Bump)`：執行版本遞增 `python yscb.py dev bump-[revision|patch|minor|major] <module>`。
  2. `Step 2 (Regression)`：實機執行 `python yscb.py dev test <module>` (或 `dev test --all`) 100% Passed。
  3. `Step 3 (Release)`：正式打包發布 `python yscb.py dev release <module>` (產出純淨發布包至 `build/` 與 `release/`)。
  4. `Step 4 (Formal Sync)`：以正式發布通道同步至環境：`python yscb.py install <module> --force`（或 `python yscb.py update <module>`）。

#### 3. 🚨 發布、安裝與部署免測防呆鐵律 (Release & Install Guardrails)
- **嚴禁未獲授權主動正式發布**：日常熱開發中未獲開發者明確指示 (如未下達 bump/release 指令) 前，**絕對禁止**自主切入軌道 B 執行 `dev release`，應一律維持軌道 A (`@build`) 部署開發版。
- **部署後免重複測試鐵律 (No Redundant Test Post-Deployment)**：在通過沙盒測試並完成 `@build` 本地部署或正式版覆蓋安裝後，**不需要且嚴禁重複調用 `dev test` 跑測**！安裝部署僅為產物物化與環境同步操作，部署完成後直接結案交付。

#### 4. 📦 語意 URI 與源碼解耦鐵律 (VFS & Decoupling Governance)
- **嚴禁硬編碼相對路徑**：模組內部跨空間檔案存取**嚴禁使用硬編碼之宿主相對路徑**，必須 100% 使用語意空間協議（`storage://`、`cache://`、`config://`、`module.source://`、`module.build://`、`module.release://`）。

### 🧠 知識庫檢索與代碼搜尋規範 (Knowledge-DB Search Standards)

#### 1. 搜尋工具二分流決策矩陣 (Tool Routing Matrix)

| 查詢特徵與情境 | 推薦工具 | 適用說明 |
| :--- | :---: | :--- |
| **純標點 / 語法錨點 / 字串常數**（例：`__#{`、`__@{`、`<!--`、`[x]`、`TODO:`、`0x7FFF`） | `grep_search` | 標點會被分詞器過濾；直接逐字節精確匹配行號。 |
| **精確符號定位**（已知唯一全名，僅需取得單檔行號） | `grep_search` | 單檔行位址定點。 |
| **代碼標識符 / 類別 / 函式**（例：`PIDController`、`ThesaurusEngine`） | `knowledge-db search -s` | 取得駝峰/底線拆解、Docstring 摘要與上下文代碼切片。 |
| **業務概念 / 架構邏輯 / 多詞組合**（例：`三階加權展開`、`尋路演算法`、`佔位符解析`） | `knowledge-db search -s` | 享有同義詞擴展、多跳鏈式傳播與 BM25 加權排序。 |

---

#### 2. 語意廣搜心法：拒絕狹隘關鍵字 (Semantic Breadth Formulation)

- **初始檢索目的**：在未掌握專案全貌前，優先用語意化詞組抓取宏觀架構廣度，嚴禁直接使用單一檔名或表面變數孤立搜尋。
- **三維語意查詢公式**：
  $$\text{Query} = \text{[領域概念]} + \text{[架構機制]} + \text{[核心動詞]}$$
  - 例：「排查 ContextInit 佔位符失效」 ➔ `search '佔位符 語意URI 拓撲映射 發布流水線' -s`
  - 例：「詞庫改為 contribute 提供」 ➔ `search '詞庫解耦 contributes 宣告式注入 跨模組聚合' -s`

---

#### 3. 簽名 + 情境複合檢索 (Signature + Context Co-Search)

- **通用簽名消歧義**：遇到通用名稱之函式或方法（如 `resolve`、`compile`、`update`、`create`、`validate`、`init`），強制採用 **「簽名詞 + 業務情境詞」** 複合檢索。
- **Docstring 交叉加權**：簽名詞命中函式標頭，情境詞命中 Docstring 註解，過濾同名無關簽章。
  - 例：尋找佔位符路徑解算 ➔ `search 'resolve 佔位符 拓撲 產物工廠' -s`（避免單搜 `resolve`）
  - 例：尋找模組升級與快照 ➔ `search 'update 模組升級 雙軌快照' -s`（避免單搜 `update`）

---

#### 4. 兩階段檢索流程 (`--ftype` Routing)

- **Phase A (宏觀脈絡 / 廣度)**：`python yscb.py knowledge-db search '<語意化情境詞組>' --ftype=md -s`（或不加 `--ftype` 全空間檢索）。
- **Phase B (微觀實作 / 深度)**：`python yscb.py knowledge-db search '<簽名詞 業務情境詞>' --ftype=c,cpp,py -s`。

---

#### 5. 執行紀律 (Guardrails)

1. **第一反射原則**：凡標識符、概念、功能探索與架構查詢，強制調用 `python yscb.py knowledge-db search`。
2. **新詞主動補足鐵律**：在分析、修改或排查途中，凡遭遇當前上下文未曾具備之任何新名詞、新欄位、新協議或未知概念，嚴禁憑字面臆測，必須即刻將其轉化為語意化查詢（`python yscb.py knowledge-db search '<新詞 業務情境>' -s`），主動補足對應知識上下文後方可繼續推進。
3. **禁止模糊探索**：嚴禁以 `grep_search` 進行未指定精確符號之全專案正則遍歷或關鍵字廣蒐。
4. **禁止盲目翻讀**：嚴禁在未定位精確行位址前使用 `list_dir` / `view_file` 盲目列出目錄或整檔閱讀。
5. **強制切片預覽**：檢索強制附加 `-s`（或 `--snippet`）直接獲取帶行號之上下文代碼切片與 Docstring。
6. **註解結構保護**：編寫或重構 Public API 時，嚴禁破壞標準 Docstring 註解結構。
<!-- YSCB_AGENTS_END -->

## 4. 專案特化工程規範 (Project Specific Standards)
*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*


