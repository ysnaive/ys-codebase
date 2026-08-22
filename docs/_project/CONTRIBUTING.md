---
target: "Project/Contributing"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb_installer.py"
  - "source/"
  - "build/"
related_docs:
  - "./STANDARDS.md"
  - "../_global/ARCHITECTURE.md"
last_updated: "2026-08-22"
---

# 模組開發與發布貢獻指南 (Contributing Guide)

本指南引導開發者如何在 `ys-codebase` 體系中開發新的功能模組，並將其編譯發布至中央庫。

---

## 🚀 建立新模組的標準流程

### 步驟 1：在 `source/` 建立模組目錄
```bash
# 建立模組資料夾
mkdir -p source/my-new-module
```

### 步驟 2：撰寫 `manifest.json` 與源碼
在 `source/my-new-module/manifest.json` 定義模組元數據：
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
若模組需要特殊的構建流程（如文檔預處理、代碼編譯或壓縮），可在 `source/my-new-module/build.py` 撰寫自訂建置邏輯：
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
python yscb_installer.py build my-new-module
```
建置成功後，`build/my-new-module/` 將生成純淨發布包與帶有 `built_at` 時間戳的 `manifest.json`。

---

### 步驟 5：執行測試與推送
```bash
# 執行全量整合測試
python tests/test_installer.py

# 推送回中央遠端倉庫
python yscb_installer.py push -m "feat(module): add my-new-module"
```
