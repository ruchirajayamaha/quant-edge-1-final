# Public Streamlit deployment

The GitHub repository is public. That makes the source available; it does not
create a running public Streamlit service. A localhost URL works on the server's
own computer. No public app URL is claimed until a real deployment is verified.

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

Not deployed. The repository is ready, but deployment needs the owner to sign in to Community Cloud with
GitHub, accept its terms and authorise access. Those steps were not done for the owner. Once a URL exists,
verify it as above, record the result in `FINAL_SUBMISSION/supporting/Verification_Summary.md`, add it to
`FINAL_SUBMISSION/00_START_HERE.md` and `03_Links_and_Run_Instructions.md`, then run
`python scripts/package_submission.py` and push.
