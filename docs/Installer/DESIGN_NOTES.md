---
target: "Core/Installer/DesignNotes"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb_installer.py"
related_docs:
  - "./README.md"
last_updated: "2026-08-22"
---

# Installer 工程妥協與設計筆記 (Design Notes)

記錄 `yscb_installer.py` 在開發與演進過程中的非直觀設計考量、跨平台邊界條件與妥協記錄。

---

## 📌 設計考量與坑點記錄

### 1. Windows 控制台 UTF-8 編碼保護
> [!CAUTION]
> Windows 預設的 PowerShell / CMD 控制台常使用 `cp950` 或 `cp437`，在輸出繁體中文、表格邊框或特殊符號時容易引發 `UnicodeEncodeError` 導致終端崩潰。

- **解決方案**：
  在腳本最頂部強制透過 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 重新配置編碼，即使在極端編碼環境下亦自動以替代字元安全輸出，絕不崩潰。

---

### 2. 堅持 Zero External Dependency (純標準庫)
> [!NOTE]
> 雖然使用 `click` 或 `rich` 可以輕易做出華麗的終端 UI，使用 `gitpython` 能簡化 Git 調度，但這會強迫使用者在乾淨環境下執行 `pip install`，破壞了「5秒即插即用」的核心定位。

- **妥協與實踐**：
  全部使用標準庫 `argparse` 與 `subprocess` 封裝，手刻格式化表格與說明手冊，換取 100% 免安裝環境依賴的極致相容性。

---

### 3. Windows 長路徑與 Git 權限 (Long Paths)
> [!WARNING]
> Windows 預設的 260 字元路徑限制可能導致深層目錄 checkout 失敗。

- **最佳實踐建議**：
  在 Git 交互時建議確保 `core.longpaths=true`，並於 `yscb_installer.py` 處理遞迴目錄清理時使用 `ignore_errors=True` 避免被 Windows 檔案鎖死阻斷。
