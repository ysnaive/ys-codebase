# API 規格書 (API & Interface Specification)

> 功能名稱：架構轉型遷移、SOP 規範對齊、Dogfooding 流水線與 Changelog 防呆加固  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.2  

---

## 1. 模組、腳本與擴充介面總覽

| 介面 / 檔案名稱 | 實體路徑 | 類型 | 職責概述 |
| :--- | :--- | :---: | :--- |
| `dogfooding_pipeline_ext.md` | `extensions/dogfooding_pipeline_ext.md`<br>`source/agents-workflow/workflows/extensions/` | Add | SOP Extension 擴充契約，定義 Stage 1~4 全流程檢核矩陣 |
| `verify_plan.py` | `source/agents-workflow/scripts/verify_plan.py` | Modify | 加固計畫合規掃描邏輯，新增 `changelog.md` 存在性與格式檢驗 |
| `NewPlan.md` | `source/agents-workflow/workflows/NewPlan.md` | Modify | SOP 主流程，定義 Phase 0 伴隨建立 `changelog.md` 剛性約束與時機提前 |
| `Review.md` | `source/agents-workflow/workflows/Review.md` | Modify | SOP 指南，定義 `ext list/show` 與 `docs audit` 之調用合約 |
| `DocumentationStandards.md` | `source/agents-workflow/workflows/DocumentationStandards.md` | Modify | 知識庫規範，定義 `docs init/audit/new-topic` 之調用合約 |
| `AGENTS.md` | `project://AGENTS.md` | Modify | 專案準則，第 4 節規範 Dogfooding 三層空間與防呆鐵律 |

---

## 2. 核心介面契約與資料結構 (Interface Contracts & Schemas)

### 2.1 `verify_plan.py` 加固契約 (Python Signature & Behavior)

```python
# ── source/agents-workflow/scripts/verify_plan.py ─────────────────────────

def verify_plan_directory(plan_dir: Path, extensions: list) -> Tuple[List[str], List[str]]:
    """
    掃描單一 Dev Plan 目錄並驗證其合規性。
    
    加固規則：
    1. 移除 changelog.md 略過邏輯。
    2. 檢查 plan_dir / "changelog.md" 是否存在：
       - 若不存在，向 errors 追加: f"[{plan_dir.name}] 缺少必備計畫變更日誌: changelog.md"
       - 若存在，讀取內容並驗證是否包含標題 "# 計畫變更紀錄" 或表格 "| 日期時間 | 類型 | 摘要 |"
    3. handoff.md 仍視為可選暫存檔案（略過格式檢查）。
    4. 其餘 Phase 檔案 (P00~P07 / FT_plan / umbrella_overview) 維持嚴格 Header 格式校驗。
    """
```

### 2.2 `NewPlan.md` Phase 0 剛性伴隨初始化契約 (Plan Creation & Changelog Binding)

```markdown
<!-- NewPlan.md Phase 0 執行步驟契約修訂 -->

### Phase 0：語意化需求討論 (Semantic Requirements Discovery)

#### 執行步驟
1. **建立工作目錄**：`plans://{YYYY_MM_DD_HHMM_功能名稱}/`
2. **雙星伴隨初始化 (Mandatory Co-Initialization)**：
   - 依模組 `workflows/templates/P00_semantic_requirements.md` 建立 `P00_semantic_requirements.md`（狀態標記為 `Discussing`）。
   - **同時**依 `workflows/templates/changelog.md` 建立 `changelog.md`，並立即寫入第 1 筆紀錄（開立計畫目錄與 P00 草稿）。
   - 🚨 **防呆鐵律**：嚴禁延至分流後才建立 `changelog.md`！Phase 0 的所有討論、調研 (R01/R02) 與 DR 決策必須即時記錄於 `changelog.md`。
3. **開放式討論與深度調研 (Phase 0-R)**：...
4. **等待討論結束宣告**：...
5. **執行三大層級分流判定**：
   - **Level 1 (Full Track)**：確認 `changelog.md` 已就緒，進入 Phase 1 ~ 7 完整流程。
```

### 2.3 `dogfooding_pipeline_ext.md` 擴充契約 (YAML Frontmatter & Checklist)

```yaml
---
name: "dogfooding_pipeline_ext"
phase: "P04, P05, P06, P07, FT_plan"
trigger: "always"
description: "自引用 (Dogfooding) 三層空間修改、構建、全量回歸與自引用更新閉環 Checklist"
---
```

**Checklist 欄位契約**：
```markdown
# Extension: Dogfooding 自引用流水線與防呆驗收

## 擴充 Checklist
- [ ] **Stage 1 (源碼空間確認)**：所有檔案修改均 100% 位於 `ys_codebase/source/` 或 `ys_codebase/yscb_*.py`，無任何直接編輯 `modules/` 或 `.agents/` 的越界行為。
- [ ] **Stage 2 (模組打包構建)**：已執行 `python yscb_cli.py installer build <module>` (或 `build --all`)，且 `ys_codebase/build/` 正確生成。
- [ ] **Stage 3 (全量回歸測試)**：已實機執行 `python test/run_regression.py` 並取得 `Ran 23 tests ... ALL PASSED` 日誌。
- [ ] **Stage 4 (自引用同步)**：
  - [ ] 根目錄起手腳本已覆蓋同步 (`yscb_installer.py` / `yscb_cli.py`)。
  - [ ] 已執行 `python yscb_cli.py installer install <module> --force` 部署至 `modules/`。
  - [ ] 若工作流有變更，已執行 `python yscb_cli.py agents-workflow --ide-antigravity` 重新生成 `.agents/workflows/`。
  - [ ] 執行 `python yscb_cli.py installer status` 驗證自引用模組狀態為 `[已安裝 (build)]`。
```

---

## 3. 關鍵依賴與第三方套件

| 呼叫功能 | 依賴項目與模組位置 | 呼叫方式 / 簽名 | 驗證狀態 |
| :--- | :--- | :--- | :---: |
| **CLI 路由器** | `yscb_cli.py` (根目錄與源碼) | `python yscb_cli.py <module> <args...>` | ✅ 已驗證 |
| **安裝構建器** | `ys_codebase/yscb_installer.py` | `InstallerCLI.main()` | ✅ 已驗證 |
| **驗證工具** | `source/agents-workflow/scripts/verify_plan.py` | `subprocess.run([sys.executable, ...])` | ✅ 待加固驗證 |
| **回歸套件** | `test/run_regression.py` | `unittest.TextTestRunner()` | ✅ 100% Passed |

> **第三方依賴約束**：**零第三方依賴 (Zero External Dependency)**。100% 基於 Python 3.8+ 標準庫（`pathlib`, `sys`, `os`, `json`, `re`, `subprocess`, `unittest`, `argparse`）。

---

## 4. Decision Records

### [API:DR-01] `verify_plan.py` 檢查層級契約確立
- **議題**：`verify_plan.py` 是否應對 `changelog.md` 進行格式深度校驗？
- **結論**：`verify_plan.py` 將檢查：1. 檔案是否存在；2. 是否具備有效 Markdown 標題或變更表格欄位。若有缺漏則視為合規性未通過。
- **理由**：兼顧檢查嚴謹性與靈活性，防止空檔或完全遺漏的情況。

### [API:DR-02] `NewPlan.md` Phase 0 雙星伴隨初始化契約確立
- **議題**：如何確保 `changelog.md` 不會因時序滯後而被遺漏？
- **結論**：在 `NewPlan.md` Phase 0 步驟 2 剛性規定「開立計畫目錄時必須【同時】建立 `P00` 與 `changelog.md`」，並將分流表格中原本滯後的描述修正為「確認 `changelog.md` 已就緒」。
- **理由**：自 Phase 0 起點即建立完整決策日誌鏈，徹底消除歧義。
