# Step 5 / C1 closure — 2026-10-31

**R1 and R2 are CLOSED. Step 6 engineering can proceed.** Human validation and approval of the selection/evaluation protocol remain pending; this technical review does not authorize inspecting holdout strategy outcomes.

- Independently reran the connected suite: **71 passed in 21.07s**, no failed tests or setup errors. The first run hit the sandbox's default temporary-directory permissions; a fresh workspace-local `--basetemp tmp/pytest_step5_codex_7b9686a2` resolved that environment issue without changing application code.
- R1: a genuinely different configuration now produces **111 draws / seed 42** consistently in the primary estimates, bundle metadata and uncertainty's base replication. The primary/uncertainty base-seed VaR and ES differences are exactly zero, and the effective config hash agrees.
- R2: the complete saved artifact strictly parses; non-applicable metadata uses `null`. All **54 baseline risk rows** retain their original VaR and ES exactly. Scalar historical/Normal checks agree within **2.08e-17**, and the 450 rational-tail oracle cases still pass.
- All **53 market/context hashes** match. Accepted Steps 3/4 code, config, contracts, requirements and active snapshot pointer are unchanged.
- Visible outputs now exist in `results/step5_c1_preview/`: **3 figures in PNG and SVG, 6 CSV tables, strict JSON, HTML index and provenance manifest**. Checked CSV/JSON agreement and all 3,020 fixed-exposure loss observations against development returns. Outputs are development previews, not final evaluation results. Final report composition should simplify dense labels where necessary.
- The preview initially recorded an older recorder-script hash. Codex reran the existing exporter after source changes settled. All **16 artifact hashes**, every recorded source hash and the authoritative JSON now agree. This export refresh changed no financial runtime, configuration or source data and left the Step 4 preview intact.

The original review and baseline artifact remain available. `CODEX_CLOSURE_CHECKPOINT.json` records the latest post-refresh state and supersedes earlier preview-manifest hashes for this closure. No Step 6 analytics were started by this review.
