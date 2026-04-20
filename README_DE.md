# Finde Eier der Größe L

Sprachversionen: [English](README.md) | [中文](README_中文.md)

Eine leichtgewichtige Web-App (ohne Node.js), um zu prüfen, ob Supermärkte in Erlangen Eier der Größe L haben.

## Funktionen

- OpenStreetMap-Karte mit Supermarktpunkten aus `Supermarkets.txt`
- 4 Marker-Status:
  - Gruen = viele
  - Gelb = wenige
  - Rot = keine
  - Grau = unbekannt / unter Schwellwert
- Klick auf einen Marker zeigt Marke + Adresse und ermoeglicht Abstimmung (viele / wenige / keine)
- Gueltigkeit einer Stimme: 3 Stunden
- Dieselbe IP kann innerhalb von 3 Stunden nicht denselben Status fuer denselben Markt erneut abstimmen
- Markerfarbe basiert auf dem Status mit den meisten Stimmen
- Wenn alle Status unter dem Schwellwert (3) liegen, wird der Marker grau angezeigt
- UI unterstuetzt Englisch, Chinesisch und Deutsch

## Starten

1. Stelle sicher, dass Python 3 installiert ist.
2. Im Projektordner ausfuehren:

```powershell
python app.py
```

3. Oeffnen:

```text
http://127.0.0.1:8000
```

## Laufzeitdateien

- `geocode_cache.json` (Adress -> Koordinaten-Cache)
- `votes.db` (SQLite-Speicher fuer Stimmen)

## Hinweise

- Der erste Start kann langsamer sein, weil Koordinaten ueber OpenStreetMap Nominatim abgerufen und gecacht werden.
- Die Voting-API ist lokal und leichtgewichtig, gedacht fuer einfache Deployments.
