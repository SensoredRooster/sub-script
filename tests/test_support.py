from __future__ import annotations

import io
import json
import zipfile

from subscript.telemetry import redact_mapping, redact_text


def test_redaction_masks_known_secret_fields_and_bearer_tokens():
    value = {
        "client_secret": "super-secret-value",
        "token_file": "token.json",
        "nested": {
            "password": "hunter2",
            "safe": "hello",
        },
    }
    redacted = redact_mapping(value)
    assert redacted["client_secret"] == "[REDACTED]"
    assert redacted["token_file"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "hello"
    assert "[REDACTED]" in redact_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456")


def test_support_center_is_visible_and_local_first(app_env):
    page = app_env.client.get("/support")
    assert page.status_code == 200
    assert "Support & diagnostics" in page.text
    assert "Download Support Bundle" in page.text
    assert "Open Logs Folder" in page.text
    assert "Report Issue on GitHub" in page.text
    assert "Nothing is uploaded automatically" in page.text
    assert "Remote support upload is not configured" in page.text


def test_support_status_exposes_session_and_watchers(app_env):
    response = app_env.client.get("/support/status")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"]
    assert data["version"]
    assert "log_dir" in data
    assert "profile_watchers" in data


def test_support_bundle_contains_redacted_diagnostics(app_env):
    app_env.cfg["youtube"]["client_secrets_file"] = "credentials.json"
    app_env.cfg["platforms"] = {
        "tiktok": {
            "enabled": True,
            "client_secret": "do-not-export-me",
            "token_file": "tiktok-token.json",
        }
    }
    response = app_env.client.post("/support/bundle")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "diagnostics/manifest.json" in names
        assert "diagnostics/config.redacted.json" in names
        assert "README.txt" in names
        config = json.loads(archive.read("diagnostics/config.redacted.json"))
        assert config["platforms"]["tiktok"]["client_secret"] == "[REDACTED]"
        assert config["platforms"]["tiktok"]["token_file"] == "[REDACTED]"
        manifest = json.loads(archive.read("diagnostics/manifest.json"))
        assert manifest["session_id"]
        assert manifest["version"]


def test_remote_support_upload_is_disabled_without_collector(app_env, monkeypatch):
    monkeypatch.delenv("SUBSCRIPT_SUPPORT_UPLOAD_URL", raising=False)
    app_env.cfg.pop("support", None)
    response = app_env.client.post("/support/upload")
    assert response.status_code == 409
    assert "not configured" in response.json()["error"]


def test_support_routes_back_to_repo_and_issue_tracker(app_env):
    repo = app_env.client.get("/support/repository", follow_redirects=False)
    assert repo.status_code == 303
    assert repo.headers["location"] == "https://github.com/SensoredRooster/sub-script"

    report = app_env.client.get("/support/report", follow_redirects=False)
    assert report.status_code == 303
    assert report.headers["location"].startswith(
        "https://github.com/SensoredRooster/sub-script/issues/new"
    )
    assert "Session%20ID" in report.headers["location"] or "Session+ID" in report.headers["location"]
