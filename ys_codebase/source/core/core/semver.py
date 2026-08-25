"""
Four-Segment SemVer Parser, Comparator and Constraint Solver.
Format: major.minor.patch[.revision][-prerelease] (e.g. 1.0.0.0, 1.0.1.build, 2.0.0-beta.1)
100% Python Standard Library implementation.
"""
from typing import NamedTuple, Optional, List, Tuple, Union
import functools
import re

class VersionTuple(NamedTuple):
    """四段式版本數值四元組 (major.minor.patch.revision, prerelease)"""
    major: int
    minor: int
    patch: int
    revision: Union[int, str] = 0
    prerelease: str = ""

    @property
    def is_build(self) -> bool:
        return str(self.revision).lower() == "build"

    @property
    def triplet(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __str__(self) -> str:
        if self.prerelease:
            base = f"{self.major}.{self.minor}.{self.patch}"
            return f"{base}-{self.prerelease}"
        return f"{self.major}.{self.minor}.{self.patch}.{self.revision}"

_SEMVER_FOUR_SEGMENT_REGEX = re.compile(
    r"^(?:v|V)?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:\.(?P<revision>[0-9A-Za-z_-]+))?"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)

def parse_semver(version_str: Union[str, VersionTuple]) -> VersionTuple:
    """
    解析版本字串為 VersionTuple：
    - 三段式 '1.0.0' 自動補齊為 (1, 0, 0, 0, "")。
    - 四段式 '1.0.1.213' 解析為 (1, 0, 1, 213, "")。
    - '1.0.1.build' 解析為 (1, 0, 1, 'build', "")。
    - '2.0.0-beta.1' 解析為 (2, 0, 0, 0, 'beta.1')。
    若格式畸形或非字串拋出 ValueError。
    """
    if isinstance(version_str, VersionTuple):
        return version_str
    if not isinstance(version_str, str):
        raise ValueError(f"Version must be a string, got {type(version_str).__name__}")
    
    clean_v = version_str.strip()
    if not clean_v:
        raise ValueError("Version string cannot be empty")
        
    match = _SEMVER_FOUR_SEGMENT_REGEX.match(clean_v)
    if not match:
        raise ValueError(f"Invalid SemVer string format: '{version_str}'")
    
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    raw_rev = match.group("revision")
    prerelease = match.group("prerelease") or ""
    
    if raw_rev is None or raw_rev == "":
        revision: Union[int, str] = 0
    elif raw_rev.isdigit():
        revision = int(raw_rev)
    else:
        revision = raw_rev
        
    return VersionTuple(major, minor, patch, revision, prerelease)

def normalize_version(version_str: str) -> str:
    """將任意合法版本字串標準化為四段式字串 (例 '1.0.0' -> '1.0.0.0')"""
    return str(parse_semver(version_str))

def _compare_prerelease(pre1: str, pre2: str) -> int:
    if pre1 == pre2:
        return 0
    parts1 = pre1.split(".")
    parts2 = pre2.split(".")
    for p1, p2 in zip(parts1, parts2):
        if p1 == p2:
            continue
        p1_is_num = p1.isdigit()
        p2_is_num = p2.isdigit()
        if p1_is_num and p2_is_num:
            return 1 if int(p1) > int(p2) else -1
        elif p1_is_num and not p2_is_num:
            return -1
        elif not p1_is_num and p2_is_num:
            return 1
        else:
            return 1 if p1 > p2 else -1
    return 1 if len(parts1) > len(parts2) else -1

def compare_semver(v1: Union[str, VersionTuple], v2: Union[str, VersionTuple]) -> int:
    """
    比較兩版本大小：
    - 前三段 major.minor.patch 數值決定主要大小。
    - 數值相等時：
        - 正式版 > 預發布版 (1.0.0 > 1.0.0-beta)
        - 若皆有預發布標籤，比較 prerelease 標記
        - 若皆無預發布標籤，比較 revision (整數 > 'build')
    - 回傳: 1 (v1 > v2), -1 (v1 < v2), 0 (v1 == v2)。
    """
    t1 = parse_semver(v1)
    t2 = parse_semver(v2)
    
    # 1. 比較 major, minor, patch 數值三元組
    if t1.triplet > t2.triplet:
        return 1
    elif t1.triplet < t2.triplet:
        return -1
    
    # 2. 比較 prerelease
    if not t1.prerelease and t2.prerelease:
        return 1
    if t1.prerelease and not t2.prerelease:
        return -1
    if t1.prerelease and t2.prerelease:
        return _compare_prerelease(t1.prerelease, t2.prerelease)

    # 3. 前三段相等且皆無 prerelease，比較 revision
    r1, r2 = t1.revision, t2.revision
    if r1 == r2:
        return 0
    
    r1_is_int = isinstance(r1, int)
    r2_is_int = isinstance(r2, int)
    
    if r1_is_int and r2_is_int:
        return 1 if int(r1) > int(r2) else -1
    elif r1_is_int and not r2_is_int:
        return 1
    elif not r1_is_int and r2_is_int:
        return -1
    else:
        return 1 if str(r1) > str(r2) else -1

def bump_version(current_ver: str, bump_type: str) -> str:
    t = parse_semver(current_ver)
    b_type = bump_type.strip().lower()
    
    if b_type == "major":
        return str(VersionTuple(t.major + 1, 0, 0, 0))
    elif b_type == "minor":
        return str(VersionTuple(t.major, t.minor + 1, 0, 0))
    elif b_type == "patch":
        return str(VersionTuple(t.major, t.minor, t.patch + 1, 0))
    elif b_type == "revision":
        next_rev = t.revision + 1 if isinstance(t.revision, int) else 1
        return str(VersionTuple(t.major, t.minor, t.patch, next_rev))
    else:
        explicit_t = parse_semver(bump_type)
        if compare_semver(explicit_t, t) < 0:
            raise ValueError(f"Explicit version '{bump_type}' must be greater than current version '{current_ver}'")
        return str(explicit_t)

def _match_single_clause(version: str, clause: str) -> bool:
    clause = clause.strip()
    if not clause or clause == "*":
        return True
    
    op = ""
    target_v = ""
    for prefix in (">=", "<=", "!=", "==", "~=", "^=", "^", ">", "<", "="):
        if clause.startswith(prefix):
            op = prefix
            target_v = clause[len(prefix):].strip()
            break
    
    if not op:
        op = "=="
        target_v = clause
    
    if op == "=":
        op = "=="
    elif op == "^":
        op = "^="
    
    if op == "==":
        if target_v.endswith(".*"):
            prefix_target = target_v[:-2]
            v_tuple = parse_semver(version)
            parts = prefix_target.split(".")
            if len(parts) == 1:
                return v_tuple.major == int(parts[0])
            elif len(parts) == 2:
                return v_tuple.major == int(parts[0]) and v_tuple.minor == int(parts[1])
            elif len(parts) == 3:
                return v_tuple.triplet == (int(parts[0]), int(parts[1]), int(parts[2]))
            return False
        
        target_tuple = parse_semver(target_v)
        v_tuple = parse_semver(version)
        if "." not in target_v.lstrip("vV") or target_v.count(".") == 2:
            return v_tuple.triplet == target_tuple.triplet
        return compare_semver(version, target_v) == 0
    elif op == "!=":
        return compare_semver(version, target_v) != 0
    elif op == ">":
        return compare_semver(version, target_v) > 0
    elif op == ">=":
        return compare_semver(version, target_v) >= 0
    elif op == "<":
        return compare_semver(version, target_v) < 0
    elif op == "<=":
        return compare_semver(version, target_v) <= 0
    elif op in ("~=", "^="):
        v_target = parse_semver(target_v)
        v_curr = parse_semver(version)
        if compare_semver(v_curr, v_target) < 0:
            return False
        if v_target.major == 0:
            return v_curr.major == 0 and v_curr.minor == v_target.minor
        return v_curr.major == v_target.major
    
    return False

def match_constraint(version: Union[str, VersionTuple], constraint: Optional[str]) -> bool:
    v_str = str(version)
    if not constraint or constraint.strip() == "" or constraint.strip() == "*":
        return True
    
    clauses = [c.strip() for c in constraint.split(",") if c.strip()]
    for c in clauses:
        if not _match_single_clause(v_str, c):
            return False
    return True

def find_best_version(versions: List[str], constraint: Optional[str] = None) -> Optional[str]:
    if not versions:
        return None
    
    valid_candidates: List[str] = []
    for v in versions:
        try:
            if match_constraint(v, constraint):
                valid_candidates.append(v)
        except Exception:
            continue
    
    if not valid_candidates:
        return None
    
    sorted_candidates = sorted(valid_candidates, key=functools.cmp_to_key(compare_semver))
    return sorted_candidates[-1]
