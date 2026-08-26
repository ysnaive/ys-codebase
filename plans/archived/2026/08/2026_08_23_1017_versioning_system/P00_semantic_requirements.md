# 語意化需求書 (Semantic Requirements)

> 功能名稱：完善版本號系統、相依相容性檢查、鏈式增量遷移與更新覆蓋防護  
> 建立日期：2026-08-23  
> 計畫類型：Feature / Refactor  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.1  

---

## [類型：Feature / Refactor] 語意化需求

### 依據專題調研報告 (Technical Research References)
- 📄 [R01_versioning_rigidity_and_progression.md](./R01_versioning_rigidity_and_progression.md)：版本號語意剛性、專案特化 SemVer 映射、SSOT 與防呆守門。
- 📄 [R02_version_control_update_and_override_mechanisms.md](./R02_version_control_update_and_override_mechanisms.md)：資產分級保護、五階段事務性升級回滾流水線與鏈式線性增量遷移。

---

### 現況痛點 (Current Pain Points)
1. **多點分散定義與版本失真**：版本號分散於 `manifest.json`、`__version__`、`yscb_installer.py`、`yscb_config.json` 等處，缺乏 SSOT 單一真實來源。
2. **缺乏 SemVer 解析與相依性相容約束引擎**：`manifest.json` 的 `dependencies` 僅支援字串名稱（如 `["core"]`），缺乏版本區間校驗（如 `core >= 2.0.0`、`^2.0.0`），安裝時無法即時防呆相容性衝突。
3. **升級覆蓋的資料破壞風險**：模組更新時若全量覆蓋，會沖刷下游專案自訂的 `config.project.json` 與 `AGENTS.md` 特化規則；若不覆蓋又無法注入新設定欄位。
4. **跨版本遷移缺乏鏈式增量架構**：目前 `_migration.py` 缺乏標準的鏈式增量步階執行邏輯與失敗原子回滾 (Rollback) 機制。

---

### 專案適配 SemVer 三級判定公理 (Project-tailored SemVer Axioms)
- **`MAJOR` (全域心智 / 典範轉移)**：專案根目錄調用方式發生根本性重構、工具庫架構全面換代。*(平時極少觸發)*
- **`MINOR` (資料格式 / Schema 變更)**：`config.project.json` / `manifest.json` 結構重組、SOP 模板不相容升級，**必須提供 `_migration.py` 增量遷移步階**。
- **`PATCH` (日常功能遞增 / 內部修復)**：所有向後相容的日常迭代（新增 API、CLI 指令、SOP 擴充、Bug 修復、效能優化、重構、文檔更新），**零 Migration 需求**。

---

### 使用情境 (User / Developer Scenarios)

**情境 1：全模組版本狀態一覽與一鍵檢查更新 (Version Status & Check-Update CLI)**
- 開發者執行 `python yscb_cli.py version status`，終端以 Markdown 表格輸出所有模組的【源碼版本】、【建置版本】與【安裝版本】對照矩陣。
- 開發者執行 `python yscb_cli.py version check-update`，自動比對遠端/源碼最新版本，清晰列出可更新模組、目標版本、更新等級 (Patch / Minor / Major) 與 Migration 需求。
- 開發者/Agent 執行 `python yscb_cli.py version bump <module> <major|minor|patch>`，自動以 `source/<module>/manifest.json` 為 SSOT 遞進版本。

**情境 2：相依約束宣告與安裝相容性防呆 (Dependency Compatibility Gate)**
- 模組在 `manifest.json` 中宣告 `dependencies: ["core >= 2.0.0", "agents-workflow ^1.0.0"]`。
- 在執行 `yscb_installer.py install` 或 `build` 時，相依解析引擎自動比對已安裝/建置之模組版本。若相容性不滿足，立即中止並給出清晰錯誤指引，防止執行期崩潰。

**情境 3：資產分級安全覆蓋與範本增量合併 (Tiered Safe Overwrite)**
- 下游專案升級模組時：
  - 純代碼產物（`modules/<mod>/scripts/` 等）100% 冪等原子覆蓋。
  - `config.project.json` 透過 `deep_merge(template, user_config)` 安全合併，自動補齊新版欄位預設值，下游專案已修改的自訂路徑絕對不被沖刷。
  - `config.local.json` 100% 唯讀保留。
  - `AGENTS.md` 透過定界標記 (`<!-- YSCB_AGENTS_BEGIN -->`) 軟合併，下游特化規則完整保留。

**情境 4：鏈式線性增量遷移 (Sequential Incremental Migration Engine)**
- 模組升級跨越版本（如 `v1.0.x` ➔ `v1.3.x`）時，安裝器自動調用 `_migration.py 1.0.0 1.3.0`。
- 模組以 `@runner.step("1.1.x")`、`@runner.step("1.2.x")` 註冊 Minor 代際步階，內部線性依序執行 `Step(1.1.x) ➔ Step(1.2.x) ➔ Step(1.3.x)`。任一步階若失敗拋出異常，立即觸發 Snapshot 還原回滾，保證升級原子性。

```python
# modules/<module>/scripts/_migration.py
import sys
from pathlib import Path
from yscb_core import MigrationRunner

runner = MigrationRunner()

# 註冊 1.0.x -> 1.1.x 遷移邏輯
@runner.step("1.1.x")
def migrate_to_1_1(project_root: Path, module_dir: Path):
    """將舊版 config 欄位 paths.plans 改名為 paths.plans_dir"""
    pass

# 註冊 1.1.x -> 1.2.x 遷移邏輯
@runner.step("1.2.x")
def migrate_to_1_2(project_root: Path, module_dir: Path):
    """新增預設 extensions 目錄結構"""
    pass

if __name__ == "__main__":
    old_ver = sys.argv[1]
    new_ver = sys.argv[2]
    # runner 會自動依序執行: old < step <= new
    runner.run(old_ver, new_ver)
```

**情境 5：SOP 生命週期與外掛式插件防呆守門閉環 (SOP Lifecycle & Pluggable Quality Gate)**
- 在 `P01` 宣告預計 Bump Level、`P04` 鎖定 Target Version、`Phase 7` 結案自動 Bump。
- **通則動態外掛 Hook**：`verify_plan.py` 保持純淨通用，僅動態掃描 `sop_ext://` 下是否存在 `<ext_name>_verify.py` 並自動調用執行。
- **專案特化落地**：本專案建立 `extensions/dogfooding_pipeline_verify.py`，專門於本專案開發結案時檢驗「源碼修改是否有執行版本遞增」、「全專案源碼/建置/安裝三態一致性」與「`CHANGELOG.md` 紀錄完整性」。

---

### 明確的非目標 (Explicit Out of Scope)
1. **引入第三方套件**：100% 使用 Python 3.8+ 標準庫（`urllib`、`pathlib`、`json`、`shutil`、`re`、`unittest`），嚴禁外部依賴。
2. **遠端複雜 Package Server 開發**：本計畫專注於本機與 Git 來源之安裝升級與相依解析，不自建遠端 Package Registry 伺服器。
3. **在通則腳本硬編碼特化邏輯**：嚴禁在 `agents-workflow` 通用腳本中寫入特定專案特化邏輯，一律透過 `sop_ext://` 插件化解耦。

---

## 開放議題紀錄 (Open Questions)

| # | 議題描述 | 狀態 | 結論 |
|---|---------|------|------|
| 1 | 本次「完善版本號系統」的核心聚焦範疇為何？ | ✅ 已解決 | 涵蓋：SemVer 解析器、相依版本約束檢查、專案適配三級 Bump、資產分級安全覆蓋、鏈式增量 Migration 與 SOP 守門。 |
| 2 | 版本號的語意與格式預期？ | ✅ 已解決 | 遵循 SemVer 2.0.0 規範。定義專案適配公理：Major (全域心智/典範轉移)、Minor (需 Migration 之資料格式變更)、Patch (日常功能遞增與修復)。 |
| 3 | 相依約束表達式語法支援？ | ✅ 已解決 | 支援精確比對 (`==1.0.0` / `1.0.0`)、區間比較 (`>=1.0.0, <2.0.0`)、Caret (`^1.0.0`)、Tilde (`~1.0.0`) 與萬用字元 (`*`)。 |
| 4 | 升級覆蓋與 Migration 執行模型？ | ✅ 已解決 | 採三大資產分級保護（純代碼原子替換、配置增量合併、文檔標記軟合併）+ 鏈式線性增量遷移 (`@runner.step("1.1.x")`) + 失敗自動 Snapshot 回滾。 |
| 5 | 本地開發發布時如何確認正確遞增版本號且不污染通用 SOP？ | ✅ 已解決 | 採「通則動態外掛 Hook (`verify_plan.py`) + 專案特化腳本 (`extensions/dogfooding_pipeline_verify.py`)」完全解耦方案。 |

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
| **Level 1：Full Track** | ☑ **(推薦)** | 單一功能主題（完善版本號系統、相依約束、鏈式遷移與覆蓋防護），涉及 `core` SDK、`installer` 引擎、`agents-workflow` CLI 與專案擴充，需完整 P01~P07 規格、架構、API、測試與實作驗證。 |
| **Level 2：Full Track $\times$ n<br/>(啟用分類型主計畫 Umbrella)** | ☐ | 多個獨立功能主題、跨領域大型重構。本次為單一高內聚架構模組體系，無需拆分 Umbrella。 |

> 分流後立即執行：
> - **Level 1 (Full Track)** → 確認 `changelog.md` 就緒，進入 Phase 1 需求規格轉譯 (`P01_requirements_spec.md`)。
