from pathlib import Path


SITE = Path(__file__).parents[1] / "docs"


def test_public_site_has_required_pages_and_shared_navigation():
    required = [SITE / "index.html", SITE / "terms" / "index.html", SITE / "privacy" / "index.html"]
    assert all(path.is_file() for path in required)

    for page in required:
        html = page.read_text(encoding="utf-8")
        assert "Terms" in html
        assert "Privacy" in html
        assert "styles.css" in html


def test_public_site_relative_links_resolve():
    pages = [SITE / "index.html", SITE / "terms" / "index.html", SITE / "privacy" / "index.html"]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        for href in (
            'href="./"',
            'href="../"',
            'href="terms/"',
            'href="../terms/"',
            'href="privacy/"',
            'href="../privacy/"',
        ):
            if href in html:
                target = href.split('href="', 1)[1].split('"', 1)[0]
                if target.endswith("/"):
                    assert (page.parent / target / "index.html").is_file()
                else:
                    assert (page.parent / target).is_file()


def test_public_site_contains_no_known_credential_files_or_values():
    text = "\n".join(path.read_text(encoding="utf-8") for path in SITE.rglob("*.html"))
    for marker in (
        "client_secret",
        "client_secrets.json",
        "access_token",
        "refresh_token",
        "credentials.json",
        "token.json",
    ):
        assert marker not in text.lower()
