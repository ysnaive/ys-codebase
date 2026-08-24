# 詳細 API 規範書 (API Specification)

> 功能名稱：核心模組雜項功能完善與 Core/Dev 標準測試套件建立 (Core Misc Polish & Core/Dev Standard Tests)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01 / P02：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：In Progress  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 核心介面與 API 簽名 (Core Interfaces & Signatures)

### 1.1 `core.engine.AtomicEngine` API 增強

```python
class AtomicEngine:
    def act_download(self, module_name: str, version: str, provider_url: str) -> str:
        """
        [增強] 下載指定模組版本至 mirror://<module_name>/<version>/。
        支援本地目錄結構與遠端 HTTP/Git URL (依據 index.json 之 files 清冊進行批次抓取)。
        :param module_name: 目標模組識別碼
        :param version: 語意化版本號
        :param provider_url: 本地目錄路徑或遠端 Provider 基礎 URL
        :return: 鏡像 URI (例 "mirror://dev/1.0.0/")
        :raises FileNotFoundError: 當 Provider 找不到套件或檔案清冊時拋出
        :raises RuntimeError: 當遠端下載中斷或網路失敗時拋出
        """

    def act_lock(self, operation: str, timeout: float = 10.0) -> None:
        """
        [新增] 獲取跨進程排他檔案鎖 (temp://.yscb.lock)。
        採用原子模式建立鎖檔案；若已存在且超過 timeout (秒) 則判定為崩潰殘留並強制自癒覆蓋。
        :param operation: 操作名稱識別碼 (例 "install", "update", "reload")
        :param timeout: 死鎖逾時自癒門檻 (預設 10.0 秒)
        :raises BlockingIOError: 當有活躍進程正在佔用鎖時拋出
        """

    def act_unlock(self, operation: str) -> None:
        """
        [新增] 釋放跨進程排他檔案鎖 (temp://.yscb.lock)。
        :param operation: 操作名稱識別碼
        """
```

### 1.2 `core.installer.Installer` API 增強

```python
class Installer:
    def cmd_update(self, module_name: Optional[str] = None, provider: Optional[str] = None) -> int:
        """
        [增強] 批次或針對單一模組執行 SemVer 動態版本探測與升級。
        向 Provider 查詢最新可用版本，比對本地已安裝版本並自動執行下載與 reload。
        :param module_name: 指定模組名（若為 None 則更新所有已安裝模組）
        :param provider: 指定 Provider URL（若為 None 則依 config 階層解析）
        :return: 0 表示成功或已是最新，1 表示錯誤
        """
```

### 1.3 `core.contributes.ContributesAggregator` 5 大來源多層合併

```python
class ContributesAggregator:
    def scan_and_inject(self, clean: bool = True) -> Dict[str, Any]:
        """
        [增強] 掃描 5 大來源之 contributes 宣告並執行深度字典合併：
        1. Default 預設內建
        2. module://manifest.json
        3. module://contributes.{module}.json
        4. config://config.project.json (專案層級優先級最高)
        5. config://config.local.json (本地層級)
        :param clean: 是否先清空既有註冊表
        :return: 聚合後之完整 contributes 字典
        """
```

### 1.4 宿主單檔 `yscb.py self-update`

```python
def cmd_self_update(provider_url: str) -> int:
    """
    [增強] 宿主單檔原子自我更新。
    自 Provider 下載最新 yscb.py 至 yscb.py.tmp，
    透過 py_compile.compile 驗證語法完整後，執行 os.replace 原子覆蓋。
    :param provider_url: Provider 來源 URL 或目錄
    :return: 0 成功，1 失敗
    """
```

---

## 2. 規範產物與模板 Schema (Specification Artifacts)

### 2.1 [`source/core/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core) 規範說明書
定義 `path_placeholders`、`uri_schemes`、`events` 之宣告格式與資料型別。

### 2.2 `source/core/config.project.json` 專案組態範本
定義 `paths`、`modules`、`contributes` 之標準專案組態結構。

---

## 3. 持久化標準測試套件類別定義 (Standard Test Suites Classes)

### 3.1 `source/core/tests/`
- **`TestCoreURI`**（繼承 `YSCBTestCase`）：測試 15 大 URI 協議、15 大 VFS I/O 方法、佔位符代換與異常。
- **`TestCoreEngine`**（繼承 `YSCBTestCase`）：測試 12 大原子操作、快照回滾、跨進程鎖與遠端批次下載。
- **`TestCoreInstaller`**（繼承 `YSCBTestCase`）：測試 7 大套件管理指令、反向相依阻斷與動態版本升級。
- **`TestCoreContributes`**（繼承 `YSCBTestCase`）：測試 5 大來源聚合、動態 handler 呼叫與 URI 協議注入。

### 3.2 `source/dev/tests/`
- **`TestDevScaffold`**（繼承 `YSCBTestCase`）：測試模組目錄腳手架建立、範本檔案生成與命名防呆。
- **`TestDevChecker`**（繼承 `YSCBTestCase`）：測試合規模組驗證、manifest 缺少必填項攔截與 cli.py AST 語法檢驗。
- **`TestDevBuilder`**（繼承 `YSCBTestCase`）：測試版本化建置、**Layer 1 `tests/` 與 `.yscbignore` 全域排除斷言**與自訂規則。
- **`TestDevTester`**（繼承 `YSCBTestCase`）：測試兩階段探索、`make_contract_suite` 動態合成、`@require` 條件跳過與 CLI 參數解析。

---

## 4. 決策紀錄 (Decision Records)

- **[sub_06:DR-01] 遠端下載協議對齊**：支援 Provider `index.json` 之 `files: [...]` 陣列進行清冊批次抓取。
- **[sub_06:DR-02] 跨進程檔案鎖設計**：於 `temp://.yscb.lock` 採用 `os.open` 搭配 `O_CREAT | O_EXCL` 實作原子建立，並記錄 PID 與時間戳記支援 10s 逾時清理。
- **[sub_06:DR-03] 標準測試套件持久化規範**：測試檔案存放於 `source/<mod>/tests/test_*.py`，統一繼承 `dev.testing.YSCBTestCase`。
- **[sub_06:DR-04] contributes.format.md 與 config.project.json 模板交付**：於 `source/core/contributes.format.md` 與 `source/core/config.project.json` 提供正式規範檔案。
