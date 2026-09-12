# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：yscb-module-dev 技能手冊全方位品質優化與能力補齊 (Skill Quality Refinement & Capability Completion)  
> 建立日期：2026-09-08  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 計畫類型：Docs / Quality / Refactor / Toolchain  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 全方位審查並評估 `yscb-module-dev` skill 現有內容優化改善空間以及現有內容缺失部分。
  - 納入前期對話已確立之核心規範：
    1. CLI 實作與 Contributes 宣告對稱性。
    2. 下游第三方開發端無 `source`，全面改為 `module://` 語意 URI 引用。
    3. 語意改進：所有「業務意圖與開發情境」統一改為「觸發時機」，強化 Agent 剛性引導。
    4. 移除「開發交付前自檢速查」冗餘章節（資訊已包含於雙軌開發）。
    5. 軌道 B（版本晉升交付）嚴格標註僅在開發者明確指示時進行。
    6. 三大模組品質維護著重區分四大視角（1. 維護標準 `docs://`、2. `user_guild.md`、3. `dev_guild.md`、4. `install_guild.md`），嚴禁橫跨視角。
  - 完整納入兩份報告的所有內容：
    - 審查報告 [skill_audit_report.md](file:///home/developer/.gemini/antigravity-ide/brain/57cba36e-8679-4f29-8c13-c6e611f3a54d/skill_audit_report.md)（A-1~A-3 實質問題、B-1~B-3 語意改善、C-1~C-3 排版結構優化）。
    - 缺失報告 [skill_missing_content_report.md](file:///home/developer/.gemini/antigravity-ide/brain/57cba36e-8679-4f29-8c13-c6e611f3a54d/skill_missing_content_report.md)（GAP-01~GAP-07 模組工程 7 大能力缺失）。
  - **核心擴展**：於 `dev check` 管線中添加能支援剛性檢測之項目，使新規範具備機器自動化檢驗與防線守門能力，拒絕純書面規範。
- **核心目標**：
  - 修正手冊中所有實質錯誤（章節編號、標題語意矛盾、測試範例漏掉 `mark_passed()` 導致全數判定 `UNKNOWN` 等）。
  - 補齊 YSCB 模組工程 7 大關鍵能力缺口（`dev create` 腳手架、`hook.dev.py` 沙盒鉤子、4-tier 分類與跑測過濾、`optional`/`pip_dependencies` 進階清單、`configurable/` 目錄規範、AST 靜態紅線清冊、發布管線進階指令）。
  - 於 `source/dev/dev/checker.py` 中擴充 `dev check` 剛性檢驗管線（`_manifest.md` 替代舊 `contributes.format.md`、測試案例 AST 檢查 `mark_passed()`、`hook.dev.py` 語法簽名檢查、第三方文檔路徑純淨度檢查、`configurable/` 規範檢驗）。
  - 嚴格落實四大視角文檔隔離與「觸發時機」剛性分流，使 `yscb-module-dev` 成為零歧義、與底層程式碼 100% 同步的權威開發手冊。
- **邊界排除 (Explicitly Excluded)**：
  - 僅修改 `dev` 工具鏈中之 `checker.py` 及其測試套件，不更動 `core` 模組核心派發器與其他業務模組。
  - 不引入未在專案代碼中實現的虛構功能。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 測試狀態約定修正與斷言清單補全**：
  `testing_and_sandbox.md` 範例必須補上 `self.mark_passed()`，避免誤導開發者產生無效測試；同時系統性列出 `YSCBTestCase` 專屬斷言（`assertSuccess`, `assertFailed`, `assertFileExists`, `assertJsonEquals`, `assertExecutionTime`, `run_cli` 等）。
- **[P00:DR-02] 4-Tier 測試分類標籤與沙盒隔離機制收錄**：
  完整收錄 `Requirement` 列舉（`LOGIC`, `ENV`, `NETWORK`, `WORKFLOW`, `PERF` 及正交 `ISOLATED_SANDBOX`），說明 `--type` 與 `--target` 篩選語法，並提供契約測試 `BaseModuleContractTestCase` 導引。
- **[P00:DR-03] 沙盒測試生命週期鉤子機制收錄**：
  於測試手冊正式收錄 `scripts/hook.dev.py`（`on_test_setup`, `on_test_teardown`），指引有環境預置需求之模組如何標準化宣告前後置作業。
- **[P00:DR-04] 官方模組腳手架生成指引收錄**：
  收錄 `python yscb.py dev create <name> [--desc="..."]`，明列其自動生成的 8 大標準檔案結構，杜絕手動拼裝遺漏。
- **[P00:DR-05] 模組清單進階規格與配置範本目錄收錄**：
  擴充 `manifest.json` 欄位規格（`optional` 弱依賴與 `pip_dependencies` 第三方套件）；明確規範模組預設配置範本必須存放於 `configurable/` 子目錄，嚴禁根目錄散落。
- **[P00:DR-06] AST 靜態檢核紅線清冊與反模式對照**：
  在驗收清單中具象化 AST 檢查紅線（禁止 `def main`、禁止 `if __name__ == '__main__':`、禁止頂層可執行語句、禁止硬編碼 Probing 字串、禁止反模式直接讀檔、測試類別繼承限制）。
- **[P00:DR-07] 語意導引與四大視角剛性隔離**：
  `SKILL.md` 全面以「觸發時機」取代「業務意圖與開發情境」；嚴格隔離「維護標準 `docs://`」、「第三方使用者 `user_guild.md`」、「第三方開發者 `dev_guild.md`」、「安裝指引 `install_guild.md`」四大視角，嚴禁橫跨。
- **[P00:DR-08] 發布管線進階指令收錄**：
  收錄 `dev release-check`（不打包純驗證）與 `dev release-git`（測試-驗證-發布-本地 Commit/Tag 一鍵管線），標註授權守門與本地邊界。
- **[P00:DR-09] `dev check` 管線剛性檢核能力增強 (Checker Rigid Enforcement)**：
  在 `dev/checker.py` 中落實自動化剛性檢核：
  1. 淘汰舊版 `contributes.format.md` 檢查，改為強制檢核 `contributes/_manifest.md`。
  2. AST 靜態檢測測試方法是否呼叫 `mark_passed()`，阻斷遺漏狀態之假測試。
  3. 檢驗 `scripts/hook.dev.py` 語法、簽名（`on_test_setup/teardown(context)`）與無副作用頂層語句。
  4. 掃描第三方文檔中是否出現 `project://source/` 硬編碼路徑污染。
  5. 強化 `configurable/` 檔案命名格式規範。

---

## 3. 開放議題與確認紀錄

- [x] 子計畫編號確認：因 `sub_03` 已結案完成，本次依用戶確認開立為 `sub_04_yscb_module_dev_skill_refinement`。
- [x] 修復與優化範疇：囊括審查報告與缺失報告之 2 項實質修復、4 項語意改善、3 項排版優化、7 大缺失能力補齊。
- [x] 代碼擴充範疇確認：納入 `dev check` 5 項自動化剛性檢測能力。
