import json
import sys

import pytest

from subscript import secure_store as ss


def test_roundtrip_and_no_plaintext(tmp_path):
    p = tmp_path / "token.json"
    ss.write_token_text(p, json.dumps({"access_token": "secret-value"}))
    assert ss.token_exists(p)
    assert json.loads(ss.read_token_text(p))["access_token"] == "secret-value"
    if ss.dpapi_available():
        assert not p.exists()
        assert b"secret-value" not in ss.protected_path(p).read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI migration is Windows-only")
def test_plaintext_file_is_migrated(tmp_path):
    p = tmp_path / "token.json"
    p.write_text('{"refresh_token": "r1"}', encoding="utf-8")
    assert ss.read_token_text(p) == '{"refresh_token": "r1"}'
    assert not p.exists() and ss.protected_path(p).is_file()
    assert ss.read_token_text(p) == '{"refresh_token": "r1"}'


def test_missing_and_delete(tmp_path):
    p = tmp_path / "t.json"
    assert ss.read_token_text(p) is None and not ss.token_exists(p)
    ss.write_token_text(p, "{}")
    ss.delete_token(p)
    assert not ss.token_exists(p)
