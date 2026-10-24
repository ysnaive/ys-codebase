# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_04_onboarding_and_config_coaching  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書中有對應介面、Token 錨點與技能規格
- [x] **邊界防護**：EC-01 ~ EC-05 有具體錯誤處理與防呆策略（空錨點自動抹除、全綠免改短路、唯讀教學護欄、雙入口自適應開場、單反引號語意連結）
- [x] **依賴純淨**：符合 NFR-01（片段 15~25 行、技能主檔 < 250 行）與 NFR-02（100% Python 標準庫零外部依賴）指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/agents-workflow/README.md`、`docs/agents-workflow/README.md` | Modify | 更新匯出技能列表（新增 `/how-to-config-yscb`、`/how-to-yscb`、`/todo`、`testing-sop`）與擴充錨點清冊 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 新增 §7 下游專案接入與互動教學雙星技能（`PROJECT_ROLE_AND_BOUNDARIES`、`/how-to-config-yscb`、`/how-to-yscb`）操作指南 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登記 `[DN-AW-13]` Turn 0 角色空間邊界常駐過濾、三處聯動對齊與教練實戰 Session 物理隔離防坑設計 |
| **微觀註解** | `compiler.py`、`scripts/cli.py`、`contributes/_manifest.md` | Modify | 同步更新 `_resolve_source_path`、`tokens` Docstring 與各模組 `contributes/_manifest.md` 清冊 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 07 結案時追加 `sub_04` 高階變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若下游專案僅安裝了 `core` 與 `agents-workflow`，而未安裝 `dev`、`server` 或 `knowledge-db`，`how-to-config-yscb` 與 `how-to-yscb` 是否會出現斷鏈或殘留空標籤？  
> [*] **防護解法**：各模組之 `config_guide.md` 與 `usage_guide.md` 均透過該模組自身的 `contributes/agents-workflow.json` (`mode: "below"`) 動態註冊。未安裝之模組不會參與 `core.contributes.get("agents-workflow")` 聚合，且 `ArtifactCompiler` 在 Stage 1 Step 3 會自動抹除已完成解算或無匹配之 `__@{HOW_TO_CONFIG_MODULES}__` / `__@{HOW_TO_YSCB_MODULES}__` 標籤行，保證物化檔案 100% 乾淨且僅包含已安裝模組。

> [?] **尖銳問題 2**：在本地開發或沙盒測試中，當多個模組皆定義 `module://<mod>/assets/config_guide.md` 時，若目標模組尚未打包至 `.modules/<mod>/`，`ArtifactCompiler._resolve_source_path()` 是否會誤讀其他模組的同名檔案？  
> [*] **防護解法**：於 `_resolve_source_path()` 拆解 `module://<mod>/<rel_p>` 時，明確比對 `<mod>` 名稱：若 `<mod> != "agents-workflow"`，本地 Fallback 僅查找同級目錄 `os.path.join(os.path.dirname(self.module_root), mod_name, rel_p)`，絕不退回 `self.module_root` (`agents-workflow`)。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：修復 `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` (`_resolve_source_path` 跨模組同級目錄 Fallback 防串線) 與 `scripts/cli.py` (`tokens` 相容 `value`/`name`)。
2. **TASK-02**：更新 `AgentsStandards.md`（新增 `` `__@{PROJECT_ROLE_AND_BOUNDARIES}__` ``）、`context-init/SKILL.md`（提取角色邊界與狀態卡底部提示）、新建 `how-to-config-yscb/SKILL.md` 與 `how-to-yscb/SKILL.md`，並更新 `agents-workflow/contributes/{agents-workflow.json,_manifest.md}`。
3. **TASK-03**：於四大核心模組（`core`、`dev`、`server`、`knowledge-db`）建立 `assets/{config_guide.md,usage_guide.md}`（各 15~25 行，含單反引號隨包手冊語意連結）並更新各模組 `contributes/{agents-workflow.json,_manifest.md}`。
4. **TASK-04**：於 `test_compiler.py` 與 `test_plans_model_record.py` 擴充單元與邊界測試（驗證雙星技能契約、三要素指南結構、`PROJECT_ROLE_AND_BOUNDARIES` 注入/抹除與跨模組 sibling fallback；本倉之 `project_role.md` 與 `testing_guide.md` 留待實機執行 `/how-to-config-yscb` 時自動探勘草擬與確認後代寫）。
5. **TASK-DOC**：同步更新 `ys_codebase/source/agents-workflow/README.md`、`docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}` 與微觀 Docstring。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 測試歸戶遵循 `testing-sop` 鐵律 1**：不新建計畫名碎片測試檔，直接於既有 `test_compiler.py`（測試 `_resolve_source_path` 跨模組同名檔案隔離、`tokens` CLI 輸出、`PROJECT_ROLE_AND_BOUNDARIES` 注入與空值抹除）與 `test_plans_model_record.py`（測試 16 個匯出技能契約、`how-to-config-yscb` 與 `how-to-yscb` 結構及四大模組片段行數與語意連結）擴充實質正負雙向斷言。

