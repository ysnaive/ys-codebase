# 測試計畫 (Test Plan)

> 功能名稱：Module 安裝期連動系統設計 (Installation-time Interlock System)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.3  

---

## 1. 核心自動化測試矩陣 (Automated Test Matrix)

| ID | 類別 | 對應項目 | 測試描述與操作步驟 | 預期結果 | 實測狀態 |
|:---|:---|:---|:---|:---|:---:|
| **FT-01** | 功能 | FR-01 | 模擬模組安裝完成，驗證 `_broadcast_modules_changed()` 正確調用已安裝模組的 `scripts/_on_modules_changed.py`。 | 成功傳遞 `(event_type, target_module)` 參數並執行 | ✅ Passed |
| **FT-02** | 功能 | FR-01 | 驗證 `installer build` 指令執行完畢後，嚴格**不觸發** `_broadcast_modules_changed()`。 | 確保 build 產物純淨，零廣播副作用 | ✅ Passed |
| **FT-03** | 功能 | FR-03 | 於 `test_interlock.py` 呼叫 `ProjectContext.get_contributions("agents-workflow")`，讀取 Mock 外掛模組。 | 正確解析並返回貢獻模組名稱、目錄路徑與 `contributes` 字典清單 | ✅ Passed |
| **FT-04** | 功能 | FR-04 | 驗證 `sop_patches` 與 `sop_extensions` 之剛性 Schema 格式校驗。 | 正確識別合格的 manifest 宣告 | ✅ Passed |
| **FT-05** | 功能 | FR-05 | 觸發 `agents-workflow` 的 `_on_modules_changed.py`，驗證在已存在 `.agents/workflows/` 的環境下自動重新生成指令。 | 工作流指令自動更新且無任何異常拋出 | ✅ Passed |
| **FT-06** | 功能 | FR-06 | 執行 `sop_synthesizer.py`，測試 `NewPlan.md` 的 `Phase0` Slot 注入（append 與 prepend 模式）。 | 內容精確注入於 `Phase0` 區塊，標記被乾淨剝除 | ✅ Passed |
| **FT-07** | 功能 | FR-06 | 測試無任何外掛注入時，`sop_synthesizer.py` 正則剝除所有 `<!-- YSCB_SLOT:... -->` 標記。 | 輸出 Markdown 100% 純淨，無任何 `YSCB_SLOT` 殘留 | ✅ Passed |
| **FT-08** | 功能 | FR-07 | 執行 `ext list` 與 `verify_plan.py`，測試雙層 Extension 發現鏈（`sop_ext://` 優先於 `modules/<plugin>/` 同名擴充）。 | 正確標記 `[sop_ext]` 與 `[module: xxx]`，且專案自定義同名擴充優先調度 | ✅ Passed |
| **ET-01** | 邊界 | EC-01 | 測試安裝未提供 `_on_modules_changed.py` 的模組。 | Installer 正常靜默略過，不報錯不阻塞 | ✅ Passed |
| **ET-02** | 邊界 | EC-02 | 測試 `_on_modules_changed.py` 內部拋出 Exception 或 exit code != 0。 | Installer 捕獲異常並輸出 `[WARN]`，核心安裝事務維持成功 | ✅ Passed |
| **ET-03** | 邊界 | EC-03 | 測試 `manifest.json` 缺少 `contributes` 或其值非字典時。 | `get_contributions()` 寬容過濾，安全返回空清單 | ✅ Passed |
| **ET-04** | 邊界 | EC-04 | 測試 `sop_patches` 指向不存在的 `target_sop` 檔案。 | 合成引擎輸出 Warning 並略過，不崩潰 | ✅ Passed |
| **ET-05** | 邊界 | EC-05 | 測試 `sop_patches` 指向不存在的 `target_slot` 標記。 | 合成引擎輸出 Warning 並略過，保留原文檔 | ✅ Passed |
| **ET-06** | 邊界 | EC-06 | 測試 `content_file` 檔案路徑不存在。 | 合成引擎輸出 Warning 並略過該注入，不崩潰 | ✅ Passed |
| **ET-07** | 邊界 | EC-07 | 測試 `contributes.sop_extensions` 宣告之驗證腳本不存在。 | `verify_plan` 標記警告並跳過，不中斷整體合規檢查 | ✅ Passed |
| **ET-08** | 邊界 | EC-08 | 測試兩個模組同時注入相同 SOP 的相同 Slot。 | 線性疊加注入，不崩潰，行為穩定 | ✅ Passed |
| **RT-01** | 回歸 | 全域 | 執行 `python test/run_regression.py` 全套單元測試與 E2E 下游沙盒模擬。 | 全數 100% Passed (共 53 項單元/整合測試 + E2E 下游沙盒模擬) | ✅ Passed |
| **PT-01** | 效能 | NFR-01 | 量測 `get_contributions()` + 9 份 SOP 動態 Slot 合成與正則剝除之總耗時。 | 實測總耗時 `< 5ms`（遠低於 150ms 上限） | ✅ Passed |

---

## 2. UX 與手動視覺互動驗證 (UX Validation)

| ID | 驗證主題 | 測試描述與操作路徑 | 開發者體驗與視覺反饋 | 驗證狀態 |
|:---|:---|:---|:---|:---:|
| **UX-01** | `ext list` 終端雙層來源標籤排版 | 執行 `python yscb_cli.py agents-workflow ext list`，觀察輸出是否清晰呈現 `[sop_ext]`（專案自定義）與 `[module: xxx]`（模組連動）。 | 表格整齊、來源標籤清晰直觀、顏色與對齊無瑕疵 | ⬜ 等待開發者確認 |
| **UX-02** | 連動產生物純淨度與 IDE 無感同步 | 安裝 Mock 外掛模組後，檢視 `.agents/workflows/NewPlan.md`，確認包含 Mock 規則且無任何 HTML `YSCB_SLOT` 註解殘留。 | 內容精確注入、排版純淨專業、IDE 指令完全無感即時同步 | ⬜ 等待開發者確認 |

---

## 3. Bug 修復記錄 (Defect Log)

- **BUG-01: Windows CP950 Console UnicodeEncodeError**
  - **根因**：`_on_modules_changed.py` 印出箭頭符號 `➔` 時未經 UTF-8 編碼防呆，觸發 CP950 解碼失敗。
  - **修復**：在腳本開頭導入標準 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 防呆區塊。
- **BUG-02: 跨模組 CLI 模組命名衝突 (Namespace Shadowing)**
  - **根因**：`_on_modules_changed.py` 中 `from cli import ...` 因 `sys.path` 順序加載到 `core/scripts/cli.py`。
  - **修復**：採用 `importlib.util.spec_from_file_location` 隔離加載自身模組的 `cli.py`。

---

## 4. 測試結論與 Phase 6 Checkpoint

- [x] **Agent CLI 自動化測試**：已實機執行 `python test/run_regression.py` 並全部通過（53/53 Passed + E2E 100% Passed）
- [ ] **開發者 UX / 手動測試確認**：開發者明確回覆「UX 驗證通過」或指示免測，允許進入 Phase 7
