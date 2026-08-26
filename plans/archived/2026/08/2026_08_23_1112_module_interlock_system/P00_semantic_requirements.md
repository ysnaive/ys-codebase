# 語意化需求書 (Semantic Requirements)

> 功能名稱：Module 安裝期連動系統設計 (Installation-time Interlock System)  
> 建立日期：2026-08-23  
> 計畫類型：Feature  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.1  

---

## [類型：Feature] 語意化需求

> 依據調研報告：[R01_installation_interlock_mechanisms.md](./R01_installation_interlock_mechanisms.md)

### 使用情境 (User / Developer Scenarios)

**情境 1：強相依特化擴充模組安裝連動 (Hard Dependency Extension - Case 1)**
- **場景**：專案安裝 Unity 特化工作流模組 `agents-workflow-unity`（相依於 `agents-workflow`）。
- **觸發動作**：使用者執行 `python yscb_cli.py installer install agents-workflow-unity`。
- **期望結果**：
  1. 安裝器依序安裝相依模組。
  2. 安裝完成後，`agents-workflow` 自動感知 Unity 模組已安裝，並讀取其宣告之 SOP 補丁與 Extension。
  3. 自動重新生成 `.agents/workflows/` 中的 IDE 指令（例如在 `ContextInit.md` 與 `NewPlan.md` 注入 Unity 特化規範），且 `verify` 指令能自動調度 Unity 編譯驗證腳本。

**情境 2：選配獨立模組安裝連動 (Soft / Optional Integration - Case 2)**
- **場景**：專案已安裝 `agents-workflow`，隨後獨立安裝專案知識庫工具 `docs`（無相依）。
- **觸發動作**：使用者執行 `python yscb_cli.py installer install docs`。
- **期望結果**：
  1. 安裝器安裝 `docs` 模組，並廣播通用模組變更事件。
  2. `agents-workflow` 感知到 `docs` 模組已加入，自動將「知識庫巡檢指令」與「主題模板指南」注入 `Review.md` 與 `NewPlan.md`，並啟用 `docs_audit_verify` 擴充。
  3. 若 `agents-workflow` 未安裝，`docs` 模組自身仍可 100% 獨立正常運作，無任何報錯。

---

### API 使用者心智 (Developer Mental Model)

#### 1. 貢獻端模組 (Plugin Module) 宣告方式 (`manifest.json`)
```json
{
  "name": "agents-workflow-unity",
  "version": "1.0.0",
  "dependencies": ["core >= 2.1.0", "agents-workflow >= 1.0.0"],
  "contributes": {
    "agents-workflow": {
      "schema_version": "1.0",
      "sop_patches": [
        {
          "target_sop": "NewPlan.md",
          "target_phase": "Phase 0",
          "position": "append",
          "content_file": "workflows/templates/unity_rules.md"
        }
      ],
      "sop_extensions": [
        {
          "name": "unity_compilation_verify",
          "script": "scripts/unity_compilation_verify.py"
        }
      ]
    }
  }
}
```

#### 2. 主機模組 (Host Module) 查詢方式 (`Python SDK`)
```python
from yscb_core import ProjectContext

ctx = ProjectContext()
# 通用安全提取所有貢獻至 "agents-workflow" 命名空間之模組資料
contributions = ctx.get_contributions("agents-workflow")
for mod_name, mod_dir, payload in contributions:
    patches = payload.get("sop_patches", [])
    extensions = payload.get("sop_extensions", [])
    # 進行主機端的自主任務合成與調度
```

---

### 明確的焦點範疇與非目標 (Scope Focus & Explicit Out of Scope)

#### 本次核心聚焦目標 (In Scope)
1. **Installer 通用生命週期廣播架構 (Generic Lifecycle Hook)**：
   - 於 `yscb_installer.py` 實作安裝/升級/卸載後的通用 `_on_modules_changed.py` 廣播機制（零領域業務耦合）。
2. **Core SDK 命名空間貢獻查詢通道 (Contribution Query Infrastructure)**：
   - 於 `yscb_core.ProjectContext` 實作 `get_contributions(namespace: str)`，支援從所有已安裝模組的 `manifest.json` 安全提取結構化貢獻字典。
3. **`agents-workflow` 主機公開協定與動態合成引擎 (Host Protocol & Synthesizer)**：
   - 定義並公開 `"agents-workflow"` 命名空間之剛性協定格式 (`schema_version`, `sop_patches`, `sop_extensions`)。
   - 於 `agents-workflow` 實作 `_on_modules_changed.py`，連動觸發 SOP 章節動態補丁合成與 IDE 指令更新。
   - 擴充 `verify_plan.py` 與 `ext list/show` 支援多來源動態 Extension 掃描與調度。

#### 明確的非目標 (Explicit Out of Scope)
- **非目標 1 (龐大特定業務代碼)**：本次不實作複雜的 Unity 實機引擎代碼或龐大知識庫專用引擎，聚焦於「連動架構、Hook 與公開協定」，透過標準測試模組進行端到端連動驗證。
- **非目標 2 (執行期通訊)**：不包含執行期記憶體內的 Event Bus 或 RPC 呼叫。


---

## 開放議題紀錄 (Open Questions)

| # | 議題描述 | 狀態 | 結論 |
|---|---------|------|------|
| 1 | 避免 Installer 耦合領域知識 | ✅ 已解決 | 採主機-外掛模式：Installer 僅廣播通用 `_on_modules_changed.py`，Core 提供 `get_contributions()`，業務邏輯由 Host 模組完全自理 |
| 2 | SOP 補丁衝突優先級排序 | ✅ 已解決 | 依已安裝模組順序線性疊加，同章節支援 append/prepend |
| 3 | 安裝順序無關性保證 | ✅ 已解決 | Installer 在任何模組異動後觸發通用廣播，Host 模組自動重新索引收斂 |

---

## 討論結束確認 (Discussion Close Gate)

> [!CAUTION]
> **Agent 執行鐵律**：本欄位**必須由開發者明確宣告**後，Agent 才可將狀態更新為 `Confirmed` 並觸發 Track 分流。Agent 嚴禁自行判定討論完整並推進。

- [x] **開發者已明確宣告討論結束**，P00 語意需求內容已完整且正確。

---

## 三大分流層級判定 (Three-Tier Phasing Matrix)

> 本區塊在開發者確認 P00 後填寫。

| 分流層級 | 判定結果 | 適用場景與判定理由 |
| :--- | :---: | :--- |
| **Level 0：Fast Track** | ☐ | 修改檔案 ≤ 2、不變更 Public API、無跨模組依賴、純 Bug 修復或局部微調 |
| **Level 1：Full Track** | ☑ (推薦) | 單一架構演進情境（Module 安裝期連動與公開協定系統），涉及 `installer`、`core`、`agents-workflow` 三方協同與 1:1 知識庫交付 |
| **Level 2：Full Track $\times$ n<br/>(啟用分類型主計畫 Umbrella)** | ☐ | 多個功能語意/情境、跨模組大型架構重構。子計畫拆分評估以**單個 Full Track 能處理之顆粒度**為單位 |

