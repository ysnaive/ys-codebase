# 需求規格說明書 (Requirements Specification)

> 功能名稱：Dev 模組測試效能瓶頸優化、Mock 模組建置隔離與 Windows Unicode/cp950 編碼異常修復  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Windows 控制台與子進程編碼安全防禦 | 在 `dev.tester`、`dev.testing.case` 等所有 `subprocess.run` 與終端輸出處理中，標準化啟用 `encoding="utf-8"`, `errors="replace"`，並在控制台 print/write 時防禦 cp950 編碼字符溢出。 | P0 | [P00:DR-01] |
| **FR-02** | 測試四層分類體系精準歸類 (`WORKFLOW`) | 將跨模組調度與高階多進程 E2E 測試（如 `test_dev_test_high_level_orchestration` 等）精準標記為 `@require(Requirement.WORKFLOW)`，使日常回歸 (`LOGIC` + `ENV`) 預設跳過重型測試。 | P0 | [P00:DR-02] |
| **FR-03** | 單元測試去子進程化與 Mock 隔離 | 重構驗證清理邏輯、參數調度與內部狀態之單元測試（如 `test_run_test_all_success_cleans_sandboxes`），以 Mock 取代遞迴 fork 子進程與全量沙盒。 | P0 | [P00:DR-02] |
| **FR-04** | 建置與發布測試全面改採 Mock Module 隔離 | 重構 `test_builder.py` 與 `test_release_pipeline.py`，全面改以動態生成之輕量 Mock Module 測試 build、package_release、revision purge 與 index.json，完全解除對真實官方模組原始碼的打包依賴。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Windows cp950 終端輸出包含非繁體中文/非 BMP Unicode 字符或替換字元 `\ufffd` | 控制台輸出層自動轉義或 replace，保證進程零崩潰並完整呈現診斷摘要。 |
| **EC-02** | Mock 模組在沙盒測試中打包與發布 | 產物完全局限在測試沙盒內部之 `module.build://` 與 `module.release://`，嚴禁外溢或覆蓋真實空間。 |
| **EC-03** | 開發者透過 CLI 明確指定 `--workflow` 或 `--all-types` | `WORKFLOW` 類別測試正常被 TestDiscovery 收集並完整執行驗證。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能指標 | 日常預設回歸測試 `python yscb.py dev test --all` 總耗時壓縮至 $\le 5.0$ 秒（由 12.5 秒加速超過 60%）。 |
| **NFR-02** | 相容與零副作用 | 官方新增或修改模組時，建置/發布測試零破壞；全庫既有 119 個測試案例保持 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：Windows 平台 `sys.stdout.encoding` 在某些終端下為 `cp950`，直接 `print(str)` 若包含無法編碼之字符會引發 `UnicodeEncodeError`。
- **`[!CAUTION]`**：`test_builder.py` 過去對 `core` 與 `dev` 進行打包，當模組檔案增多或版本遞增時會拖慢測試速度並產生殘留依賴；改採動態 Mock Module 可保證測試時間恆定在毫秒級。
