# API 與介面規格書 (API & Interface Specification)

> 功能名稱：專案特化技能建置與 Layer 2 宣告式擴充引導工作流 (sub_05_skill_creator_extension_workflow)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Medium)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `skill-creator` (Skill Export & Frontmatter Contract) | `ys_codebase/source/agents-workflow/assets/skills/skill-creator/SKILL.md` | Public | 專案特化技能建置與 Layer 2 宣告式擴充四步工作流主入口（主動指令型極簡契約 + 三軌分流 + 藍圖確認卡 + 三步驗證守門） |
| `extension-guide.md` (1-Level Reference Schema) | `ys_codebase/source/agents-workflow/assets/skills/skill-creator/references/extension-guide.md` | Public | 單層按需載入擴充參考手冊（全系統 22 個 Stage 1 Token 錨點地圖、Stage 2 語意 URI 轉換規則、三軌 `contribute.json` 最小增量範本） |
| `SKILL_CREATOR_STANDARDS` (Stage 1 Content Token) | `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Public | `skill-creator/SKILL.md` 尾部開放之專案特化技能建置規範動態注入錨點 |
| `LITERAL_FENCED_BLOCK_REGEX` (`<!-- yscb:literal -->`) | `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Internal | 在 Stage 1 與 Stage 2 預先抽離保護首行標註 `<!-- yscb:literal -->` 之教學代碼塊，並於 Stage 2 剝除標記行、保留字面量佔位符原貌 |
| `test_ft_11_sub05_skill_creator_extension_workflow` | `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` | Internal | 驗證 `skill-creator` 雙層結構、22 個錨點完整性、零裸寫標籤、三步編譯驗證守門與實機 Stage 1/2 編譯無警告且保留字面量範例之單元測試方法 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. contributes/agents-workflow.json 匯出與 Token 契約
EXPORT_SKILL_CREATOR_SCHEMA = {
    "type": "skill",
    "name": "skill-creator",
    "source": "module://agents-workflow/assets/skills/skill-creator",
    "description": (
        "引導建立專案功能特化 Skill、環境注意事項攔截規則或階段錨點注入配置，"
        "自動對接語意 URI 與雙層編譯註冊閉環。"
        "僅於顯式輸入 /skill-creator 或明確指示建立新 Skill 與擴充工作流規範時觸發。"
    ),
}

TOKEN_SKILL_CREATOR_STANDARDS_SCHEMA = {
    "value": "SKILL_CREATOR_STANDARDS",
    "description": "專案特化技能建置與擴充規則注入錨點（位於 skill-creator/SKILL.md）",
}


# 2. skill-creator/SKILL.md 結構與輸出狀態卡契約
# Pre-conditions:
#   - 開發者輸入 /skill-creator 或明確要求建立專案特化 Skill / 擴充工作流規範。
# Post-conditions:
#   - 步驟 1 完成三軌擴充判定 (軌跡 ① 純錨點注入 / 軌跡 ② 環境攔截型 Skill / 軌跡 ③ 功能特化型 Skill)。
#   - 步驟 2 執行 `python yscb.py agents-workflow tokens` 與 `python yscb.py uri list`，
#     並輸出「🛠️ /SkillCreator 專案擴充藍圖確認卡」後強制 End Turn 等待拍板。
#   - 步驟 3 於 `config://agents-workflow/skills/<name>/SKILL.md` 或 `snippets/<name>.md` 生成合規資產。
#   - 步驟 4 最小增量更新 `config://agents-workflow/contribute.json`，並依序通過：
#     ① `python yscb.py contributes check` (exit_code == 0)
#     ② `python yscb.py agents-workflow compile` (0 Error / 0 Warning)
#     ③ `python yscb.py agents-workflow release` (物化同步至目標平台)


# 3. 測試驗證方法簽名 (tests/test_plans_model_record.py)
def test_ft_11_sub05_skill_creator_extension_workflow(self) -> None:
    """
    [sub_05 FR-01 ~ FR-05, EC-01 ~ EC-05, NFR-01 ~ NFR-02]:
    驗證 skill-creator 雙層結構、三軌分流、藍圖確認卡、22 個 Stage 1 錨點地圖、
    三步驗證守門與實機 ArtifactCompiler 編譯零警告。
    """
    ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  1. **`EC-01` 編譯器正則誤觸防禦**：`skill-creator/SKILL.md` 與 `references/extension-guide.md` 內所有散文／表格中之真實語意標籤必須 100% 使用單反引號包覆；抽象教學範例統一置於 Fenced Code Block 內，確保 `check_unenclosed_tags()` 與 `ArtifactCompiler.compile_stage1()` / `release()` 零 Warning、零 Error。
  2. **`EC-02` 過度建技攔截**：當需求僅涉及單一開發階段或熱啟動之局部微調（$\le 15$ 行規則）時，步驟 1 與步驟 2 強制引導降級為「軌跡 ①：純錨點注入模式 (`Anchor-Only Injection`)」，拒絕無謂新增獨立 Skill。
  3. **`EC-03` 雙軌路徑引用防呆**：同技能內部引用 `references/` 強制使用標準相對路徑 `./references/<file>.md`；跨技能、跨模板或跨專案目錄引用強制使用單反引號語意 URI。
  4. **`EC-04` 三步編譯驗證失敗阻斷**：步驟 4 執行 `contributes check` 或 `agents-workflow compile` 若出現任何非零退出碼、`[compiler:error]` 或 `[compiler:warning]`，強制阻斷後續 `agents-workflow release` 並原地修復第一層資產。
  5. **`EC-05` 錨點結構型態防呆**：注入 `AGENTS_SKILL_ROUTING` 之內容必須為單行或多行 Markdown 表格列（`| **觸發條件** | \`skill-name\` |`），嚴禁注入標題區塊破壞路由表結構。
- **階段決策紀錄**：
  - **`[P03:DR-01]`**：`skill-creator` 與 `contributes/agents-workflow.json` 之 `description` 嚴格保持一字不差同步，並遵循主動指令型極簡契約（以 `僅於顯式輸入 /skill-creator 或明確指示建立新 Skill 與擴充工作流規範時觸發。` 結尾，不含括號大小寫變體），確保 `test_ft_08` 100% 通過。
  - **`[P03:DR-02]`**：`references/extension-guide.md` 明確收錄全系統 22 個 Stage 1 Token（`agents-workflow` 21 個 + `knowledge-db` 1 個 `KNOWLEDGE_DB_SPACE`），並將所有含抽象佔位符或 JSON 片段之範例封裝於 Fenced Code Block 中，保證編譯期零未解析標籤警告。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: 模組貢獻與 Token 註冊 (Bottom Layer)
  └── ys_codebase/source/agents-workflow/contributes/agents-workflow.json (新增 skill-creator export 與 SKILL_CREATOR_STANDARDS token)
  └── ys_codebase/source/agents-workflow/contributes/_manifest.md (更新導出清冊)
        │
        ▼
Step 2: 單層擴充參考手冊與技能主檔實作 (Core Asset Layer)
  └── ys_codebase/source/agents-workflow/assets/skills/skill-creator/references/extension-guide.md (22 個錨點地圖 + URI 規則 + 三軌 JSON 範本)
  └── ys_codebase/source/agents-workflow/assets/skills/skill-creator/SKILL.md (四步工作流 + 三軌分流 + 藍圖確認卡 + 三步驗證守門)
        │
        ▼
Step 3: 中樞與同儕技能互指導流 (Hub & Peer Routing Layer)
  └── ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md (§1 生命週期工作流中樞分流)
  └── ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/SKILL.md (排除情境雙向導流)
        │
        ▼
Step 4: 單元測試擴充與三層文檔同步 (Verification & Documentation Layer)
  └── ys_codebase/source/agents-workflow/tests/test_plans_model_record.py (更新 test_ft_08 + 新增 test_ft_11)
  └── ys_codebase/source/agents-workflow/README.md & docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}
```

