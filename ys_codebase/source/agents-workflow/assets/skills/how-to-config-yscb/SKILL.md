---
name: how-to-config-yscb
description: 盤點與診斷專案內 YSCB 各模組組態、工作流空間映射及專案角色邊界設定狀況，並於確認後代寫修復配置。僅於顯式輸入 /how-to-config-yscb 或明確要求檢查與設定工具包組態時觸發。
---

# YSCB 專案空間自適應配置與跨模組組態體檢教練 (/how-to-config-yscb)

本 Skill 為開發者提供一站式「專案空間自適應探勘 + 多模組組態健康度體檢 + 專案角色邊界與模組 `contribute.json` 互動式代寫修復」。當專案初次接入 YSCB、新增模組或調整目錄結構時，透過本技能確保專案設定 100% 契合第一方源碼結構並通過三步編譯發布守門。

---

## 核心原則

1. **唯讀探勘先行，草案確認後寫入 (Audit First, Confirm Before Write)**：步驟 1 與步驟 2 僅允許使用唯讀工具與 `🟢 [SAFE]` CLI 指令進行空間探勘與健康度診斷；未經開發者確認診斷卡與配置草案前，**嚴禁自動覆寫任何組態檔**。
2. **全綠免改短路 (All-Green Short-Circuit)**：若專案已完成完整配置且所有模組健康檢查均為 `🟢 [OK]`，直接輸出全綠健康報告卡並詢問是否有特定參數欲微調，嚴禁無意義重複產生長篇草案或覆寫正常設定。
3. **本體空間三處一次對齊 (First-Party Trinity Alignment)**：對專案根目錄執行單次結構探勘後，必須同步對齊「專案角色與主客體空間邊界 (`project_role.md`) + 專案測試框架與規範 (`testing_guide.md`) + 代碼語意檢索空間 (`knowledge-db` `spaces.source`)」，杜絕重複掃描或設定脫節。
4. **雙層組態精準分流 (Config Tier Guardrail)**：跨成員共享的專案規範與目錄映射（如 `paths.plans`、`paths.docs`、`paths.standards`、空間邊界與檢索範圍）強制寫入 `config.project.json` 或 `config://<mod>/contribute.json`；開發者個人 IDE 偏好（如 `release_targets` 選用 `antigravity` / `claude` / `codex`，除非全團隊統一規範）或本機 Port 覆寫強制引導寫入 `config.local.json`，並主動檢核 `.gitignore` 是否已涵蓋 `*.local.json`。
5. **不污染日常啟動 (Zero Startup Pollution)**：完整健檢矩陣與多模組設定指南僅於顯式呼叫 `/how-to-config-yscb` 時載入，絕不塞入日常 `/context-init`。

---

## 執行步驟（四步互動閉環）

當開發者輸入 `/how-to-config-yscb` 時，強制依序執行以下四步閉環：

```markdown
/how-to-config-yscb 配置與體檢閉環：
- [ ] Step 1：全專案設定與空間拓撲自動探勘 (Auto-Discovery & Health Audit)
- [ ] Step 2：呈遞「設定健康度報告與代寫提案卡」並暫停請示 (Diagnosis & Draft Proposal Card)
- [ ] Step 3：確認後代寫修復與三步嚴格編譯驗證守門 (Guided Fix & 3-Step Verification Gate)
- [ ] Step 4：新開實戰 Session 隔離提醒 (Clean-Session Handoff Notice)
```

### Step 1：全專案設定與空間拓撲自動探勘 (Auto-Discovery & Health Audit)

1. **執行基礎健康檢查 (`🟢 [SAFE]`)**：
   - `python __${yscb.host://yscb.py}__ status`（確認宿主環境與已安裝模組清單）
   - `python __${yscb.host://yscb.py}__ config list`（檢視全域與各模組組態值）
   - `python __${yscb.host://yscb.py}__ uri check`（確認語意 URI 綁定路徑是否真實存在）
   - `python __${yscb.host://yscb.py}__ contributes check`（確認跨模組 contributes 與快取完整性）
2. **探勘專案第一方目錄拓撲與 `.gitignore` 防護**：
   - 掃描專案根目錄與頂層結構（如 `src/`、`app/`、`packages/`、`tests/`、`docs/`、`plans/`、`README.md`、`pyproject.toml`、`package.json`、`pytest.ini`、`Makefile` 等），辨識本體業務空間、測試框架與外部工具包黑盒目錄。
   - 檢查專案 `.gitignore` 是否已包含 `*.local.json`（若缺失則列為待修復提醒項）。
3. **檢查 `agents-workflow` 內建設定與第一方畫像錨點**：
   - **工作流目錄映射與發布目標**：檢查 `paths.plans`、`paths.docs`、`paths.standards`（團隊共享規範，應位於 `config.project.json`）與 `release_targets`（個人 IDE 偏好，預設位於 `config.local.json`），並依據當前生效之 `release_target` 從 `contributes` 的 `projections` 設定**動態解析出實際的二層物化目標路徑**（**嚴禁硬編碼 `.agents/` 或 `.claude/`**）。
   - **第一方專案畫像與測試規範**：檢查 [`config/agents-workflow/contribute.json`](`__#{config://agents-workflow/contribute.json}__`) 是否已注入：
     - `PROJECT_ROLE_AND_BOUNDARIES`（指向 `config://agents-workflow/snippets/project_role.md`）
     - `TESTING_SOP_STANDARDS`（指向 `config://agents-workflow/snippets/testing_guide.md`）
4. **依序執行已安裝模組之設定與健康度檢查**：

`__@{HOW_TO_CONFIG_MODULES}__`

---

### Step 2：呈遞「設定健康度報告與代寫提案卡」 (Diagnosis & Draft Proposal Card)

完成 Step 1 探勘後，依檢查結果分流呈遞診斷卡並**立即 End Turn 等待開發者確認**：

- **情境 A：全綠免改短路 (All-Green Short-Circuit)**
  - 若所有基礎檢查、模組體檢與 `project_role.md` / `testing_guide.md` 均為 `🟢 [OK]`：
  - 直接輸出極簡「全綠健康報告卡」，僅詢問：「目前專案與所有已安裝模組組態均為 `🟢 [OK]`，請問是否有特定參數欲微調或需重新生成角色邊界片段？」並立即 End Turn。
- **情境 B：存在未配置或異常項目 (`🟡 [未配置]` / `🔴 [異常]`)**
  - 輸出結構化診斷表（標示 `🟢 [OK]` / `🟡 [未配置]` / `🔴 [異常]`，並明確標註建議寫入層級為 `config.project.json`、`contribute.json` 或 `config.local.json`）。
  - **一次生成「本體空間三處一次對齊草案 (First-Party Trinity Alignment Draft)」**：
    1. **專案角色與空間邊界 (`config://agents-workflow/snippets/project_role.md`，極簡三要素 80~120 Tokens）**：
       - 以 `## 0. 專案角色與主客體空間邊界 (Project Role & Scope Boundaries)` 獨立成節，包含：
       - **① 開發者角色與專案使命**：「你是 `[XXX 專案]` 的開發人員，本專案核心目的為 `[YYY]`。」
       - **② 本體業務空間 (`First-Party Scope`)**：列出探勘出的第一方源碼、測試與文檔目錄，明確標註「日常開發、測試與 `/discuss` 優先級 1~2 排查 **100% 聚焦於此**」。
       - **③ 外部工具包與黑盒依賴 (`External Toolkits`)**：
         - 自動將 `module://`（`.modules/` YSCB 運行空間，僅讀隨包 `README.md`）與常見第三方目錄（`vendor/`、`third_party/`、`external/`、`.venv/`、`node_modules/`）納入，明確規定「預設視為穩定黑盒，嚴禁主動深讀內部實作、嚴禁直接修改（除非在 `/discuss` 完成優先級 1~2 排查並備妥跨界鐵證）」。
         - 依據當前生效之 `release_target` 從 `contributes` 的 `projections` **動態解析出實際的二層物化目錄與規範入口檔**（嚴禁硬編碼 `.agents/` 或 `.claude/`），明確標註為「工作流二層物化唯讀空間（按技能指引唯讀調用，嚴禁手動直接修改，所有客製化一律走第一層 `config://agents-workflow/`）」。
    2. **專案測試規範 (`config://agents-workflow/snippets/testing_guide.md`)**：匯整探勘到的測試框架、單測/回歸執行指令、測試目錄結構與跑測防呆紅線，注入 `TESTING_SOP_STANDARDS`。
    3. **代碼語意檢索空間 (`config://knowledge-db/contribute.json`)** *(若已安裝 `knowledge-db`)*：直接復用上述 `First-Party Scope` 與 `External Toolkits` 清單，對齊 `spaces.source` 的 `include` 與 `exclude`。
  - 若某模組出現進階設定疑問，按需讀取該模組體檢卡底部的隨包手冊連結深挖。
  - 向開發者請示：「是否同意由我直接代寫套用上述配置草案並執行編譯發布？或有哪些目錄邊界需微調？」並立即 End Turn。

---

### Step 3：確認後代寫修復與三步嚴格編譯驗證守門 (Guided Fix & 3-Step Verification Gate)

獲得開發者確認後：

1. **代寫組態與第一層片段**：
   - 遵循第一層扁平慣例寫入 `config://agents-workflow/snippets/{project_role.md,testing_guide.md}`、更新 [`config/agents-workflow/contribute.json`](`__#{config://agents-workflow/contribute.json}__`) 及相關模組之 `config.project.json` / `config.local.json`。
2. **強制執行三步驗證守門 (Mandatory 3-Step Verification Gate)**：
   - **步驟 ①（Schema 校驗）**：執行 `python __${yscb.host://yscb.py}__ contributes check`，確認 `contribute.json` 結構合法。
   - **步驟 ②（Stage 1 編譯與標籤語法零錯誤驗證）**：執行 `python __${yscb.host://yscb.py}__ agents-workflow compile`，確認 **0 Error / 0 Warning**（確保片段內無拼錯 Token 或未加單反引號之裸寫語意 URI 標籤）。
   - **步驟 ③（Stage 2 正式物化投射）**：執行 `python __${yscb.host://yscb.py}__ agents-workflow release`（若首次未設定目標則先引導設定 `release_target`），將更新後的設定與錨點正式投射至當前 `release_target` 對應之規範入口檔與二層技能目錄。
   - *(選配)* 若變更了 `knowledge-db` 空間範圍，執行或提示重建知識庫索引。

---

### Step 4：新開實戰 Session 隔離提醒 (Clean-Session Handoff Notice)

完成三步驗證守門後，輸出收尾卡提醒開發者：

```markdown
### ✅ 專案組態對齊與發布已完成 (Configuration & Release Verified)
- **已更新組態**：[列出實際寫入之檔案路徑]
- **三步守門驗證**：`contributes check` [PASS] / `agents-workflow compile` [PASS] / `agents-workflow release` [PASS]
- **💡 建議開啟全新實戰 Session (Clean-Session Handoff)**：
  - 本次對話已載入大量跨模組組態體檢上下文，且更新後的專案角色邊界與技能已正式物化至當前 `release_target` 目標空間。
  - 建議現在**開啟一個全新的對話視窗**，輸入 `/context-init` 載入最新專案角色邊界，或輸入 `/new-plan` 開始正式開發任務！
```

---

## 常見踩坑指南 (Gotchas)

- **嚴禁在未確認草案前直接改寫組態**：Step 1 與 Step 2 必須維持純唯讀探勘，唯有在開發者明確同意 Step 2 診斷與草案卡後，方可進入 Step 3 寫入設定。
- **嚴禁在草擬 `project_role.md` 時硬編碼 `.agents/` 或 `.claude/`**：必須依據當前生效之 `release_target` 從 `contributes` 的 `projections` 設定動態解析出實際二層物化路徑。
- **修改 `contribute.json` 後切勿遺漏三步驗證**：任何 `contribute.json` 或片段變更後，必須依序執行 `contributes check`、`agents-workflow compile` 與 `agents-workflow release` 方能生效。
