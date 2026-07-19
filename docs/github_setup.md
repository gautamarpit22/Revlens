# Publishing to GitHub (one-time)

```bash
cd /Users/arpitgautam/Downloads/revlens_2
git init
git add .
git commit -m "RevLens: revenue intelligence platform (phases 1-5)"
# create repo on github.com -> name: revlens, public, NO readme/gitignore (we have them)
git remote add origin https://github.com/<your-username>/revlens.git
git branch -M main
git push -u origin main
```

Sanity before push: `.gitignore` already excludes sample_data/, *.duckdb, .venv, target/,
dbt_packages/ — verify with `git status` that no data files or venv are staged.
After push: Actions tab -> the CI pipeline (small-world Dagster run + contract gate +
echo evals) should go green on the first push. Add repo link + Loom link to your resume.
