"""
JSON Schema Draft-07 Compiler for `module:vscode-support` (`vscode_support/schema_compiler.py`).
Compiles per-module `contributes/<mod>.schema.json`, `config/<mod>.schema.json`,
and meta schemas (`format-meta.schema.json`, `manifest.schema.json`) into `project://.vscode/schemas/`.
Strictly adheres to Zero-Probing (reads only from `module://` and `module.mirror://`).
"""

import functools
import glob
import json
import os
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple

from core import contributes, uri, vfs
from core.context import cell_span, get_runtime_context
from core.semver import compare_semver, parse_semver
from core.validator import ContributesValidator

DRAFT_07_URI = "http://json-schema.org/draft-07/schema#"
_MAX_MIRROR_ZIP_CACHE_ENTRIES = 64


class SchemaCompiler:
    """
    動態單檔級 JSON Schema 編譯器。
    重用 `ContributesValidator.parse_type_signature` 與 `module.mirror://` 內之原始組態模板，
    生成 Draft-07 JSON Schema 並清理已移除模組之孤兒 Schema。
    """

    def __init__(self, yscb_dir: Optional[str] = None) -> None:
        self.yscb_dir = os.path.abspath(yscb_dir or uri.resolve_yscb_root())
        self._cached_uri_snippets: Optional[List[Dict[str, Any]]] = None

    @property
    def _mirror_zip_bundle_cache(
        self,
    ) -> Dict[Tuple[str, int], Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]:
        return get_runtime_context().get_module_state("vscode_support.mirror_zip_cache", dict)

    def _collect_uri_scheme_snippets(self) -> List[Dict[str, Any]]:
        """
        動態收集全系統已註冊之語意 URI 協議與相對路徑前綴，
        生成 VS Code JSON Schema 原生支援之 `defaultSnippets` 補全清單。
        """
        if self._cached_uri_snippets is not None:
            return list(self._cached_uri_snippets)

        schemes: Dict[str, str] = {
            "project": "專案業務根目錄 (project_root)",
            "yscb": "YS-Codebase 工具庫根目錄",
            "yscb.host": "宿主工程根目錄 (yscb.py 所在目錄)",
            "config": "模組團隊版控設定檔空間根目錄 (yscb://config/)",
            "config.local": "模組本機開發環境設定與私密憑證空間根目錄 (yscb://.config.local/)",
            "module": "本地模組運行端空間根目錄 (yscb://.modules/)",
            "module.source": "模組源碼空間根目錄 (yscb://source/)",
            "module.build": "本地開發完整建置產物空間根目錄 (yscb://.build/)",
            "module.release": "模組發布來源空間根目錄 (yscb://release/)",
            "module.mirror": "本地端模組鏡像庫空間根目錄 (yscb://.mirror/)",
            "cache": "模組快取與中繼暫存空間根目錄 (yscb://.cache/)",
            "storage": "模組團隊版控持久化儲存空間根目錄 (yscb://storage/)",
            "storage.local": "模組本機持久化運行狀態與索引空間根目錄 (yscb://.storage.local/)",
            "snapshot": "組態歷史快照空間目錄 (yscb://.snapshots/)",
            "yscb.venv": "YSCB 私有微虛擬環境空間根目錄 (yscb://.venv/)",
        }
        try:
            raw_schemes = contributes.get("core", "uri_schemes")
            if isinstance(raw_schemes, list):
                for item in raw_schemes:
                    if isinstance(item, dict):
                        token = str(item.get("token", "")).strip()
                        desc = str(item.get("description", "")).strip()
                        if token:
                            schemes[token] = desc or f"語意 URI 協議 {token}://"
        except Exception:
            pass

        snippets: List[Dict[str, Any]] = []
        for token in sorted(schemes.keys()):
            prefix = f"{token}://"
            snippets.append(
                {
                    "label": prefix,
                    "description": schemes[token],
                    "body": f"{prefix}$1",
                }
            )
        snippets.append(
            {
                "label": "./",
                "description": "相對路徑前綴",
                "body": "./$1",
            }
        )
        return snippets

    def _build_uri_path_schema(self, is_path: bool = False) -> Dict[str, Any]:
        """建構支援語意 URI 協議前綴補全 (`defaultSnippets`) 之字串 Schema。"""
        label = "檔案/目錄路徑或語意 URI (支援輸入協議前綴如 project://, config://, module://)" if is_path else "語意 URI 或路徑 (支援輸入協議前綴如 project://, config://, module://)"
        return {
            "type": "string",
            "minLength": 1,
            "markdownDescription": label,
            "defaultSnippets": self._collect_uri_scheme_snippets(),
        }

    def _parsed_rule_to_json_schema(self, parsed: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        required = bool(parsed.get("required", False))
        has_default = bool(parsed.get("has_default", False))
        default_val = parsed.get("default")
        merge_strategy = parsed.get("merge_strategy")
        t_name = parsed.get("type", "any")

        schema: Dict[str, Any] = {}

        if t_name == "ref":
            ref_name = parsed.get("ref_name", "")
            schema = {"$ref": f"#/$defs/{ref_name}"}
        elif t_name == "enum":
            schema = {
                "type": "string",
                "enum": list(parsed.get("enum_values", [])),
            }
        elif t_name in ("uri", "path"):
            schema = self._build_uri_path_schema(is_path=(t_name == "path"))
        elif t_name == "str":
            schema = {"type": "string"}
        elif t_name == "int":
            schema = {"type": "integer"}
        elif t_name == "float":
            schema = {"type": "number"}
        elif t_name == "bool":
            schema = {"type": "boolean"}
        elif t_name == "any":
            schema = {}
        elif t_name == "list":
            item_parsed = parsed.get("item_type")
            item_schema, _ = self._parsed_rule_to_json_schema(item_parsed) if isinstance(item_parsed, dict) else ({}, False)
            schema = {
                "type": "array",
                "items": item_schema,
            }
        elif t_name == "dict":
            val_parsed = parsed.get("value_type")
            val_schema, _ = self._parsed_rule_to_json_schema(val_parsed) if isinstance(val_parsed, dict) else ({}, False)
            schema = {
                "type": "object",
                "additionalProperties": val_schema if val_schema else True,
            }
        else:
            schema = {}

        if has_default and default_val is not None:
            schema["default"] = default_val

        field_desc = parsed.get("description")
        md_parts: List[str] = []
        if field_desc:
            schema["description"] = str(field_desc)
            md_parts.append(str(field_desc))
        elif "markdownDescription" in schema:
            md_parts.append(str(schema["markdownDescription"]))

        if t_name in ("uri", "path") and field_desc:
            md_parts.append("*(支援輸入語意 URI 協議前綴如 `project://`, `config://`, `module://`)*")

        if merge_strategy:
            md_parts.append(f"*(合併策略: `{merge_strategy}`)*")

        if md_parts:
            schema["markdownDescription"] = "\n\n".join(md_parts)

        return schema, required

    def _format_node_to_json_schema(self, fmt_node: Any) -> Tuple[Dict[str, Any], bool]:
        """遞迴將 `_format.json` 的結構節點（str / list / dict）轉譯為 JSON Schema。"""
        if isinstance(fmt_node, str):
            return self._parsed_rule_to_json_schema(ContributesValidator.parse_type_signature(fmt_node))

        if isinstance(fmt_node, list):
            if len(fmt_node) > 0:
                item_schema, _ = self._format_node_to_json_schema(fmt_node[0])
            else:
                item_schema = {}
            return {
                "type": "array",
                "items": item_schema,
            }, False

        if isinstance(fmt_node, dict):
            properties: Dict[str, Any] = {}
            required_keys: List[str] = []
            wildcard_schema: Optional[Dict[str, Any]] = None

            for k, v in fmt_node.items():
                if k == "*":
                    wildcard_schema, _ = self._format_node_to_json_schema(v)
                else:
                    prop_schema, is_req = self._format_node_to_json_schema(v)
                    properties[k] = prop_schema
                    if is_req:
                        required_keys.append(k)

            obj_schema: Dict[str, Any] = {"type": "object"}
            if properties:
                obj_schema["properties"] = properties
            if required_keys:
                obj_schema["required"] = sorted(required_keys)

            if wildcard_schema is not None:
                obj_schema["additionalProperties"] = wildcard_schema if wildcard_schema else True
            else:
                obj_schema["additionalProperties"] = False
                obj_schema["patternProperties"] = {"^__.*__$": {}}

            return obj_schema, False

        return {}, False

    def _compile_type_defs(self, fmt_data: Dict[str, Any]) -> Dict[str, Any]:
        """將 `_format.json` 中的 `_types` 區段編譯為 JSON Schema `$defs` 字典。"""
        defs: Dict[str, Any] = {}
        raw_types = fmt_data.get("_types", {})
        if isinstance(raw_types, dict):
            for type_name, type_def in raw_types.items():
                type_schema, _ = self._format_node_to_json_schema(type_def)
                defs[type_name] = type_schema
        return defs

    def compile_contributes_schema(self, mod_name: str, fmt_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        將指定模組之 `contributes/_format.json` 轉譯為完整 Draft-07 JSON Schema。
        支援頂層直接放置擴充點鍵或外層包裹 `{"<mod_name>": { ... }}`（相容 `config/<mod>/contribute.json`）。
        """
        defs = self._compile_type_defs(fmt_data)

        ext_properties: Dict[str, Any] = {}
        for ext_key, ext_spec in fmt_data.items():
            if ext_key == "_types" or not isinstance(ext_spec, dict):
                continue
            fmt_body = ext_spec.get("format")
            if fmt_body is None:
                continue
            prop_schema, _ = self._format_node_to_json_schema(fmt_body)
            desc = ext_spec.get("description")
            merge_strat = ext_spec.get("merge")
            if desc:
                prop_schema["description"] = str(desc)
                if merge_strat:
                    prop_schema["markdownDescription"] = f"{desc} *(合併策略: `{merge_strat}`)*"
                elif "markdownDescription" not in prop_schema:
                    prop_schema["markdownDescription"] = str(desc)
            ext_properties[ext_key] = prop_schema

        # 支援 config/<mod>/contribute.json 外層包裹 {"<mod>": { ... }}
        inner_ext_obj: Dict[str, Any] = {
            "type": "object",
            "properties": dict(ext_properties),
            "additionalProperties": False,
            "patternProperties": {"^__.*__$": {}},
        }
        top_properties = dict(ext_properties)
        if mod_name not in top_properties:
            top_properties[mod_name] = inner_ext_obj

        root_schema: Dict[str, Any] = {
            "$schema": DRAFT_07_URI,
            "title": f"YS-Codebase Contributes Schema for '{mod_name}'",
            "type": "object",
            "properties": top_properties,
            "additionalProperties": False,
            "patternProperties": {"^__.*__$": {}},
        }
        if defs:
            root_schema["$defs"] = defs
        return root_schema

    def _infer_value_schema(self, val: Any, key_name: str = "") -> Dict[str, Any]:
        """根據組態模板範例值推導基本型別 JSON Schema（對 `!undefined` 標註必填檢查，並為路徑欄位注入 URI 協議補全）。"""
        leaf_key = key_name.rsplit(".", 1)[-1] if key_name else ""
        is_path_key = any(tok in leaf_key.lower() for tok in ("path", "dir", "root", "uri", "source", "target"))
        if val == "!undefined":
            res_undef: Dict[str, Any] = {
                "type": "string",
                "minLength": 1,
                "not": {"const": "!undefined"},
                "markdownDescription": "必填設定項（請替換預設佔位符 `!undefined`）",
            }
            if is_path_key:
                res_undef["defaultSnippets"] = self._collect_uri_scheme_snippets()
            return res_undef
        if isinstance(val, bool):
            return {"type": "boolean", "default": val}
        if isinstance(val, int):
            return {"type": "integer", "default": val}
        if isinstance(val, float):
            return {"type": "number", "default": val}
        if isinstance(val, str):
            res_str: Dict[str, Any] = {"type": "string", "default": val}
            if "://" in val or val.startswith(("./", "../")) or is_path_key:
                res_str["defaultSnippets"] = self._collect_uri_scheme_snippets()
            return res_str
        if isinstance(val, list):
            if len(val) > 0 and all(isinstance(x, str) for x in val):
                item_schema: Dict[str, Any] = {"type": "string"}
                if any("://" in x or x.startswith(("./", "../")) for x in val) or is_path_key:
                    item_schema["defaultSnippets"] = self._collect_uri_scheme_snippets()
            else:
                item_schema = {}
            return {
                "type": "array",
                "items": item_schema,
                "default": val,
            }
        if isinstance(val, dict):
            props: Dict[str, Any] = {}
            req: List[str] = []
            for k, v in val.items():
                child_key = f"{key_name}.{k}" if key_name else k
                props[k] = self._infer_value_schema(v, key_name=child_key)
                if v == "!undefined":
                    req.append(k)
            res: Dict[str, Any] = {
                "type": "object",
                "properties": props,
            }
            if req:
                res["required"] = sorted(req)
            return res
        return {}

    def compile_config_schema(
        self,
        mod_name: str,
        template_data: Optional[Dict[str, Any]] = None,
        fmt_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        由模組 `configurable/_format.json`（優先，與 `contributes/_format.json` 共享同一套型別與 `@desc` DSL）
        或組態模板字典 (`template_data` Fallback) 編譯 `schemas/config/<mod>.schema.json`。
        """
        defs: Dict[str, Any] = {}
        props: Dict[str, Any] = {}
        req: List[str] = []

        if isinstance(fmt_data, dict) and fmt_data:
            defs = self._compile_type_defs(fmt_data)

            for k, v in fmt_data.items():
                if k == "_types":
                    continue
                is_rule_wrapper = (
                    isinstance(v, dict)
                    and "format" in v
                    and set(v.keys()).issubset({"format", "description", "merge", "default"})
                    and isinstance(v.get("description"), (str, type(None)))
                )
                if is_rule_wrapper:
                    prop_schema, is_req = self._format_node_to_json_schema(v["format"])
                    desc = v.get("description")
                    if desc:
                        prop_schema["description"] = str(desc)
                        if "markdownDescription" not in prop_schema:
                            prop_schema["markdownDescription"] = str(desc)
                    if "default" in v and v["default"] is not None:
                        prop_schema["default"] = v["default"]
                else:
                    prop_schema, is_req = self._format_node_to_json_schema(v)
                props[k] = prop_schema
                if is_req:
                    req.append(k)

        if isinstance(template_data, dict) and template_data:
            inferred = self._infer_value_schema(template_data)
            inferred_props = inferred.get("properties", {})
            inferred_req = inferred.get("required", [])
            for k, v_schema in inferred_props.items():
                if k not in props:
                    props[k] = v_schema
                elif "default" not in props[k] and "default" in v_schema:
                    props[k]["default"] = v_schema["default"]
            if not fmt_data:
                for rk in inferred_req:
                    if rk not in req:
                        req.append(rk)

        root_schema: Dict[str, Any] = {
            "$schema": DRAFT_07_URI,
            "title": f"YS-Codebase Configuration Schema for '{mod_name}'",
            "type": "object",
            "properties": props,
            "additionalProperties": False if fmt_data else True,
        }
        if req:
            root_schema["required"] = sorted(req)
        if defs:
            root_schema["$defs"] = defs
        return root_schema

    def build_format_meta_schema(self) -> Dict[str, Any]:
        """建構校驗 `**/contributes/_format.json` 與 `**/configurable/_format.json` 之元 Schema。"""
        return {
            "$schema": DRAFT_07_URI,
            "title": "YS-Codebase _format.json Meta Schema",
            "type": "object",
            "properties": {
                "_types": {
                    "type": "object",
                    "description": "宣告可重用之命名結構型別（透過 $TypeName 引用）",
                    "additionalProperties": {
                        "type": ["object", "string", "array"]
                    },
                }
            },
            "additionalProperties": {
                "oneOf": [
                    {
                        "type": "object",
                        "required": ["format"],
                        "properties": {
                            "description": {"type": "string"},
                            "merge": {
                                "type": "string",
                                "enum": ["merge", "extend", "replace", "unique"],
                            },
                            "format": {
                                "type": ["object", "array", "string"],
                            },
                        },
                        "additionalProperties": False,
                    },
                    {
                        "type": ["string", "array"],
                    },
                    {
                        "type": "object",
                        "not": {"required": ["format"]},
                    },
                ]
            },
        }

    def build_manifest_meta_schema(self) -> Dict[str, Any]:
        """建構校驗 `**/manifest.json` 之元 Schema，與 `dev.checker` 靜態檢核契約完全對齊。"""
        return {
            "$schema": DRAFT_07_URI,
            "title": "YS-Codebase Module manifest.json Meta Schema",
            "type": "object",
            "required": ["name", "version", "entry", "dependencies"],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "name": {"type": "string", "minLength": 1},
                "version": {
                    "type": "string",
                    "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+(\\.[0-9]+)?(-[0-9A-Za-z.-]+)?$",
                },
                "description": {"type": "string"},
                "author": {"type": "string"},
                "entry": {"type": "string", "minLength": 1},
                "dependencies": {
                    "oneOf": [
                        {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                        {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    ]
                },
                "optional": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "required": ["version", "hint"],
                        "properties": {
                            "version": {"type": "string", "minLength": 1},
                            "hint": {"type": "string", "minLength": 1},
                        },
                        "additionalProperties": False,
                    },
                },
                "pip_dependencies": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "null"]},
                },
                "uris": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "onboarding": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "release": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["feature", "bugfix", "hotfix", "refactor", "security", "docs"],
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["optional", "low", "normal", "recommended", "high", "critical"],
                        },
                        "summary": {"type": "string"},
                        "sha256": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        }

    def _discover_installed_modules(self) -> List[str]:
        """自 `self.yscb_dir/.modules` 與 `module://` 探索目前已安裝之模組名稱清單（按字母排序）。"""
        mods: Set[str] = set()
        local_modules_dir = os.path.join(self.yscb_dir, ".modules")
        if os.path.isdir(local_modules_dir):
            try:
                for item in os.listdir(local_modules_dir):
                    if not item.startswith(".") and os.path.isdir(os.path.join(local_modules_dir, item)):
                        mods.add(item)
            except Exception:
                pass
        try:
            if vfs.exists("module://"):
                for item in vfs.listdir("module://"):
                    if not item.startswith(".") and vfs.is_dir(f"module://{item}"):
                        mods.add(item)
        except Exception:
            pass
        return sorted(mods)

    @staticmethod
    def _select_latest_mirror_zip(mirror_dir: str) -> Optional[str]:
        """Select the latest module mirror archive in `mirror_dir` using four-segment SemVer ordering."""
        if not os.path.isdir(mirror_dir):
            return None
        zip_files = glob.glob(os.path.join(mirror_dir, "*.zip"))
        if not zip_files:
            return None

        def _is_valid_semver(s: str) -> bool:
            try:
                parse_semver(s)
                return True
            except Exception:
                return False

        def _cmp_zip_paths(p1: str, p2: str) -> int:
            s1 = os.path.splitext(os.path.basename(p1))[0]
            s2 = os.path.splitext(os.path.basename(p2))[0]
            v1_ok, v2_ok = _is_valid_semver(s1), _is_valid_semver(s2)
            if v1_ok and v2_ok:
                return compare_semver(s1, s2)
            if v1_ok != v2_ok:
                return 1 if v1_ok else -1
            return 1 if s1 > s2 else (-1 if s1 < s2 else 0)

        return sorted(zip_files, key=functools.cmp_to_key(_cmp_zip_paths))[-1]

    def _read_mirror_zip_config_bundle(
        self, latest_zip: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Single-pass reader for `.mirror/<mod>/*.zip` that extracts both `configurable/_format.json`
        and merged `configurable/config.*.json` templates while caching by `(path, mtime_ns)` in `RuntimeContext`.
        """
        if not latest_zip or not os.path.isfile(latest_zip):
            return None, None
        try:
            st_mtime_ns = int(getattr(os.stat(latest_zip), "st_mtime_ns", 0))
        except OSError:
            return None, None

        cache = self._mirror_zip_bundle_cache
        cache_key = (os.path.normcase(os.path.abspath(latest_zip)), st_mtime_ns)
        if cache_key in cache:
            return cache[cache_key]

        fmt_data: Optional[Dict[str, Any]] = None
        merged_tpl: Dict[str, Any] = {}
        found_tpl = False
        try:
            with zipfile.ZipFile(latest_zip, "r") as zf:
                for member in sorted(zf.namelist()):
                    norm_m = member.replace("\\", "/")
                    if norm_m == "configurable/_format.json":
                        try:
                            loaded_fmt = json.loads(zf.read(member).decode("utf-8"))
                            if isinstance(loaded_fmt, dict):
                                fmt_data = loaded_fmt
                        except Exception:
                            pass
                    elif norm_m.startswith("configurable/") and norm_m.endswith(".json"):
                        base_m = os.path.basename(norm_m)
                        if not base_m.startswith("_"):
                            try:
                                loaded_tpl = json.loads(zf.read(member).decode("utf-8"))
                                if isinstance(loaded_tpl, dict):
                                    merged_tpl.update(loaded_tpl)
                                    found_tpl = True
                            except Exception:
                                pass
        except Exception:
            return None, None

        res = (fmt_data, merged_tpl if found_tpl else None)
        if len(cache) >= _MAX_MIRROR_ZIP_CACHE_ENTRIES:
            cache.pop(next(iter(cache)), None)
        cache[cache_key] = res
        return res

    def _load_module_config_format(self, mod_name: str, latest_zip: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """優先自 `self.yscb_dir/.modules/<mod>/configurable/_format.json`、`module://<mod>/configurable/_format.json` 或 `module.mirror://<mod>/*.zip` 讀取組態 `_format.json` 契約。"""
        local_modules_dir = os.path.join(self.yscb_dir, ".modules")
        if os.path.isdir(local_modules_dir):
            local_fmt = os.path.join(local_modules_dir, mod_name, "configurable", "_format.json")
            if vfs.is_file(local_fmt):
                try:
                    data = vfs.read_json(local_fmt)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass

        fmt_uri = f"module://{mod_name}/configurable/_format.json"
        if vfs.exists(fmt_uri):
            try:
                data = vfs.read_json(fmt_uri)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        if latest_zip is None:
            latest_zip = self._select_latest_mirror_zip(os.path.join(self.yscb_dir, ".mirror", mod_name))
        if not latest_zip:
            return None
        fmt_data, _ = self._read_mirror_zip_config_bundle(latest_zip)
        return fmt_data

    def _load_module_config_template(self, mod_name: str, latest_zip: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """嚴守 Zero-Probing：自 `module.mirror://<mod>/*.zip` 記憶體讀取 `configurable/config.*.json` 原始組態模板並合併。"""
        if latest_zip is None:
            latest_zip = self._select_latest_mirror_zip(os.path.join(self.yscb_dir, ".mirror", mod_name))
        if not latest_zip:
            return None
        _, tpl_data = self._read_mirror_zip_config_bundle(latest_zip)
        return tpl_data

    def _write_json_zero_touch(self, file_path: str, data: Dict[str, Any]) -> bool:
        """Zero-Touch JSON 寫入：若既有檔案內容完全一致則略過寫盤，避免變更 mtime。"""
        if vfs.is_file(file_path):
            try:
                if vfs.read_json(file_path) == data:
                    return False
            except Exception:
                pass
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        vfs.write_text(file_path, json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8", atomic=True)
        return True

    def _write_and_track_schema(
        self,
        schemas_root: str,
        rel_schema_path: str,
        schema_data: Dict[str, Any],
        active_schema_files: Set[str],
        bindings: Optional[List[Dict[str, Any]]] = None,
        file_match: Optional[List[str]] = None,
    ) -> None:
        """寫入單檔 JSON Schema 並記錄至活躍清單，若提供 `file_match` 則一併附加 `json.schemas` 綁定。"""
        abs_schema_path = os.path.join(schemas_root, *rel_schema_path.split("/"))
        self._write_json_zero_touch(abs_schema_path, schema_data)
        active_schema_files.add(os.path.normcase(os.path.abspath(abs_schema_path)))
        if bindings is not None and file_match:
            bindings.append({"fileMatch": file_match, "url": f"./.vscode/schemas/{rel_schema_path}"})

    def _append_contributed_schema_bindings(self, bindings: List[Dict[str, Any]]) -> None:
        """讀取 `vscode-support.json_schemas` 擴充點（或預設保底規則）並附加至 `bindings`。"""
        contributed_rules: Dict[str, Any] = {}
        try:
            raw_rules = contributes.get("vscode-support", "json_schemas")
            if isinstance(raw_rules, dict):
                contributed_rules = raw_rules
        except Exception:
            pass

        if not contributed_rules:
            contributed_rules = {
                "format-meta": {
                    "file_match": ["**/contributes/_format.json", "**/configurable/_format.json"],
                    "schema_source": "static_file",
                    "schema_path": "meta/format-meta.schema.json",
                },
                "manifest": {
                    "file_match": [
                        "**/source/*/manifest.json",
                        "**/modules/*/manifest.json",
                        "**/.modules/*/manifest.json",
                    ],
                    "schema_source": "static_file",
                    "schema_path": "meta/manifest.schema.json",
                },
            }

        source_subdir_map = {"contributes_format": "contributes", "configurable_template": "config"}
        for rule_id in sorted(contributed_rules.keys()):
            if rule_id.startswith("__"):
                continue
            rule = contributed_rules[rule_id]
            if not isinstance(rule, dict):
                continue
            f_match = rule.get("file_match", [])
            s_source = rule.get("schema_source", "static_file")
            s_path = rule.get("schema_path", "")
            if not isinstance(f_match, list) or not f_match:
                continue
            if s_source == "static_file":
                if not s_path:
                    continue
                clean_rel = s_path.lstrip("./").replace("\\", "/")
                bindings.append({"fileMatch": list(f_match), "url": f"./.vscode/schemas/{clean_rel}"})
            elif s_source in source_subdir_map:
                subdir = source_subdir_map[s_source]
                target_mod = s_path.strip() if s_path else rule_id
                rel_url = target_mod if target_mod.endswith(".json") else f"{subdir}/{target_mod}.schema.json"
                bindings.append({"fileMatch": list(f_match), "url": f"./.vscode/schemas/{rel_url.lstrip('./')}"})

    @staticmethod
    def _cleanup_orphan_schemas(schemas_root: str, active_schema_files: Set[str]) -> None:
        """清理 `.vscode/schemas/` 下已不再使用之孤兒 `.schema.json`。"""
        for sub in ("contributes", "config", "meta"):
            sub_dir = os.path.join(schemas_root, sub)
            if os.path.isdir(sub_dir):
                for fname in os.listdir(sub_dir):
                    if fname.endswith(".json"):
                        fpath = os.path.join(sub_dir, fname)
                        if os.path.normcase(os.path.abspath(fpath)) not in active_schema_files:
                            try:
                                os.remove(fpath)
                            except OSError:
                                pass

    def sync_all_schemas(self, proj_root: str) -> List[Dict[str, Any]]:
        """
        編譯所有已安裝模組之 Contributes Schema、Config Schema 與 Meta Schema 至 `project://.vscode/schemas/`，
        清理已移除模組之孤兒 Schema 與舊版子目錄 `.gitignore`，
        並回傳應寫入 `.vscode/settings.json` `"json.schemas"` 之綁定條目清單。
        """
        with cell_span("vsc.compile_schemas"):
            self._cached_uri_snippets = None
            self._cached_uri_snippets = self._collect_uri_scheme_snippets()
            try:
                return self._sync_all_schemas_impl(proj_root)
            finally:
                self._cached_uri_snippets = None

    def _sync_all_schemas_impl(self, proj_root: str) -> List[Dict[str, Any]]:
        schemas_root = os.path.join(proj_root, ".vscode", "schemas")
        os.makedirs(schemas_root, exist_ok=True)

        gi_path = os.path.join(schemas_root, ".gitignore")
        if vfs.is_file(gi_path):
            try:
                vfs.remove(gi_path, missing_ok=True)
            except Exception:
                pass

        active_schema_files: Set[str] = set()
        bindings: List[Dict[str, Any]] = []
        installed_mods = self._discover_installed_modules()
        local_modules_dir = os.path.join(self.yscb_dir, ".modules")
        has_local_modules = os.path.isdir(local_modules_dir)

        for mod in installed_mods:
            fmt_data: Optional[Dict[str, Any]] = None
            if has_local_modules:
                local_fmt = os.path.join(local_modules_dir, mod, "contributes", "_format.json")
                if vfs.is_file(local_fmt):
                    try:
                        loaded = vfs.read_json(local_fmt)
                        if isinstance(loaded, dict):
                            fmt_data = loaded
                    except Exception:
                        pass
            if fmt_data is None:
                fmt_uri = f"module://{mod}/contributes/_format.json"
                if vfs.exists(fmt_uri):
                    try:
                        loaded = vfs.read_json(fmt_uri)
                        if isinstance(loaded, dict):
                            fmt_data = loaded
                    except Exception:
                        pass
            if isinstance(fmt_data, dict):
                try:
                    c_schema = self.compile_contributes_schema(mod, fmt_data)
                    self._write_and_track_schema(
                        schemas_root,
                        f"contributes/{mod}.schema.json",
                        c_schema,
                        active_schema_files,
                        bindings=bindings,
                        file_match=[f"**/contributes/{mod}.json", f"**/config/{mod}/contribute.json"],
                    )
                except Exception:
                    pass

        for mod in installed_mods:
            latest_zip = self._select_latest_mirror_zip(os.path.join(self.yscb_dir, ".mirror", mod)) or ""
            cfg_fmt = self._load_module_config_format(mod, latest_zip=latest_zip)
            tpl_data = self._load_module_config_template(mod, latest_zip=latest_zip)
            if cfg_fmt is not None or tpl_data is not None:
                cfg_schema = self.compile_config_schema(mod, template_data=tpl_data, fmt_data=cfg_fmt)
                self._write_and_track_schema(
                    schemas_root,
                    f"config/{mod}.schema.json",
                    cfg_schema,
                    active_schema_files,
                    bindings=bindings,
                    file_match=[
                        f"**/config/{mod}/config.*.json",
                        f"**/.config.local/{mod}/config.*.json",
                        f"**/source/{mod}/configurable/config.*.json",
                        f"**/{mod}/configurable/config.*.json",
                    ],
                )

        self._write_and_track_schema(
            schemas_root, "meta/format-meta.schema.json", self.build_format_meta_schema(), active_schema_files
        )
        self._write_and_track_schema(
            schemas_root, "meta/manifest.schema.json", self.build_manifest_meta_schema(), active_schema_files
        )
        self._append_contributed_schema_bindings(bindings)
        self._cleanup_orphan_schemas(schemas_root, active_schema_files)
        return bindings
