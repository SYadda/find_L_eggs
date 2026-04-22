# Find L Eggs
## Visit the site: [find-l-eggs.live](https://find-l-eggs.live)
Language versions: [中文](README_中文.md) | [Deutsch](README_DE.md)

Lightweight web app (no Node.js) to check whether supermarkets in Erlangen, Fürth, and Nürnberg have L-size eggs.

## Features

- OpenStreetMap map with supermarket points from `Supermarkets.txt`
- 4 marker states:
  - green = plenty
  - yellow = few
  - red = none
  - gray = unknown / below threshold
- Click marker to view brand + address and submit vote (plenty / few / none)
- Vote validity: 12 hours
- Same IP cannot submit the same vote for the same market within 1 hour
- Main marker color is based on the highest vote count
- 0 votes = gray, 1-2 votes = light colors, 3+ votes = dark colors only if the latest submission is within 3 hours (otherwise light colors)
- UI supports English, Chinese, and German

## Run

1. Make sure Python 3 is installed.
2. In this folder, run:

```powershell
python app.py
```

3. Open:

```text
http://127.0.0.1:8000
```

## Data files created at runtime

- `geocode_cache.json` (address -> coordinates cache)
- `votes.db` (SQLite vote storage)

## Notes

- First run may be slower because coordinates are fetched from OpenStreetMap Nominatim and cached.
- Voting API is local and lightweight, intended for simple deployment.
