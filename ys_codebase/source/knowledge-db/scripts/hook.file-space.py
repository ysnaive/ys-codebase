"""
Space event subscriber hook for module:knowledge-db.
Listens to `on_file_space_changed` emitted by `module:file-space` and triggers
transactional cursor consumption (`consume_diff(consumer_id="knowledge-db")`)
and incremental hot-patching of the unified semantic index.
"""

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from knowledge_db.engine import KnowledgeEngine, get_engine
from knowledge_db.service import get_active_worker
from file_space import ScanDiffResult, consume_diff


@contextmanager
def _resolve_consume_diff(
    engine: KnowledgeEngine,
    space_name: Optional[str] = None,
    consumer_id: str = "knowledge-db",
    auto_refresh: Optional[bool] = None,
) -> Iterator[ScanDiffResult]:
    """透過 engine.scanner 或全域 file_space.consume_diff 開啟增量變更消費交易"""
    scanner = getattr(engine, "scanner", None)
    if scanner is not None and hasattr(scanner, "consume_diff"):
        if auto_refresh is not None:
            with scanner.consume_diff(
                space_name=space_name, consumer_id=consumer_id, auto_refresh=auto_refresh
            ) as diff_res:
                yield diff_res
        else:
            with scanner.consume_diff(
                space_name=space_name, consumer_id=consumer_id
            ) as diff_res:
                yield diff_res
    elif scanner is not None and hasattr(scanner, "diff") and hasattr(scanner, "ack"):
        diff_res = scanner.diff(
            space_name=space_name,
            consumer_id=consumer_id,
            auto_refresh=False if auto_refresh is False else True,
        )
        yield diff_res
        scanner.ack(
            space_name=space_name,
            consumer_id=consumer_id,
            generation=diff_res.to_generation,
        )
    else:
        with consume_diff(
            space_name=space_name, consumer_id=consumer_id
        ) as diff_res:
            yield diff_res


def on_file_space_changed(
    context: Any = None,
    spaces: Optional[List[str]] = None,
    diff_summary: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    當 `file-space` 模組完成二進位指紋快照更新並廣播 `on_file_space_changed` 時觸發。
    使用 `consume_diff(consumer_id="knowledge-db")` 拉取自上次游標水位以來的增量變更，
    並對全域統一索引執行 4 階段熱修補（若基礎索引尚未建置則觸發全量建置）。
    """
    explicit_engine_obj: Optional[KnowledgeEngine] = None
    target_space: Optional[str] = None

    if isinstance(context, dict):
        explicit_engine_obj = context.get("engine")
        target_space = context.get("space_name")
        if spaces is None and isinstance(context.get("spaces"), list):
            spaces = context.get("spaces")
    elif context is not None:
        explicit_engine_obj = getattr(context, "engine", None)
        target_space = getattr(context, "space_name", None)

    if explicit_engine_obj is None and "engine" in kwargs:
        explicit_engine_obj = kwargs.get("engine")

    if target_space is None and spaces and len(spaces) == 1:
        target_space = spaces[0]

    # 若專屬常駐 KnowledgeDBServiceWorker 在線且未顯式指定獨立測試 engine，透過 O(1) Event 喚醒由後台兩階段處理
    if explicit_engine_obj is None:
        active_worker = get_active_worker()
        if active_worker is not None and (not hasattr(active_worker, "is_alive") or active_worker.is_alive()):
            active_worker.notify_space_changed()
            return {
                "status": "queued_to_worker",
                "patched_count": 0,
                "worker": getattr(active_worker, "name", "knowledge-db-worker"),
            }

    engine = explicit_engine_obj or get_engine()
    indices_dir = engine.pipeline.get_indices_dir()
    bin_file = indices_dir / "unified.index.bin.gz"
    auto_refresh = False if diff_summary is not None else None

    with _resolve_consume_diff(
        engine,
        space_name=target_space,
        consumer_id="knowledge-db",
        auto_refresh=auto_refresh,
    ) as diff_res:
        if not diff_res.has_changes:
            return {
                "status": "noop",
                "patched_count": 0,
                "to_generation": diff_res.to_generation,
            }

        if not bin_file.exists() and engine.pipeline.unified_index is None:
            engine.pipeline.build_unified_index(force=True, allow_parallel=False)
            return {
                "status": "rebuilt",
                "patched_count": len(diff_res.detail.dirty_files),
                "to_generation": diff_res.to_generation,
            }

        patch_res = engine.pipeline.hot_patch_unified_index(diff_res.detail)
        if not patch_res.success:
            engine.pipeline.build_unified_index(force=True, allow_parallel=False)
            return {
                "status": "rebuilt",
                "patched_count": len(diff_res.detail.dirty_files),
                "to_generation": diff_res.to_generation,
            }

        return {
            "status": "patched",
            "patched_count": patch_res.patched_count,
            "vector_degraded": patch_res.vector_degraded,
            "to_generation": diff_res.to_generation,
        }
