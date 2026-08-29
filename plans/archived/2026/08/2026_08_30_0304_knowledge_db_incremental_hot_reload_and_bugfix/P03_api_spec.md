# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Knowledge-DB Hot Reload 缺陷修復與增量效能優化  
> 建立日期：2026-08-30  
> 所屬主計畫：無 (獨立 Level 1 計畫)  
> 狀態：Confirmed  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ScanDiffDetail` | `knowledge_db/scanner.py` | Public | 定義單次 JIT 嗅探之新增、修改、刪除檔案集合資料結構 |
| `FingerprintScanner.check_invalidation` | `knowledge_db/scanner.py` | Public | 執行全專案空間聯集 JIT 嗅探，返回 100% 完整清冊與差量明細 |
| `SemanticBundler._file_symbols_cache` | `knowledge_db/bundler.py` | Internal | 維護記憶體中單檔符號快取池 `Dict[str, List[UnifiedSymbol]]` |
| `SemanticBundler.bundle_dirty_files` | `knowledge_db/bundler.py` | Public | 僅針對新增與修改之檔案執行 AST 解析，並同步更新記憶體符號快取池 |
| `InvertedIndex.patch_incremental` | `knowledge_db/retrieval.py` | Public | 差量移除舊 Postings、注入新符號 Postings 並動態重算 `field_avgdl` |
| `InvertedIndex.save_binary` | `knowledge_db/retrieval.py` | Public | 支援 `compresslevel: int = 1` 參數快速二進位 Gzip 寫盤 |
| `KnowledgeEngine._hot_patch_unified_index` | `knowledge_db/engine.py` | Internal | 執行增量熱自愈修補管線並快速持久化快照 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. scanner.py
@dataclass
class ScanDiffDetail:
    """JIT 變更嗅探之差量明細"""
    added: Set[str] = field(default_factory=set)       # canonical paths of added files
    modified: Set[str] = field(default_factory=set)    # canonical paths of modified files
    deleted: Set[str] = field(default_factory=set)     # canonical paths of deleted files

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    @property
    def dirty_files(self) -> Set[str]:
        return self.added | self.modified | self.deleted


class FingerprintScanner:
    def check_invalidation(
        self,
        spaces: Optional[List[SpaceConfig]] = None,
        snapshot_path: Optional[Union[str, Path]] = None,
    ) -> Tuple[bool, int, str, Dict[str, Tuple[float, int]], ScanDiffDetail]:
        """
        對全專案空間聯集 (Union Scope) 執行極速 JIT 變更嗅探。
        保證 100% 完整走訪所有目標檔案，絕不提早中斷。

        :return: (is_dirty, scanned_file_count, reason, full_current_files_map, diff_detail)
        """


# 2. bundler.py
class SemanticBundler:
    def __init__(...):
        ...
        self._file_symbols_cache: Dict[str, List[UnifiedSymbol]] = {}

    def clear_symbols_cache(self) -> None:
        """清空記憶體符號快取"""
        self._file_symbols_cache.clear()

    def bundle_dirty_files(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[SpaceConfig]] = None,
    ) -> Tuple[Dict[str, List[UnifiedSymbol]], Set[str]]:
        """
        僅針對 dirty_diff 中 added 與 modified 的檔案執行 AST 解析，
        同步自 _file_symbols_cache 移除 deleted 檔案，
        回傳 (new_symbols_by_file, dirty_canonical_keys)。
        """


# 3. retrieval.py
class InvertedIndex:
    def patch_incremental(
        self,
        dirty_canonical_keys: Set[str],
        new_symbols_by_file: Dict[str, List[UnifiedSymbol]],
        tokenizer: Optional[CodeTokenizer] = None,
    ) -> None:
        """
        差量修補倒排索引：
        1. 找出並移除 dirty_canonical_keys 檔案所產生的所有舊 doc_id 及對應 Posting。
        2. 扣減 field_total_lengths 與 doc_count。
        3. 將 new_symbols_by_file 中的新符號加入 symbols 與 index。
        4. 累加 field_total_lengths 與 doc_count，重新計算 field_avgdl。
        """

    def save_binary(
        self,
        file_path: Union[str, Path],
        compresslevel: int = 1,
    ) -> None:
        """原子寫入二進位 Gzip 檔案，預設 compresslevel=1 快速壓縮。"""


# 4. engine.py
class KnowledgeEngine:
    def _hot_patch_unified_index(
        self,
        diff_detail: ScanDiffDetail,
        full_files_map: Dict[str, Tuple[float, int]],
    ) -> bool:
        """
        執行增量熱修補管線：
        1. 若 _unified_index 為 None，回傳 False 以便退回全量重構。
        2. 調用 bundler.bundle_dirty_files(diff_detail) 解析 dirty 檔案。
        3. 調用 _unified_index.patch_incremental(dirty_keys, new_symbols, self.tokenizer)。
        4. 保存 unified.meta.bin (full_files_map) 與 unified.index.bin.gz (compresslevel=1)。
        5. 回傳 True 代表熱自愈成功。
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
┌────────────────────────────────────────────────────────┐
│ 1. scanner.py: ScanDiffDetail & check_invalidation     │ (底層嗅探無相依)
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ 2. bundler.py: _file_symbols_cache & bundle_dirty_files│ (依賴 scanner 差量結構)
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ 3. retrieval.py: InvertedIndex.patch_incremental       │ (依賴 UnifiedSymbol 符號結構)
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ 4. engine.py: _hot_patch_unified_index & search整合    │ (上層協調整合)
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ 5. tests/test_incremental_hot_reload.py 測試套件實作   │ (全生命週期驗證)
└────────────────────────────────────────────────────────┘
```
