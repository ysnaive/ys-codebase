# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_host_and_core_foundation_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-10 在 API 規格書與架構計畫中皆具備精確實作路徑與方法契約
- [x] **邊界防護**：EC-01 ~ EC-06 涵蓋同前綴目錄穿越防禦、舊版 Mock 平鋪相容、臨時測試目錄雙層路徑讀取與空格參數解析
- [x] **依賴純淨**：嚴格遵守 `[DN-21]` 保留 `yscb.py` 薄代理函式，嚴格維持 `semver.py` 正向版本比較與 `~=` Major 鎖定

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-26]` 雙層分桶指令聚合與 `uri` 記憶體快取設計決策 |
| **微觀日誌** | `plans/.../changelog.md` | Modify | 記錄本子計畫各階段演進歷史 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：`ContributesAggregator` 引入 `__modules__` 後，若既有單元測試（如 `test_cli_router.py`）傳入未分桶的舊版平鋪結構，是否會導致 CLI Guild 拋出 KeyError？  
> [*] **防護解法**：`core/providers.py:get_agents_cli_guild()` 採雙軌容錯機制：若 `commands` 包含 `"__modules__"` 則遍歷模組分桶；若不包含則平滑回退為遍歷頂層平鋪結構，確保舊測試 Mock 100% 通過。

> [?] **尖銳問題 2**：`uri.resolve()` 引入 `(yscb_dir, mtime)` 記憶體快取後，若執行時期其他進程或測試動態更新了 `contributes.merged.json`，是否會讀到陳舊快取？  
> [*] **防護解法**：快取判定在每次調用時皆以極速微秒級之 `os.path.getmtime(target)` 比較，一旦檔案 `mtime` 變更或檔案不存在立即失效重讀，達成零陳舊風險與零多餘 I/O。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01 (基礎與 Schema)**：修改 `source/core/contributes/_format.json`、`core.json` 與 `core/semver.py`
- [x] **TASK-02 (底層組件)**：修改 `source/core/core/commands/registry.py`、`core/uri.py` 與 `core/__init__.py`
- [x] **TASK-03 (聚合與提供者)**：修改 `source/core/core/contributes.py` 與 `source/core/core/providers.py`
- [x] **TASK-04 (核心服務與宿主)**：修改 `source/core/core/engine.py`、`core/pip_manager.py`、`core/ide_projector.py`、`core/commands/dispatcher.py`、`core/installer.py` 與 `yscb.py`
- [x] **TASK-05 (單元測試與回歸)**：擴充/驗證 `test_contributes_cmd.py`、`test_uri.py`、`test_core_commands.py` 等，執行全模組測試

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 零回歸交付保證**：
  本次重構與修復以全套 192 項 `core` 單元測試及全生態系 550 項單元測試 100% 綠燈為唯一驗收通過標準。

