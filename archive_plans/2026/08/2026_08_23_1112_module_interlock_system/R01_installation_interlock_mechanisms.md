# 技術調研報告：模組安裝期連動機制與 SOP/Extension 擴充架構

> 功能名稱：Module 安裝期連動系統設計 (Installation-time Interlock System)  
> 建立日期：2026-08-23  
> 所屬主計畫：2026_08_23_1112_module_interlock_system  
> 狀態：Concluded  
> 擴充項目：none  
> 模板版本：v1.0  

---

## 1. 背景痛點與架構原則

在 `ys-codebase` 模組生態中，擴充模組需要與主機模組進行安裝期連動：
- **Case 1 (強相依特化模組)**：`agents-workflow-unity` 依賴於 `agents-workflow`，需注入 Unity 特化規範至 SOP 並添加驗證 Extension。
- **Case 2 (選配/無相依協同模組)**：`docs`（專案知識庫）無硬性依賴，但當專案存在 `agents-workflow` 時，需自動注入知識庫巡檢至 SOP 與 Extension。

### 🚨 核心解耦鐵律：主機-外掛模式 (Host-Plugin Model)
1. **Installer 零領域知識**：`yscb_installer.py` 是純粹的套件管理器，**絕對禁止**包含任何 SOP、Markdown、Unity 或 Antigravity IDE 領域代碼。
2. **Core SDK 純資料聚合**：`yscb_core` 僅提供通用字典讀取與安全查詢介面，不解析具體業務欄位。
3. **主機模組完全自理**：`agents-workflow` 作為「SOP 主機」，主動查詢其他模組的貢獻資料並負責合成與調度。

---

## 2. 三大剛性協定合約 (The Three Rigid Protocol Contracts)

```
┌─────────────────────────────────────────────────────────────┐
│ 協定合約 I：Installer 通用生命週期廣播合約                   │
│   • 檔案協定: scripts/_on_modules_changed.py                │
│   • 呼叫簽名: python _on_modules_changed.py <event> <target>│
├─────────────────────────────────────────────────────────────┤
│ 協定合約 II：Core SDK 命名空間貢獻查詢合約                  │
│   • 資料協定: manifest.json -> contributes.<namespace>     │
│   • API 簽名: context.get_contributions(namespace)          │
├─────────────────────────────────────────────────────────────┤
│ 協定合約 III：agents-workflow SOP 主機擴充合約              │
│   • 命名空間: "agents-workflow"                             │
│   • 欄位規格: sop_patches 与 sop_extensions 剛性 Schema     │
└─────────────────────────────────────────────────────────────┘
```

---

### 協定合約 I：Installer 通用生命週期廣播 (Lifecycle Broadcast Contract)

- **觸發時機**：在任何 `install`, `pull`, `remove` 成功結束後，Installer 遍歷已安裝模組。
- **檔案規格**：若模組目錄包含 `scripts/_on_modules_changed.py`（或 `_on_modules_changed.py`），以獨立子進程執行：
  ```bash
  python <module_dir>/scripts/_on_modules_changed.py <event_type> <target_module_name>
  ```
  - `event_type`：`"installed"` | `"removed"` | `"updated"`
  - `target_module_name`：本次被安裝/移除/更新的模組名稱
- **防禦性約束**：
  - 若 Hook 拋出異常或 Exit code != 0，Installer 僅輸出 `[WARN]` 記錄，**絕不阻斷或回滾**核心安裝事務。
  - Installer 傳參嚴格限制於 `(event_type, target_module_name)`，不傳遞任何私有業務狀態。

---

### 協定合約 II：Core SDK 通用貢獻查詢 (Contribution Registry Contract)

- **資料協定 (`manifest.json`)**：
  `manifest.json` 頂層新增可選 `contributes` 欄位，其第一層 Key 必須為**目標主機模組的命名空間 (Host Namespace)**：
  ```json
  {
    "name": "any-plugin-module",
    "version": "1.0.0",
    "contributes": {
      "<host-module-namespace>": {
        "... arbitrary namespaced payload ..."
      }
    }
  }
  ```
- **SDK API 簽名 (`yscb_core.ProjectContext`)**：
  ```python
  class ProjectContext:
      def get_contributions(self, namespace: str) -> List[Tuple[str, Path, Dict[str, Any]]]:
          """
          安全讀取所有已安裝模組中，宣告於指定 namespace 之貢獻內容。
          返回: [(模組名稱, 模組實體目錄路徑, 貢獻 Payload 字典), ...]
          """
  ```

---

### 協定合約 III：`agents-workflow` SOP 主機擴充合約 (Host Extension Contract)

主機命名空間剛性定義為 `"agents-workflow"`。任何模組欲向 `agents-workflow` 提供擴充，必須於 `manifest.json` 遵照以下剛性 JSON Schema：

```json
{
  "contributes": {
    "agents-workflow": {
      "schema_version": "1.0",
      "sop_patches": [
        {
          "target_sop": "NewPlan.md",
          "target_phase": "Phase 0",
          "position": "append",
          "content_file": "workflows/templates/unity_phase0_rules.md"
        }
      ],
      "sop_extensions": [
        {
          "name": "unity_compilation_verify",
          "script": "scripts/unity_compilation_verify.py",
          "doc": "workflows/extensions/unity_compilation_ext.md"
        }
      ]
    }
  }
}
```

#### Schema 欄位剛性定義
1. **`schema_version`**：固定為字串 `"1.0"`。
2. **`sop_patches`**（可選清單）：
   - `target_sop`（必填）：目標 SOP 檔案名稱（如 `ContextInit.md`, `NewPlan.md`, `Review.md`）。
   - `target_slot`（必填）：目標 Slot 名稱（剛性定義於主機 SOP Slot 全集，如 `Phase0`, `Phase1`, `Step1`）。
   - `position`（必填）：`"append"`（追加於 Slot 標記之後）或 `"prepend"`（置於 Slot 標記之前）。
   - `content_file`（必填）：相對於貢獻模組根目錄的 Markdown 檔案路徑。
3. **`sop_extensions`**（可選清單）：
   - `name`（必填）：Extension 唯一名稱（如 `unity_compilation_verify`）。
   - `script`（可選）：驗證腳本路徑（相對於貢獻模組根目錄）。
   - `doc`（可選）：SOP Extension 說明文檔路徑。

#### 更新後的 `agents-workflow-unity` 範例
```json
{
  "contributes": {
    "agents-workflow": {
      "schema_version": "1.0",
      "sop_patches": [
        {
          "target_sop": "NewPlan.md",
          "target_slot": "Phase0",
          "position": "append",
          "content_file": "workflows/templates/unity_phase0_rules.md"
        }
      ],
      "sop_extensions": [
        {
          "name": "unity_compilation_verify",
          "script": "scripts/unity_compilation_verify.py",
          "doc": "workflows/extensions/unity_compilation_ext.md"
        }
      ]
    }
  }
}

---

## 3. 端到端連動流程驗證 (End-to-End Sequence)

### 情境 A：`agents-workflow-unity`（強相依安裝）
1. 使用者執行 `python yscb_cli.py installer install agents-workflow-unity`。
2. Installer 拓撲解析：依序安裝 `core` ➔ `agents-workflow` ➔ `agents-workflow-unity`。
3. `agents-workflow-unity` 安裝完成後，Installer 觸發通用廣播 `_on_modules_changed.py`。
4. `agents-workflow` 的 `_on_modules_changed.py` 被調用 ➔ 調用 `ProjectContext.get_contributions("agents-workflow")` ➔ 取得 Unity 模組貢獻的 `sop_patches` 與 `sop_extensions` ➔ 自動重新編譯 `.agents/workflows/` 指令！

### 情境 B：`docs` 知識庫（選配獨立安裝）
1. 專案已存在 `agents-workflow`。
2. 使用者執行 `python yscb_cli.py installer install docs`。
3. `docs` 安裝完成 ➔ Installer 廣播 `_on_modules_changed.py`。
4. `agents-workflow` 感知變更 ➔ 讀取 `docs` 的 `contributes["agents-workflow"]` ➔ 自動將知識庫巡檢規範合成進 `Review.md` 與 `NewPlan.md`。

---

## 4. 最終定稿架構確立 (Final Architecture)

### 4a. SOP Slot 全集 (Slot Full Registry)

僅以下 SOP 具備跨模組注入的業務意義，其餘 SOP（`Continue`、`Discuss`、`Pause`、`Research`）為通用防呆結構，不植入 Slot：

| 目標 SOP | Slot 名稱清單 | 描述 |
| :--- | :--- | :--- |
| **`NewPlan.md`** | `Phase0` `Phase1` `Phase2` `Phase3` `Phase4` `Phase5` `Phase6` `Phase7` | 各 Phase 末尾，供領域特化視角診斷舕加複检清單 |
| **`Review.md`** | `Step1` `Step2` `Step3` `Step4` | 各步驟末尾，供領域特化稽核 Checklist |
| **`ContextInit.md`** | `Step1` `Step2` `Step3` `Step4` | 各步驟末尾（輕量），供連動模組注入「需額外加載的模組規範摘要」 |

**標記格式**：`<!-- YSCB_SLOT:<SlotName> -->`

**清除規則**：合成引擎在輸出前執行正則剖除：
```python
clean = re.sub(r'<!--\s*YSCB_SLOT:[a-zA-Z0-9_]+\s*-->\n?', '', content)
```

### 4b. Extension 雙層發現鏈 (Two-Tier Discovery Chain)

```
第一層 (sop_ext://) ———————————————「用戶自定義層」 最高優先
  實體路徑: ./extensions/
  定位: 專案開發者手寫、專案專屬特化或覆蓋內建 Extension

第二層 (modules/<plugin>/) —————「模組連動注入層」 随模組安裝自動隨掛
  實體路徑: ./modules/<plugin>/scripts/, ./modules/<plugin>/workflows/extensions/
  定位: 模組自帶、隨插即用，免複製免污染專案目錄

同名覆蓋規則: 若 sop_ext:// 存在同名 Extension，以第一層為準
```

`ext list` 輸出格式：
```text
dogfooding_pipeline_ext   | [always]    | [sop_ext]
docs_audit_verify         | [always]    | [module: docs]
unity_compilation_verify  | [on_demand] | [module: agents-workflow-unity]
```

### 4c. 調研結論 (Final Architecture Conclusion)

透過上述三大剛性協定合約與完善後的架構補充：
- `yscb_installer.py` 與 `yscb_core` 保持 100% 通用與純淨。
- `agents-workflow` 擁有完整的自主性與擴充能力。
- 達成 100% 安裝順序無關性與高內聚低耦合。
- `build` 不觸發廣播，給法承諷 Slot 標記純淨創建 SOP 純淨資料流。
