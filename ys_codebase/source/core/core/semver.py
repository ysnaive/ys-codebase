"""
SemVer 2.0.0 Parser, Comparator and Constraint Solver.
100% Python Standard Library implementation.
"""
from typing import NamedTuple, Optional, List, Tuple
import functools
import re

class VersionTuple(NamedTuple):
    """SemVer 2.0.0 版本數值四元組"""
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base

_SEMVER_REGEX = re.compile(
    r"^(?:v|V)?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)

def parse_semver(version_str: str) -> VersionTuple:
    """
    解析標準 SemVer 2.0.0 版本字串（如 '1.10.0', '2.0.0-beta.1'）。
    若格式畸形拋出 ValueError。
    """
    if not isinstance(version_str, str):
        raise ValueError(f"Version must be a string, got {type(version_str).__name__}")
    
    clean_v = version_str.strip()
    match = _SEMVER_REGEX.match(clean_v)
    if not match:
        raise ValueError(f"Invalid SemVer 2.0.0 string format: '{version_str}'")
    
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    prerelease = match.group("prerelease") or ""
    return VersionTuple(major, minor, patch, prerelease)

def _compare_prerelease(pre1: str, pre2: str) -> int:
    """
    比較兩 prerelease 標記：
    - 正式版 > 預發布版 (由呼叫端處理)
    - 逐段比較識別碼 (數值段按數字比，字串段按 ASCII 字典序比)
    """
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
            return -1  # 數字段優先級低於非數字段
        elif not p1_is_num and p2_is_num:
            return 1
        else:
            return 1 if p1 > p2 else -1
            
    return 1 if len(parts1) > len(parts2) else -1

def compare_semver(v1: str, v2: str) -> int:
    """
    比較兩版本大小：
    - 回傳 1: v1 > v2
    - 回傳 -1: v1 < v2
    - 回傳 0: v1 == v2
    """
    t1 = parse_semver(v1)
    t2 = parse_semver(v2)
    
    # 1. 比較 major, minor, patch 數值三元組
    num1 = (t1.major, t1.minor, t1.patch)
    num2 = (t2.major, t2.minor, t2.patch)
    if num1 > num2:
        return 1
    elif num1 < num2:
        return -1
    
    # 2. 數值相等，比較 prerelease
    if not t1.prerelease and not t2.prerelease:
        return 0
    if not t1.prerelease and t2.prerelease:
        return 1  # 正式版大於預發布版 (1.0.0 > 1.0.0-beta)
    if t1.prerelease and not t2.prerelease:
        return -1
    
    return _compare_prerelease(t1.prerelease, t2.prerelease)

def _match_single_clause(version: str, clause: str) -> bool:
    clause = clause.strip()
    if not clause or clause == "*":
        return True
    
    # 判斷前綴操作符
    op = ""
    target_v = ""
    for prefix in (">=", "<=", "!=", "==", "~=", "^=", ">", "<", "="):
        if clause.startswith(prefix):
            op = prefix
            target_v = clause[len(prefix):].strip()
            break
    
    if not op:
        # 無操作符，視為精確匹配 '=='
        op = "=="
        target_v = clause
    
    # 相容前綴
    if op == "=":
        op = "=="
    
    if op == "==":
        if target_v.endswith(".*"):
            prefix_target = target_v[:-2]
            v_tuple = parse_semver(version)
            parts = prefix_target.split(".")
            if len(parts) == 1:
                return v_tuple.major == int(parts[0])
            elif len(parts) == 2:
                return v_tuple.major == int(parts[0]) and v_tuple.minor == int(parts[1])
            return False
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
    elif op == "~=" or op == "^=":
        # Compatible release (>= target_v, 同 major)
        v_target = parse_semver(target_v)
        v_curr = parse_semver(version)
        if compare_semver(version, target_v) < 0:
            return False
        if v_target.major == 0:
            # 0.x 系列按 minor 鎖定
            return v_curr.major == 0 and v_curr.minor == v_target.minor
        return v_curr.major == v_target.major
    
    return False

def match_constraint(version: str, constraint: Optional[str]) -> bool:
    """
    判斷特定版本是否滿足範圍約束：
    - 支援標準前綴：'>=', '>', '<=', '<', '==', '!=', '~=', '^', '*' 或 None (無約束全匹配)。
    - 支援逗號組合：'>=1.0.0, <2.0.0'
    """
    if not constraint or constraint.strip() == "" or constraint.strip() == "*":
        return True
    
    clauses = [c.strip() for c in constraint.split(",") if c.strip()]
    for c in clauses:
        if not _match_single_clause(version, c):
            return False
    return True

def find_best_version(versions: List[str], constraint: Optional[str] = None) -> Optional[str]:
    """
    自版本字串清單中，篩選出符合 constraint 的最高版本（依 SemVer 數值排序）。
    若無可用或無合規版本，回傳 None。
    """
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
    
    # 依 SemVer 排序選取最高版本
    sorted_candidates = sorted(valid_candidates, key=functools.cmp_to_key(compare_semver))
    return sorted_candidates[-1]
