# -*- coding: utf-8 -*-
"""
YS-Codebase 核心語意化版本引擎 (SemVer 2.0.0 & VersionConstraint)

本模組 100% 使用 Python 3.8+ 標準庫實現，嚴禁引入任何第三方套件。
支援 SemVer 2.0.0 規範解析、富比較運算符、剛性遞進 (Bump) 與相依約束表達式匹配。
"""

import re
from typing import Optional, Union, Tuple, List, Any


SEMVER_REGEX = re.compile(
    r"^[vV]?(?P<major>0|[1-9]\d*)"
    r"(?:\.(?P<minor>0|[1-9]\d*))?"
    r"(?:\.(?P<patch>0|[1-9]\d*))?"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def _compare_prerelease(pre1: Optional[str], pre2: Optional[str]) -> int:
    """
    比較兩個預發布標籤 (SemVer 2.0.0 Spec Section 11)。
    - 無 prerelease 的版本優先級高於有 prerelease 的版本 (1.0.0 > 1.0.0-alpha)。
    - 若兩者皆有，依據 '.' 分割各 identifier 進行比對：
      - 純數字比對數值大小。
      - 包含字母者比對 ASCII 字典序。
      - 數字識別碼優先級低於字母識別碼。
    回傳：-1 (pre1 < pre2), 0 (pre1 == pre2), 1 (pre1 > pre2)
    """
    if pre1 is None and pre2 is None:
        return 0
    if pre1 is None and pre2 is not None:
        return 1
    if pre1 is not None and pre2 is None:
        return -1

    parts1 = pre1.split(".")  # type: ignore
    parts2 = pre2.split(".")  # type: ignore

    for p1, p2 in zip(parts1, parts2):
        if p1 == p2:
            continue
        p1_is_num = p1.isdigit()
        p2_is_num = p2.isdigit()

        if p1_is_num and p2_is_num:
            return 1 if int(p1) > int(p2) else -1
        elif p1_is_num and not p2_is_num:
            return -1  # 數字比非數字小
        elif not p1_is_num and p2_is_num:
            return 1   # 非數字比數字大
        else:
            return 1 if p1 > p2 else -1

    # 前綴相同，較長者優先級較高
    if len(parts1) > len(parts2):
        return 1
    elif len(parts1) < len(parts2):
        return -1
    return 0


class SemVer:
    """
    SemVer 2.0.0 語意化版本類別。
    """
    __slots__ = ("major", "minor", "patch", "prerelease", "build")

    def __init__(self, version: Union[str, "SemVer"]):
        if isinstance(version, SemVer):
            self.major = version.major
            self.minor = version.minor
            self.patch = version.patch
            self.prerelease = version.prerelease
            self.build = version.build
            return

        if not isinstance(version, str) or not version.strip():
            raise ValueError(f"無效的版本格式: {repr(version)}")

        cleaned = version.strip()
        match = SEMVER_REGEX.match(cleaned)
        if not match:
            raise ValueError(f"無法解析為合法 SemVer 2.0.0 格式: '{version}'")

        gd = match.groupdict()
        self.major = int(gd["major"])
        self.minor = int(gd["minor"]) if gd["minor"] is not None else 0
        self.patch = int(gd["patch"]) if gd["patch"] is not None else 0
        self.prerelease = gd["prerelease"]
        self.build = gd["build"]

    @classmethod
    def parse(cls, version_str: str) -> "SemVer":
        """寬容解析版本字串。"""
        return cls(version_str)

    @classmethod
    def is_valid(cls, version_str: Any) -> bool:
        """檢驗是否為合法版本字串。"""
        if not isinstance(version_str, str) or not version_str.strip():
            return False
        return bool(SEMVER_REGEX.match(version_str.strip()))

    def bump_major(self) -> "SemVer":
        """遞進 MAJOR (X.0.0)，MINOR 與 PATCH 歸零，清除預發布與建置元數據。"""
        return SemVer(f"{self.major + 1}.0.0")

    def bump_minor(self) -> "SemVer":
        """遞進 MINOR (X.Y.0)，PATCH 歸零，清除預發布與建置元數據。"""
        return SemVer(f"{self.major}.{self.minor + 1}.0")

    def bump_patch(self) -> "SemVer":
        """遞進 PATCH (X.Y.Z)，清除預發布與建置元數據。"""
        return SemVer(f"{self.major}.{self.minor}.{self.patch + 1}")

    def bump(self, level: str) -> "SemVer":
        """
        依指定級別遞進版本。
        
        :param level: 'major' | 'minor' | 'patch' (不分大小寫)
        """
        norm_level = level.strip().lower()
        if norm_level == "major":
            return self.bump_major()
        elif norm_level == "minor":
            return self.bump_minor()
        elif norm_level == "patch":
            return self.bump_patch()
        else:
            raise ValueError(f"未知的遞進等級 '{level}'，僅支援 'major', 'minor', 'patch'。")

    def __tuple_key(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            if not SemVer.is_valid(other):
                return False
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        return (
            self.__tuple_key() == other.__tuple_key()
            and _compare_prerelease(self.prerelease, other.prerelease) == 0
        )

    def __ne__(self, other: Any) -> bool:
        eq = self.__eq__(other)
        if eq is NotImplemented:
            return NotImplemented
        return not eq

    def __lt__(self, other: Union[str, "SemVer"]) -> bool:
        if isinstance(other, str):
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented

        if self.__tuple_key() < other.__tuple_key():
            return True
        elif self.__tuple_key() > other.__tuple_key():
            return False

        # Major, Minor, Patch 均相同，比較 prerelease
        return _compare_prerelease(self.prerelease, other.prerelease) < 0

    def __le__(self, other: Union[str, "SemVer"]) -> bool:
        if isinstance(other, str):
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.__lt__(other) or self.__eq__(other)

    def __gt__(self, other: Union[str, "SemVer"]) -> bool:
        if isinstance(other, str):
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        return not self.__le__(other)

    def __ge__(self, other: Union[str, "SemVer"]) -> bool:
        if isinstance(other, str):
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        return not self.__lt__(other)

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease is not None:
            s += f"-{self.prerelease}"
        if self.build is not None:
            s += f"+{self.build}"
        return s

    def __repr__(self) -> str:
        return f"SemVer('{str(self)}')"


class VersionConstraint:
    """
    語意化版本相依約束表達式解析與匹配器。
    """
    __slots__ = ("raw_expr", "_predicates")

    def __init__(self, constraint_expr: str):
        self.raw_expr = constraint_expr.strip() if constraint_expr else "*"
        self._predicates: List[Tuple[str, SemVer]] = []
        self._parse(self.raw_expr)

    def _parse(self, expr: str):
        if not expr or expr == "*":
            return

        # 支援以逗號分割條件 (例: ">= 1.0.0, < 2.0.0" 或 "^1.0.0, != 1.2.0")
        raw_parts = [p.strip() for p in expr.split(",") if p.strip()]

        for part in raw_parts:
            if part == "*":
                continue

            op_match = re.match(r"^(\^|~|>=|<=|>|<|==|!=|=)?\s*(.+)$", part)
            if not op_match:
                continue

            op, v_str = op_match.groups()
            op = op or "=="
            if op == "=":
                op = "=="
            v = SemVer(v_str.strip())

            # Caret 相容 (^1.2.3)
            if op == "^":
                self._predicates.append((">=", v))
                if v.major > 0:
                    self._predicates.append(("<", SemVer(f"{v.major + 1}.0.0")))
                elif v.minor > 0:
                    self._predicates.append(("<", SemVer(f"0.{v.minor + 1}.0")))
                else:
                    self._predicates.append(("<", SemVer(f"0.0.{v.patch + 1}")))
                continue

            # Tilde 相容 (~1.2.3 或 ~1.2)
            if op == "~":
                self._predicates.append((">=", v))
                self._predicates.append(("<", SemVer(f"{v.major}.{v.minor + 1}.0")))
                continue

            # 標準運算符
            self._predicates.append((op, v))


    def matches(self, version: Union[str, SemVer]) -> bool:
        """判定版本是否滿足所有約束。"""
        if not isinstance(version, SemVer):
            try:
                version = SemVer(version)
            except Exception:
                return False

        for op, target_v in self._predicates:
            if op == ">=":
                if not (version >= target_v):
                    return False
            elif op == "<=":
                if not (version <= target_v):
                    return False
            elif op == ">":
                if not (version > target_v):
                    return False
            elif op == "<":
                if not (version < target_v):
                    return False
            elif op == "==":
                if not (version == target_v):
                    return False
            elif op == "!=":
                if not (version != target_v):
                    return False
        return True

    @classmethod
    def parse_dependency_spec(cls, spec_str: str) -> Tuple[str, "VersionConstraint"]:
        """
        解析 manifest.json 中的 dependencies 項目。
        支援 "core >= 2.0.0", "core ^1.0.0", "core" 等寫法。
        """
        if not spec_str or not spec_str.strip():
            raise ValueError("相依性描述不能為空。")

        cleaned = spec_str.strip()
        # 尋找比較運算符位置 (^, ~, >=, <=, >, <, ==, =, !=)
        match = re.search(r"(\^|~|>=|<=|>|<|==|=|!=)", cleaned)
        if match:
            idx = match.start()
            mod_name = cleaned[:idx].strip()
            expr = cleaned[idx:].strip()
            return mod_name, cls(expr)

        # 尋找空格切分 (如 "core 2.0.0")
        parts = cleaned.split(maxsplit=1)
        if len(parts) == 1:
            return parts[0].strip(), cls("*")
        else:
            return parts[0].strip(), cls(parts[1].strip())

    def __str__(self) -> str:
        return self.raw_expr

    def __repr__(self) -> str:
        return f"VersionConstraint('{self.raw_expr}')"
