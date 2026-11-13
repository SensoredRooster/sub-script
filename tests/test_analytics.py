"""Analytics store: publication recording, video-id parsing, performance math."""

from __future__ import annotations

from pathlib import Path

from subscript import analytics as A


def test_extract_video_id_formats() -> None:
    assert A.extract_video_id("https://youtu.be/abc123XYZ") == "abc123XYZ"
    assert A.extract_video_id("https://www.youtube.com/watch?v=abc123XYZ") == "abc123XYZ"
    assert A.extract_video_id("https://www.youtube.com/shorts/abc123XYZ") == "abc123XYZ"
    assert A.extract_video_id(None) is None
    assert A.extract_video_id("https://example.com/nothing") is None


def test_record_and_performance_math(tmp_path: Path) -> None:
    A.record_publication(tmp_path, video_id="v1", item_id="i1", title="A",
                         dna={"package_id": "p1", "preset": "hype"})
    A.record_publication(tmp_path, video_id="v2", item_id="i2", title="B",
                         dna={"package_id": "p1", "preset": "hype"})
    A.record_publication(tmp_path, video_id="v3", item_id="i3", title="C",
                         dna={"package_id": "p2", "preset": "story"})

    # No stats yet → empty performance.
    assert A.performance_by(tmp_path, "package_id") == {}
    assert A.performance_summary(tmp_path) == ""

    # Inject stats as if refresh_stats fetched them.
    data = A._load(tmp_path)
    data["clips"]["v1"]["stats"] = {"views": 100, "likes": 10, "comments": 1}
    data["clips"]["v2"]["stats"] = {"views": 300, "likes": 30, "comments": 3}
    data["clips"]["v3"]["stats"] = {"views": 50, "likes": 5, "comments": 0}
    A._save(tmp_path, data)

    by_pkg = A.performance_by(tmp_path, "package_id")
    assert by_pkg["p1"]["clips"] == 2
    assert by_pkg["p1"]["avg_views"] == 200.0
    assert by_pkg["p2"]["avg_views"] == 50.0

    by_preset = A.performance_by(tmp_path, "preset")
    assert by_preset["hype"]["avg_views"] == 200.0
    assert by_preset["story"]["clips"] == 1

    summary = A.performance_summary(tmp_path)
    assert "3 published clips" in summary and "p1" in summary


def test_refresh_stats_without_credentials_fails_soft(tmp_path: Path) -> None:
    A.record_publication(tmp_path, video_id="v1", item_id="i1", dna={})
    result = A.refresh_stats({}, tmp_path)
    assert result["updated"] == 0
    assert result["clips"] == 1
    assert "not connected" in result["error"]


def test_refresh_stats_empty_store(tmp_path: Path) -> None:
    assert A.refresh_stats({}, tmp_path) == {"updated": 0, "clips": 0, "error": None}


def test_refresh_stats_with_fake_service(tmp_path: Path, monkeypatch) -> None:
    A.record_publication(tmp_path, video_id="v1", item_id="i1", dna={"package_id": "p1"})

    class _FakeReq:
        def execute(self):
            return {"items": [{"id": "v1", "statistics": {
                "viewCount": "1234", "likeCount": "56", "commentCount": "7"}}]}

    class _FakeVideos:
        def list(self, **kwargs):
            return _FakeReq()

    class _FakeService:
        def videos(self):
            return _FakeVideos()

    monkeypatch.setattr(A, "_youtube_credentials", lambda cfg: object())
    import googleapiclient.discovery
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda *a, **k: _FakeService())

    result = A.refresh_stats({}, tmp_path)
    assert result == {"updated": 1, "clips": 1, "error": None}
    clip = A._load(tmp_path)["clips"]["v1"]
    assert clip["stats"] == {"views": 1234, "likes": 56, "comments": 7}
