"""
Space event subscriber hook for module:knowledge-db.
Listens to `on_file_space_changed` emitted by `core.space` and triggers
transactional cursor consumption (`consume_diff(consumer_id="knowledge-db")`)
and incremental hot-patching of the unified semantic index via `IndexingPipeline.sync_incremental_changes`.
"""

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from core.context import get_env
from core.space import ScanDiffResult, consume_diff


def get_engine() -> Any:
    """Resolve `knowledge_db.engine.get_engine` dynamically while allowing test monkeypatching."""
    from knowledge_db.engine import get_engine as _get_engine

    return _get_engine()


def get_active_worker() -> Any:
    """Resolve `knowledge_db.service.get_active_worker` dynamically while allowing test monkeypatching."""
    from knowledge_db.service import get_active_worker as _get_active_worker

    return _get_active_worker()


@contextmanager
def _resolve_consume_diff(
    engine: Any,
    space_name: Optional[str] = None,
    consumer_id: str = "knowledge-db",
    auto_refresh: Optional[bool] = None,
) -> Iterator[ScanDiffResult]:
    """透過 engine.scanner 或全域 core.space.consume_diff 開啟增量變更消費交易"""
    scanner = getattr(engine, "scanner", None)
    if scanner is not None and hasattr(scanner, "consume_diff"):
        if auto_refresh is not None:
            with scanner.consume_diff(
                space_name, consumer_id=consumer_id, auto_refresh=auto_refresh
            ) as diff_res:
                yield diff_res
        else:
            with scanner.consume_diff(
                space_name, consumer_id=consumer_id
            ) as diff_res:
                yield diff_res
    elif scanner is not None and hasattr(scanner, "diff") and hasattr(scanner, "ack"):
        diff_res = scanner.diff(
            space_name,
            consumer_id=consumer_id,
            auto_refresh=False if auto_refresh is False else True,
        )
        yield diff_res
        scanner.ack(
            space_name,
            consumer_id=consumer_id,
            generation=diff_res.to_generation,
            space_generations=getattr(diff_res, "space_generations", None),
        )
    else:
        with consume_diff(
            space_name, consumer_id=consumer_id
        ) as diff_res:
            yield diff_res


def on_file_space_changed(
    context: Any = None,
    spaces: Optional[List[str]] = None,
    diff_summary: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    當 `core.space` 完成二進位指紋快照更新並廣播 `on_file_space_changed` 時觸發。
    統一委派至 `engine.pipeline.sync_incremental_changes` 執行交易式游標消費與增量熱修補。
    """
    explicit_engine_obj: Optional[Any] = None
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

    if explicit_engine_obj is None:
        active_worker = get_active_worker()
        if active_worker is not None and (not hasattr(active_worker, "is_alive") or active_worker.is_alive()):
            active_worker.notify_space_changed()
            return {
                "status": "queued_to_worker",
                "patched_count": 0,
                "worker": getattr(active_worker, "name", "knowledge-db-worker"),
            }
        # Never fall back to synchronous full-pipeline indexing on the server event-broadcast thread
        # when the background worker has not started or is tearing down.
        if get_env("YSCB_IN_SERVER_WORKER") == "1":
            return {
                "status": "noop",
                "patched_count": 0,
            }

    engine = explicit_engine_obj or get_engine()
    auto_refresh = False if diff_summary is not None else None

    @contextmanager
    def _hook_consume(
        space_name: Optional[str] = None,
        consumer_id: str = "knowledge-db",
        auto_refresh: Optional[bool] = None,
    ) -> Iterator[ScanDiffResult]:
        with _resolve_consume_diff(
            engine,
            space_name=space_name,
            consumer_id=consumer_id,
            auto_refresh=auto_refresh,
        ) as diff_res:
            yield diff_res

    return engine.pipeline.sync_incremental_changes(
        space_name=target_space,
        auto_refresh=auto_refresh,
        allow_parallel=False,
        consume_fn=_hook_consume,
    )
