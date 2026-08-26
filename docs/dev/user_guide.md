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

#### 💡 本機開發一鍵直裝 (`install <mod>@build`)
當本地修改了 `source/<module>/` 程式碼並執行 `dev build <module>` 後，若希望在宿主環境直接載入最新開發建置產物進行交互調試，無需走正式 release 流程，可直接執行：
```bash
python yscb.py install <module_name>@build --force
```
- **核心特例機制**：當 revision 為 `build` 或以 `.build` 結尾時，套件管理器自動鎖定直連本地端 `module.build://`，免去先手動跑 release 的冗餘負擔。


### 3.2 發布就緒預檢 (`dev release-check`)
獨立執行 3-Gate 發布守門檢驗，確認模組是否已就緒發布：
```bash
# 標準預檢
python yscb.py dev release-check <module_name>

# 強制覆蓋模式預檢（放行同版本衝突）
python yscb.py dev release-check <module_name> --force
```
- **注意**：本指令專注於單一模組發布審查，**明確拒絕 `--all` 參數**。
- **檢查項目**：Gate 1 靜態合規性、Gate 2 版本庫未重複（`--force` 時放行）、Gate 3 版本號嚴格大於在庫最高 revision（`--force` 時允許同版本原地覆蓋，但歷史舊版本回退仍被阻斷）。

### 3.3 純淨正式發布 (`dev release`)
執行 3-Gate 校驗通過後，產出純淨發布包並實施產物治理：
```bash
# 發布單一模組
python yscb.py dev release <module_name>

# 原地覆蓋同版本發布（剛打包發現註解/文檔小瑕疵時使用，免 bump revision）
python yscb.py dev release <module_name> --force

# 依模組依賴 DAG 拓撲排序批次發布
python yscb.py dev release --all [--force]
```
- **特性**：
  - 嚴格排除 `tests/` 與 `.yscbignore`。
  - 自動執行 **3-Revision 時序滑動窗口保留**與**跨三元組升級舊版收斂淘汰**。
  - `--force` 模式：支援物理覆蓋同名 `.zip` 產物，重新計算 hash 並同步更新 `release/<mod>/index.json`。
  - 以磁碟真實存在的 zip 檔案為唯一事實來源動態更新 `release/<mod>/index.json`。

### 3.4 安全提交流水線 (`dev release-git`)
一鍵執行標準 4 步發布與版本控制流水線：
```bash
# 標準安全發布
python yscb.py dev release-git <module_name> "<commit message>"

# 強制重新覆蓋發布並覆蓋 Git Tag
python yscb.py dev release-git <module_name> "<commit message>" --force
```
- **智慧感應機制**：
  - 若目標版本**尚未發布**：依序執行 `dev test` ➔ `dev release-check` ➔ `dev release` ➔ 本地 Git Commit & Tag。
  - 若目標版本**已發布且無 `--force`**：自動安全略過 release 打包步驟，直接推進執行後續的 Local Git Commit & Tag。
  - 若目標版本**已發布且傳入 `--force`**：重新調用 `dev release --force` 物理覆蓋打包產物，並以 `git tag -f` 覆蓋標籤。
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

---

## 5. Agent 指令防呆情境與調用規範 (Dev Command Abuse Guardrails)

為避免 Agent 在開發過程中濫用指令造成環境污染或效能浪費，`dev` 模組在 `contributes.core.commands` 明確定義 6 大情境防呆規範：

| 指令 | ✅ 推薦/適用情境 | 🚨 絕對禁止/不適用情境 |
| :--- | :--- | :--- |
| `dev test <mod>` | • 正在開發當前模組，需驗證單元邏輯或整體功能<br/>• 微調時優先附加 `--no-build` 或 `-k <pattern>` | • 嚴禁在跑測前手動執行 `dev build`<br/>• 嚴禁在日常開發中頻繁執行 `dev test --all`<br/>• 嚴禁調用內部原子操作 `dev op-test` |
| `dev check <mod>` | • 代碼編寫完成後進行靜態合規與語法預檢 | • 嚴禁未修改代碼即無意義高頻重複執行 |
| `dev build <mod>` | • 手動打包本地測試包供跨環境測試或本地直裝物化 | • 嚴禁在跑測前手動 build (dev test 內部自動前置構建) |
| `dev release <mod>` | • 模組通過全部測試，正式打包發布 (Phase 7 結案前) | • 開發者未明確下達發布指示前絕對禁止執行 |
| `dev bump-*` | • 依架構變更或修復類型單向遞增版本號 | • 未獲開發者明確指示前絕對禁止擅自執行 |
| `dev release-git` | • 發布完成後進行本地 git commit 與 tag (絕不 push) | • 未獲指示前絕對禁止擅自執行 |

