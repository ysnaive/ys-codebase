"""Multi-source package provider client supporting local paths, HTTP(S), @build, and exact-version source packaging."""

from __future__ import annotations

import fnmatch
from http.client import HTTPConnection, HTTPException, HTTPMessage, HTTPSConnection
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import threading
import time
from typing import IO, ClassVar, Final, Mapping, NoReturn, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
import urllib.request
import uuid
import weakref
import zipfile

from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    assert_no_symlink_raw_path,
    has_symlink_raw_path,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    try_resolve_contained_subpath,
)
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.observability import clamp_positive_sec
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    JsonObject,
    ModuleId,
    MutableJsonObject,
    SemVer4,
    is_valid_relative_segment,
    require_pure_bool,
    require_pure_str,
    safe_realpath,
    strict_parse_json_object,
)
from core.foundation.proc import is_public_env_truthy
from core.packaging.installer.models import (
    INS_MAX_ZIP_ARCHIVE_BYTES,
    IndexReleaseRecord,
    RemoteModuleIndex,
    ins_assert_not_reserved_module_id,
    ins_parse_manifest_dict,
    ins_parse_remote_index,
    ins_open_verified_zip_stream,
    ins_peek_zip_manifest,
    ins_verify_zip_archive,
)

_PACKAGE_IGNORE_PATTERNS: Final[tuple[str, ...]] = (
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.tmp",
    "*.bak",
    ".tmp_*",
    ".staging_*",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".DS_Store",
)
_TEXT_NORMALIZE_EXTS: Final[frozenset[str]] = frozenset(
    {".py", ".json", ".tmpl", ".md", ".txt", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh"}
)
_TEXT_NORMALIZE_NAMES: Final[frozenset[str]] = frozenset({".yscbignore", ".gitignore"})
_DETERMINISTIC_ZIP_DATE: Final[tuple[int, int, int, int, int, int]] = (2020, 1, 1, 0, 0, 0)
_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost", "::1"})
_NOFOLLOW_READ_FLAGS: Final[int] = (
    os.O_RDONLY
    | (os.O_BINARY if IS_WINDOWS else 0)
    | (0 if IS_WINDOWS else os.O_NOFOLLOW | os.O_NONBLOCK)
)
_NOFOLLOW_EXCL_WRITE_FLAGS: Final[int] = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | (os.O_BINARY if IS_WINDOWS else 0)
    | (0 if IS_WINDOWS else os.O_NOFOLLOW)
)


_MAX_HTTP_REDIRECTS: Final[int] = 5


def ins_is_http_provider(raw_provider: str) -> bool:
    """Return True when raw_provider uses an http:// or https:// scheme."""
    lowered = raw_provider.strip().lower()
    return lowered.startswith(("http://", "https://"))


def _classify_ip_tier(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    if isinstance(ip_obj, ipaddress.IPv6Address):
        if ip_obj.ipv4_mapped is not None:
            return _classify_ip_tier(ip_obj.ipv4_mapped)
        if ip_obj.sixtofour is not None:
            return _classify_ip_tier(ip_obj.sixtofour)
        if ip_obj.teredo is not None:
            srv_tier = _classify_ip_tier(ip_obj.teredo[0])
            cli_tier = _classify_ip_tier(ip_obj.teredo[1])
            if "forbidden" in (srv_tier, cli_tier) or {srv_tier, cli_tier} == {"loopback", "private_lan"}:
                return "forbidden"
            if "loopback" in (srv_tier, cli_tier):
                return "loopback"
            if "private_lan" in (srv_tier, cli_tier):
                return "private_lan"
            return "public"
    if ip_obj.is_link_local or ip_obj.is_unspecified or ip_obj.is_multicast:
        return "forbidden"
    if ip_obj.is_loopback:
        return "loopback"
    if ip_obj.is_reserved:
        return "forbidden"
    if ip_obj.is_global:
        return "public"
    return "private_lan"


def _allowed_dest_tiers_for_origin(origin_tier: str) -> frozenset[str]:
    if origin_tier == "loopback":
        return frozenset({"loopback", "public"})
    if origin_tier == "private_lan":
        return frozenset({"private_lan", "public"})
    if origin_tier == "public":
        return frozenset({"public"})
    return frozenset()


def _is_loopback_http_host(raw_host: str) -> bool:
    clean = raw_host.strip().lower().strip("[]")
    if not clean:
        return False
    if clean == "localhost" or clean.endswith(".localhost"):
        return True
    try:
        ip_obj = ipaddress.ip_address(clean.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        return False
    return ip_obj.is_loopback


def _classify_host_origin_tier(hostname: str) -> str:
    clean = hostname.strip().lower().strip("[]")
    if not clean:
        return "forbidden"
    if clean in _LOOPBACK_HOSTS or clean.endswith(".localhost"):
        return "loopback"
    try:
        ip_lit = ipaddress.ip_address(clean.split("%", 1)[0])
        if isinstance(ip_lit, ipaddress.IPv6Address) and ip_lit.ipv4_mapped is not None:
            mapped_tier = _classify_ip_tier(ip_lit.ipv4_mapped)
            return "forbidden" if mapped_tier == "loopback" else mapped_tier
        return _classify_ip_tier(ip_lit)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(clean, None, type=socket.SOCK_STREAM)
    except OSError:
        return "public"
    if not infos:
        return "public"
    tiers: set[str] = set()
    for info in infos:
        addr_raw = info[4][0]
        if not isinstance(addr_raw, str):
            return "forbidden"
        try:
            tiers.add(_classify_ip_tier(ipaddress.ip_address(addr_raw.split("%", 1)[0])))
        except ValueError:
            return "forbidden"
    if "forbidden" in tiers or "loopback" in tiers or len(tiers) > 1:
        return "forbidden"
    if "private_lan" in tiers:
        return "private_lan"
    return "public"


def _reject_ssrf_connection(message: str, *, raise_security_error: bool) -> NoReturn:
    if raise_security_error:
        raise YscbError(ErrorCode.SECURITY_GATED, message)
    raise URLError(message)


def _open_verified_provider_socket(
    host: str,
    port: int,
    timeout: Optional[float],
    source_address: Optional[tuple[str, int]],
    allowed_tiers: frozenset[str],
    *,
    raise_security_error: bool,
) -> tuple[socket.socket, str]:
    clean = host.strip().lower().strip("[]")
    if not clean:
        _reject_ssrf_connection("Empty target host in HTTP(S) connection.", raise_security_error=raise_security_error)
    infos = socket.getaddrinfo(clean, port, 0, socket.SOCK_STREAM)
    if not infos:
        raise OSError(f"Unable to resolve host '{host}'.")
    verified: list[tuple[int, int, int, tuple[object, ...], str]] = []
    for af, socktype, proto, _canon, sa in infos:
        addr_raw = sa[0]
        if not isinstance(addr_raw, str):
            _reject_ssrf_connection(
                f"Unsupported socket address for host '{host}'.",
                raise_security_error=raise_security_error,
            )
        try:
            ip_obj = ipaddress.ip_address(addr_raw.split("%", 1)[0])
        except ValueError:
            _reject_ssrf_connection(
                f"Invalid resolved IP '{addr_raw}' for host '{host}'.",
                raise_security_error=raise_security_error,
            )
        tier = _classify_ip_tier(ip_obj)
        if tier not in allowed_tiers:
            _reject_ssrf_connection(
                f"Refusing connection to '{host}' ({addr_raw}, tier={tier}); allowed={sorted(allowed_tiers)}.",
                raise_security_error=raise_security_error,
            )
        verified.append((af, socktype, proto, sa, tier))
    last_err: Optional[OSError] = None
    for af, socktype, proto, sa, conn_tier in verified:
        sock: Optional[socket.socket] = None
        try:
            sock = socket.socket(af, socktype, proto)
            if timeout is not None:
                sock.settimeout(timeout)
            if source_address is not None:
                sock.bind(source_address)
            sock.connect(sa)
            return (sock, conn_tier)
        except OSError as exc:
            last_err = exc
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    if last_err is not None:
        raise last_err
    raise OSError(f"Failed to connect to '{host}:{port}'.")


def _split_http_authority_host_port(authority: str, *, default_port: int) -> tuple[str, int]:
    parsed = urlparse(f"http://{authority}")
    host_val = parsed.hostname or authority
    port_val = parsed.port if parsed.port is not None else default_port
    return (host_val, port_val)


class _ProviderHttpTierBudget:
    __slots__ = ("_allowed_tiers",)

    def __init__(self, initial_tiers: frozenset[str]) -> None:
        self._allowed_tiers = initial_tiers

    @property
    def allowed_tiers(self) -> frozenset[str]:
        return self._allowed_tiers

    def narrow(self, next_tiers: frozenset[str]) -> None:
        self._allowed_tiers = self._allowed_tiers & next_tiers


class _PinnedProviderHttpConnection(HTTPConnection):
    def __init__(
        self,
        host: str,
        *,
        tier_budget: _ProviderHttpTierBudget,
        raise_security_error: bool,
        timeout: Optional[float] = None,
        source_address: Optional[tuple[str, int]] = None,
        blocksize: int = 8192,
    ) -> None:
        if timeout is None:
            super().__init__(host, source_address=source_address, blocksize=blocksize)
        else:
            super().__init__(host, timeout=timeout, source_address=source_address, blocksize=blocksize)
        self._target_host, self._target_port = _split_http_authority_host_port(host, default_port=80)
        self._conn_timeout = timeout
        self._conn_source_address = source_address
        self._tier_budget = tier_budget
        self._raise_security_error = raise_security_error
        self._pinned_tunnel_host: Optional[str] = None

    def set_tunnel(
        self,
        host: str,
        port: Optional[int] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._pinned_tunnel_host = host
        super().set_tunnel(host, port=port, headers=headers)

    def connect(self) -> None:
        if self._pinned_tunnel_host is not None:
            _reject_ssrf_connection(
                "HTTP CONNECT proxy tunneling is forbidden for package provider connections.",
                raise_security_error=self._raise_security_error,
            )
        eff_tmo = self._conn_timeout if isinstance(self._conn_timeout, (int, float)) else None
        sock, conn_tier = _open_verified_provider_socket(
            self._target_host,
            self._target_port,
            eff_tmo,
            self._conn_source_address,
            self._tier_budget.allowed_tiers & frozenset({"loopback"}),
            raise_security_error=self._raise_security_error,
        )
        self._tier_budget.narrow(_allowed_dest_tiers_for_origin(conn_tier))
        self.sock = sock


class _PinnedProviderHttpsConnection(HTTPSConnection):
    def __init__(
        self,
        host: str,
        *,
        tier_budget: _ProviderHttpTierBudget,
        raise_security_error: bool,
        timeout: Optional[float] = None,
        source_address: Optional[tuple[str, int]] = None,
        context: Optional[ssl.SSLContext] = None,
        blocksize: int = 8192,
    ) -> None:
        eff_ctx = context if context is not None else ssl.create_default_context()
        if timeout is None:
            super().__init__(host, source_address=source_address, context=eff_ctx, blocksize=blocksize)
        else:
            super().__init__(
                host,
                timeout=timeout,
                source_address=source_address,
                context=eff_ctx,
                blocksize=blocksize,
            )
        self._target_host, self._target_port = _split_http_authority_host_port(host, default_port=443)
        self._conn_timeout = timeout
        self._conn_source_address = source_address
        self._tier_budget = tier_budget
        self._raise_security_error = raise_security_error
        self._ssl_ctx = eff_ctx
        self._pinned_tunnel_host: Optional[str] = None

    def set_tunnel(
        self,
        host: str,
        port: Optional[int] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._pinned_tunnel_host = host
        super().set_tunnel(host, port=port, headers=headers)

    def connect(self) -> None:
        if self._pinned_tunnel_host is not None:
            _reject_ssrf_connection(
                "HTTP CONNECT proxy tunneling is forbidden for package provider connections.",
                raise_security_error=self._raise_security_error,
            )
        eff_tmo = self._conn_timeout if isinstance(self._conn_timeout, (int, float)) else None
        raw_sock, conn_tier = _open_verified_provider_socket(
            self._target_host,
            self._target_port,
            eff_tmo,
            self._conn_source_address,
            self._tier_budget.allowed_tiers,
            raise_security_error=self._raise_security_error,
        )
        self._tier_budget.narrow(_allowed_dest_tiers_for_origin(conn_tier))
        try:
            sni_host = self._target_host.strip("[]")
            self.sock = self._ssl_ctx.wrap_socket(raw_sock, server_hostname=sni_host)
        except BaseException:
            try:
                raw_sock.close()
            except OSError:
                pass
            raise


class _PinnedProviderHttpHandler(urllib.request.HTTPHandler):
    def __init__(self, *, tier_budget: _ProviderHttpTierBudget, raise_security_error: bool) -> None:
        super().__init__()
        self._tier_budget = tier_budget
        self._raise_security_error = raise_security_error

    def _make_conn(
        self,
        host: str,
        timeout: Optional[float] = None,
        source_address: Optional[tuple[str, int]] = None,
        blocksize: int = 8192,
    ) -> HTTPConnection:
        return _PinnedProviderHttpConnection(
            host,
            tier_budget=self._tier_budget,
            raise_security_error=self._raise_security_error,
            timeout=timeout,
            source_address=source_address,
            blocksize=blocksize,
        )

    def http_open(self, req: urllib.request.Request) -> object:
        return self.do_open(self._make_conn, req)


class _PinnedProviderHttpsHandler(urllib.request.HTTPSHandler):
    def __init__(self, *, tier_budget: _ProviderHttpTierBudget, raise_security_error: bool) -> None:
        super().__init__()
        self._tier_budget = tier_budget
        self._raise_security_error = raise_security_error

    def _make_conn(
        self,
        host: str,
        timeout: Optional[float] = None,
        source_address: Optional[tuple[str, int]] = None,
        context: Optional[ssl.SSLContext] = None,
        blocksize: int = 8192,
    ) -> HTTPSConnection:
        return _PinnedProviderHttpsConnection(
            host,
            tier_budget=self._tier_budget,
            raise_security_error=self._raise_security_error,
            timeout=timeout,
            source_address=source_address,
            context=context,
            blocksize=blocksize,
        )

    def https_open(self, req: urllib.request.Request) -> object:
        return self.do_open(self._make_conn, req)


class _SafeHttpRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, *, tier_budget: _ProviderHttpTierBudget, raise_security_error: bool) -> None:
        super().__init__()
        self._tier_budget = tier_budget
        self._raise_security_error = raise_security_error
        self._redirect_count = 0

    def _reject_redirect(self, message: str, fp: Optional[IO[bytes]] = None) -> NoReturn:
        if fp is not None:
            try:
                fp.close()
            except OSError:
                pass
        _reject_ssrf_connection(message, raise_security_error=self._raise_security_error)

    def _precheck_redirect_headers(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        headers: HTTPMessage,
    ) -> None:
        raw_loc = headers.get("location")
        if raw_loc is None:
            raw_loc = headers.get("uri")
        if raw_loc is None:
            return
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_loc):
            self._reject_redirect("Control characters forbidden in HTTP redirect Location header.", fp=fp)
        target_raw = raw_loc.strip()
        try:
            raw_parsed = urlparse(target_raw)
            _ = raw_parsed.port
            joined_url = urljoin(req.full_url, target_raw)
            dst_parsed = urlparse(joined_url)
            _ = dst_parsed.port
        except ValueError as exc:
            self._reject_redirect(f"Malformed redirect target URL '{target_raw}': {exc}", fp=fp)
        if raw_parsed.scheme and raw_parsed.scheme.lower() not in ("http", "https"):
            self._reject_redirect(f"Unsupported HTTP redirect scheme in '{target_raw}'.", fp=fp)
        dst_scheme = dst_parsed.scheme.lower()
        dst_host = (dst_parsed.hostname or "").lower()
        if dst_scheme not in ("http", "https") or not dst_host:
            self._reject_redirect(f"Unsupported HTTP redirect scheme or host in '{joined_url}'.", fp=fp)

    def http_error_301(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
    ) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_301(req, fp, code, msg, headers)

    def http_error_302(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
    ) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_302(req, fp, code, msg, headers)

    def http_error_303(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
    ) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_303(req, fp, code, msg, headers)

    def http_error_307(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
    ) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_307(req, fp, code, msg, headers)

    def http_error_308(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
    ) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_308(req, fp, code, msg, headers)

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Optional[urllib.request.Request]:
        self._redirect_count += 1
        if self._redirect_count > _MAX_HTTP_REDIRECTS:
            self._reject_redirect(
                f"Exceeded maximum HTTP redirects ({_MAX_HTTP_REDIRECTS}) at '{newurl}'.",
                fp=fp,
            )
        try:
            src_parsed = urlparse(req.full_url)
            dst_parsed = urlparse(newurl)
            _ = dst_parsed.port
        except ValueError as exc:
            self._reject_redirect(f"Malformed redirect target URL '{newurl}': {exc}", fp=fp)
        src_scheme = src_parsed.scheme.lower()
        dst_scheme = dst_parsed.scheme.lower()
        dst_host = (dst_parsed.hostname or "").lower()
        if dst_scheme not in ("http", "https") or not dst_host:
            self._reject_redirect(f"Unsupported HTTP redirect scheme or host in '{newurl}'.", fp=fp)
        if src_scheme == "https" and dst_scheme != "https":
            self._reject_redirect(f"Refusing HTTPS-to-HTTP protocol downgrade redirect to '{newurl}'.", fp=fp)
        if dst_scheme == "http" and not _is_loopback_http_host(dst_host):
            self._reject_redirect(f"Refusing plaintext HTTP redirect to non-loopback host '{dst_host}'.", fp=fp)
        dst_tier = _classify_host_origin_tier(dst_host)
        if dst_tier not in self._tier_budget.allowed_tiers:
            self._reject_redirect(
                f"Refusing redirect to disallowed host '{dst_host}' (tier={dst_tier}).",
                fp=fp,
            )
        self._tier_budget.narrow(_allowed_dest_tiers_for_origin(dst_tier))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ins_build_safe_http_opener(
    initial_url: str,
    *,
    raise_security_error: bool,
) -> urllib.request.OpenerDirector:
    """Build a urllib OpenerDirector enforcing HTTPS no-downgrade, 4-tier origin SSRF, and DNS-rebinding guards."""
    parsed = urlparse(initial_url)
    _ = parsed.port
    scheme = (parsed.scheme or "").lower()
    host_only = (parsed.hostname or "").lower()
    if scheme == "http" and not _is_loopback_http_host(host_only):
        _reject_ssrf_connection(
            f"Refusing insecure non-HTTPS remote URL: '{initial_url}'.",
            raise_security_error=raise_security_error,
        )
    origin_tier = _classify_host_origin_tier(host_only)
    allowed_tiers = _allowed_dest_tiers_for_origin(origin_tier)
    if not allowed_tiers:
        _reject_ssrf_connection(
            f"Refusing connection to forbidden host '{host_only}'.",
            raise_security_error=raise_security_error,
        )
    budget = _ProviderHttpTierBudget(allowed_tiers)
    http_h = _PinnedProviderHttpHandler(
        tier_budget=budget,
        raise_security_error=raise_security_error,
    )
    https_h = _PinnedProviderHttpsHandler(
        tier_budget=budget,
        raise_security_error=raise_security_error,
    )
    redirect_handler = _SafeHttpRedirectHandler(
        tier_budget=budget,
        raise_security_error=raise_security_error,
    )
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), http_h, https_h, redirect_handler)


_WIN_FILE_URI_LOCAL_PATH_RE: Final[re.Pattern[str]] = re.compile(r"^/[A-Za-z]:/")


def _validate_windows_file_uri_path(raw_path: str, *, raw_uri: str, is_unc: bool) -> None:
    decoded = unquote(raw_path)
    if "\x00" in decoded or "|" in decoded:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid Windows file:// URI path: {raw_uri!r}")
    if is_unc:
        if not decoded.startswith("/") or ":" in decoded:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid Windows UNC file:// URI path: {raw_uri!r}")
        return
    if _WIN_FILE_URI_LOCAL_PATH_RE.match(decoded) is None or ":" in decoded[3:]:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid Windows drive file:// URI path: {raw_uri!r}")


def ins_resolve_file_uri_to_host_path(raw_uri: str) -> HostPath:
    """Parse and validate a file:// URI into a symlink-free HostPath with POSIX/Windows UNC parity."""
    cleaned = raw_uri.strip()
    try:
        parsed = urlparse(cleaned)
        port_val = parsed.port
    except ValueError as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Malformed file:// URI {raw_uri!r}: {exc}") from exc
    if (
        parsed.scheme.lower() != "file"
        or port_val is not None
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid file:// URI syntax: {raw_uri!r}")
    raw_netloc = parsed.netloc
    host_clean = (parsed.hostname or "").lower()
    if not raw_netloc or host_clean in _LOOPBACK_HOSTS:
        if not parsed.path:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Empty path in file:// URI: {raw_uri!r}")
        if IS_WINDOWS:
            _validate_windows_file_uri_path(parsed.path, raw_uri=raw_uri, is_unc=False)
        try:
            local_raw = urllib.request.url2pathname(parsed.path)
        except (OSError, ValueError) as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid file:// path {raw_uri!r}: {exc}") from exc
        while not IS_WINDOWS and local_raw.startswith("//"):
            local_raw = local_raw[1:]
    else:
        if not IS_WINDOWS:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Non-local file:// authority {raw_netloc!r} is unsupported on POSIX.",
            )
        if ":" in raw_netloc or not is_valid_relative_segment(raw_netloc):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Invalid Windows UNC host in file:// URI: {raw_uri!r}",
            )
        _validate_windows_file_uri_path(parsed.path, raw_uri=raw_uri, is_unc=True)
        try:
            local_raw = urllib.request.url2pathname(f"//{raw_netloc}{parsed.path}")
        except (OSError, ValueError) as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid Windows UNC file:// URI {raw_uri!r}: {exc}") from exc
    cand_p = Path(local_raw)
    if not cand_p.is_absolute():
        raise YscbError(ErrorCode.CONFIG_INVALID, f"file:// URI must resolve to an absolute path: {raw_uri!r}")
    anchor_str = cand_p.anchor
    tail_str = local_raw[len(anchor_str) :]
    has_trail = local_raw.endswith(("/", "\\")) if IS_WINDOWS else local_raw.endswith("/")
    _validate_provider_tail_syntax(tail_str, raw_label=raw_uri)
    try:
        resolved = HostPath(local_raw)
    except ValueError as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid file:// provider path {raw_uri!r}: {exc}") from exc
    walked_cur = _walk_provider_nonsymlink_segments(
        anchor_str,
        tail_str,
        raw_label=raw_uri,
        has_trailing_sep=has_trail,
    )
    _verify_walked_provider_matches_resolved(walked_cur, resolved, raw_label=raw_uri)
    return resolved


def _split_provider_segments(raw_tail: str) -> tuple[str, ...]:
    sep_pattern = r"[\\/]+" if IS_WINDOWS else r"/+"
    return tuple(seg for seg in re.split(sep_pattern, raw_tail) if seg)


def _validate_provider_tail_syntax(raw_tail: str, *, raw_label: str) -> None:
    if "\x00" in raw_tail or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_tail):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Control characters forbidden in provider path {raw_label!r}.")
    for seg in _split_provider_segments(raw_tail):
        if seg not in (".", "..") and not is_valid_relative_segment(seg):
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid path segment {seg!r} in provider {raw_label!r}.")


def _canonicalize_checked_nonsymlink_step(raw_step: str) -> str:
    assert_no_symlink_raw_path(raw_step)
    if os.path.lexists(raw_step):
        return safe_realpath(raw_step)
    return raw_step


def _verify_walked_provider_matches_resolved(
    walked_cur: str,
    resolved: HostPath,
    *,
    raw_label: str,
) -> None:
    assert_no_symlink_raw_path(str(resolved))
    try:
        walked_hp = HostPath(walked_cur)
    except ValueError as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid resolved provider path {raw_label!r}: {exc}") from exc
    if walked_hp != resolved:
        raise YscbError(
            ErrorCode.SECURITY_GATED,
            f"Provider path {raw_label!r} diverged from symlink-free segment traversal.",
        )


def _walk_provider_nonsymlink_segments(
    start_dir: str,
    raw_tail: str,
    *,
    raw_label: str,
    has_trailing_sep: bool,
) -> str:
    cur = _canonicalize_checked_nonsymlink_step(start_dir)
    for seg in _split_provider_segments(raw_tail):
        if seg == ".":
            cur = _canonicalize_checked_nonsymlink_step(cur)
            if os.path.lexists(cur) and not os.path.isdir(cur):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Refusing non-directory traversal segment in provider path {raw_label!r}.",
                )
        elif seg == "..":
            cur = _canonicalize_checked_nonsymlink_step(cur)
            if os.path.lexists(cur) and not os.path.isdir(cur):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Refusing parent traversal across non-directory '{cur}' in provider path {raw_label!r}.",
                )
            cur = _canonicalize_checked_nonsymlink_step(os.path.dirname(cur))
        else:
            if os.path.lexists(cur) and not os.path.isdir(cur):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Refusing child traversal across non-directory '{cur}' in provider path {raw_label!r}.",
                )
            cur = _canonicalize_checked_nonsymlink_step(os.path.join(cur, seg))
    if has_trailing_sep and os.path.lexists(cur) and not os.path.isdir(cur):
        raise YscbError(
            ErrorCode.SECURITY_GATED,
            f"Trailing slash on non-directory provider path {raw_label!r}.",
        )
    return cur


def _resolve_local_provider_dir(yscb_root: HostPath, raw_provider: str) -> HostPath:
    cleaned = raw_provider.strip()
    if not cleaned:
        raise YscbError(ErrorCode.CONFIG_INVALID, "Provider path or URL cannot be empty.")
    if cleaned.lower().startswith("file://"):
        return ins_resolve_file_uri_to_host_path(cleaned)
    if "://" in cleaned:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Unsupported provider URI scheme: {raw_provider!r}")
    cand_p = Path(cleaned)
    if not cand_p.is_absolute() and bool(cand_p.drive or cand_p.anchor):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Drive- or root-relative provider path is unsupported: {raw_provider!r}")
    tail_str = cleaned[len(cand_p.anchor) :] if cand_p.is_absolute() else cleaned
    has_trail = cleaned.endswith(("/", "\\")) if IS_WINDOWS else cleaned.endswith("/")
    _validate_provider_tail_syntax(tail_str, raw_label=raw_provider)
    try:
        resolved = yscb_root.resolve_caller_relative(cleaned)
    except ValueError as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid local provider path {raw_provider!r}: {exc}") from exc
    start_anchor = cand_p.anchor if cand_p.is_absolute() else str(yscb_root)
    walked_cur = _walk_provider_nonsymlink_segments(
        start_anchor,
        tail_str,
        raw_label=raw_provider,
        has_trailing_sep=has_trail,
    )
    _verify_walked_provider_matches_resolved(walked_cur, resolved, raw_label=raw_provider)
    return resolved


def _candidate_local_module_dirs(prov_dir: HostPath, module_id: ModuleId) -> tuple[HostPath, ...]:
    out: list[HostPath] = []
    direct = try_resolve_contained_subpath(prov_dir, module_id.value)
    if direct is not None:
        out.append(direct)
    nested_rel = try_resolve_contained_subpath(prov_dir, "release", module_id.value)
    if nested_rel is not None and nested_rel not in out:
        out.append(nested_rel)
    if prov_dir.path.name == module_id.value and prov_dir not in out:
        out.append(prov_dir)
    return tuple(out)


def _candidate_local_source_roots(
    yscb_root: HostPath,
    prov_dir: HostPath,
    module_id: ModuleId,
    host_dir: Optional[HostPath] = None,
) -> tuple[HostPath, ...]:
    roots: list[HostPath] = [yscb_root]
    if host_dir is not None and host_dir not in roots:
        roots.append(host_dir)
    if prov_dir not in roots:
        roots.append(prov_dir)
    cand_parent = None
    if prov_dir.path.name == "release":
        cand_parent = prov_dir.path.parent
    elif prov_dir.path.name == module_id.value and prov_dir.path.parent.name == "release":
        cand_parent = prov_dir.path.parent.parent
    if cand_parent is not None and cand_parent != cand_parent.parent:
        raw_cand = str(cand_parent)
        if not is_symlink_or_reparse(raw_cand) and not has_symlink_raw_path(raw_cand):
            try:
                hp = HostPath(raw_cand)
                if hp not in roots:
                    roots.append(hp)
            except ValueError:
                pass
    return tuple(roots)


def _should_ignore_source_rel(rel_posix: str, patterns: tuple[str, ...]) -> bool:
    norm_rel = rel_posix.strip("/")
    parts = [seg for seg in norm_rel.split("/") if seg]
    if ".git" in parts:
        return True
    base_name = parts[-1] if parts else ""
    for raw_pat in patterns:
        pat = raw_pat.replace("\\", "/").strip("/")
        if not pat:
            continue
        has_glob = any(ch in pat for ch in ("*", "?", "["))
        if "/" not in pat and any(fnmatch.fnmatch(seg, pat) for seg in parts):
            return True
        if (
            fnmatch.fnmatch(base_name, pat)
            or fnmatch.fnmatch(norm_rel, pat)
            or fnmatch.fnmatch(norm_rel, f"{pat}/*")
            or (not has_glob and norm_rel.startswith(f"{pat}/"))
            or (pat.endswith("/*") and norm_rel.startswith(f"{pat[:-2]}/"))
        ):
            return True
    return False


def _load_yscbignore_patterns(source_dir: HostPath) -> tuple[str, ...]:
    extra: list[str] = list(_PACKAGE_IGNORE_PATTERNS)
    ignore_hp = try_resolve_contained_subpath(source_dir, ".yscbignore")
    if ignore_hp is not None:
        try:
            raw_bytes = read_nofollow_regular_bytes(str(ignore_hp), max_bytes=262144)
        except FileNotFoundError:
            raw_bytes = None
        except OSError as exc:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Failed reading .yscbignore in '{source_dir}': {safe_exception_summary(exc)}",
            ) from exc
        else:
            if raw_bytes is None and os.path.lexists(str(ignore_hp)):
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Refusing symlink or oversized .yscbignore in '{source_dir}'.",
                )
        if raw_bytes is not None:
            for line in raw_bytes.decode("utf-8", errors="replace").splitlines():
                cleaned = line.strip()
                if cleaned and not cleaned.startswith("#"):
                    extra.append(cleaned)
    return tuple(extra)


def _collect_source_files(source_dir: HostPath, ignore_patterns: tuple[str, ...]) -> list[tuple[str, HostPath]]:
    collected: list[tuple[str, HostPath]] = []
    stack: list[tuple[str, HostPath]] = [("", source_dir)]
    while stack:
        rel_prefix, cur_hp = stack.pop()
        raw_cur = str(cur_hp)
        if is_symlink_or_reparse(raw_cur) or has_symlink_raw_path(raw_cur):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Refusing symlink directory inside module source '{source_dir}': '{cur_hp}'.",
            )
        try:
            with os.scandir(raw_cur) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Failed scanning module source '{cur_hp}': {safe_exception_summary(exc)}",
            ) from exc
        child_dirs: list[tuple[str, HostPath]] = []
        for entry in entries:
            if not is_valid_relative_segment(entry.name):
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Invalid filename {entry.name!r} inside module source '{cur_hp}'.",
                )
            rel_item = f"{rel_prefix}/{entry.name}" if rel_prefix else entry.name
            if _should_ignore_source_rel(rel_item, ignore_patterns):
                continue
            if entry.is_symlink() or is_symlink_or_reparse(entry.path):
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Symbolic link '{entry.path}' forbidden inside module source '{source_dir}'.",
                )
            child_hp = resolve_contained_subpath(cur_hp, entry.name)
            if entry.is_dir(follow_symlinks=False):
                child_dirs.append((rel_item, child_hp))
            elif entry.is_file(follow_symlinks=False):
                collected.append((rel_item, child_hp))
        for item in reversed(child_dirs):
            stack.append(item)
    collected.sort(key=lambda pair: pair[0])
    return collected


def _read_normalized_source_file(file_hp: HostPath, rel_posix: str, max_bytes: int) -> bytes:
    try:
        raw = read_nofollow_regular_bytes(str(file_hp), max_bytes=max_bytes)
    except OSError as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Failed reading source file '{file_hp}': {safe_exception_summary(exc)}",
        ) from exc
    if raw is None:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Source file '{file_hp}' unreadable, symlinked, or exceeds package size limit.",
        )
    base_name = rel_posix.rsplit("/", 1)[-1]
    dot_idx = base_name.rfind(".")
    ext = base_name[dot_idx:].lower() if dot_idx >= 0 else ""
    if ext in _TEXT_NORMALIZE_EXTS or base_name in _TEXT_NORMALIZE_NAMES:
        try:
            text = raw.decode("utf-8")
            return text.replace("\r\n", "\n").encode("utf-8")
        except UnicodeDecodeError:
            return raw
    return raw


def _write_exclusive_temp_bytes(tmp_raw: str, payload: bytes) -> None:
    try:
        fd = os.open(tmp_raw, _NOFOLLOW_EXCL_WRITE_FLAGS, 0o644)
    except OSError as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Failed creating temporary archive '{tmp_raw}': {safe_exception_summary(exc)}",
        ) from exc
    try:
        out_f = os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        raise
    with out_f:
        out_f.write(payload)
        out_f.flush()


def _package_source_dir_to_temp_zip(
    source_dir: HostPath,
    module_id: ModuleId,
    target_version: SemVer4,
    tmp_zip_raw: str,
    max_total_bytes: int,
) -> bool:
    raw_src = str(source_dir)
    if not os.path.isdir(raw_src) or is_symlink_or_reparse(raw_src) or has_symlink_raw_path(raw_src):
        return False
    mf_hp = try_resolve_contained_subpath(source_dir, "manifest.json")
    if mf_hp is None:
        return False
    try:
        mf_bytes = read_nofollow_regular_bytes(str(mf_hp), max_bytes=MAX_JSON_FILE_BYTES)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Failed reading manifest.json in '{source_dir}': {safe_exception_summary(exc)}",
        ) from exc
    if mf_bytes is None:
        if os.path.lexists(str(mf_hp)):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Refusing symlink or oversized manifest.json in '{source_dir}'.",
            )
        return False
    try:
        mf_doc = strict_parse_json_object(mf_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Malformed manifest.json in '{source_dir}': {safe_exception_summary(exc)}",
        ) from exc
    mf = ins_parse_manifest_dict(mf_doc, expected_module_id=module_id)

    if target_version.is_build:
        if target_version.triple() != (0, 0, 0) and mf.version.triple() != target_version.triple():
            return False
        effective_ver = (
            SemVer4(mf.version.major, mf.version.minor, mf.version.patch, 0, is_build=True)
            if target_version.triple() == (0, 0, 0)
            else target_version
        )
    else:
        if mf.version != target_version or mf.version.is_build:
            return False
        effective_ver = target_version

    ignores = _load_yscbignore_patterns(source_dir)
    files = _collect_source_files(source_dir, ignores)
    total_bytes = 0
    fd = os.open(tmp_zip_raw, _NOFOLLOW_EXCL_WRITE_FLAGS, 0o644)
    try:
        raw_out = os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        raise
    with raw_out, zipfile.ZipFile(raw_out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_posix, f_hp in files:
            zi = zipfile.ZipInfo(filename=rel_posix, date_time=_DETERMINISTIC_ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o644 & 0xFFFF) << 16
            if rel_posix == "manifest.json":
                patched_mf: MutableJsonObject = dict(mf_doc)
                patched_mf["schema_version"] = 2
                patched_mf["version"] = str(effective_ver)
                payload = (json.dumps(patched_mf, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            else:
                payload = _read_normalized_source_file(f_hp, rel_posix, max_total_bytes)
            total_bytes += len(payload)
            if total_bytes > max_total_bytes:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Packaged module '{module_id}' exceeds {max_total_bytes} bytes limit.",
                )
            zf.writestr(zi, payload, compress_type=zipfile.ZIP_DEFLATED)
    return True


def _replace_temp_onto_dest(tmp_raw: str, dest_zip: HostPath) -> None:
    dst_raw = str(dest_zip)
    assert_no_symlink_raw_path(dst_raw)
    last_exc: Optional[OSError] = None
    for attempt in range(5):
        assert_no_symlink_raw_path(dst_raw)
        if os.path.lexists(dst_raw) and not is_symlink_or_reparse(dst_raw):
            try:
                os.chmod(dst_raw, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
        try:
            os.replace(tmp_raw, dst_raw)
            return
        except OSError as exc:
            last_exc = exc
            if attempt < 4:
                time.sleep(0.015 * (attempt + 1))
    raise YscbError(
        ErrorCode.PACKAGE_INTEGRITY_ERROR,
        f"Failed atomically writing package archive '{dest_zip}': {safe_exception_summary(last_exc) if last_exc else 'replace failed'}",
    ) from last_exc


def _stream_copy_regular_nofollow(
    raw_src: str,
    tmp_raw: str,
    lstat_res: os.stat_result,
    max_bytes: int,
) -> None:
    try:
        src_fd = os.open(raw_src, _NOFOLLOW_READ_FLAGS)
    except OSError as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Failed opening local package zip '{raw_src}': {safe_exception_summary(exc)}",
        ) from exc
    try:
        f_st = os.fstat(src_fd)
        if not stat.S_ISREG(f_st.st_mode):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Local package archive '{raw_src}' is not a regular file.",
            )
        if not IS_WINDOWS and (f_st.st_dev, f_st.st_ino) != (lstat_res.st_dev, lstat_res.st_ino):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Detected file swap race while opening local package archive '{raw_src}'.",
            )
        if f_st.st_size > max_bytes:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Local package archive '{raw_src}' exceeds {max_bytes} bytes limit.",
            )
        if not IS_WINDOWS:
            os.set_blocking(src_fd, True)
        dst_fd = os.open(tmp_raw, _NOFOLLOW_EXCL_WRITE_FLAGS, 0o644)
        try:
            dst_file = os.fdopen(dst_fd, "wb")
        except BaseException:
            os.close(dst_fd)
            raise
        copied = 0
        with dst_file:
            while True:
                chunk = os.read(src_fd, 65536)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > max_bytes:
                    raise YscbError(
                        ErrorCode.PACKAGE_INTEGRITY_ERROR,
                        f"Local package archive '{raw_src}' exceeded {max_bytes} bytes limit during copy.",
                    )
                dst_file.write(chunk)
            dst_file.flush()
    except YscbError:
        raise
    except OSError as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Failed copying local package archive '{raw_src}': {safe_exception_summary(exc)}",
        ) from exc
    finally:
        os.close(src_fd)


def _copy_or_rewrite_build_zip(
    src_zip: HostPath,
    dest_zip: HostPath,
    tmp_raw: str,
    module_id: ModuleId,
    eff_build_ver: SemVer4,
    max_bytes: int,
) -> HostPath:
    ins_verify_zip_archive(src_zip, expected_sha256=None, ignore_sha256=True)
    with ins_open_verified_zip_stream(src_zip) as raw_in, zipfile.ZipFile(raw_in, "r") as zf_in:
        mf_bytes = zf_in.read("manifest.json")
        raw_mf = strict_parse_json_object(mf_bytes.decode("utf-8"))
        ins_parse_manifest_dict(raw_mf, expected_module_id=module_id)
        if raw_mf.get("version") == str(eff_build_ver) and raw_mf.get("schema_version") == 2:
            need_rewrite = False
        else:
            need_rewrite = True
        if need_rewrite:
            fd = os.open(tmp_raw, _NOFOLLOW_EXCL_WRITE_FLAGS, 0o644)
            try:
                out_f = os.fdopen(fd, "wb")
            except BaseException:
                os.close(fd)
                raise
            with out_f, zipfile.ZipFile(out_f, "w", compression=zipfile.ZIP_DEFLATED) as zf_out:
                for info in zf_in.infolist():
                    if info.is_dir() or info.filename.endswith("/"):
                        continue
                    zi = zipfile.ZipInfo(filename=info.filename, date_time=_DETERMINISTIC_ZIP_DATE)
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zi.external_attr = (0o644 & 0xFFFF) << 16
                    if info.filename == "manifest.json":
                        patched_mf: MutableJsonObject = dict(raw_mf)
                        patched_mf["schema_version"] = 2
                        patched_mf["version"] = str(eff_build_ver)
                        entry_data = (json.dumps(patched_mf, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
                    else:
                        entry_data = zf_in.read(info)
                    zf_out.writestr(zi, entry_data, compress_type=zipfile.ZIP_DEFLATED)
    if not need_rewrite:
        return _copy_verified_source_zip(
            src_zip,
            dest_zip,
            tmp_raw,
            max_bytes=max_bytes,
            expected_sha256=None,
            ignore_sha256=True,
        )
    ins_verify_zip_archive(HostPath(tmp_raw), expected_sha256=None, ignore_sha256=True)
    ins_peek_zip_manifest(HostPath(tmp_raw), expected_module_id=module_id, expected_version=eff_build_ver)
    _replace_temp_onto_dest(tmp_raw, dest_zip)
    return dest_zip


def _copy_verified_source_zip(
    src_zip: HostPath,
    dest_zip: HostPath,
    tmp_raw: str,
    *,
    max_bytes: int,
    expected_sha256: Optional[str],
    ignore_sha256: bool,
    expected_module_id: Optional[ModuleId] = None,
    expected_version: Optional[SemVer4] = None,
) -> HostPath:
    raw_src = str(src_zip)
    if is_symlink_or_reparse(raw_src) or has_symlink_raw_path(raw_src):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Refusing symlink package zip '{src_zip}'.",
        )
    try:
        st = os.lstat(raw_src)
    except OSError as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Package zip archive not found or unreadable at '{src_zip}': {safe_exception_summary(exc)}",
        ) from exc
    if not stat.S_ISREG(st.st_mode):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Local package archive '{src_zip}' must be a regular file.",
        )
    if st.st_size > max_bytes:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Local package archive '{src_zip}' exceeds {max_bytes} bytes limit.",
        )
    if src_zip == dest_zip:
        ins_verify_zip_archive(
            dest_zip,
            expected_sha256=expected_sha256,
            ignore_sha256=ignore_sha256,
        )
        if expected_module_id is not None:
            ins_peek_zip_manifest(
                dest_zip,
                expected_module_id=expected_module_id,
                expected_version=expected_version,
            )
        return dest_zip
    _stream_copy_regular_nofollow(raw_src, tmp_raw, st, max_bytes)
    tmp_hp = HostPath(tmp_raw)
    ins_verify_zip_archive(
        tmp_hp,
        expected_sha256=expected_sha256,
        ignore_sha256=ignore_sha256,
    )
    if expected_module_id is not None:
        ins_peek_zip_manifest(
            tmp_hp,
            expected_module_id=expected_module_id,
            expected_version=expected_version,
        )
    _replace_temp_onto_dest(tmp_raw, dest_zip)
    return dest_zip


def _version_archive_filenames(version: SemVer4) -> tuple[str, ...]:
    canon = f"{version}.zip"
    if not version.is_build and version.revision == 0 and not version.prerelease:
        short = f"{version.major}.{version.minor}.{version.patch}.zip"
        if short != canon:
            return (canon, short)
    return (canon,)


def _find_matching_raw_release_entry(raw_rels: Mapping[object, object], target: SemVer4) -> Optional[Mapping[object, object]]:
    direct = raw_rels.get(str(target))
    if isinstance(direct, Mapping):
        return direct
    for raw_k, raw_v in raw_rels.items():
        if type(raw_k) is str and isinstance(raw_v, Mapping):
            try:
                if SemVer4.parse(raw_k) == target:
                    return raw_v
            except ValueError:
                continue
    return None


def _read_exact_source_manifest(
    source_roots: tuple[HostPath, ...],
    module_id: ModuleId,
    target_version: SemVer4,
) -> Optional[Mapping[ModuleId, object]]:
    for root_cand in source_roots:
        mf_hp = try_resolve_contained_subpath(root_cand, "source", module_id.value, "manifest.json")
        if mf_hp is None or not os.path.isfile(str(mf_hp)) or is_symlink_or_reparse(str(mf_hp)):
            continue
        try:
            raw_bytes = read_nofollow_regular_bytes(str(mf_hp), max_bytes=MAX_JSON_FILE_BYTES)
            if raw_bytes is None:
                continue
            mf_doc = strict_parse_json_object(raw_bytes.decode("utf-8"))
            parsed_mf = ins_parse_manifest_dict(mf_doc, expected_module_id=module_id)
        except (OSError, UnicodeDecodeError, ValueError, YscbError):
            continue
        if parsed_mf.version == target_version and not parsed_mf.version.is_build:
            return parsed_mf.dependencies
    return None


def _enrich_local_index_missing_deps(
    index: RemoteModuleIndex,
    raw_doc: JsonObject,
    mod_dir: HostPath,
    source_roots: tuple[HostPath, ...],
) -> RemoteModuleIndex:
    raw_rels = raw_doc.get("releases")
    rels_mapping = raw_rels if isinstance(raw_rels, Mapping) else None
    all_vers: list[SemVer4] = []
    seen_vers: set[SemVer4] = set()
    for v in index.versions:
        if not v.is_build and v not in seen_vers:
            seen_vers.add(v)
            all_vers.append(v)
    for rec_item in index.releases.values():
        if not rec_item.version.is_build and rec_item.version not in seen_vers:
            seen_vers.add(rec_item.version)
            all_vers.append(rec_item.version)

    updated_rels: dict[str, IndexReleaseRecord] = dict(index.releases)
    changed = False
    for ver in all_vers:
        ver_key = str(ver)
        existing_rec = updated_rels.get(ver_key)
        raw_entry = _find_matching_raw_release_entry(rels_mapping, ver) if rels_mapping is not None else None
        if isinstance(raw_entry, Mapping) and "dependencies" in raw_entry:
            continue
        inferred_deps = None
        for fname in _version_archive_filenames(ver):
            cand_zip = try_resolve_contained_subpath(mod_dir, fname)
            if cand_zip is not None and os.path.isfile(str(cand_zip)) and not is_symlink_or_reparse(str(cand_zip)):
                try:
                    zip_mf = ins_peek_zip_manifest(cand_zip, expected_module_id=index.module_id)
                    inferred_deps = zip_mf.dependencies
                except YscbError:
                    pass
                break
        if inferred_deps is None:
            src_deps = _read_exact_source_manifest(source_roots, index.module_id, ver)
            if src_deps is not None:
                inferred_deps = src_deps
        if inferred_deps is not None:
            if existing_rec is not None:
                updated_rels[ver_key] = IndexReleaseRecord(
                    version=existing_rec.version,
                    sha256=existing_rec.sha256,
                    status=existing_rec.status,
                    dependencies=inferred_deps,
                    urgency=existing_rec.urgency,
                    summary=existing_rec.summary,
                    yanked=existing_rec.yanked,
                )
            else:
                updated_rels[ver_key] = IndexReleaseRecord(
                    version=ver,
                    sha256="",
                    status="active",
                    dependencies=inferred_deps,
                )
            changed = True
    if not changed:
        return index
    return RemoteModuleIndex(
        module_id=index.module_id,
        versions=index.versions,
        releases=updated_rels,
    )


class _InsOfflineProviderRegistry:
    """Weak registry tracking offline ProviderClient instances without exposing private state."""

    guard: ClassVar[threading.Lock] = threading.Lock()
    offline_clients: ClassVar[weakref.WeakSet[ProviderClient]] = weakref.WeakSet()

    @classmethod
    def mark_offline(cls, client: ProviderClient) -> None:
        with cls.guard:
            cls.offline_clients.add(client)

    @classmethod
    def is_offline(cls, client: ProviderClient) -> bool:
        with cls.guard:
            return client in cls.offline_clients


def ins_is_provider_offline(provider: ProviderClient) -> bool:
    """Return True when provider was initialized in offline mode or YSCB_OFFLINE is active."""
    return _InsOfflineProviderRegistry.is_offline(provider) or is_public_env_truthy("YSCB_OFFLINE")


class ProviderClient:
    """Multi-source package fetcher (local directory / HTTP(S) / @build / exact-version source packaging / --offline)."""

    MAX_REMOTE_PACKAGE_BYTES: int = 20 * 1024 * 1024

    def __init__(
        self,
        *,
        yscb_root: HostPath,
        default_provider: str,
        offline: bool = False,
        timeout_sec: float = 15.0,
        host_dir: Optional[HostPath] = None,
    ) -> None:
        if not isinstance(yscb_root, HostPath):
            raise ValueError(f"ProviderClient.yscb_root must be HostPath, got {yscb_root!r}")
        assert_no_symlink_raw_path(str(yscb_root))
        if host_dir is not None:
            if not isinstance(host_dir, HostPath):
                raise ValueError(f"ProviderClient.host_dir must be HostPath or None, got {host_dir!r}")
            assert_no_symlink_raw_path(str(host_dir))
        require_pure_str(default_provider, "ProviderClient.default_provider")
        require_pure_bool(offline, "ProviderClient.offline")
        safe_timeout = clamp_positive_sec(
            timeout_sec,
            min_sec=0.05,
            max_sec=3600.0,
            label="ProviderClient.timeout_sec",
        )
        self._yscb_root = yscb_root
        self._host_dir = host_dir
        self._default_provider = default_provider.strip()
        self._offline = offline or is_public_env_truthy("YSCB_OFFLINE")
        if self._offline or is_public_env_truthy("YSCB_OFFLINE"):
            _InsOfflineProviderRegistry.mark_offline(self)
        self._timeout_sec = safe_timeout
        self._tmp_lock = threading.Lock()
        self._tmp_seq = 0

    def _next_temp_zip_path(self, dest_zip: HostPath) -> str:
        with self._tmp_lock:
            self._tmp_seq += 1
            seq = self._tmp_seq
        return f"{dest_zip}.tmp_{os.getpid()}_{seq}_{uuid.uuid4().hex[:8]}"

    def _effective_provider(self, provider: Optional[str]) -> str:
        if provider is not None:
            require_pure_str(provider, "provider")
            cleaned = provider.strip()
            if cleaned:
                return cleaned
        if not self._default_provider:
            raise YscbError(ErrorCode.CONFIG_INVALID, "No package provider configured.")
        return self._default_provider

    def _http_stream_bytes(self, url: str, *, max_bytes: int) -> bytes:
        if self._offline or is_public_env_truthy("YSCB_OFFLINE"):
            raise YscbError(
                ErrorCode.TRANSPORT_LOST,
                f"Offline mode forbids remote HTTP(S) request to '{url}'.",
            )
        try:
            parsed = urlparse(url)
            _ = parsed.port
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid HTTP(S) provider URL '{url}': {exc}") from exc
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid HTTP(S) provider URL: '{url}'.")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "yscb-core/2.0", "Connection": "close"},
        )
        opener = ins_build_safe_http_opener(url, raise_security_error=True)
        chunks: list[bytes] = []
        total = 0
        try:
            with opener.open(req, timeout=self._timeout_sec) as resp:
                try:
                    cl_header = resp.headers.get("Content-Length") if resp.headers is not None else None
                    if isinstance(cl_header, str) and cl_header.strip().isdigit():
                        if int(cl_header.strip()) > max_bytes:
                            raise YscbError(
                                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                                f"Remote payload at '{url}' declares Content-Length {cl_header.strip()} exceeding {max_bytes} bytes limit.",
                            )
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            raise YscbError(
                                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                                f"Remote download from '{url}' exceeded {max_bytes} bytes limit.",
                            )
                        chunks.append(chunk)
                finally:
                    resp.close()
        except YscbError:
            raise
        except HTTPError as exc:
            try:
                exc.close()
            except OSError:
                pass
            code = ErrorCode.DEPENDENCY_CONFLICT if exc.code == 404 else ErrorCode.TRANSPORT_LOST
            raise YscbError(
                code,
                f"HTTP {exc.code} fetching '{url}': {safe_exception_summary(exc)}",
            ) from exc
        except (URLError, HTTPException, TimeoutError, OSError, ValueError) as exc:
            raise YscbError(
                ErrorCode.TRANSPORT_LOST,
                f"Network error fetching '{url}': {safe_exception_summary(exc)}",
            ) from exc
        return b"".join(chunks)

    def fetch_index(self, module_id: ModuleId, *, provider: Optional[str] = None) -> RemoteModuleIndex:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"ProviderClient.fetch_index requires ModuleId, got {module_id!r}")
        ins_assert_not_reserved_module_id(module_id, label="ProviderClient.fetch_index module_id")
        eff_prov = self._effective_provider(provider)
        if ins_is_http_provider(eff_prov):
            url = f"{eff_prov.rstrip('/')}/{module_id.value}/index.json"
            max_idx_bytes = min(MAX_JSON_FILE_BYTES, self.MAX_REMOTE_PACKAGE_BYTES)
            raw_bytes = self._http_stream_bytes(url, max_bytes=max_idx_bytes)
            try:
                doc = strict_parse_json_object(raw_bytes.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Malformed remote index.json from '{url}': {safe_exception_summary(exc)}",
                ) from exc
            return ins_parse_remote_index(doc, module_id)

        base_local_dir = self._host_dir if self._host_dir is not None else self._yscb_root
        prov_dir = _resolve_local_provider_dir(base_local_dir, eff_prov)
        for mod_dir in _candidate_local_module_dirs(prov_dir, module_id):
            idx_hp = try_resolve_contained_subpath(mod_dir, "index.json")
            if idx_hp is None or not os.path.lexists(str(idx_hp)):
                continue
            if is_symlink_or_reparse(str(idx_hp)) or has_symlink_raw_path(str(idx_hp)):
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Refusing symlink index.json at '{idx_hp}'.",
                )
            try:
                raw_bytes = read_nofollow_regular_bytes(str(idx_hp), max_bytes=MAX_JSON_FILE_BYTES)
            except OSError as exc:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Failed reading index.json at '{idx_hp}': {safe_exception_summary(exc)}",
                ) from exc
            if raw_bytes is None:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Unreadable or oversized index.json at '{idx_hp}'.",
                )
            try:
                doc = strict_parse_json_object(raw_bytes.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Malformed local index.json at '{idx_hp}': {safe_exception_summary(exc)}",
                ) from exc
            parsed_idx = ins_parse_remote_index(doc, module_id)
            source_roots = _candidate_local_source_roots(self._yscb_root, prov_dir, module_id, self._host_dir)
            return _enrich_local_index_missing_deps(parsed_idx, doc, mod_dir, source_roots)

        raise YscbError(
            ErrorCode.DEPENDENCY_CONFLICT,
            f"Module index not found for '{module_id}' in local provider '{eff_prov}'.",
        )

    def _find_dot_build_zip(
        self,
        module_id: ModuleId,
        version: SemVer4,
    ) -> Optional[tuple[HostPath, SemVer4]]:
        build_root = try_resolve_contained_subpath(self._yscb_root, ".build")
        if build_root is None or not os.path.isdir(str(build_root)):
            return None
        candidates: list[HostPath] = []
        for direct in (
            try_resolve_contained_subpath(build_root, f"{module_id.value}.zip"),
            try_resolve_contained_subpath(build_root, f"{module_id.value}.build.zip"),
            try_resolve_contained_subpath(build_root, module_id.value, f"{version}.zip"),
        ):
            if (
                direct is not None
                and direct not in candidates
                and os.path.isfile(str(direct))
                and not is_symlink_or_reparse(str(direct))
            ):
                candidates.append(direct)
        sub_dir = try_resolve_contained_subpath(build_root, module_id.value)
        if sub_dir is not None and os.path.isdir(str(sub_dir)) and not is_symlink_or_reparse(str(sub_dir)):
            matched: list[tuple[float, HostPath]] = []
            try:
                with os.scandir(str(sub_dir)) as it:
                    for ent in it:
                        if ent.is_symlink() or not ent.name.endswith(".zip"):
                            continue
                        try:
                            st = ent.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        if stat.S_ISREG(st.st_mode):
                            cand_hp = try_resolve_contained_subpath(sub_dir, ent.name)
                            if cand_hp is not None and cand_hp not in candidates:
                                matched.append((st.st_mtime, cand_hp))
            except OSError:
                matched = []
            matched.sort(key=lambda item: item[0], reverse=True)
            candidates.extend(hp for _mt, hp in matched)

        req_triple = version.triple()
        for cand_zip in candidates:
            mf = ins_peek_zip_manifest(cand_zip, expected_module_id=module_id)
            b_ver = SemVer4(mf.version.major, mf.version.minor, mf.version.patch, 0, is_build=True)
            if req_triple == (0, 0, 0) or b_ver.triple() == req_triple:
                return (cand_zip, b_ver)
        return None

    def fetch_package_zip(
        self,
        module_id: ModuleId,
        version: SemVer4,
        dest_zip: HostPath,
        *,
        provider: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        ignore_sha256: bool = False,
    ) -> HostPath:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"ProviderClient.fetch_package_zip requires ModuleId, got {module_id!r}")
        ins_assert_not_reserved_module_id(module_id, label="ProviderClient.fetch_package_zip module_id")
        if not isinstance(version, SemVer4):
            raise ValueError(f"ProviderClient.fetch_package_zip requires SemVer4, got {version!r}")
        if not isinstance(dest_zip, HostPath):
            raise ValueError(f"ProviderClient.fetch_package_zip requires HostPath dest_zip, got {dest_zip!r}")
        require_pure_bool(ignore_sha256, "ignore_sha256")
        if expected_sha256 is not None:
            require_pure_str(expected_sha256, "expected_sha256")

        assert_no_symlink_raw_path(str(dest_zip))
        os.makedirs(str(dest_zip.path.parent), exist_ok=True)
        assert_no_symlink_raw_path(str(dest_zip))
        tmp_raw = self._next_temp_zip_path(dest_zip)
        local_archive_cap = min(self.MAX_REMOTE_PACKAGE_BYTES, INS_MAX_ZIP_ARCHIVE_BYTES)

        try:
            if version.is_build:
                found_build = self._find_dot_build_zip(module_id, version)
                if found_build is not None:
                    build_zip, eff_build_ver = found_build
                    return _copy_or_rewrite_build_zip(
                        build_zip,
                        dest_zip,
                        tmp_raw,
                        module_id,
                        eff_build_ver,
                        INS_MAX_ZIP_ARCHIVE_BYTES,
                    )
                build_source_roots: list[HostPath] = [self._yscb_root]
                if self._host_dir is not None and self._host_dir not in build_source_roots:
                    build_source_roots.append(self._host_dir)
                try:
                    eff_build_prov = self._effective_provider(provider)
                except YscbError:
                    if provider is not None:
                        raise
                    eff_build_prov = ""
                if eff_build_prov and not ins_is_http_provider(eff_build_prov):
                    base_local_b = self._host_dir if self._host_dir is not None else self._yscb_root
                    try:
                        prov_dir_b = _resolve_local_provider_dir(base_local_b, eff_build_prov)
                    except YscbError:
                        if provider is not None:
                            raise
                        prov_dir_b = None
                    if prov_dir_b is not None:
                        for cand_r in _candidate_local_source_roots(
                            self._yscb_root,
                            prov_dir_b,
                            module_id,
                            self._host_dir,
                        ):
                            if cand_r not in build_source_roots:
                                build_source_roots.append(cand_r)
                for root_cand in build_source_roots:
                    src_dir = try_resolve_contained_subpath(root_cand, "source", module_id.value)
                    if src_dir is not None and _package_source_dir_to_temp_zip(
                        src_dir,
                        module_id,
                        version,
                        tmp_raw,
                        self.MAX_REMOTE_PACKAGE_BYTES,
                    ):
                        ins_verify_zip_archive(HostPath(tmp_raw), expected_sha256=None, ignore_sha256=True)
                        _replace_temp_onto_dest(tmp_raw, dest_zip)
                        return dest_zip
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Build artifact not found for '{module_id}@{version}' under '.build/' or matching 'source/{module_id.value}/'.",
                )

            eff_prov = self._effective_provider(provider)
            archive_names = _version_archive_filenames(version)
            if ins_is_http_provider(eff_prov):
                if self._offline or is_public_env_truthy("YSCB_OFFLINE"):
                    raise YscbError(
                        ErrorCode.TRANSPORT_LOST,
                        f"Offline mode forbids remote package download for '{module_id}@{version}'.",
                    )
                raw_zip_bytes: Optional[bytes] = None
                last_not_found: Optional[YscbError] = None
                for fname in archive_names:
                    url = f"{eff_prov.rstrip('/')}/{module_id.value}/{fname}"
                    try:
                        raw_zip_bytes = self._http_stream_bytes(url, max_bytes=local_archive_cap)
                        break
                    except YscbError as exc:
                        if exc.detail.code == ErrorCode.DEPENDENCY_CONFLICT:
                            last_not_found = exc
                            continue
                        raise
                if raw_zip_bytes is None:
                    if last_not_found is not None:
                        raise last_not_found
                    raise YscbError(
                        ErrorCode.DEPENDENCY_CONFLICT,
                        f"Remote archive not found for '{module_id}@{version}'.",
                    )
                _write_exclusive_temp_bytes(tmp_raw, raw_zip_bytes)
                ins_verify_zip_archive(
                    HostPath(tmp_raw),
                    expected_sha256=expected_sha256,
                    ignore_sha256=ignore_sha256,
                )
                ins_peek_zip_manifest(
                    HostPath(tmp_raw),
                    expected_module_id=module_id,
                    expected_version=version,
                )
                _replace_temp_onto_dest(tmp_raw, dest_zip)
                return dest_zip

            base_local_dir = self._host_dir if self._host_dir is not None else self._yscb_root
            prov_dir = _resolve_local_provider_dir(base_local_dir, eff_prov)
            for mod_dir in _candidate_local_module_dirs(prov_dir, module_id):
                for fname in archive_names:
                    cand_zip = try_resolve_contained_subpath(mod_dir, fname)
                    if cand_zip is not None and os.path.lexists(str(cand_zip)):
                        if not ignore_sha256 and expected_sha256 is None:
                            raise YscbError(
                                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                                f"Missing SHA-256 digest in index.json for prebuilt archive '{cand_zip}'.",
                            )
                        return _copy_verified_source_zip(
                            cand_zip,
                            dest_zip,
                            tmp_raw,
                            max_bytes=local_archive_cap,
                            expected_sha256=expected_sha256,
                            ignore_sha256=ignore_sha256,
                            expected_module_id=module_id,
                            expected_version=version,
                        )

            for root_cand in _candidate_local_source_roots(self._yscb_root, prov_dir, module_id, self._host_dir):
                src_dir = try_resolve_contained_subpath(root_cand, "source", module_id.value)
                if src_dir is None:
                    continue
                if _package_source_dir_to_temp_zip(
                    src_dir,
                    module_id,
                    version,
                    tmp_raw,
                    self.MAX_REMOTE_PACKAGE_BYTES,
                ):
                    ins_verify_zip_archive(
                        HostPath(tmp_raw),
                        expected_sha256=None if expected_sha256 is None else expected_sha256,
                        ignore_sha256=True if expected_sha256 is None else ignore_sha256,
                    )
                    _replace_temp_onto_dest(tmp_raw, dest_zip)
                    return dest_zip

            raise YscbError(
                ErrorCode.DEPENDENCY_CONFLICT,
                f"Package archive '{module_id}@{version}.zip' not found in local provider '{eff_prov}' or exact-version 'source/{module_id.value}/'.",
            )
        finally:
            if os.path.lexists(tmp_raw):
                try:
                    os.unlink(tmp_raw)
                except OSError:
                    pass
