# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 熱重載新增與修改檔案靜默 no-op 修復 (Hot Reload Silent No-op Fix)  
> 建立日期：2026-09-06  
> 所屬主計畫：無 (獨立標準計畫)  
> 狀態：Confirmed  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `IndexingPipeline.hot_patch_unified_index` | `knowledge_db/pipeline.py` | Internal Public | 增量熱補丁進入點；補齊 `_unified_index` 磁碟快取懶加載契約 |
| `HotReloadServer._execute_debounced_patch` | `knowledge_db/daemon.py` | Private Worker | 防抖到期熱修補調度器；補齊熱修補失敗時之全量兜底與日誌明細 |
| `HotReloadServer._run_startup_check` | `knowledge_db/daemon.py` | Private Worker | 伺服器啟動離線變更修補；補齊增量修補失敗時之全量兜底 |
| `FingerprintScanner.scan_space` | `knowledge_db/scanner.py` | Public | 廢除 JSON 指紋檔，以 `unified.meta.bin` (`BinarySnapshotManager`) 比對差量並原子持久化 |
| `KnowledgeEngine.status` | `knowledge_db/engine.py` | Public | 自 `unified.meta.bin` 二進位快照反查空間檔案數，保證與 JIT/Daemon 真理來源 100% 一致 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `IndexingPipeline.hot_patch_unified_index`

```python
def hot_patch_unified_index(
    self,
    diff_detail: ScanDiffDetail,
    full_files_map: Dict[str, Tuple[float, int]],
    timeout_seconds: Optional[float] = None,
) -> HotPatchResult:
    """
    執行增量熱自癒修補管線：
    1. 若記憶體 _unified_index 為空且磁碟存在 unified.index.bin.gz，自動呼叫 InvertedIndex.load_binary 還原。
    2. 若依然為空（無磁碟快照或還原異常），回傳 HotPatchResult(False) 供上層兜底。
    3. 正常解析 dirty 檔案，差量更新倒排索引、調用圖譜與向量特徵快照。
    """
```

### 2.2 `HotReloadServer._execute_debounced_patch`

```python
def _execute_debounced_patch(self) -> None:
    """
    防抖到期處理常式：
    1. 比對快照取得 diff_detail (added, modified, deleted)。
    2. 若 has_changes，優先嘗試 pipeline.hot_patch_unified_index。
    3. 剛性兜底：若 hot_patch 未成功修補或拋出例外，強制呼叫 pipeline.build_unified_index(force=True, current_files=full_files_map)。
    4. 輸出結構化變更明細日誌 (N added, N modified, N deleted)。
    """
```

### 2.3 `FingerprintScanner` & `KnowledgeEngine.status` (Physical SSOT)

```python
def scan_space(self, space_config: SpaceConfig, force: bool = False) -> ScanDiffResult:
    """
    對指定空間進行差量掃描：
    1. 載入 storage/indices/unified.meta.bin 作為快照基準。
    2. 比對當前工作目錄之 (mtime, size)。
    3. 計算 added, modified, deleted, unchanged。
    4. 原子持久化更新回 unified.meta.bin，不產生任何 JSON 指紋檔案。
    """

def status(self) -> Dict[str, Any]:
    """
    獲取全系統狀態：
    各空間之 cached_files 直接讀取 unified.meta.bin 並依空間規則匹配計數，達成絕對 SSOT。
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1] InvertedIndex.load_binary 磁碟反序列化
    ▲
    │ 調用懶加載
[Step 2] IndexingPipeline.hot_patch_unified_index 內部自我補齊
    ▲
    │ 調用增量修補
[Step 3] HotReloadServer._execute_debounced_patch 失敗防護與兜底重建
    ▲
    │ 啟動檢查防護
[Step 4] HotReloadServer._run_startup_check 對齊兜底邏輯
    ▲
    │ 物理級 SSOT 收斂
[Step 5] scanner.py & engine.py 廢除 JSON，全面切換為 unified.meta.bin
    ▲
    │ 驗證保證
[Step 6] test_hot_reload_server.py & test_scanner.py 單元驗證
```
