---
name: "dogfooding_pipeline_ext"
phase: "P04, P05, P06, P07, FT_plan"
trigger: "always"
description: "自引用 (Dogfooding) 三層空間修改、構建、全量回歸與自引用更新閉環 Checklist"
---

# Extension: Dogfooding 自引用流水線與防呆驗收

本 Extension 適用於 `ys-codebase` 工具庫自引用專案。規範 Agent 在進行任何源碼修改時，必須遵守三層空間隔離並落實標準四步閉環流水線。

---

## 擴充 Checklist

- [ ] **Stage 1 (源碼空間確認與版本號維護)**：
  - [ ] 所有檔案修改均 100% 位於 `ys_codebase/source/` 或 `ys_codebase/yscb_*.py`，無任何直接編輯 `modules/` 或 `.agents/` 的越界行為。
  - [ ] 若源碼有實質邏輯/設定變更，已執行 `python yscb_cli.py version bump <module> <level>` 正確遞進 `manifest.json` 版本號（SemVer 剛性維護）。
- [ ] **Stage 2 (模組打包構建)**：已執行 `python yscb_cli.py installer build <module>` (或 `build --all`)，且 `ys_codebase/build/` 正確生成並繼承最新版本號。
- [ ] **Stage 3 (全量回歸測試)**：已實機執行 `python test/run_regression.py` 並取得全量測試 100% Passed。
- [ ] **Stage 4 (自引用同步與發布檢驗)**：
  - [ ] 根目錄起手腳本已覆蓋同步 (`yscb_installer.py` / `yscb_cli.py`)。
  - [ ] 已執行 `python yscb_cli.py installer install <module> --force` 部署至 `modules/`。
  - [ ] 若工作流有變更，已執行 `python yscb_cli.py agents-workflow --ide-antigravity` 重新生成 `.agents/workflows/`。
  - [ ] 執行 `python yscb_cli.py version status` 驗證自引用模組狀態為 `[SYNCED]`。
  - [ ] 執行 `python yscb_cli.py agents-workflow verify` 驗證 `dogfooding_pipeline_verify.py` 外掛 100% 通過。

---

## 結果寫入規範

```markdown
### Extension: dogfooding_pipeline_ext 執行結果
| 檢查項目 | 狀態 | 發現與備註 |
|:---|:---:|:---|
| Stage 1: 源碼空間確認 (ys_codebase/) | ✅ | 100% 於 source 目錄進行修改，無 modules/ 直修 |
| Stage 2: 模組打包構建 (build) | ✅ | build/ 目錄產物已重新生成 |
| Stage 3: 全量回歸測試 (test) | ✅ | python test/run_regression.py 100% 通過 |
| Stage 4: 自引用同步 (install/ide) | ✅ | modules/ 已強制覆蓋安裝，IDE 指令已重新生成 |
**結論**：已通過 Dogfooding 自引用標準四步流水線驗收。
```
