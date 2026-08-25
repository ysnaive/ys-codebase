# 專題調研報告 (Research Report)

> 主題名稱：套件框架宏觀架構與程式邏輯地毯式建檢評估報告 (Framework Architecture & Logic Robustness Audit)  
> 報告編號：R01  
> 建立日期：2026-08-25  
> 報告狀態：Confirmed (Phase 0 調研全數收斂)  
> 所屬計畫：[sub_11_framework_robustness_and_bugfix](./P00_semantic_requirements.md)  
> 依據版本：`core@1.0.0`, `dev@1.0.0`, `yscb.py`  

---

## 1. 成果總綱與結論 (Executive Summary)

針對 YS-Codebase 重構後的整體套件框架（涵蓋 `yscb.py`、`module:core`、`module:dev`、語意 URI 系統、原子操作引擎與沙盒測試框架），從**軟體工程、抽象設計、擴充能力、魯棒性**等面向進行全量靜態與動態程式碼建檢：

- **整體評級**：框架骨幹設計優秀，微內核分離明確，主流程 48 項測試 100% 綠燈，已具備投入後續開發之基礎。
- **改進焦點**：清除實作落地時滋生的「軟相容手段與跨空間穿透」、落實真實 SemVer 2.0.0 版本運算器，以及補齊微內核物理拓撲之設計邏輯註解。

```
┌─────────────────────────────────────────────────────────────────┐
│ 套件框架健全度評估總覽                                           │
├──────────────────────────────────────┬──────────────────────────┤
│ 架構骨架穩健性                       │ 🟢 優秀 (高內聚低耦合)   │
│ 核心邏輯正確性 (Happy Path)          │ 🟢 正常運作 (48/48 通過) │
│ 邊緣情境魯棒性 (Edge Case)           │ 🟡 需收斂 6 大軟相容手段 │
│ 多版本 / 真實 SemVer 語法支援        │ 🔴 尚未實作 (字串比對)   │
│ 並發 / 多實例安全性                  │ 🟡 基礎保護 (有 TOCTOU)  │
│ 沙盒隔離嚴謹度                       │ 🟢 物理進程隔離保證      │
│ 第三方協議擴充能力                   │ 🟢 驗證運作正常 (100% 閉環)│
└──────────────────────────────────────┴──────────────────────────┘
```

---

## 2. 維度一：架構層面 (Architecture & Data Flow)

### 2.1 架構設計亮點
1. **超薄宿主 + 微內核分離**：`yscb.py` 嚴格維持百餘行，100% Python 標準庫零外部依賴，僅負責路徑探測與純粹命令派發。
2. **語意 URI 協議體系**：提供 14 組自宣告協議，將實體路徑完全抽象化，杜絕模組程式碼硬編碼脆弱相對路徑。
3. **類事務安全保證**：`act_snapshot` ➔ `act_lock` ➔ `act_prepare` ➔ `act_reload` ➔ 失敗時 `act_restore_snapshot`，提供高可靠性套件管理。
4. **高信度沙盒映射**：`mock_downstream_project / host_env / mock_provider` 完整模擬下游真實環境。

---

### 2.2 架構缺陷、原始碼片段與深度分析

#### 【Issue A1】`_find_host_config()` 的命名語意歧義與註解缺失 (Severity: LOW / REFACTOR)

- **檔案位置**：`ys_codebase/source/core/core/uri.py` (Line 74-106)
- **問題分析**：
  原函數命名 `_find_host_config` 帶有「動態向上盲目推導/猜測」的語意模糊，且未顯式闡述常量自定位的微內核物理拓撲保證。
- **具體處置方案**：
  1. **補齊設計邏輯註解**：在 `_get_yscb_root` 與組態獲取處完整闡明物理拓撲保證與零 I/O Fast-Path 意圖。
  2. **剛性重構函數命名**：將 `_find_host_config()` 全域重構為 **`_get_host_config()`**，杜絕「推導」歧義，與物理拓撲概念剛性對齊。

---

#### 【Issue A2】SemVer 為假版本解算與字串排序 Bug (Severity: MEDIUM)

- **檔案位置**：`ys_codebase/source/core/core/engine.py` (Line 254-290) 與 `core/core/installer.py` (Line 79)
- **問題原始碼片段**：
```python
# engine.py: act_solve_deps
def act_solve_deps(
    self, 
    target_module: str, 
    version_constraint: Optional[str], 
    provider_url: str
) -> List[Tuple[str, str]]:
    target_ver = version_constraint or "1.0.0"  # <-- 完全未解析版本範圍語法！
    ...
```
```python
# installer.py: cmd_update
if "versions" in res and isinstance(res["versions"], list) and res["versions"]:
    latest_ver = sorted(res["versions"])[-1]  # <-- 預設純字串排序！
```
- **深度分析**：
  1. `act_solve_deps` 接受 `version_constraint` 但完全不解析 `>=`, `~=`, `^`, `*` 等常見語法，只作字串傳遞。**SemVer 版本約束實際上是空操作**。
  2. `cmd_update` 中的版本比較使用字串排序（`sorted(versions)[-1]`），`"1.10.0" < "1.9.0"` 在純字串序下會判定 `1.9.0` 比 `1.10.0` 還新——這是**已知的 SemVer 經典字串排序 Bug**。
- **改進方向**：在 `core` 內建輕量級的 SemVer 2.0.0 三元組（`major, minor, patch, prerelease`）比對器與範圍過濾函式。

---

#### 【Issue A3】檔案鎖 TOCTOU 競態與快照粒度 (Severity: LOW)

- **檔案位置**：`ys_codebase/source/core/core/engine.py` (Line 88-127, Line 374-393)
- **問題原始碼片段**：
```python
# engine.py: act_lock
if os.path.exists(lock_path):
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            lock_info = json.load(f)
        lock_time = lock_info.get("timestamp", 0)
        if now - lock_time > timeout:
            os.remove(lock_path)  # <-- TOCTOU: 檢查與刪除存在競態窗口
    except Exception: ...

try:
    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    ...
```
```python
# engine.py: act_snapshot
def act_snapshot(self, tag: Optional[str] = None) -> str:
    host_dir, _ = uri._find_host_config()
    host_cfg = os.path.join(host_dir, "yscb.config.json")
    snapshot_id = tag or f"snap_{int(time.time())}"
    snap_dir = f"snapshot://{snapshot_id}"
    uri.makedirs(snap_dir)
    if os.path.isfile(host_cfg):
        uri.copy(host_cfg, f"{snap_dir}/yscb.config.json")  # <-- 僅備份設定檔，不備份模組實體
    return snapshot_id
```
- **深度分析**：
  1. **TOCTOU 鎖競態**：在「判斷 lock 過期 ➔ 刪除 ➔ 重建」的窗口中，存在 TOCTOU（Time-of-Check-Time-of-Use）競態條件。但 `os.O_CREAT | os.O_EXCL` 由 OS 核心層提供剛性互斥原子性保證；10s 過期清除僅是異常崩潰後的自我修復 (Self-Healing) 容災機制。在 YSCB 的單 CLI 同步調度模型下，此設計**正確且充分，不需修改邏輯**。
  2. **快照粒度不足**：快照僅儲存 `yscb.config.json`，不備份 `modules/` 目錄（由 `mirror/` 不可變版本庫保證）。然而 `config.root://`（模組專屬設定）未被快照納入，若安裝過程修改了模組設定後失敗回滾，設定目錄將殘留於不一致狀態。
- **改進方向**：
  1. **TOCTOU 鎖結論**：維持既有設計，補齊設計意圖註解——闡明 `os.O_EXCL` 原子保護 + 10s 容災自修復的設計邊界與正確性保證。
  2. **快照範圍擴充**：`act_snapshot` 在備份 `yscb.config.json` 的同時，將 `config.root://`（各模組的 `config.project.json` 與 `config.local.json`）一併備份至 `snapshot://{snap_id}/config/`。
  3. **還原雙層閉環**：`act_restore_snapshot` 還原 `yscb.config.json` 時，同步完整還原 `config/` 目錄，達成 100% 純淨的組態級回滾。
  4. **補齊設計註解**：在 `engine.py` 註解闡明「Mirror 不可變源碼 + Snapshot 雙層組態備份 + OS 原子鎖保護」之原子還原模型。

---

#### 【Issue A4】全域可變狀態的並發/測試污染 (Severity: LOW)

- **檔案位置**：`ys_codebase/source/core/core/uri.py` (Line 16-17, Line 44-63)
- **問題原始碼片段**：
```python
_active_module_context: Optional[str] = None
_active_host_dir: Optional[str] = None
```
- **改進方向**：
  1. 在 `core.uri` 提供 `@contextmanager` 封裝（如 `module_scope(mod)` 與 `host_scope(path)`），在區塊退出時 `finally` 自動還原舊全域狀態，防止測試與 Hook 調用殘留。
  2. 補齊註解說明單進程同步調度模型下全域狀態的設計邊界與作用域。

---

#### 【Issue A5】偏離 R01~R05 剛性設計哲學：多處軟相容手段、跨空間穿透與多重猜測 (Severity: HIGH)

- **問題背景與設計哲學衝突**：
  在前期 R01~R05 宏觀架構調研中，YS-Codebase 確立了 **「剛性拓撲、零臆測 (Rigid Topology & Zero Speculation)」** 的核心原則——除 `install`（套件來源抽象）與 `contributes`（5 大聲明來源矩陣）外，其餘所有子系統皆為 1:1 剛性確定性映射。然而在落地實作中，為了規避邊界報錯，程式碼中產生了 6 大違反空間隔離與零臆測的「軟相容手段」：

- **6 大退化點清冊與問題代碼**：
  1. **`yscb.py:load_config` (Line 28-42)**：
     ```python
     while True: # 🚨 向上無限制爬樹至磁碟根目錄，沙盒環境下會越界偷取外層宿主組態造成沙盒穿透污染！
         cfg_path = os.path.join(curr, CONFIG_FILENAME)
         ...
     ```
     - **剛性對策**：`yscb.py` 必然與 `yscb.config.json` 位於同一目錄，僅錨定同層目錄，徹底移除向上爬樹。
  2. **`contributes.py:scan_and_inject` (Line 23, 37, 51)**：
     ```python
     if not installed_modules and uri.exists("module.source.root://"): # 🚨 運行空間 modules/ 為空時，私自跑去 source/ 抓未編譯源碼！
         installed_modules = uri.listdir("module.source.root://")
     if not uri.exists(manifest_uri) and uri.exists(f"module.source.root://{donor}/manifest.json"): # 🚨 跨界抓 manifest
     ```
     - **剛性對策**：`ContributesAggregator` 為運行期注入引擎，**100% 僅讀取已安裝於 `modules/` 的正式產物**，全面移除對 `module.source.root://` 的所有穿透 fallback。
  3. **`contributes.py:scan_and_inject` (Line 63-64)**：
     ```python
     if not uri.exists(proj_cfg_uri) and uri.exists("project://config.project.json"): # 🚨 模組配置穿透至專案根目錄
         proj_cfg_uri = "project://config.project.json"
     ```
     - **剛性對策**：`config.root://{target}/config.project.json` 與 `project://` 是完全不同的空間概念，嚴格僅讀取 `config.root://` 模組專屬設定檔。
  4. **`uri.py:resolve` (Line 231-236)**：
     ```python
     try:
         host_dir, _ = _get_host_config()
         proj_d = _get_project_dir(host_dir, yscb_dir)
         return os.path.normpath(os.path.join(proj_d or host_dir, uri))
     except Exception:
         return os.path.normpath(os.path.join(yscb_dir, uri)) # 🚨 無協議字串雙重猜測
     ```
     - **剛性對策**：`resolve()` 僅接受語意 URI (`xxx://...`) 或作業系統絕對路徑，非標準字串直接拋出 `ValueError`。
  5. **`installer.py:cmd_install / cmd_update` (Line 21, 47)**：
     ```python
     default_provider = cfg.get("default_provider") or cfg.get("installed_modules", {}).get("core", {}).get("provider") or "./ys_codebase/build" # 🚨 3 層 fallback + 硬編碼
     ```
     - **剛性對策**：`yscb.config.json` 缺少 `default_provider` 時顯式報錯阻斷，移除後門硬編碼 `"./ys_codebase/build"`。
  6. **`sandbox.py:create_sandbox` (Line 131-140)**：
     ```python
     if not curr_yscb or not os.path.isfile(curr_yscb):
         fallback_yscb = os.path.abspath("yscb.py") # 🚨 宿主 yscb.py 多重猜測
     ```
     - **剛性對策**：剛性定位 `host_d/yscb.py`，不存在則拋出明確錯誤。

- **綜合處置方針**：
  全面進行「剛性架構回歸與軟相容清除 (Rigid Topology Restoration)」，將上述 6 處軟相容手段全數剔除，徹底回歸 R01~R05 剛性拓撲與零臆測鐵律。

---

## 3. 維度二：程式邏輯層面 (Programmatic Logic & Module Interaction)

### 3.1 邏輯設計亮點
1. **`_deep_infill_dict` 的遞迴補填設計**：只補缺漏鍵、保留使用者值，是增量設定升級的正確實作。
2. **Hook 廣播的 try-except 隔離**：單一 Hook 崩潰不影響主流程，零擴散設計完善。
3. **`filter_suite` 純函式遞迴**：無副作用、可組合，是測試過濾的正確抽象層次。
4. **Builder 的 `os.walk` 深度忽略**：`dirs[:] = [...]` 原地過濾確保 `os.walk` 不會深入已忽略的目錄，效能上優於先走完再過濾。

---

### 3.2 程式邏輯缺陷、原始碼片段與深度分析

#### 【Issue L1】`context.py` 與 `uri.py` 中的 `ExecutionContext` 重複且定義不一致 (Severity: LOW)

- **檔案位置**：`ys_codebase/source/core/core/context.py` vs `core/core/uri.py`
- **問題原始碼片段**：
```python
# core/core/context.py (Line 7-11)
@dataclass
class ExecutionContext:
    module_name: str
    command: str
    args: List[str] = field(default_factory=list)

# core/core/uri.py (Line 36-42)
@dataclass(frozen=True)
class ExecutionContext:
    """執行期語意上下文介面 (Execution Context Interface)"""
    module_name: str
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```
- **深度分析**：
  `context.py` 的版本缺少 `metadata`，`command` 非 Optional，且不是 `frozen`。`engine.py` 和所有 Hook 只使用 `uri.py` 中的版本。`context.py` 是一個未被使用的殭屍檔案，存在會讓開發者誤用產生型態不相容。
- **改進方向 (採方案 B)**：
  1. 將最新完整版 `@dataclass(frozen=True)` 的 `ExecutionContext` 統一定義在 `core/core/context.py` 作為單一真相來源 (SSOT)。
  2. `core/core/uri.py` 透過 `from core.context import ExecutionContext` 引用並重新導出，保證既有呼叫端 100% 向後相容。

---

#### 【Issue L2】`act_download()` 本地 Provider 拷貝多版本目錄 (Severity: MEDIUM)

- **檔案位置**：`ys_codebase/source/core/core/engine.py` (Line 134-145)
- **問題原始碼片段**：
```python
# 1. Check if local provider directory
local_src = os.path.join(provider_url, module_name, version)
if not os.path.isdir(local_src):
    local_src = os.path.join(provider_url, module_name)
if not os.path.isdir(local_src):
    local_src = os.path.join(provider_url, "build", module_name, version)
if not os.path.isdir(local_src):
    local_src = os.path.join(provider_url, "build", module_name)
if os.path.isdir(local_src):
    uri.copy(local_src, dest_mirror_uri)  # <-- 若命中模組根目錄，會把內部所有版本子資料夾整包拷貝！
    return dest_mirror_uri
```
- **深度分析**：
  當命中第四個分支（`provider_url/build/module_name`）時，由於該路徑沒有版本子目錄，`uri.copy` 會將整個模組資料夾（內含 `1.0.0/`、`2.0.0/` 等所有版本）拷貝進 `mirror://<mod>/<version>/`，造成鏡像內部出現巢狀版本目錄污染。
- **改進方向**：嚴格限定複製目標為特定版本目錄 `provider/<mod>/<ver>`，若無版本目錄則需 Double-Check 內部 `manifest.json` 的版本。

---

#### 【Issue L3】沙盒模組繼承版本硬編碼 `1.0.0` (Severity: LOW)

- **檔案位置**：`ys_codebase/source/dev/dev/testing/sandbox.py` (Line 119-125)
- **問題原始碼片段**：
```python
host_config["installed_modules"][mod_name] = {
    "version": "1.0.0",  # <-- 硬編碼！
    "installed_at": "host_inherited",
    "provider": prov_uri,
    "description": f"Standard host module {mod_name}"
}
```
- **深度分析**：
  沙盒繼承父層模組時，未讀取該模組真實 `manifest.json` 中的 `version` 欄位，一律寫入 `"1.0.0"`。若未來模組升版至 `1.1.0`，沙盒的 `yscb.config.json` 仍記錄 `1.0.0`，可能觸發版本不一致相關的防護機制。
- **改進方向**：
  在沙盒拷貝模組時，動態讀取 `mod_src_path/manifest.json` 中的真實 `version` 與 `description` 填入沙盒的 `yscb.config.json`，保證 100% 真實一致。

---

#### 【Issue L4】測試報告成功/失敗數統計算法微疵 (Severity: LOW)

- **檔案位置**：`ys_codebase/source/dev/dev/testing/runner.py` (Line 146-148)
- **問題原始碼片段**：
```python
mod_info = {
    "name": mod_name,
    "passed": mod_failed == 0,
    "contract_total": contract_total,
    "contract_passed": contract_total if mod_failed == 0 else max(0, contract_total - mod_failed),
    "custom_total": custom_total,
    "custom_passed": custom_total if mod_failed == 0 else max(0, custom_total - mod_failed),
    "errors": err_msgs
}
```
- **深度分析**：
  此估算假設「失敗全扣在 contract 上，然後再扣 custom 上」，但實際上 `mod_failed` 可能全都來自 custom tests，此時顯示的 `contract_passed` 仍正確但 `custom_passed` 算法不準確（從 `custom_total` 直接減去 `mod_failed`，忽略了可能有些 contract 也失敗的情形）。
- **改進方向**：
  1. **精準分類歸屬**：依據失敗案例所屬的 TestCase 類別（Contract / Custom）精確統計各自分類的通過數與失敗數，杜絕交叉誤扣。
  2. **獨立失敗清單**：若有失敗或錯誤案例，在診斷報告中以獨立清單區塊清楚列出「模組名、測試函數名、失敗類型與錯誤摘要」，提升 CLI 終端除錯效率。

---

## 4. 修復優先級矩陣與後續推進建議

| 優先級 | 編號 | 問題簡述 | 影響範疇 | 建議對策 |
| :---: | :---: | :--- | :--- | :--- |
| 🔴 **P0** | **A5** | 偏離剛性設計哲學：6 大軟相容手段與跨空間穿透 | 全域空間與拓撲 | 全面清除軟相容 fallback，回歸 100% 剛性拓撲與零臆測 |
| 🟠 **P1** | **A2** | SemVer 字串排序與版本比對缺陷 | 套件升級與依賴求解 | 引入標準 SemVer 三元組比對演算法 |
| 🟡 **P2** | **A1** | `_find_host_config` 命名語意歧義與註解缺失 | 全域 URI 解析 | 補齊物理拓撲註解，並重命名為 `_get_host_config` |
| 🟡 **P2** | **L1** | `context.py` 殭屍類別清理與統一 | 程式碼清潔度 | 採方案 B：`context.py` 作為 SSOT，由 `uri.py` re-export |
| 🟡 **P2** | **L2** | `act_download` 本地 Provider 多版本拷貝 | 套件鏡像純淨度 | 嚴格比對版本目錄與 manifest 版本 |
| 🟡 **P2** | **A3** | 檔案鎖 TOCTOU 競態與快照粒度 | 進程並發安全 | 快照範圍擴充納入 `config/` 目錄，達成雙層組態還原閉環 |
| 🟡 **P2** | **A4** | 全域可變狀態的並發/測試污染 | 線程安全/模組隔離 | 實作 `module_scope` / `host_scope` 上下文管理器自動還原 |
| 🟢 **P3** | **L3** | 沙盒繼承版本動態讀取 | 測試環境真實度 | 讀取 `manifest.json` 版本取代硬編碼 |
| 🟢 **P3** | **L4** | 測試報表分類計數精確化與失敗清單 | CLI 視覺診斷 | 精準分離分類計數，並以獨立清單區塊列出失敗測試案例 |
