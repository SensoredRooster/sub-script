"""Store OAuth tokens encrypted at rest with Windows DPAPI (per-user), with plaintext migration.

On Windows a token configured as ``token.json`` is kept as ``token.json.dpapi``: bytes
encrypted by ``CryptProtectData`` for the current Windows user, so other accounts on the PC
and anyone who copies the file to another machine cannot read it. Existing plaintext token
files are migrated transparently on first read (the plaintext copy is deleted only after the
encrypted copy has been written and verified). On other platforms tokens stay plaintext JSON
with owner-only permissions.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

PROTECTED_SUFFIX = ".dpapi"
_ENTROPY = b"SubScript OAuth token v1"


def protected_path(path: Path) -> Path:
    return path.with_name(path.name + PROTECTED_SUFFIX)


def dpapi_available() -> bool:
    return sys.platform == "win32"


if sys.platform == "win32":  # pragma: no cover - exercised on Windows CI
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    def _crypt(func_name: str, data: bytes) -> bytes:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        src, _keep = _blob(data)
        ent, _keep2 = _blob(_ENTROPY)
        out = _Blob()
        func = getattr(crypt32, func_name)
        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        if not func(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(out)):
            raise OSError(ctypes.GetLastError(), "DPAPI call failed")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32.LocalFree(out.pbData)

    def protect(data: bytes) -> bytes:
        return _crypt("CryptProtectData", data)

    def unprotect(data: bytes) -> bytes:
        return _crypt("CryptUnprotectData", data)
else:
    def protect(data: bytes) -> bytes:
        raise OSError("DPAPI is only available on Windows")

    def unprotect(data: bytes) -> bytes:
        raise OSError("DPAPI is only available on Windows")


def token_exists(path: Path) -> bool:
    return protected_path(path).is_file() or path.is_file()


def write_token_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if dpapi_available():
        enc = protect(text.encode("utf-8"))
        target = protected_path(path)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(enc)
        os.replace(tmp, target)
        if path.is_file():
            path.unlink()
        return
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def read_token_text(path: Path) -> str | None:
    """Return the token JSON text, or None when no token is stored. Migrates plaintext files."""
    enc = protected_path(path)
    if enc.is_file() and dpapi_available():
        return unprotect(enc.read_bytes()).decode("utf-8")
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if dpapi_available():
        try:
            data = protect(text.encode("utf-8"))
            if unprotect(data).decode("utf-8") == text:
                tmp = enc.with_name(enc.name + ".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, enc)
                path.unlink()
        except OSError:
            pass  # keep the plaintext file; it still works
    return text


def delete_token(path: Path) -> None:
    for candidate in (path, protected_path(path)):
        if candidate.is_file():
            candidate.unlink()
