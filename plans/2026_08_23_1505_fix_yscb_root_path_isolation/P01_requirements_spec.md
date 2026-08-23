# 需求規格書 (Requirements Specification)

> 功能名稱：fix_yscb_root_path_isolation (Module 檔案系統、快取儲存與 yscb:// 統一路徑轉換器完備性架構)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 依據 P00 / 調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md) / [R01_existing_filesystem_survey.md](./R01_existing_filesystem_survey.md) / [R02_semantic_uri_system_architecture.md](./R02_semantic_uri_system_architecture.md)  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 功能需求 (Functional Requirements)

| ID | 功能描述 | 輸入 | 處理 | 輸出 | 對應 P00 語意 |
|:---|:---------|:-----|:-----|:-----|:-------------|
| **FR-01** | **`yscb://` 工具庫安裝基底隔離與動態解耦** | `paths.yscb_root` 配置為子目錄（如 `./yscb`）並執行 `install` / `build` / `remove` / `status` | Installer (`ModuleManager` / `ConfigManager`) 全量改以 `get_yscb_root()` 作為安裝與操作基底；目標目錄不存在時自動 `mkdir -p` | 模組運行產物 (`modules/`)、源碼 (`source/`)、建置物 (`build/`) 與快取 (`.yscb_cache/`) 100% 置於 `yscb://`，`project://` 零污染 | P00 情境 1 |
| **FR-02** | **模組專屬命名空間快取 Core SDK API** | 模組名稱 `module_name: str` | `ProjectContext.get_module_cache_dir(module_name)` 解析為 `yscb://.yscb_cache/modules/<module_name>/` 並自動遞迴建立目錄 | 回傳該模組專屬快取目錄之絕對 `Path` | P00 情境 2 |
| **FR-03** | **泛型 `cache://` 與 `storage://` 語意 URI 動態解析** | 語意 URI 字串（例：`cache://knowledge-db/index.json`、`storage://knowledge-db/meta.db`） | `ProjectURI.resolve()` 提取 Authority 作為模組名稱，分別分流映射至 `yscb://.yscb_cache/modules/<mod>/` 或 `project://.yscb_storage/<mod>/` | 解析為實體絕對 `Path`，支援 `python yscb_cli.py uri resolve` | P00 情境 3 |
| **FR-04** | **統一路徑轉換器唯一入口與 API 接口完備度校驗** | 任意路徑或語意 URI | `ProjectURI.resolve()` 與 `ProjectURI.validate()` 執行路徑斜線正規化、合法性斷言與 `is_relative_to(BasePath)` 邊界防護 | 回傳校驗後絕對路徑；若越界逃逸拋出 `SecurityError` 或回傳 `!undefined` | P00 情境 4 & [ARCH:DR-URI-01~02] |
| **FR-05** | **反向最長前綴精確匹配演算法 (LPM)** | 本機實體檔案路徑 `path: Union[str, Path]` | `ProjectURI.to_uri(path)` 收集所有已啟動 Scheme，依包含性篩選後採最長路徑深度 (LPM) 與 `Domain > Scoped > Spatial` 規則消歧 | 回傳最精確、最短之語意 URI 字串 | P00 情境 4 & R02 |
| **FR-06** | **統一快取生命週期維護工具鏈與卸載安全連動** | CLI 指令 `cache clean` / `cache status` 或 `installer remove <mod>` | 1. `cache clean`：安全遞迴清理指定模組或全域快取<br>2. `cache status`：統計各模組快取檔案數與空間佔用<br>3. `remove`：自動連動清理 `cache://<mod>/` | 終端輸出格式化統計表格與清理結果 | P00 情境 5 |
| **FR-07** | **既有模組快取平滑自動遷移** | 舊版 `agents-workflow` 快取存在於 `.yscb_cache/ide_manifest_*.json` | 於初始化或首次存取時，自動將舊版檔案遷移至 `yscb://.yscb_cache/modules/agents-workflow/` | 無感平滑遷移，保持舊專案 100% 向後相容 | P00 情境 6 |
| **FR-08** | **設定檔語意 URI 自動遞迴解析** | 2×2 設定檔中含有 `project://` 或 `yscb://` 語意 URI 之設定值 | `ConfigManager.load()` 在載入字典時，自動偵測並遞迴調用 `ProjectURI.resolve()` 展開為實體路徑 | 回傳已完全解析為實體絕對路徑之設定字典 | P00 API 心智 & R02 |

---

## 非功能需求 (Non-Functional Requirements)

| ID | 類別 | 約束描述 | 驗證方式 |
|:---|:-----|:---------|:---------|
| **NFR-01** | **零外部相依 (Zero External Dependency)** | 全套路徑轉換器、正規化引擎、快取管理器與 CLI 工具必須 100% 使用 Python 3.8+ 標準庫（`pathlib.Path`, `re`, `os`, `json`, `shutil`），嚴禁引入第三方套件。 | `python test/run_regression.py` 於無外部依賴純淨環境執行驗證 |
| **NFR-02** | **執行效能 (High Performance)** | 語意 URI 解析、邊界校驗與最長前綴匹配具備微秒級 (µs) 執行效率，不得引入可感知之啟動或指令調度延遲。 | 效能基準測試 (PT-01)：10,000 次 URI 解析耗時 $\le$ 150ms |
| **NFR-03** | **跨平台相容性 (Cross-Platform)** | 統一處理 Windows 反斜線 `\` 與 POSIX 正斜線 `/`，支援 Windows 大小寫不敏感特性，並強制 UTF-8 控制台編碼防呆。 | GitHub Actions Windows & Ubuntu 矩陣 CI 雙平台驗證 |
| **NFR-04** | **沙盒安全性 (Sandbox Security)** | 100% 阻斷 `..` 越界逃逸，確保任何解析結果無法超出對應 BasePath。 | 安全邊界測試 (ET-03)：越界路徑必須被安全阻斷 |

---

## Edge Cases

| ID | 場景描述 | 預期行為 | 對應 FR |
|:---|:---------|:---------|:--------|
| **EC-01** | `paths.yscb_root` 指定為不存在的多層深層子目錄（如 `./sub/tools/yscb`） | Installer 自動遞迴 `mkdir -p` 建立目錄結構，安裝流暢完成不拋出 `FileNotFoundError` | FR-01 |
| **EC-02** | 傳入之 URI 包含冗餘多重斜線（如 `docs:///topic//sub///file.md`）或反斜線（`docs:\\topic\\file.md`） | 自動正規化為標準 POSIX 正斜線 `docs://topic/sub/file.md` 並精確解析 | FR-04 |
| **EC-03** | 傳入之 URI 試圖透過 `..` 逃逸出 BasePath（如 `docs://../../Windows/System32`） | `validate()` 判定為不合法，`resolve()` 拋出 `SecurityError` 或回傳 `!undefined`，絕不回傳越界實體路徑 | FR-04 |
| **EC-04** | `cache://` 未提供模組名稱 Authority（如 `cache://` 或 `cache:///index.json`） | `validate()` 判定格式錯誤，提示缺少模組命名空間，安全回退 | FR-03 |
| **EC-05** | 執行 `installer remove <module>` 時，該模組從未產生過快取目錄（目錄不存在） | 快取清理靜默跳過，不中斷卸載事務流水線 | FR-06 |
| **EC-06** | `to_uri(path)` 傳入完全位於專案與工具庫外部之系統絕對路徑（如 `C:/Windows/temp`） | 無法匹配任何 Scheme 時，安全回退回傳標準絕對路徑字串，不崩潰 | FR-05 |
| **EC-07** | `paths.yscb_root` 設為 `"."`（即工具庫與專案根目錄同一層） | 系統平滑降級相容，`yscb://` 與 `project://` 解析為相同根目錄，快取收斂至 `./.yscb_cache/` | FR-01, FR-02 |

---

## 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :---: | :---: | :--- |
| **`dogfooding_pipeline_ext`** | `always` | **✅ 納入 (Included)** | 本專案呈現 Dogfooding 自引用狀態，修改 Core SDK (`source/core/`)、`yscb_installer.py` 與 `yscb_cli.py` 後，必須 100% 執行 Stage 1~4 閉環驗收（源碼修改 ➔ build ➔ regression ➔ install 自引用同步）。 |
| **`ext_template`** | `on_demand` | **❌ 排除 (Excluded)** | 為模組提供之空範本，非專案特化守門腳本。 |

---

## 外部研究摘要

| 主題 | 摘要 | 來源 | 可信度 |
|:---|:---|:---|:---:|
| RFC 3986 URI 規範 | URI 語法之 Scheme, Authority, Path 拆分與正規化準則 | [RFC 3986 Uniform Resource Identifier](https://datatracker.ietf.org/doc/html/rfc3986) | 高 |
| Longest Prefix Match (LPM) | 最長前綴匹配算法於路由表與語意路徑反向匹配之應用 | [IP Route Lookup & LPM](https://en.wikipedia.org/wiki/Longest_prefix_match) | 高 |

---

## Decision Records

### [REQ:DR-01] 統一路徑轉換器唯一入口與完備度校驗
- **議題**：模組在處理路徑時容易自行拼接相對路徑，當 `yscb_root` 或工作目錄變更時頻繁崩潰。
- **結論**：全專案所有模組凡涉及檔案路徑定位與存取，**100% 必須經由 `ProjectURI` / `ProjectContext` 統一轉換器**；轉換器接口內建格式正規化、合法性斷言與 `is_relative_to` 沙盒圍欄防護。
- **理由**：從架構源頭消除散落各處的硬編碼路徑與目錄逃逸漏洞。
- **排除方案**：允許模組自行解析相對路徑（排除原因：容易發生跨平台路徑分隔符號錯誤與路徑混淆）。

### [REQ:DR-02] 泛型模組命名空間快取 (`cache://`) 與生命週期連動
- **議題**：各模組的中繼檔案與快取缺乏標準存放位置，散落於根目錄或模組目錄內。
- **結論**：統一收斂至 `yscb://.yscb_cache/modules/<module_name>/`，以 `cache://<module>/<subpath>` 動態解析，並於模組卸載時自動連動清理。
- **理由**：實現模組間快取徹底隔離，防止命名衝突與 Git 污染，簡化 CI/CD 清理成本。
