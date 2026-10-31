# Public Streamlit deployment

**Live at https://quant-edge-1-final.streamlit.app/**, verified signed out. Results are in
`FINAL_SUBMISSION/supporting/Verification_Summary.md`.

The GitHub repository is public. That makes the source available; it does not
create a running public Streamlit service. A localhost URL works on the server's
own computer.

## Community Cloud settings

1. Sign in to https://share.streamlit.io/ using the appropriate GitHub account.
2. Create an app from this repository:
   - Repository: `ruchirajayamaha/quant-edge-1-final`
   - Branch: `main`
   - Main file / entrypoint: `streamlit_app.py`
   - Advanced settings: Python `3.11` (the verified numerical environment).
3. Select an available app subdomain and deploy. Record the actual returned
   `https://...streamlit.app` URL; a suggested name is not an existing deployment.
4. Check app settings / Sharing and confirm public access. Open the actual URL
   in a signed-out or private browser window to verify judges need no login.

The root entrypoint adds this repository's `src/` to the Python import path and
executes the existing `app/Home.py`. This avoids a missing `quantedge` package when
Cloud installs root requirements without a separate local editable install.
The pinned requirements and frozen analytical sources are not modified.

No market-data API key is needed for normal offline app launch. The frozen data,
results, source hashes and report files must be included in the deployed commit.
TeX/Matplotlib/report-authoring dependencies are not needed to view existing PDFs.

## Before claiming the deployment is ready

- Finish and test any in-progress app/report redesign, then commit/push its related
  files. Cloud deploys the GitHub branch, not uncommitted local files.
- Check build logs for actual Linux/Python dependency failures; local Windows
  success alone does not prove the Cloud build succeeds. Fix only the demonstrated
  issue and preserve the numerical source/manifest conventions.
- Open all six views and verify portfolio/confidence/model/date controls.
- Verify PDF downloads deliver the intended final versions.
- Record the actual deployed commit, public URL and signed-out access check.
- Add that real URL to the repository/submission instructions and rebuild packaging
  after verification. Do not substitute a GitHub URL or a localhost URL for it.

Official references:
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app

## Current status

Deployed from `main` with `streamlit_app.py` on Python 3.11, under the owner's Community Cloud account.

`.streamlit/config.toml` turns the file watcher off, because an update otherwise raised import errors in open
sessions. So a push changes files on disk at once, but new Python code needs **Reboot app** in the Manage app
menu. PDFs and other documents are read from disk and do not need a reboot.
