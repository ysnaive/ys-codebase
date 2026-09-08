# 生態系模組 CLI 活躍合約與指令手冊 (Module CLI & Commands Guild)

本手冊定義 YSCB 模組 CLI 命令合約規範、`CmdBags` 參數存取、同構指令樹派發機制與 `dev` 模組工具鏈完整操作指南。

---

## 💻 1. 強型別 `CmdBags` 活躍執行合約

YS-Codebase 生態系已全面廢除舊式 `argparse` 與手工字串剖析，所有 CLI 命令統一採用強型別 `CmdBags` 活躍執行合約。

### 1.1 合約函式簽名
所有模組子指令的入口函式簽名必須嚴格宣告為：

```python
from core.commands import CmdBags

def <command_name>(cmd_bags: CmdBags) -> int:
    """指令執行邏輯。成功回傳 0，失敗回傳非 0 整數。"""
    ...
```

### 1.2 `CmdBags` API 與參數存取範式
`CmdBags` 為不可變結構體，提供強型別存取介面：

```python
def my_command(cmd_bags: CmdBags) -> int:
    # 1. 取得位置參數 (Positional Arguments)
    # 若在 commands 宣告為 args: {"target": {"type": "str", "required": True}}
    target = cmd_bags.args.get("target")

    # 2. 判定布林旗標 (Boolean Flag Options)
    # 例如 --force 或 -f
    is_force = cmd_bags.has_option("force")

    # 3. 取得具值選項 (Key-Value Options)
    # 例如 --tier=minor 或 -t minor
    tier = cmd_bags.get_option("tier")  # 若未提供則為 None 或預設值

    # 4. 存取原生額外參數 (Raw trailing arguments，若有)
    extra_args = cmd_bags.raw_args

    return 0
```

> [!IMPORTANT]
> **嚴禁**在模組內部建立 `argparse.ArgumentParser` 或手寫 `sys.argv` 剖析。參數型別轉換、列舉約束與預設值已由 `core.commands` 核心層在進入合約前完全解算。

---

## ⚖️ 2. CLI 實作與 Contributes 宣告對稱性規範 (Implementation & Declaration Symmetry)

模組在 `scripts/cli.py` 實作的任何 CLI 行為，必須與自身 `contributes/core.json` 保持剛性雙向對稱：

1. **指令實作與節點宣告 1:1 對稱**：
   - 實作的每個活躍合約函式 `def <cmd_name>(cmd_bags: CmdBags) -> int`，必須在 `contributes/core.json` 的 `commands` 中擁有完全對應的指令節點宣告。
   - 反之，在 `commands` 宣告的每個節點，必須在 `scripts/cli.py` 存在具體實作函式。嚴禁「有實作無宣告」或「有宣告無實作」。
2. **參數字典 (`args`) 完整對齊**：
   - 代碼中 `cmd_bags.args.get("<param>")` 取用的所有參數，必須在宣告節點的 `args` 字典內完整定義。
   - 包含其型別 (`type`)、是否必填 (`required`)、列舉約束 (`choice` / `choices`) 與說明 (`description`)。
3. **正交選項 (`options`) 完整對齊**：
   - 代碼中透過 `cmd_bags.has_option("<opt>")` 或 `cmd_bags.get_option("<opt>")` 存取的選項，必須在宣告節點的 `options` 完整宣告。
   - 選項若需接收值，必須透過子 `args` 字典定義（純旗標選項則省略子 `args`）。
   - 選項的別名清單 (`alias`) 與說明必須與代碼解析邏輯 100% 一致。
4. **使用指引 (`usage.pros` / `usage.cons`) 語意客觀性**：
   - 宣告節點必須包含 `usage.pros`（適用/推薦情境）與 `usage.cons`（🚨 絕對禁止/濫用情境），為 `--help` 渲染與 Agent 決策提供剛性界限。
5. **權限分級 (`tier`) 客觀評定**：
   - `safe`（自主安全）：無副作用的純讀取/查詢指令。
   - `conditional`（階段條件）：特定流程或開發階段中調用之指令。
   - `gated`（授權守門）：具備破壞性、修改檔案、安裝/刪除模組、重置快取或發布行為之高風險指令，嚴禁標記為 `safe`。
6. **常駐 IPC 執行相容性 (`server_compatible`)**：
   - 若指令標記為 `server_compatible: true`，函式實作必須具備常駐 Worker 進程安全性（無全域殘留狀態、無跨進程檔案鎖衝突、不依賴啟動初始 CWD）。

---

## 🌲 3. 同構指令樹與平鋪命名規範

### 3.1 平鋪函式命名約定 (Flat Function Convention)
為避免多層類別嵌套帶來的呼叫開銷與複雜度，實作端約定以**底線平鋪命名**函式：

| CLI 呼叫層級 | 對應實作函式名 | 範例模組 |
| :--- | :--- | :--- |
| `python yscb.py <mod> <action>` | `def <action>(cmd_bags: CmdBags) -> int` | `def status(cmd_bags)` |
| `python yscb.py <mod> <subsys> <action>` | `def <subsys>_<action>(cmd_bags: CmdBags) -> int` | `def plan_status(cmd_bags)` |
| `python yscb.py <mod> <subsys> <item> <action>` | `def <subsys>_<item>_<action>(cmd_bags: CmdBags) -> int` | `def release_target_add(cmd_bags)` |

### 3.2 同構指令節點類型
指令樹節點支援三大拓撲型態：
1. **純葉子節點 (Leaf)**：無子命令，直接綁定執行函式。
2. **純分支節點 (Branch)**：僅作為群組容器，未傳入子指令時自動渲染該分支的 `SUBCOMMANDS` 清單。
3. **複合分支節點 (Hybrid)**：既可帶子指令派發，亦可單獨執行自身預設行為（例如 `python yscb.py dev test` 既可直接跑測，亦可作為分支）。

---

## ⚡ 4. 微內核延遲載入規範 (PEP 562 Lazy Loading)

為確保 CLI 冷啟動耗時保持在極速 $<1\text{ms}$，生態系模組必須遵守 PEP 562 延遲載入規範：

1. **淨化頂層 Import**：模組 `__init__.py` 或 `scripts/cli.py` 頂層嚴禁直接 `import` 重量級第三方套件或內部大型子系統。
2. **`__getattr__` 按需載入**：在頂層利用 `__getattr__(name)` 動態載入函式或類別。
3. **函式內區域導入 (Function-scoped Import)**：耗時或重型邏輯下沉至子指令函式內部執行時導入。

---

## 🛠️ 5. Dev 工具鏈 CLI 指令全景矩陣

`dev` 模組提供全生命週期的開發者工具鏈：

### 5.1 模組骨架初始化 (Scaffold Bootstrapping)
開發生態系新模組時，**強制使用**官方腳手架指令建立目錄骨架：

```bash
# 建立全新標準模組骨架
python yscb.py dev create <mod_name> --desc="模組用途描述"
```

#### 自動生成之 8 大標準檔案拓撲
執行 `dev create` 後將在 `source/<mod_name>/` 自動產出完整結構：
```text
source/<mod_name>/
├── manifest.json            # 預設 version: 0.1.0，宣告 core 依賴
├── scripts/
│   └── cli.py               # 內建 process(args)、UTF-8 防護、sys.path 修正
├── <pkg_name>/
│   └── __init__.py          # 內建 __version__ = "0.1.0"
├── tests/
│   ├── __init__.py
│   └── test_basic.py        # 基礎測試範本
├── .yscbignore              # 預設忽略 tests/、*.tmp、*.bak
└── contributes/
    ├── _format.json         # Ingress 擴充點規格範本
    ├── _manifest.md         # Egress 對外契約導覽清冊範本
    └── core.json            # 預設向 Core 註冊之 hello 命令
```

### 5.2 靜態合規檢驗 (`dev check`)
```bash
# 靜態合規與語法預檢 (驗證 manifest、contributes、AST 語法與紅線)
python yscb.py dev check <mod_name>
python yscb.py dev check --all
python yscb.py dev check <mod_name> --json
```

### 5.3 打包與版本管理
```bash
# 開發建置打包 (產出 project://.build/<mod>/<ver>.build.zip，包含 tests/ 與 hook.dev.py)
python yscb.py dev build <mod_name>

# 語意化版本單向遞增 (Major.Minor.Patch.Revision) - 🚨 僅限開發者明確指示時
python yscb.py dev bump-revision <mod_name>  # 日常修復、文檔修訂 (1.0.0.0 -> 1.0.0.1)
python yscb.py dev bump-patch <mod_name>     # 向下相容 Bug 修復 (1.0.0.0 -> 1.0.1.0)
python yscb.py dev bump-minor <mod_name>     # 向下相容新功能 (1.0.0.0 -> 1.1.0.0)
python yscb.py dev bump-major <mod_name>     # 破壞性重大變更 (1.0.0.0 -> 2.0.0.0)
```

### 5.4 隔離沙盒測試 (`dev test`)
```bash
# 執行指定模組沙盒測試 (自動 build -> 建立拋棄式沙盒 -> 跑測 -> 清理)
python yscb.py dev test <mod_name>

# 啟用靜音節流輸出 (全通時單行靜默，節省 95% Token I/O)
python yscb.py dev test <mod_name> -q

# 略過前置 build 快速跑測 (微調代碼時加速驗證)
python yscb.py dev test <mod_name> --no-build

# 局部聚焦跑測 (傳入 unittest pattern 或精確目標)
python yscb.py dev test <mod_name> -k test_ft_01
python yscb.py dev test <mod_name> --target=TestMyMod.test_ft_01
```

### 5.5 發布流水線 (🔴 授權守門)
```bash
# 1. 發布前 3-Gate 校驗 (靜態合規、測試通過標記、依賴拓撲；不進行打包)
python yscb.py dev release-check <mod_name>
python yscb.py dev release-check <mod_name> --force  # 覆寫模式 (僅限特殊授權)

# 2. 純淨發布打包 (排除 tests/ 與 .yscbignore，產出發布包至 project://release/)
python yscb.py dev release <mod_name>
python yscb.py dev release --all                     # 依拓撲順序批量發布

# 3. 本地 Git 一鍵安全發布 (自動依序 test -> release-check -> release -> 本機 git commit 與 tag)
python yscb.py dev release-git <mod_name> "feat: 完成特定功能"
```
> [!CAUTION]
> **發布防呆鐵律**：`release-git` 僅於本機 Git Repo 建立 Commit 與 Tag，**嚴禁遠端 push**；版本晉升與發布行為必須獲得開發者明確授權。

---

## 🔄 6. 伺服器常駐守護進程協同與自動自癒

本節深化 [SKILL.md 軌道 A](../SKILL.md#軌道-a本地開發調試-dogfooding-track) 中提及的 Server 自癒機制。若開發的模組包含常駐背景服務（如 Service Worker 或生命週期 Watcher）：

1. **`server_compatible` 旗標**：在命令宣告中標記 `server_compatible: true`，支援透過 IPC HTTP 高速熱派發至常駐 Worker。
2. **Server 背景自動熱重載機制 (`ModulesWatcher`)**：
   - 當透過 `install <mod>@build` 或正式安裝物化更新 `project://.modules/` 時，Server 後台的 `ModulesWatcher` 會在 500ms 內自動感知受影響模組並精確分流：
     - 若變更為領域模組（如 `knowledge-db`）：自動觸發 Worker 子進程平滑重啟，代碼記憶體即時刷新。
     - 若變更為核心/守護模組（如 `server`, `core`）：自動觸發 Master 優雅自重啟整棵進程樹。
   - **因此在日常模組物化後，完全無需手動執行 reload**。
3. **診斷與輔助指令**：
   ```bash
   # 檢視進程樹 PID、動態 Port 與各模組 Background Services 運行狀態
   python yscb.py server status

   # (可選/輔助) 手動強制重啟 Worker 子進程或刷新
   python yscb.py server reload
   ```
