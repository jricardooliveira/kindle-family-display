# Schnellstart auf Deutsch

Voraussetzung: Docker mit Docker Compose auf einem Rechner im Heimnetz. Zum
Ausprobieren reicht ein Browser; ein Kindle, Kalender, Konto oder API-Schlüssel
ist nicht erforderlich.

Nach dem Klonen im Projektverzeichnis ausführen:

```sh
cp config.de.example.toml config.toml
mkdir -p photos calendars secrets
docker compose up --build -d
```

Die Beispielkonfiguration zeigt Wetter für **Berlin** und Nachrichten von
**Tagesschau Inland**, auf Deutsch und in der Zeitzone `Europe/Berlin`.
Öffnen Sie auf dem Server [Nachrichten und Wetter](http://127.0.0.1:8000/kindle/news-weather.png)
oder [Familie](http://127.0.0.1:8000/kindle/family.png).
Der [Status](http://127.0.0.1:8000/api/status) zeigt Fehler und Aktualisierungszeiten.
Öffentliche Datenquellen brauchen Internetzugang; bei Ausfällen bleiben zuletzt
geladene Daten verfügbar. Ohne Kalender zeigt die Familienseite Wetter und
Wissensfakten im täglichen Wechsel.

## Ohne Internet ausprobieren

Setzen Sie in `config.toml` `demo_mode = true`. Die Demo zeigt erfundene deutsche
Beispieldaten ohne externe Anfragen. Für echte Daten wieder `false` setzen.
Die erste Docker-Installation bzw. der erste Build benötigt Internetzugang.

Nach Änderungen neu starten:

```sh
docker compose up -d --force-recreate
```

## Anpassen

- `language`: `"pt"`, `"en"` oder `"de"` für alle eingebauten Anzeigetexte.
- `country`: `"PT"`, `"GB"` oder `"DE"` für die nationale Nachrichtenrubrik und
  die optionale KI-Bewertung. Sprache, Land und Zeitzone sind unabhängig.
- `timezone`: eine IANA-Zeitzone, zum Beispiel `"Europe/Berlin"`.
- `weather_latitude`, `weather_longitude`, `weather_location`: ersetzen Sie den
  Beispielort Berlin durch Ihren Wohnort. Es findet keine Standortbestimmung statt.
- Weitere Einstellungen und Kalenderbeispiele stehen in `config.example.toml`.
  Überschriften aus RSS, Kalendertexte, Personennamen und eigene Bildtitel bleiben
  in der Originalsprache. Ein Sprachwechsel wählt keine anderen RSS-Feeds aus.
- Die Standardgröße ist 800×600. Für einen Paperwhite 11 im Querformat:
  `screen_width = 1648`, `screen_height = 1236`, `screen_rotation = 90`.

`config.toml` ist privat und wird nicht in Git gespeichert. Geben Sie private
Kalenderlinks nicht weiter. Umgebungsvariablen haben Vorrang vor `config.toml`.

## Kindle verbinden

Die Anwendung ist zunächst nur auf dem Server erreichbar. Legen Sie für den
Zugriff im Heimnetz eine `.env` mit der tatsächlichen LAN-Adresse des Servers an:

```dotenv
BIND_ADDRESS=192.168.1.50
APP_PORT=8000
```

Starten Sie den Container erneut. Öffnen Sie auf einem anderen Gerät im selben
Netz `http://192.168.1.50:8000/kindle/news-weather.png` (Adresse anpassen).

Auf dem Kindle werden KOReader und das TRMNL-KOReader-Plugin benötigt:

1. `trmnl.koplugin` nach `koreader/plugins/` kopieren und KOReader neu starten.
2. Einen beliebigen, nicht leeren Text in `apikey.txt` des Plugins eintragen.
3. Als Basis-URL `http://192.168.1.50:8000` eintragen und die Aktualisierungsrate
   des Servers aktivieren.
4. Die TRMNL-Anzeige starten. Alle fünf Minuten erscheint die nächste Seite;
   leere Seiten werden übersprungen.

Der Dienst hat keine Anmeldung. Nur im Heimnetz betreiben, nicht ins Internet
freigeben. Weitere Gerätehinweise: [device-setup.md](device-setup.md).

## Nachrichtenquelle

[Tagesschau dokumentiert diesen RSS-Feed](https://www.tagesschau.de/infoservices/rssfeeds)
für Inlandsnachrichten. Die Inhalte sind für private, nicht kommerzielle Nutzung
vorgesehen; die Nutzungsbedingungen des Anbieters gelten. In `config.toml` können
Sie andere Feeds ergänzen. `category = "national"` zeigt nationale Nachrichten;
für `"world"` ist `curated = true` oder eine Auswahl über `keywords` erforderlich.

Andere Startkonfigurationen: [English](setup.en.md) · [Português](setup.pt.md).
