name: Hourly Traffic & Weather Data Collector

on:
  schedule:
    - cron: '0 * * * *'  # Runs hourly
  workflow_dispatch:      # Allows manual trigger

jobs:
  collect-data:
    runs-on: ubuntu-latest
    permissions:
      contents: write     # Grants write permissions to save CSV files

    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests

      - name: Run Collector Script
        env:
          GOOGLE_MAPS_API_KEY: ${{ secrets.GOOGLE_MAPS_API_KEY }}
          OPENWEATHER_API_KEY: ${{ secrets.OPENWEATHER_API_KEY }}
        run: python collector.py

      - name: Commit and Push CSV updates
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --quiet && git diff --staged --quiet || (git commit -m "Auto-update raw and enriched dataset" && git push)
