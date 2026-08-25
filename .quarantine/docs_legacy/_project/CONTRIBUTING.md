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
  - "./ARCHITECTURE.md"
last_updated: "2026-08-22"
---

# 模組開發與發布貢獻指南 (Contributing Guide)

本指南引導開發者如何在 `ys-codebase` 體系中開發新的功能模組，並進行回歸測試與發布。

---

## 🚀 建立新模組的標準流程

### 步驟 1：在 `ys_codebase/source/` 建立模組目錄
```bash
mkdir -p ys_codebase/source/my-new-module
```

### 步驟 2：撰寫 `manifest.json` 與源碼
在 `ys_codebase/source/my-new-module/manifest.json` 定義模組元數據（必須相依 `core`）：
```json
{
  "name": "my-new-module",
  "version": "1.0.0",
  "description": "新模組說明",
  "dependencies": ["core"]
}
```

編寫模組所需之代碼、文檔或配置範本（`config.project.template.json` / `config.local.template.json`）。

---

### 步驟 3：撰寫腳本並引用 `yscb_core`
在 `ys_codebase/source/my-new-module/scripts/cli.py` 撰寫 CLI 入口：
```python
import argparse
from yscb_core import ProjectContext, ConfigManager, Console

def main():
    parser = argparse.ArgumentParser(description="My New Module CLI")
    # 定義指令...
    args = parser.parse_args()
    Console.info("執行 My New Module...")

if __name__ == "__main__":
    main()
```

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

---

## 🚨 Dogfooding 自引用環境開發紀律

當在 `ys-codebase` 本體倉庫進行開發與維護時，專案呈現「自引用 (Dogfooding)」狀態。請務必嚴格遵循以下四步閉環：

```text
  [Stage 1: 源碼開發] ➔ 編輯 ys_codebase/source/ (唯一源碼來源，嚴禁直接編輯 modules/)
          │
  [Stage 2: 模組打包] ➔ python yscb_cli.py installer build <module>
          │
  [Stage 3: 品質守門] ➔ python test/run_regression.py (23 Tests + E2E 100% Passed)
          │
  [Stage 4: 自引用更新] ➔ python yscb_cli.py installer install <module> --force
                         python yscb_cli.py agents-workflow --ide-antigravity
```

---

### 步驟 6：提交與推送
```bash
git add .
git commit -m "feat(module): add my-new-module"
git push origin main
```

