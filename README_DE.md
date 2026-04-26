# Finde Eier der Größe L

Sprachversionen: [English](README.md) | [中文](README_中文.md)

## Direkt auf die Website: [find-l-eggs.live](https://find-l-eggs.live)

Eine leichtgewichtige Web-App (ohne Node.js), um zu prüfen, ob Supermärkte in Erlangen, Fürth und Nürnberg Eier der Größe L haben.

## Funktionen

- OpenStreetMap-Karte mit Supermarktpunkten aus `Supermarkets.txt`
- 4 Marker-Status:
  - Gruen = viele
  - Gelb = wenige
  - Rot = keine
  - Grau = unbekannt / unter Schwellwert
- Klick auf einen Marker zeigt Marke + Adresse und ermoeglicht Abstimmung (viele / wenige / keine)
- Gueltigkeit einer Stimme: 12 Stunden
- Dieselbe IP kann innerhalb von 1 Stunde nicht denselben Status fuer denselben Markt erneut abstimmen
- Markerfarbe basiert auf dem Status mit den meisten Stimmen
- 0 Stimmen = grau, 1-2 Stimmen = helle Farben, 3+ Stimmen = nur dann dunkle Farben, wenn die neueste Meldung innerhalb von 3 Stunden liegt (sonst helle Farben)
- UI unterstuetzt Englisch, Chinesisch und Deutsch

## Update

- Erste vorlaeufige Unterstuetzung fuer Supermaerkte in ganz Deutschland wurde hinzugefuegt.

## To-do-Liste

- Aktuell wird nur REWE unterstuetzt; weitere Supermarktketten folgen spaeter.
- Fuer einige Supermarktadressen koennen ueber OpenStreetMap derzeit keine Koordinaten ermittelt werden.
- Einige Maerkte fehlen noch in der Supermarktliste der `overview`-Seite; gleichnamige Staedte muessen in bestimmten Faellen noch geprueft werden.

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
