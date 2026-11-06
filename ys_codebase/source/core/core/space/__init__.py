"""
Core File-Space Atomic Engine (`core.space`).
100% Python Standard Library. Zero Third-Party Dependencies.
Provides `<owner>/<name>` namespace-isolated presets & spaces, `<name>` short-name union addressing,
explicit `presets` expansion (including `@gitignore`), three-coordinate precompiled rule matching (`match`),
zero-redundancy `os.scandir` pruned traversal (`ls`), and atomic Blake2b fingerprinting (`hash`).
"""

from .exceptions import SpaceError, SpaceNotFoundError
from .hasher import (
    FileHashEntry,
    SpaceHashResult,
    compute_file_hash,
    compute_space_merkle_root,
    hash_space_or_path,
    hash_target,
)
from .registry import (
    MatchExplainResult,
    SpaceFileEntry,
    SpaceMatchDetail,
    SpaceRegistry,
    compute_canonical_rel_path,
    iter_space_files,
    match_path,
)
from .schema import (
    CompiledRuleSet,
    GitignoreEvaluator,
    HashPolicy,
    PresetConfig,
    RuleItem,
    SpaceConfig,
    resolve_semantic_or_rel_path,
)

__all__ = [
    "CompiledRuleSet",
    "FileHashEntry",
    "GitignoreEvaluator",
    "HashPolicy",
    "MatchExplainResult",
    "PresetConfig",
    "RuleItem",
    "SpaceConfig",
    "SpaceError",
    "SpaceFileEntry",
    "SpaceHashResult",
    "SpaceMatchDetail",
    "SpaceNotFoundError",
    "SpaceRegistry",
    "compute_canonical_rel_path",
    "compute_file_hash",
    "compute_space_merkle_root",
    "hash_space_or_path",
    "hash_target",
    "iter_space_files",
    "match_path",
    "resolve_semantic_or_rel_path",
]
