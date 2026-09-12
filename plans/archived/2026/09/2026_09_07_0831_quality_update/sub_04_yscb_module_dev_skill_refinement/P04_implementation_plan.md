# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：yscb-module-dev 技能手冊全方位品質優化與能力補齊 (Skill Quality Refinement & Capability Completion)  
> 建立日期：2026-09-08  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：
  - 軌道一手冊類（FR-01 ~ FR-09）在 5 份技能手冊檔案中有 1:1 明確落腳章節。
  - 軌道二檢核類（FR-10 ~ FR-14）在 `dev/checker.py` 擴充方法中有完整簽名與規格對應。
- [x] **邊界防護**：
  - EC-01（測試遺漏 mark_passed）：由 FR-02 手冊修正 + FR-11 AST 靜態預檢 WARN 形成雙層攔截。
  - EC-02（配置範本散落根目錄）：由 FR-05 規範 + FR-14 命名檢核阻斷。
  - EC-03（純邏輯混用沙盒）：已在 Checker 中落實 WARN，並在手冊中列為紅線。
  - EC-04（第三方手冊引用 source/）：由 FR-08 規範 + FR-13 靜態路徑掃描阻斷。
  - EC-05（未授權升版）：由 FR-08 / FR-09 授權守門警示阻斷。
  - EC-06（四大視角混淆）：由 FR-08 垂直視角清冊阻斷。
  - EC-07（hook.dev.py 語法/簽名錯誤）：由 FR-12 靜態語法檢查阻斷。
  - EC-08（遺漏 _manifest.md）：由 FR-10 靜態存在性檢查阻斷。
- [x] **依賴純淨**：100% Python 標準庫（`ast`, `os`, `re`, `json`），零外部依賴，符合 NFR-01 ~ NFR-04。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **技能主入口** | `source/dev/assets/skills/yscb-module-dev/SKILL.md` | Modify | 修正觸發時機、雙軌流水線、移除自檢速查、補齊 dev create |
| **驗收專題** | `.../references/acceptance_checklist.md` | Modify | 修正標題、四大文檔視角垂直展開、AST 紅線清冊、configurable/ 規範 |
| **CLI專題** | `.../references/cli_and_commands.md` | Modify | 增補 dev create 腳手架、3.2 編號更正、optional/pip_deps、release-check/git |
| **測試專題** | `.../references/testing_and_sandbox.md` | Modify | 範例補齊 mark_passed、4-tier 分類標籤、hook.dev.py 鉤子、斷言工具庫 |
| **貢獻專題** | `.../references/contributes_guide.md` | Modify | Host 視角備註對齊 module://、第三方無 source 哲學強化 |
| **發布日誌** | `plans/.../sub_04_.../changelog.md` | Modify | 全程留痕各 Phase 流轉與決策 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：在 `dev check` 中以 AST 靜態檢核測試類別的 `mark_passed()` 是否會誤判（例如測試方法呼叫了自定義的 helper 函式，而在 helper 內才呼叫 mark_passed）？  
> 💡 **防護解法**：在 `_check_test_classes` 中：
> 1. 檢查方法體內的直接呼叫 `self.mark_passed()`。
> 2. 檢查方法體內是否呼叫了同類別定義的自定義 helper（若有呼叫 helper，寬鬆視為可能有內部標記，降低誤報）。
> 3. 若未找到 mark_passed 且未宣告 `@require(Requirement.NONE)`，判定級別定為 `WARN`（而非阻斷編譯的 `FAIL`），提供明確診斷提示但不致誤殺特殊複雜測試結構。

> ❓ **尖銳問題 2**：`docs/` 第三方手冊路徑純淨度掃描是否會誤傷合法引用（例如文檔中在舉例「錯誤做法」時提到 `project://source/`）？  
> 💡 **防護解法**：若反面教材出現該路徑，判定級別定為 `WARN`（並提示若為反面教材請加上註解說明）。此檢查僅掃描 `docs/`（特別是 `dev_guild.md` / `user_guild.md`），不掃描 `contributes/` 內部契約。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/dev/dev/checker.py` 中實作 5 項剛性檢核管線擴充（FR-10 ~ FR-14）：
  - 汰除舊 `contributes.format.md`，新增 `contributes/_manifest.md` 剛性檢驗。
  - 新增測試方法 `self.mark_passed()` AST 靜態合規檢驗。
  - 新增 `scripts/hook.dev.py` 語法、無副作用頂層語句與函式簽名檢驗。
  - 新增 `docs/` 第三方文檔 `project://source/` 硬編碼路徑純淨度掃描。
  - 強化 `configurable/` 檔案命名與 JSON 語法檢核。
- [ ] **TASK-02**：在 `source/dev/tests/test_checker.py` 中新增 FT-10 ~ FT-14 單元測試，全面覆蓋新增的 Checker 規則。
- [ ] **TASK-03**：精修 `source/dev/assets/skills/yscb-module-dev/references/testing_and_sandbox.md`（修正範例代碼加 `mark_passed()`、補齊 4-tier 分類、沙盒鉤子 `hook.dev.py`、專屬斷言清單、`contributes check` 引流）。
- [ ] **TASK-04**：精修 `source/dev/assets/skills/yscb-module-dev/references/cli_and_commands.md`（收錄 `dev create` 官方腳手架、更正 3.2 編號、收錄 `optional`/`pip_dependencies`、收錄 `release-check`/`release-git`、Server 協同引流）。
- [ ] **TASK-05**：精修 `source/dev/assets/skills/yscb-module-dev/references/acceptance_checklist.md`（更正章節標題、四大文檔視角垂直展開優化、補全 AST 檢核紅線清冊、`configurable/` 規範、`_manifest.md` 排查入口）。
- [ ] **TASK-06**：精修 `source/dev/assets/skills/yscb-module-dev/references/contributes_guide.md`（Host 視角路徑備註、健全 `module://` 語意引用）。
- [ ] **TASK-07**：精修 `source/dev/assets/skills/yscb-module-dev/SKILL.md`（全面採用「觸發時機」剛性導航、收錄 `dev create` 起手式、移除自檢速查冗餘章節、標註軌道 B 授權守門、Unicode/Mermaid 流程優化）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 實作順序採「先底層守門代碼（TASK-01~02）➔ 後技能手冊資產（TASK-03~07）」，確保手冊完工時即可直接透過新版 `dev check` 與測試套件自舉驗收（Dogfooding）。
- **[P04:DR-02]** 既有測試套件 100% 保障：在修改 `checker.py` 前後執行回歸驗證，確保 core/dev/server/knowledge-db/agents-workflow 全生態系 0 破壞。
- **[P04:DR-03]** P06 測試計畫確認收斂定稿，鎖定 FT-01~14 與 UX-01~03。
