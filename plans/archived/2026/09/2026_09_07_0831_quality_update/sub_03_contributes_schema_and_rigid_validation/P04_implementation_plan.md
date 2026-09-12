# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Contributes 宣告架構升級與 Schema 剛性校驗 (Contributes Schema & Rigid Validation)  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-08 在 P03 API 規格書中有 100% 精確之函式、類別與回傳型別對應。
- [x] **邊界防護**：EC-01 ~ EC-06（未宣告目標寬容、跨目標越權、遞迴循環深度熔斷、懸空參照、`config://` 越權、語法損毀）均在校驗器中具備具體處理策略。
- [x] **依賴純淨**：嚴格符合 NFR-01（100% Python 標準庫零依賴）、NFR-02（全量校驗 $\le 25\text{ms}$）、NFR-03（精準 JSON Path 與拼寫建議）。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **參考手冊** | `docs/dev/reference/contributes_format.md` | New | 第三方模組開發者專屬之 Contributes 架構、Ingress/Egress 邊界與 Schema DSL 規範（已先行落檔並對齊 First-Class 語意 URI）。 |
| **工具手冊** | `docs/dev/README.md` | Modify | 掛載 `reference/contributes_format.md` 索引導航（已交付）。 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記 `DN-07`：Contributes Schema 零第三方依賴 DSL 與單向邊界隔離機制。 |
| **設計決策** | `docs/dev/DESIGN_NOTES.md` | Modify | 登記 `DN-DEV-02`：腳手架標準生成 `_format.json` 與 `_manifest.md`。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若有第三方未升級模組尚未建立 `_format.json`，微內核啟動或載入時會不會引發連鎖崩潰？  
> 💡 **防護解法**：依據 `[P01:DR-01]` 漸進相容原則，當目標模組缺失 `_format.json` 時，校驗器視為「未宣告契約」，僅輸出 `logger.warning` 記錄提示，不阻斷其他合法模組的正常加載與聚合。

> ❓ **尖銳問題 2**：指令樹的 options 具備二層分組結構（如 `options.install_mode.force`），驗證器若將通配符當作單層會不會造成誤判或漏檢？  
> 💡 **防護解法**：在 `_format.json` 中明確定錨 `"options": { "*": { "*": "$OptionDef" } }`，驗證器在走訪二層字典時，嚴格以兩次通配展開並精確核對葉子節點結構，杜絕層級錯位。

> ❓ **尖銳問題 3**：若開發者定義了遞迴參照（如 `$CommandNode` 遞迴包含 `cmd`），會不會因惡意構造或循環參照導致 Python 堆疊溢位 (RecursionError)？  
> 💡 **防護解法**：在驗證器走訪節點時注入 `depth` 計數器，硬性限制最大嵌套深度 $\le 10$，一旦超限立即拋出 `MaxRecursionDepthExceeded` 防禦異常。

> ❓ **尖銳問題 4**：開發者手動修改了 `_format.json`，微內核 JIT 嗅探能感應到並重新自癒校驗嗎？  
> 💡 **防護解法**：在 `contributes._scan_contributes_inputs()` 中，將所有已安裝模組的 `module://*/contributes/_format.json` 亦納入 mtime 與 size 快照清單，確保 Schema 變更即時觸發 JIT Dirty 並重新聚合。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：實作 `source/core/core/validator.py`
  - 實作 `TypeSignatureParser`（解析 `str!`, `enum(...)`, `= default`, `*`, `$TypeName`）
  - 實作 `ContributesValidator.validate()` 與 `validate_format_schema()`
  - 整合 `difflib.get_close_matches` 提供 Did you mean 拼寫提示
- [ ] **TASK-02**：實作 `source/core/core/commands/contributes_cmd.py` 與指令註冊
  - 實作 `contributes list` 與 `contributes check`（支援 First-Class 語意 URI 與 `--format`）
  - 於 `source/core/contributes/core.json` 註冊子指令，並清理舊 `phases` 欄位
- [ ] **TASK-03**：加固 `source/core/core/contributes.py`
  - 納入 `_format.json` 至 JIT 嗅探快照；排除 `_` 開頭特殊檔於 target 聚合之外
  - 呼叫 Validator 執行邊界檢核，過濾違規鍵並記錄警告，移除盲目 `except: pass`
  - 導出公開 SDK：`get_format`, `validate`, `list_points`
- [ ] **TASK-04**：整合 `dev` 工具鏈
  - 於 `source/dev/dev/checker.py` 新增 `ContributesCheckPass` 靜態合規阻斷
  - 更新 `source/dev/dev/scaffold.py` 生成新模組時自動附帶 `_format.json` 與 `_manifest.md`
- [ ] **TASK-05**：生態系 5 大模組落地 Ingress/Egress 契約
  - 為 `core`, `server`, `dev`, `agents-workflow`, `knowledge-db` 建立 `_format.json` 與 `_manifest.md`
  - 清理全模組 `contributes/core.json` 舊殘留之 `phases` 欄位
- [ ] **TASK-06**：單元測試與邊界測試覆蓋
  - 於 `source/core/tests/test_validator.py` 覆蓋 FT-01 ~ FT-05
  - 於 `source/core/tests/test_contributes_cmd.py` 覆蓋 FT-06, FT-07
  - 於 `source/dev/tests/test_checker.py` 覆蓋 FT-08
- [ ] **TASK-07**：全生態系回歸跑測與設計筆記留痕
  - 執行 `dev test --all --quiet` 確保 100% 通過（FT-09）
  - 更新 `docs/core/DESIGN_NOTES.md` (`DN-07`) 與 `docs/dev/DESIGN_NOTES.md` (`DN-DEV-02`)

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] JIT 嗅探納入 Schema 檔案**：`_format.json` 正式列入 `_scan_contributes_inputs()`，保障契約更動與注入數據更動享有完全相同的 JIT 自癒響應機制。
- **[P04:DR-02] 雙軌檢測容差分離**：`dev check` 採零容忍 Exit Code 1 阻斷；運行期 `scan_and_inject` 採容錯過濾與 Warning 記錄，確保開發期剛性阻斷、生產運行期高可用韌性。
