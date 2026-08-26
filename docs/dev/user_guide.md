# Dev 開發者工具鏈使用指南 (User Guide)

> 本手冊提供 `dev` 模組所有 CLI 指令的詳細參數說明、使用情境與操作範例。

---

## 1. 模組建立與合規檢查

### 1.1 建立新模組 (`dev create`)
在 `source/` 目錄下一鍵生成符合 YS-Codebase 標準規範的模組骨架。
```bash
python yscb.py dev create <module_name> [--desc="<description>"]
```
- **產出檔案**：
  - `source/<module_name>/manifest.json`：模組宣告清單（預設版本 `1.0.0.0`）。
  - `source/<module_name>/scripts/cli.py`：標準 CLI 路由進入點（具備 `main(argv)`）。
  - `source/<module_name>/<module_name>/__init__.py`：核心 Python 套件目錄。
  - `source/<module_name>/.yscbignore`：發布打包過濾規則。
  - `source/<module_name>/tests/test_basic.py`：初始單元測試檔案。

### 1.2 靜態合規檢查 (`dev check`)
檢查模組宣告與進入點是否合規。
```bash
# 檢查單一模組
python yscb.py dev check core

# 掃描檢查 source/ 下所有模組
python yscb.py dev check --all
```

---

## 2. 版本號單向遞增 (`dev bump-*`)

讀取目標模組 `manifest.json` 的版本號，依據語意化版本規範進行單向遞增並寫回：

```bash
# 1. 遞增 Revision（第四段尾號：1.0.0.0 -> 1.0.0.1）
python yscb.py dev bump-revision <module_name>

# 2. 遞增 Patch（第三段：1.0.0.1 -> 1.0.1.0）
python yscb.py dev bump-patch <module_name>

# 3. 遞增 Minor（第二段：1.0.1.0 -> 1.1.0.0）
python yscb.py dev bump-minor <module_name>

# 4. 遞增 Major（第一段：1.1.0.0 -> 2.0.0.0）
python yscb.py dev bump-major <module_name>
```

---

## 3. 本地建置與純淨發布

### 3.1 本地開發打包 (`dev build`)
用於本地調試與沙盒測試之完整開發包：
```bash
# 打包單一模組
python yscb.py dev build <module_name>

# 批次打包所有模組
python yscb.py dev build --all
```
- **特性**：
  - 打包前**一律自動物理清空**目標 `build/<mod>/` 目錄。
  - 100% 完整保留 `tests/` 與開發檔案。
  - 產物版本號標記為 `{major}.{minor}.{patch}.build`。
  - 自動更新 `build/<mod>/index.json`。

### 3.2 發布就緒預檢 (`dev release-check`)
獨立執行 3-Gate 發布守門檢驗，確認模組是否已就緒發布：
```bash
python yscb.py dev release-check <module_name>
```
- **注意**：本指令專注於單一模組發布審查，**明確拒絕 `--all` 參數**。
- **檢查項目**：Gate 1 靜態合規性、Gate 2 版本庫未重複、Gate 3 版本號嚴格大於在庫同三元組最高 revision。

### 3.3 純淨正式發布 (`dev release`)
執行 3-Gate 校驗通過後，產出純淨發布包並實施產物治理：
```bash
# 發布單一模組
python yscb.py dev release <module_name>

# 依模組依賴 DAG 拓撲排序批次發布
python yscb.py dev release --all
```
- **特性**：
  - 嚴格排除 `tests/` 與 `.yscbignore`。
  - 自動執行 **3-Revision 時序滑動窗口保留**與**跨三元組升級舊版收斂淘汰**。
  - 以磁碟真實存在的 zip 檔案為唯一事實來源動態更新 `release/<mod>/index.json`。

### 3.4 安全提交流水線 (`dev release-git`)
一鍵執行標準 4 步發布與版本控制流水線：
```bash
python yscb.py dev release-git <module_name> "<commit message>"
```
- **執行順序**：
  1. `dev test <module_name>`（跑測失敗立即中斷）。
  2. `dev release-check <module_name>`（預檢失敗立即中斷）。
  3. `dev release <module_name>`（純淨打包與產物治理）。
  4. 本地 Git 提交並打標：`git add -A` ➔ `git commit -m "<msg>"` ➔ `git tag -a "<mod>/v<ver>" -m "<msg>"`。
- 🚨 **安全承諾**：本指令**絕不執行 `git push`**，完全由開發者自主決定何時推播至遠端。

---

## 4. 沙盒測試調度 (`dev test`)

### 4.1 端到端沙盒測試
```bash
# 測試指定模組（預設自動前置執行 dev build）
python yscb.py dev test core

# 測試所有模組
python yscb.py dev test --all

# 跳過前置 build，直接測試既有 build 產物
python yscb.py dev test dev --no-build

# 僅執行標準契約測試
python yscb.py dev test --all --contract-only

# 依名稱過濾測試案例
python yscb.py dev test dev -k test_builder

# 測試失敗時保留沙盒目錄以供除錯
python yscb.py dev test core --keep-sandbox
```
