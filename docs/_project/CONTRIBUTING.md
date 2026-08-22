---
target: "Project/Contributing"
doc_type: "topic"
status: "active"
source_paths:
  - "ys_codebase/yscb_installer.py"
  - "ys_codebase/source/"
  - "ys_codebase/build/"
  - "test/run_regression.py"
related_docs:
  - "./STANDARDS.md"
  - "../_global/ARCHITECTURE.md"
last_updated: "2026-08-22"
---

# 模組開發與發布貢獻指南 (Contributing Guide)

本指南引導開發者如何在 `ys-codebase` 體系中開發新的功能模組，並進行回歸測試與發布。

---

## 🚀 建立新模組的標準流程

### 步驟 1：在 `ys_codebase/source/` 建立模組目錄
```bash
# 建立模組資料夾
mkdir -p ys_codebase/source/my-new-module
```

### 步驟 2：撰寫 `manifest.json` 與源碼
在 `ys_codebase/source/my-new-module/manifest.json` 定義模組元數據：
```json
{
  "name": "my-new-module",
  "version": "1.0.0",
  "description": "新模組說明",
  "dependencies": []
}
```

編寫模組所需之代碼、文檔或配置檔。

---

### 步驟 3：[可選] 自訂建置腳本 (`build.py`)
若模組需要特殊的構建流程（如文檔預處理、代碼編譯或壓縮），可在 `ys_codebase/source/my-new-module/build.py` 撰寫自訂建置邏輯：
```python
import sys, pathlib

src_path = pathlib.Path(sys.argv[1])
dest_path = pathlib.Path(sys.argv[2])

dest_path.mkdir(parents=True, exist_ok=True)
# 執行自訂拷貝或建置處理...
```

若無特殊需求，Installer 將自動採用標準過濾打包器。

---

### 步驟 4：執行模組建置
```bash
python ys_codebase/yscb_cli.py installer build my-new-module
```
建置成功後，`ys_codebase/build/my-new-module/` 將生成純淨發布包與帶有 `built_at` 時間戳的 `manifest.json`。

---

### 步驟 5：執行全套回歸測試
```bash
# 執行全量單元與下游沙盒回歸測試
python test/run_regression.py
```

---

### 步驟 6：提交與推送
```bash
# 提交變更並推送回中央遠端倉庫
git add .
git commit -m "feat(module): add my-new-module"
git push origin main
```
