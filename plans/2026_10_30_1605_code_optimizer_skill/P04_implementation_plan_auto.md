# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：2026_10_30_1605_code_optimizer_skill  
> 建立日期：2026-10-30  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (High)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書與受影響檔案清單中有 1:1 對應資產與介面契約
- [x] **邊界防護**：EC-01 ~ EC-05 已涵蓋未指定範圍/模式攔截、`Mode B` 純內部工具函式破壞性收斂、子代理門檻短路、`Revision Plan` 誤用阻斷與語意標籤反引號防護
- [x] **依賴純淨**：符合 NFR-01（`SKILL.md` $\le 180$ 行、單層 `references/`、長檔附 TOC）與 NFR-02（零第三方依賴、三平台投影合規）

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 於 §1 技能清單與 §5 核心 Token 擴充補入 `code-optimizer` 與 `CODE_OPTIMIZER_STANDARDS` |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 新增 §7.6 業務代碼五維度診斷與無損重構工作流 (`/code-optimizer`) 並同步更新 §7.4 Stage 1 錨點統計（23 $\to$ 24 個） |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | N/A | 本次屬標準宣告式純 Skill 與 Token 擴充，無新增反直覺底層工程妥協 |
| **微觀註解** | `ys_codebase/source/agents-workflow/contributes/_manifest.md` | Modify | 更新 19 大純 Skill 導出清冊與 `CODE_OPTIMIZER_STANDARDS` 說明 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本計畫發布摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：當開發者在 `Mode B（維護期）` 下執行 `/code-optimizer` 時，Agent 若將模組內所有函式都當成公開契約保留轉發別名，反而會在模組內部堆滿冗餘 Wrapper；但若誤刪外部有調用的函式又會破壞相容性，如何精確界定？  
> [*] **防護解法**：於 `SKILL.md` 與 `references/exploration-and-delegation.md` 建立**「`Mode B` 雙層嚴格查驗規則（Strict Two-Tier Verification in Mode B）」**：凡屬於對外公開契約（列於 `__all__`、套件入口匯出、`contributes/*.json` 或跨模組有入向調用者）一律強制**門面保護（Facade Preservation）**；但凡經全空間調用圖譜（如 `knowledge-db callers` 或全倉檢索）與匯出清單**嚴格查驗確認 0 外部跨模組調用且非對外公開契約之純內部工具函式/私有結構**，強制比照 `Mode A` 直接執行破壞性收斂（直接改名、合併、改簽名或物理移除，並同步更新模組內調用點），嚴禁為純內部工具函式保留相容轉發層。

> [?] **尖銳問題 2**：新增第 23 個模組內建 Token `CODE_OPTIMIZER_STANDARDS`（全系統第 24 個）與第 19 個內建 Skill `code-optimizer` 後，是否會導致既有 `test_compiler.py` 的硬編碼集合與數量測試失敗？  
> [*] **防護解法**：已預先排查 `ys_codebase/source/agents-workflow/tests/test_compiler.py` 之 `test_ft_08`（檢查 `expected_skills` 與 `command_driven_skills`）與 `test_ft_11`（檢查 `len(token_names)` 與 `extension-guide.md` 收錄之所有錨點），將於 TASK-04 一併同步更新 `skill-creator/references/extension-guide.md` 與 `test_compiler.py`，確保全量測試 100% 通過。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：建立 `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/` 下之三份單層參考手冊（`exploration-and-delegation.md`、`diagnostic-matrix.md`、`refactoring-playbook.md`），落實包含式三層範圍探索、支柱一子代理量化門檻、`Mode B` 純內部工具函式嚴格查證破壞性收斂、`D1~D5` 矩陣、`S1~S6` 策略與 Stage 2 `` `__%{agent_tool.*}__` `` 佔位符。
2. **TASK-02**：建立 `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md`（控制在 $\le 180$ 行），實作主動指令型極簡 Frontmatter、步驟 1 雙維度定錨詢問卡（範圍 × `Mode A/B`）、步驟 2 `R01` 調研計畫落檔、步驟 3 三大流轉出口確認卡、步驟 4 外科手術式無損重構與回歸對照、防過度設計四大紅線、`__@{CODE_OPTIMIZER_STANDARDS}__` 錨點與 Gotchas。
3. **TASK-03**：更新 `contributes/agents-workflow.json`、`_manifest.md`、`development-sop/SKILL.md`、`how-to-yscb/SKILL.md`、`skill-creator/SKILL.md` 與 `skill-creator/references/extension-guide.md`，完成 `code-optimizer` 與 `CODE_OPTIMIZER_STANDARDS` 之全鏈路註冊與導流。
4. **TASK-04**：更新 `ys_codebase/source/agents-workflow/tests/test_compiler.py`（同步更新 `test_ft_08`、`test_ft_11` 並新增 `test_ft_14_code_optimizer_skill_and_standards_anchor`）及 `docs/agents-workflow/{README.md,user_guide.md}`。
5. **TASK-05**：執行 `contributes check`、`dev check agents-workflow`、`dev test agents-workflow -q`、安裝 `agents-workflow@build --force` 與 `agents-workflow release` 完成本機物化驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認本次修改檔案數與源碼規模適中（主要為 Markdown 技能資產、JSON 註冊與單一測試檔擴充），由主 Agent 直接於當前上下文高效完成 TASK-01 ~ TASK-05，並於 Phase 06 執行完整沙盒測試與支柱三 Pre-UX 唯讀 Subagent 盲審。

