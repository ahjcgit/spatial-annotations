# Audited results dashboard

Open `index.html` directly, keeping the parent evidence directories alongside it, or
serve from the application repository:

```bash
ss -lnt '( sport = :8029 )'
python3 -m http.server 8029 --bind 0.0.0.0 \
  --directory experiments/codex-glasses/2026-11-19
```

Then open `http://<computer-LAN-IP>:8029/dashboard/`. Use another available port if needed.

Regenerate with `python3 scripts/build_pilot_dashboard.py`. It reads the raw archive,
recomputes the plotted metrics from separate host/device clocks, verifies hashes and
associations, and writes this directory. It refuses to overwrite the original report.
No inference or device connection is involved. Templates live in `demo/pilot-results/`.

`analysis.json` contains the complete audit, trial records and grouped statistics;
`trials.csv` includes failed and image-only records with unmeasured fields blank.
`data.js` embeds the same JSON for a portable page without fetch/network dependencies.

For detailed interpretation and the exact referenced-but-missing artifact checklist,
read [the analysis](../../../../docs/CODEX_PILOT_ANALYSIS.md) in the repository.
The original archive report is unchanged at `../report/index.html`.
