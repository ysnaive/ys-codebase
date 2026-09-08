# 需求規格說明書 (Requirements Specification)

> 功能名稱：yscb-module-dev 技能手冊全方位品質優化與能力補齊 (Skill Quality Refinement & Capability Completion)  
> 建立日期：2026-09-08  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

### 📚 軌道一：技能手冊與規範補全 (Skill & Guild Refinement)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 / 報告標籤 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 模組腳手架與起手式規範 | 於 `cli_and_commands.md` 與 `SKILL.md` 正式收錄 `python yscb.py dev create <name> [--desc="..."]`。說明其用途為建立標準模組骨架，並詳細列出自動生成之 8 大標準檔案與目錄拓撲（`manifest.json`, `scripts/cli.py`, `<pkg>/__init__.py`, `tests/`, `.yscbignore`, `contributes/_format.json`, `contributes/_manifest.md`, `contributes/core.json`），免除手動組裝之結構遺漏。 | P0 | [P00:DR-04]<br/>`GAP-01` |
| **FR-02** | 測試狀態判定修正與專屬斷言工具庫 | 1. 修正 `testing_and_sandbox.md` 中測試範例代碼，強制包含 `self.mark_passed()` 調用，解決沒拋例外卻全數被分類為 `UNKNOWN` 狀態之根本問題。<br/>2. 系統性收錄 `YSCBTestCase` 專屬斷言與輔助工具清單（`assertSuccess`, `assertFailed`, `assertInOutput`, `assertFileExists`, `assertJsonEquals`, `assertExecutionTime`, `run_cli`, `create_mock_package`, `create_mock_source_module`, `sandbox_dir`, `sandbox_uri`）。 | P0 | [P00:DR-01]<br/>`GAP-03` |
| **FR-03** | 4-Tier 測試分類與沙盒隔離機制 | 於 `testing_and_sandbox.md` 收錄 `@require(Requirement.XXX)` 分類體系（`LOGIC`, `ENV`, `NETWORK`, `WORKFLOW`, `PERF` 及正交 `ISOLATED_SANDBOX`）；說明離線環境自動 Skip `NETWORK` 之機制；收錄 CLI 分類跑測參數 `--type=<category>` 與精確目標定位參數 `--target=<mod:[case][.method]>`；並補充契約測試 `BaseModuleContractTestCase` 機制。 | P0 | [P00:DR-02]<br/>`GAP-03` |
| **FR-04** | 虛擬沙盒生命週期鉤子機制 | 於 `testing_and_sandbox.md` 收錄 `scripts/hook.dev.py` 之 `on_test_setup(context)` 與 `on_test_teardown(context)` 規格，指引模組如何在沙盒中進行環境變數注入（如 `MOCK_EMBEDDING`）、暫存目錄建立與資料庫預備，並說明 `dev build` 保留鉤子於 `.build.zip` 之機制。 | P0 | [P00:DR-03]<br/>`GAP-02` |
| **FR-05** | 模組清單進階規格與配置範本目錄規範 | 於 `acceptance_checklist.md` 與 `cli_and_commands.md` 擴充 `manifest.json` 完整規格，新增 `optional` 弱依賴（強制非空 `version` 與 `hint`）及 `pip_dependencies` 第三方套件規範；並於目錄結構中明確規定預設組態範本必須置於 `configurable/` 子目錄，嚴禁根目錄散落 `config.*.json`。 | P1 | [P00:DR-05]<br/>`GAP-04`<br/>`GAP-05` |
| **FR-06** | AST 靜態檢核剛性紅線清冊與反模式對照 | 於 `acceptance_checklist.md` Gate 1 明確列出 Checker AST 靜態檢核的剛性紅線清冊：<br/>1. `scripts/cli.py` 必須宣告 `process(args)` 或對應命令函式，禁絕 `main`、禁絕 `if __name__ == '__main__':`、禁絕頂層可執行語句。<br/>2. 非 core/dev 模組源碼嚴禁包含 `"module.source://"`。<br/>3. 嚴禁直接硬編碼存取 `"config.project.json"`、`"config.local.json"` 或 `"contributes.merged.json"`（必須使用 SDK）。<br/>4. 測試類別嚴禁直接繼承 `unittest.TestCase`（必須繼承 `YSCBTestCase`）。<br/>5. 嚴禁對 `LOGIC` 測試同時標註 `ISOLATED_SANDBOX`。 | P1 | [P00:DR-06]<br/>`GAP-06` |
| **FR-07** | 既有手冊實質錯誤與排版修復 | 1. 修正 `cli_and_commands.md` 章節編號：第 86 行「2.2 同構指令節點類型」更正為「3.2」(`A-1`)。<br/>2. 修正 `acceptance_checklist.md` 標題語意矛盾：「2. 三大模組品質與功能注意事項」更新為「2. 模組品質維度矩陣」(`A-2`)。<br/>3. `contributes_guide.md` Host 角色說明補充備註：本地視角路徑對齊下游第三方 `module://` 語意引用(`A-3`)。<br/>4. 補回 `acceptance_checklist.md` 在四大視角重構後遺失的 `_manifest.md` 排查入口(`B-1`)。<br/>5. `cli_and_commands.md` Server 協同章節補充指向 SKILL.md 軌道 A 之引流指針(`B-2`)。<br/>6. `testing_and_sandbox.md` 第 4 節末尾追加 `contributes check` 閉環引流提示(`B-3`)。<br/>7. 以 Unicode 箭頭與 Mermaid 圖優化 LaTeX 數學公式於非 MathJax 終端之可讀性(`C-1`)。<br/>8. 優化 `cli_and_commands.md` Dev 工具鏈矩陣結構密度(`C-2`)。<br/>9. 優化 `acceptance_checklist.md` 四大視角表格寬度，改善換行與閱讀體驗(`C-3`)。 | P1 | [P00:DR-07]<br/>`A-1~A-3`<br/>`B-1~B-3`<br/>`C-1~C-3` |
| **FR-08** | 四大文檔視角與語意防呆嚴格隔離 | 1. `SKILL.md` 全面將「業務意圖與開發情境」替換為「觸發時機」，強化 Agent 剛性反射。<br/>2. 移除 `SKILL.md` 中冗餘之「開發交付前自檢速查」章節。<br/>3. 軌道 B（版本晉升交付）嚴格標註「僅在開發者明確指示時才能進行」，杜絕自主越權升版。<br/>4. 嚴格隔離四大文檔視角（1. 維護標準 `docs://`、2. 第三方使用者 `user_guild.md`、3. 第三方開發者 `dev_guild.md`、4. 剛安裝指引 `install_guild.md`），嚴禁橫跨視角撰寫文檔。 | P0 | [P00:DR-07]<br/>用戶指示 |
| **FR-09** | 發布管線進階指令與一鍵管線整合 | 於 `cli_and_commands.md` 軌道 B 正式收錄 `dev release-check <mod> [--force|-f]`（不打包純 3-Gate 預檢）與 `dev release-git <mod> "<commit message>" [--force|-f]`（一鍵測試-預檢-發布-本地 Git Commit/Tag 管線），並強調嚴禁 remote push 之防呆鐵律。 | P2 | [P00:DR-08]<br/>`GAP-07` |

---

### 🛡️ 軌道二：`dev check` 自動化剛性檢核管線擴充 (Checker Rigid Enforcement)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-10** | Contributes 拓撲現代化檢核 | 於 `source/dev/dev/checker.py` 汰除舊版 `contributes.format.md` 檢查，改為剛性檢驗：<br/>1. 若模組包含 `contributes/` 目錄，必須存在 `contributes/_manifest.md`（Egress 清冊）。若遺漏則判定 `CheckIssue(FAIL, "CONTRIBUTES", "Module defines contributes/ but lacks 'contributes/_manifest.md' declaration index.")`。<br/>2. 若偵測到殘留之舊版 `contributes.format.md`，發出 `WARN` 提示遷移。<br/>3. 若存在 `_format.json`，強制檢核其結構符合 DSL Schema 規範。 | P0 | [P00:DR-09] |
| **FR-11** | 測試案例 `mark_passed()` 靜態合規檢驗 | 於 `checker.py` 的 `_check_test_classes` 中新增 AST 檢核：<br/>1. 遍歷繼承自 `YSCBTestCase` 之測試類別中的所有 `test_*` 方法。<br/>2. 檢查方法體內是否具備 `self.mark_passed()` 呼叫或標註 `@require(Requirement.NONE)`。<br/>3. 若測試方法未呼叫 `mark_passed()`，回報 `WARN`：「`Test method '{method_name}' in tests/{file} lacks 'self.mark_passed()' call. Unhandled tests will be marked as UNKNOWN in test runner.`」，剛性阻斷假測試與遺漏狀態標記。 | P0 | [P00:DR-09] |
| **FR-12** | 沙盒鉤子腳本 `hook.dev.py` 語法與契約檢核 | 於 `checker.py` 中新增 `_check_sandbox_hooks` 剛性檢驗：<br/>1. 若模組具備 `scripts/hook.dev.py`，進行 AST 語法解析；語法錯誤判定 `FAIL`。<br/>2. 頂層可執行語句白名單過濾：除 Docstring、Import、FunctionDef、ClassDef 外，嚴禁頂層散落可執行語句（防止沙盒匯入時產生非預期副作用）。<br/>3. 鉤子函式簽名驗證：若宣告 `on_test_setup` 或 `on_test_teardown`，其參數必須至少接受 1 個位置參數（`context`）。<br/>4. 若宣告了非標準命名的未知全域函式，發出診斷提示。 | P1 | [P00:DR-09] |
| **FR-13** | 第三方文檔路徑純淨度檢核 | 於 `checker.py` 中新增文檔路徑純淨度靜態掃描：<br/>1. 走訪模組 `docs/` 目錄下之所有 Markdown 文件（特別是 `docs/dev_guild.md` 與 `docs/user_guild.md`）。<br/>2. 掃描文字內容是否出現 `project://source/` 或本機實體源碼路徑特徵。<br/>3. 若第三方文檔出現本機源碼專屬路徑，判定 `WARN`：「`Documentation pollution in '{doc_path}': Hardcoded 'project://source/' reference detected. Use 'module://<mod>/' semantic URI for downstream consumers.`」。 | P1 | [P00:DR-09] |
| **FR-14** | `configurable/` 檔案命名與語法剛性約束 | 強化 `checker.py` 中現有 `_check_file_structure` 之 `configurable/` 檢核：<br/>1. `configurable/` 目錄內之範本檔案必須以 `config.` 開頭且副檔名為 `.json`（例如 `config.project.json`, `config.local.json`）。<br/>2. 若目錄內存在非法命名檔案（如臨時檔、非標準 JSON 檔），判定 `WARN` 或 `FAIL`。<br/>3. 確保內部所有範本均為合法 JSON 語法。 | P1 | [P00:DR-09] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 測試案例未調用 `self.mark_passed()` | 1. 運行期：`tearDown` 將狀態分類為 `UNKNOWN`。<br/>2. 靜態預檢期：`dev check` (FR-11) 發出 `WARN` 明確警告該測試方法遺漏調用。 |
| **EC-02** | 模組根目錄散落 `config.*.json` 範本檔案 | 觸發 `dev check` (FR-14) 結構檢查 `FAIL`（阻斷發布）。手冊強調所有範本必須放入 `configurable/` 子目錄。 |
| **EC-03** | 純邏輯測試混用 `ISOLATED_SANDBOX` | 觸發 `dev check` 反模式 `WARN`。手冊註明 `Requirement.LOGIC` 為純記憶體/無副作用單元測試，不得重複宣告獨佔沙盒。 |
| **EC-04** | 第三方開發者文檔引用不存在的 `source/` 實體路徑 | 1. 靜態預檢期：`dev check` (FR-13) 掃描並標記 `WARN`，防止污染下游。<br/>2. 手冊強制要求統一採用 `module://<target_mod>/` 語意引用。 |
| **EC-05** | Agent 未獲指示擅自執行軌道 B 升版或發布 | 違反專案行為準則。手冊中對 `bump-*`、`release`、`release-git` 標註 🔴 授權守門與剛性攔截警示。 |
| **EC-06** | 跨文檔視角混淆撰寫（例如在使用者手冊提及 dev 工具鏈） | 手冊提供四大視角矩陣與明確權責邊界，嚴禁跨視角滲透。 |
| **EC-07** | `scripts/hook.dev.py` 語法錯誤或函式簽名無參數 | `dev check` (FR-12) 攔截並回報 `FAIL`，避免測試引擎進入沙盒時發生不可捕獲之匯入崩潰。 |
| **EC-08** | 模組包含 `contributes/` 但遺漏 `_manifest.md` | `dev check` (FR-10) 攔截判定 `FAIL`，杜絕未建立對外契約導覽之未合規模組打包。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 實作對齊度 (Consistency) | 手冊中所列之所有 CLI 指令、選項參數、類別名稱、方法簽名與 Schema 定義，必須與 `dev`、`core` 模組程式碼 100% 嚴格一致，不得存在任何臆測或過期 API。 |
| **NFR-02** | 導航反射性 (Reflexivity) | `SKILL.md` 觸發條件與各 references 導覽指針必須具備高精確度與唯一性，確保 Agent 在面臨模組開立、測試、沙盒除錯、安裝或發布時能於 1 步內定位目標手冊。 |
| **NFR-03** | 檢測效能約束 (Performance) | `dev check` 新增之剛性靜態檢核項（AST 檢查 `mark_passed`、`hook.dev.py` 與文檔路徑掃描）執行時間增量不得超過 50ms/模組，全模組檢查（`--all`）增量不超過 200ms。 |
| **NFR-04** | 既有相容性與無回歸 (No Regression) | `dev/tests/test_checker.py` 既有 100% 測試案例全數保持通過；新增之剛性檢核規則配備專屬單元測試（FT-08 ~ FT-12）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!NOTE]
  > **SSOT 與對話節流**：本次為技能文檔品質更新與 Checker 剛性守門擴充。產物落檔後遵循極簡節流原則，對話輸出僅保留核心卡片與下一步。
- > [!IMPORTANT]
  > **機器自動化剛性守門 (Mechanized Guard)**：文檔規範必須有相應的 CI/CLI 檢核支撐。FR-10 ~ FR-14 確保了手冊定義的品質標準在 `dev check` 時能夠被機器自動捕獲，避免規範流於形式。
- > [!CAUTION]
  > **版本晉升與發布授權**：`bump-*` 與 `release` 為授權守門指令，手冊必須以最醒目方式聲明僅在開發者顯式輸入時方可執行。
