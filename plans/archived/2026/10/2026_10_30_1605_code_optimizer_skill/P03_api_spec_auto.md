# API 與介面規格書 (API & Interface Specification)

> 功能名稱：2026_10_30_1605_code_optimizer_skill  
> 建立日期：2026-10-30  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (High)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `export[name="code-optimizer"]` | `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Public | 宣告導出 `code-optimizer` 純 Skill 資產包及其極簡主動觸發 `description` |
| `token[value="CODE_OPTIMIZER_STANDARDS"]` | `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Public | 宣告位於 `code-optimizer/SKILL.md` 尾部之專案特化業務代碼診斷與無損重構擴充規則注入錨點 |
| `code-optimizer/SKILL.md` | `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md` | Public | 定義 `/code-optimizer` 四步驟工作流、雙維度定錨詢問卡、`R01` 調研診斷與三出口建議卡、四大紅線與 `__@{CODE_OPTIMIZER_STANDARDS}__` 錨點 |
| `TestArtifactCompiler.test_ft_14_code_optimizer_skill_and_standards_anchor` | `ys_codebase/source/agents-workflow/tests/test_compiler.py` | Internal | 驗證 `code-optimizer` 導出註冊、`SKILL.md` 與 3 份 `references/*.md` 結構契約、Stage 1/2 編譯零警告與三平台專有名詞投影 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. contributes/agents-workflow.json 擴充契約 (JSON Schema Contract)
EXPORT_CODE_OPTIMIZER_SPEC: dict[str, str] = {
    "type": "skill",
    "name": "code-optimizer",
    "source": "module://agents-workflow/assets/skills/code-optimizer",
    "description": "針對既有業務程式碼執行五維度靜態診斷、業務階段邏輯聚合與行為無損重構。僅於顯式輸入 /code-optimizer 時觸發，嚴禁主動觸發。",
}

TOKEN_CODE_OPTIMIZER_STANDARDS_SPEC: dict[str, str] = {
    "value": "CODE_OPTIMIZER_STANDARDS",
    "description": "專案特化業務代碼五維度診斷、架構慣例 (D5) 與無損重構驗證規則注入錨點（位於 code-optimizer/SKILL.md）",
}

# 2. tests/test_compiler.py 新增測試方法簽名
class TestArtifactCompiler(YSCBTestCase):
    def test_ft_14_code_optimizer_skill_and_standards_anchor(self) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `ArtifactCompiler.compile_stage1()` 與 `resolve_stage2_uri()` 處理 `code-optimizer/SKILL.md` 及其 `references/*.md` 時，必須保證 `0 Error` 且 stderr 無任何 `[compiler:warning]`（無未解析之語意 URI、無未加單反引號之動態標籤、無未知之 `agent_tool.*` 專有名詞鍵）。
  - 當 `CODE_OPTIMIZER_STANDARDS` 未被任何模組或專案 `insert` 注入時，Stage 1 編譯器必須自動乾淨抹除 `` `__@{CODE_OPTIMIZER_STANDARDS}__` `` 獨立行，不殘留空錨點字串。
- **階段決策紀錄**：`[P03:DR-01]` 維持 `agents_workflow` Python 編譯器核心程式碼零變更，100% 透過宣告式 `contributes/agents-workflow.json` 與標準資產結構掛載 `code-optimizer`，驗證架構的可擴充性與正交性。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: 建立 `assets/skills/code-optimizer/references/` 三大單層參考手冊
  ├── exploration-and-delegation.md
  ├── diagnostic-matrix.md
  └── refactoring-playbook.md
        │
        ▼
Step 2: 建立 `assets/skills/code-optimizer/SKILL.md` 主控技能檔 (含 `__@{CODE_OPTIMIZER_STANDARDS}__`)
        │
        ▼
Step 3: 更新 `contributes/agents-workflow.json`、`_manifest.md` 與關聯技能 (`development-sop`, `how-to-yscb`, `skill-creator`)
        │
        ▼
Step 4: 更新 `tests/test_compiler.py` 與 `docs/agents-workflow/{README.md,user_guide.md}`
        │
        ▼
Step 5: 執行 `contributes check` -> `dev check` -> `dev test` -> `install agents-workflow@build --force` -> `agents-workflow release`
```

