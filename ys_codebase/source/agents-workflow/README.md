# Agents Workflow 模組 (`agents-workflow`)

本模組為 `ys-codebase` 的標準 AI Agent 開發工作流套件，提供完整的 SOP 體系、防呆機制、規格書模板與定式輔助工具庫。

---

## 📁 模組內容結構

- **`workflows/`**：
  - `NewPlan.md`：核心標準開發作業流程（Phase 0~7 / 三大分流管控：Fast Track、Full Track、Umbrella 主計畫）
  - `Continue.md`：中斷任務接續工作流
  - `Review.md`：結案審查、合規驗證與 Extension 深度稽核
  - `Discuss.md`：根因排查 (5-Whys) 與防盲目修補
  - `Idea.md`：構想與靈感孵化池
  - `Pause.md`：任務暫停與現場凍結 (`handoff.md`)
  - `Research.md`：深度技術調研工作流
  - `ContextInit.md`：專案上下文熱啟動工作流
  - `DocumentationStandards.md`：Docs 鏡像知識庫四分法規範
  - `templates/`：P00~P07、FT、Umbrella、Docs 等標準規格書模板與 `AGENTS.template.md`
  - `extensions/`：專案特化擴充模板
- **`scripts/`**：
  - `verify_plan.py`：Dev Plan 合規性與 Extension 深度稽核工具
  - `scan_plan_status.py`：計畫進度與狀態矩陣掃描工具
  - `search_dev_plans.py`：歷史計畫與 DR 決策全文檢索工具
  - `archive_plan.py`：計畫安全歸檔工具

---

## 🚀 使用方式

### 1. 標準發布模式安裝
```bash
python yscb_installer.py install agents-workflow
```

### 2. 開發者源碼模式安裝
```bash
python yscb_installer.py install agents-workflow --source
```
