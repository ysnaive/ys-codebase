"""
Space Event Subscriber Hook for `module:ast` (`scripts/hook.core.py`).
Listens to `on_file_space_changed` emitted by `core.space`, consumes incremental diffs
via `consume_diff(consumer_id="ast")`, hot-patches or rebuilds the unified AST snapshot and call graph,
and broadcasts `on_ast_index_updated` to downstream subscribers.
"""

from contextlib import contextmanager, nullcontext
from typing import Any, Dict, Iterator, List, Optional

from core.log import log_debug


@contextmanager
def _resolve_consume_diff(
    engine: Any,
    space_name: Optional[str] = None,
    consumer_id: str = "ast",
    auto_refresh: Optional[bool] = None,
) -> Iterator[Any]:
    from core.space import consume_diff

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


def _broadcast_ast_updated(payload: Dict[str, Any]) -> None:
    try:
        from core import events  # type: ignore

        events.broadcast("on_ast_index_updated", payload, emit_module="ast")
    except Exception as exc:
        log_debug(f"Event broadcast 'on_ast_index_updated' skipped: {exc}")


def _get_current_ast_generation(engine: Any) -> int:
    snap = getattr(engine, "_snapshot", None)
    if snap is not None and hasattr(snap, "ast_generation"):
        return int(snap.ast_generation)
    if hasattr(engine, "get_persisted_meta"):
        try:
            meta = engine.get_persisted_meta()
            if isinstance(meta, dict) and "ast_generation" in meta:
                return int(meta["ast_generation"])
        except Exception:
            pass
    return 0


def _collect_engine_target_spaces(engine: Any) -> List[str]:
    """Collect target space names (both qualified and short names) managed by `engine`."""
    known_spaces: List[str] = []
    if hasattr(engine, "get_target_spaces"):
        try:
            for item in engine.get_target_spaces():
                s = str(item).strip()
                if s and s not in known_spaces:
                    known_spaces.append(s)
                short = s.split("/", 1)[-1].lstrip("/")
                if short and short not in known_spaces:
                    known_spaces.append(short)
        except Exception:
            pass
    if not known_spaces:
        bundler = getattr(engine, "bundler", None)
        if bundler is not None and hasattr(bundler, "get_target_space_names"):
            try:
                for item in bundler.get_target_space_names():
                    s = str(item).strip()
                    if s and s not in known_spaces:
                        known_spaces.append(s)
                    short = s.split("/", 1)[-1].lstrip("/")
                    if short and short not in known_spaces:
                        known_spaces.append(short)
            except Exception:
                pass
    if not known_spaces:
        space_mgr = getattr(engine, "space_manager", None)
        if space_mgr is not None and hasattr(space_mgr, "list_spaces"):
            try:
                for item in space_mgr.list_spaces():
                    if isinstance(item, str):
                        known_spaces.append(item)
                    else:
                        q_name = getattr(item, "qualified_name", "")
                        s_name = getattr(item, "short_name", "")
                        if q_name:
                            known_spaces.append(q_name)
                        if s_name and s_name not in known_spaces:
                            known_spaces.append(s_name)
            except Exception:
                known_spaces = []
    return known_spaces


def _is_target_space(name: Optional[str], known_spaces: List[str]) -> bool:
    if not name:
        return True
    if not known_spaces:
        return True
    norm = str(name).strip()
    short = norm.split("/", 1)[-1].lstrip("/")
    return norm in known_spaces or short in known_spaces


def on_file_space_changed(
    context: Any = None,
    spaces: Optional[List[str]] = None,
    diff_summary: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Triggered when `core.space` updates binary fingerprint snapshots and broadcasts `on_file_space_changed`.
    Consumes incremental diffs using `consumer_id="ast"`, updates `ASTEngine` snapshot/graph,
    and broadcasts `on_ast_index_updated`.
    """
    from ast_engine.engine import get_engine
    from ast_engine.io_utils import is_dirty_file_match, normalize_dirty_paths

    # Support explicit diff_detail argument passed by direct unit test callers
    diff_detail_arg = kwargs.get("diff_detail")
    if diff_detail_arg is not None:
        if isinstance(diff_detail_arg, dict) and not diff_detail_arg:
            return {"status": "skipped", "ast_generation": 0, "patched_count": 0}
        space_name_arg = kwargs.get("space_name") or (spaces[0] if spaces else "default")
        p_root = kwargs.get("project_root") or (context.get("project_root") if isinstance(context, dict) else None)
        s_dir = kwargs.get("storage_dir") or (context.get("storage_dir") if isinstance(context, dict) else None)
        eng = kwargs.get("engine") or get_engine(project_root=p_root, storage_dir=s_dir)
        known_for_arg = _collect_engine_target_spaces(eng)
        if not _is_target_space(str(space_name_arg), known_for_arg):
            return {
                "status": "noop",
                "ast_generation": _get_current_ast_generation(eng),
                "patched_count": 0,
                "to_generation": 0,
            }
        normalized_detail = (
            diff_detail_arg
            if "spaces" in diff_detail_arg
            else {"spaces": {str(space_name_arg): diff_detail_arg}}
        )
        eng_lock = getattr(eng, "_lock", None)
        with (eng_lock if eng_lock is not None else nullcontext()):
            snap = eng.hot_patch_index(normalized_detail, spaces=spaces)
        payload = {
            "status": "updated",
            "ast_generation": snap.ast_generation,
            "space_generations": dict(snap.space_generations),
        }
        _broadcast_ast_updated(payload)
        return payload

    engine: Optional[Any] = None
    target_space: Optional[str] = None

    if isinstance(context, dict):
        engine = context.get("engine")
        target_space = context.get("space_name")
        if spaces is None and isinstance(context.get("spaces"), list):
            spaces = context.get("spaces")
        if diff_summary is None and isinstance(context.get("diff_summary"), dict):
            diff_summary = context.get("diff_summary")
    elif context is not None:
        engine = getattr(context, "engine", None)
        target_space = getattr(context, "space_name", None)

    if engine is None:
        engine = kwargs.get("engine")
    has_explicit_engine = engine is not None
    if engine is None:
        p_root = kwargs.get("project_root") or (context.get("project_root") if isinstance(context, dict) else None)
        s_dir = kwargs.get("storage_dir") or (context.get("storage_dir") if isinstance(context, dict) else None)
        engine = get_engine(project_root=p_root, storage_dir=s_dir)

    if target_space is None and spaces and len(spaces) == 1:
        target_space = spaces[0]

    known_spaces = _collect_engine_target_spaces(engine)

    if target_space is not None and not _is_target_space(target_space, known_spaces):
        cur_ast_gen = _get_current_ast_generation(engine)
        return {
            "status": "noop",
            "ast_generation": cur_ast_gen,
            "patched_count": 0,
            "to_generation": 0,
        }

    if isinstance(spaces, list):
        spaces = [s for s in spaces if _is_target_space(s, known_spaces)]
        if not spaces and target_space is None:
            cur_ast_gen = _get_current_ast_generation(engine)
            return {
                "status": "noop",
                "ast_generation": cur_ast_gen,
                "patched_count": 0,
                "to_generation": 0,
            }

    if not has_explicit_engine:
        try:
            from core.context import get_runtime_context

            ctx_mem = get_runtime_context().get_module_state("knowledge_db.service.mem_state")
            active_kdb_worker = ctx_mem.get("active_worker") if isinstance(ctx_mem, dict) else None
            if active_kdb_worker is not None and getattr(active_kdb_worker, "is_alive", lambda: False)():
                notify_fn = getattr(active_kdb_worker, "notify_space_changed", None)
                if callable(notify_fn):
                    notify_fn()
                    return {
                        "status": "noop",
                        "ast_generation": _get_current_ast_generation(engine),
                        "patched_count": 0,
                        "to_generation": 0,
                    }
        except Exception:
            pass

    eng_lock = getattr(engine, "_lock", None)
    with (eng_lock if eng_lock is not None else nullcontext()):
        has_existing_snapshot = engine.symbols_index_path.exists() and engine.graph_index_path.exists()
        auto_refresh = False if diff_summary is not None else None

        with _resolve_consume_diff(
            engine,
            space_name=target_space,
            consumer_id="ast",
            auto_refresh=auto_refresh,
        ) as diff_res:
            if not diff_res.has_changes:
                if not has_existing_snapshot and diff_summary:
                    snap = engine.build_index(spaces=None, allow_parallel=False)
                    payload = {
                        "status": "rebuilt",
                        "ast_generation": snap.ast_generation,
                        "space_generations": dict(snap.space_generations),
                        "patched_count": len(snap.file_to_symbol_ids),
                        "to_generation": diff_res.to_generation,
                    }
                    _broadcast_ast_updated(payload)
                    return payload
                return {
                    "status": "noop",
                    "ast_generation": _get_current_ast_generation(engine),
                    "patched_count": 0,
                    "to_generation": diff_res.to_generation,
                }

            if not has_existing_snapshot:
                snap = engine.build_index(spaces=None, allow_parallel=False)
                payload = {
                    "status": "rebuilt",
                    "ast_generation": snap.ast_generation,
                    "space_generations": dict(snap.space_generations),
                    "patched_count": len(diff_res.detail.dirty_files),
                    "to_generation": diff_res.to_generation,
                }
                _broadcast_ast_updated(payload)
                return payload

            all_dirty = set(diff_res.detail.dirty_files) | set(diff_res.detail.deleted)
            parser_reg = getattr(engine, "parser_registry", None)
            if parser_reg is not None and all_dirty:
                known_files = set()
                snap_cur = getattr(engine, "_snapshot", None)
                if snap_cur is not None:
                    known_files = set(snap_cur.file_to_symbol_ids.keys()) | set(snap_cur.file_graphs.keys())
                known_norm = normalize_dirty_paths(known_files) if known_files else set()
                has_parseable = any(
                    parser_reg.get_parser(str(p)) is not None
                    or (known_norm and is_dirty_file_match(str(p), known_norm))
                    for p in all_dirty
                )
                if not has_parseable:
                    return {
                        "status": "noop",
                        "ast_generation": _get_current_ast_generation(engine),
                        "patched_count": 0,
                        "to_generation": diff_res.to_generation,
                    }

            snap = engine.hot_patch_index(
                diff_res.detail,
                spaces=spaces,
                _cursor_already_consumed=True,
            )
            payload = {
                "status": "patched",
                "ast_generation": snap.ast_generation,
                "space_generations": dict(snap.space_generations),
                "patched_count": len(diff_res.detail.dirty_files) + len(diff_res.detail.deleted),
                "to_generation": diff_res.to_generation,
            }
            _broadcast_ast_updated(payload)
            return payload
