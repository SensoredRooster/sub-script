# SubScript public site and GitHub Pages

The public OAuth-review site lives in this `docs/` directory. It is intentionally separate from the desktop app's `subscript/static/` directory, so publishing the site does not change the local application UI or package contents.

## Enable Pages without GitHub Actions

1. Push the repository's `main` branch to GitHub.
2. Open **Settings → Pages** for `SensoredRooster/sub-script`.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Choose branch **main** and folder **/docs**, then click **Save**.
5. Wait for GitHub Pages to publish the site. This branch-based setup avoids requiring a GitHub Actions billing account.

GitHub Pages only publishes these static files; it does not build or run the desktop application and it does not read credential files.

## URLs for the current repository

The configured remote is `https://github.com/SensoredRooster/sub-script`. For a normal project site with no custom domain, the expected Pages hostname and the exact URLs to enter in a developer console are:

| Use | URL |
| --- | --- |
| Website / homepage | `https://sensoredrooster.github.io/sub-script/` |
| Terms of Service | `https://sensoredrooster.github.io/sub-script/terms/` |
| Privacy Policy | `https://sensoredrooster.github.io/sub-script/privacy/` |

Confirm the final URL shown by **Settings → Pages** before submitting a review. If a custom domain is configured, use that domain with `/`, `/terms/`, and `/privacy/` instead. The site uses directory index pages so these URLs work without `.html` suffixes.

## Security checklist

Do not commit `.env`, `config.yaml`, `credentials.json`, `token.json`, OAuth client secrets, access tokens, or refresh tokens. The repository ignore rules already cover the known local credential filenames. Before pushing, review `git status` and `git diff --cached` and verify that no secret has been staged.

Before a TikTok, Meta, or X developer review, replace the bracketed legal contact and governing-law placeholders in `docs/terms/index.html` and `docs/privacy/index.html` with the actual business details. The site describes local processing and export preparation accurately; optional direct posting still requires the relevant connector, account authorization, and platform approval.
