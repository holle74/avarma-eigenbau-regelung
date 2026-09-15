# Avarma Eigenbau-Regelung

Eine selbst gebaute, datengetriebene Regelung für die **Hofman Avarma 12 kW Monoblock (R290)** –
über Modbus, ESPHome, Home Assistant und AppDaemon. Entstanden in einem Haus mit Estrich-Fußbodenheizung
(rund 1.000 m Heizrohr, 12 Heizkreise, 15 cm Verlegeabstand), in dem die Anlage im Winter an ihrer
Leistungsgrenze läuft.

Hintergrund, Regellogik und Projektgeschichte stehen im Forumsbeitrag (siehe `docs/forum-wiki-beitrag.md`).
Dieses Repo enthält den Code dazu.

> ⚠️ **Auf eigene Gefahr.** Die Regelung **schreibt Register der Wärmepumpe** (Vorlauf-Sollwert,
> Kompressor-Maximalfrequenz, Lüfter, Abtauung, Ein/Aus). Falsche Adressen oder Skalierungen können die
> Anlage in Störung schicken oder schädigen – die Hofman-Modbus-Tabelle hat mindestens eine Adressfalle
> (siehe unten). Firmwarestände unterscheiden sich. Jeden Registerzugriff an der eigenen Anlage prüfen,
> bevor geschrieben wird. Garantie- und Gewährleistungsfragen klärt jeder selbst.

## Inhalt

| Pfad | Was |
|---|---|
| `esphome/avarma-waermepumpe.yaml` | ESPHome-Konfiguration für einen ESP32-S3 mit RS485 (Modbus RTU, 9600 Baud, Adresse 1): Sensoren, Parameter-Register, schreibbare Stellgrößen, Heartbeat-Watchdog |
| `appdaemon/apps/heizung_vlt_kompressor_regelung.py` | Die eigentliche Regelung: Ein/Aus, Heizkurve auf den Rücklauf, Vorsteuerung des Vorlauf-Sollwerts, Kompressor-Deckel, Lüfter, Not-Abtauung, Übergangs- und Nachtregeln |
| `appdaemon/apps/heizung_lastverteilung.py` | Hydraulische Lastverteilung: drosselt Spender-Räume, wenn der Kompressor am Deckel hängt |
| `appdaemon/apps/heizung_thermometrie.py` | Lernt die Zeitkonstante des Gebäudes (RC-Modell), schreibt nichts an die Anlage |
| `appdaemon/apps/heizung_beobachter.py` | Statuszeile ins Log alle 5 Minuten |
| `appdaemon/apps/apps.yaml` | AppDaemon-Konfiguration der vier Apps |
| `homeassistant/automations.yaml` | Frost-Vorschau aus der Wetterprognose, Interim-Durchflussschutz |
| `docs/forum-wiki-beitrag.md` | Ausführliche Beschreibung (Warum, Aufbau, Regellogik, Geschichte, Fallstricke) |

## Voraussetzungen

- Hofman Avarma (getestet: 12 kW Monoblock R290) mit zugänglicher RS485-Modbus-Schnittstelle
- ESP32-S3 mit RS485-Transceiver (hier ein Waveshare-Board), ESPHome ≥ 2026.4
- Home Assistant mit AppDaemon-App (Community Add-ons)
- Raumthermostate in Home Assistant (hier free@home, 9 Räume) und – für die Lastverteilung – Ventilstellungen je Heizkreis
- Ein **externer Außenfühler** (der eingebaute Avarma-Fühler sitzt oft in der Sonne; hier bis +3,6 K zu warm)
- Eine Wetter-Integration mit Stundenprognose (für das Vorladen vor Frost)
- Optional, aber sehr empfohlen: eine Zeitreihen-Datenbank mit Grafana, um das Verhalten auszuwerten.
  **Nicht mehr das InfluxDB-1.x-Add-on** – es ist seit August 2026 archiviert und aus dem Store entfernt.
  Gepflegte Alternativen unter HAOS: InfluxDB 2 oder VictoriaMetrics (jeweils als Community-App).
  Den Repair-Knopf beim alten Add-on nicht drücken: er deinstalliert es samt Daten.

## Benötigte Helfer in Home Assistant

Anlegen über *Einstellungen → Geräte & Dienste → Helfer*.

| Entity | Typ | Zweck |
|---|---|---|
| `input_boolean.wp_autostart_aktiv` | Schalter | Erlaubt der Regelung, die WP selbst einzuschalten |
| `input_boolean.wp_heizgrenze_aktiv` | Schalter | Erlaubt alle automatischen Abschaltungen (Heizgrenze, Takten, Raum warm, Nacht) |
| `input_number.wp_heizkurve_offset` | Zahl, −3…+3, Schritt 0,5 °C | Parallelverschiebung der Heizkurve, wird von der Regelung angepasst |
| `input_number.wp_prognose_aussentemperatur_minimum_24h` | Zahl, −30…40, Schritt 0,1 °C | Minimum der 24-h-Prognose, befüllt von der Automation |
| `input_number.wp_spender_<raum>_original_soll` (4×) | Zahl, −1…30, Schritt 0,5 °C | Gesicherte Original-Sollwerte der Spender-Räume (−1 = nicht gedrosselt) |
| `input_datetime.wp_taktsperre_bis` | Datum + Uhrzeit | Ende der Sperre nach einer Takt-Abschaltung |
| `sensor.aussentemperatur_avarma_korrigiert` | Template | Externer Außenfühler, ggf. kalibriert |
| `sensor.wp_aussentemperatur_mittel_3h` | Statistik (mean, max_age 3 h) | Grundlage der Heizgrenze |
| `sensor.wp_spreizung_vl_rl` | Template | Vorlauf minus Rücklauf (der Register-Wert „Temperaturdifferenz Hauptkreis“ ist **nicht** die Spreizung) |
| `sensor.wp_raumtemperatur_mittel_eg` | Min/Max (mean) | Mittel der Räume im Erdgeschoss für die Übergangsregeln |
| `sensor.durchfluss_berechnet` | Template | `Pumpenleistung_% × 0,22` in L/min (siehe Beitrag, Abschnitt Durchfluss) |

## Einrichtung – empfohlene Reihenfolge

1. **Nur lesen.** ESPHome flashen, aber zunächst ohne schreibbare `number`/`select`/`switch`-Entities. Alle Werte gegen das Bedienpanel der Anlage prüfen – Adressen *und* Skalierungen.
2. **Beobachter laufen lassen.** `heizung_beobachter` und `heizung_thermometrie` schreiben nichts. Ein paar Tage Daten sammeln.
3. **Schreibende Entities einzeln freischalten** und jede Änderung am Panel gegenprüfen. Besonders: Lüfter-Solldrehzahl (siehe Fallstricke).
4. **Entity-IDs anpassen.** Die Konstanten oben in jeder `.py`-Datei zeigen auf diese Installation.
5. **Regelung starten** mit `input_boolean.wp_autostart_aktiv` = aus und die WP von Hand einschalten. Log beobachten (`VL-Soll`, `Kompressor-Deckel`, `Luefter`).
6. Erst dann Autostart und Heizgrenze einschalten.

Der **Heartbeat-Watchdog** im ESP setzt Vorlauf-Soll und Kompressor-Maximum nach 30 Minuten ohne Befehl auf 32 °C / 90 Hz zurück. So bleibt die Anlage auch bei Ausfall von Home Assistant heizfähig.

## Wichtige Fallstricke (Kurzfassung)

- **Zwei Adressspalten in der Hofman-Modbus-Tabelle.** „Decimal“ ist die echte Modbus-Adresse, „Decimal+1“ nur die Panel-Anzeige. Hier lag P114 deshalb auf 8303 – das ist P115, der Vorlauf-Übertemperaturschutz.
- **Lüfter-Solldrehzahl P72 (8262)** speichert Drehzahl ÷ 10. Beim ESPHome-`number` ist `multiply` gegenüber `sensor`-Filtern **invertiert**: `multiply: 0.1` ergibt echte U/min in der Entity.
- **P2 (Vorlauf-Soll) steht nach einem Anlagenneustart auf 45 °C.**
- **Betriebsmodus (4097) vor jedem Test prüfen** – stand hier einmal auf „Kühlen“.
- **Ein Werksreset (P87)** hat hier 6 Parameter verändert (u. a. Warmwasserfunktion eingeschaltet). P87 ist deshalb bewusst nicht als Entity angelegt.
- **Der Durchflussmesser (4368)** lieferte hier nie plausible Werte.
- **AppDaemon `set_state`** lässt Attribute mit `0`, `False` oder `None` stillschweigend weg – Werte, die legitim 0 werden können, als String setzen.

Ausführlich: `docs/forum-wiki-beitrag.md`.

## Entstehung

Entwickelt von einem Avarma-Besitzer ohne Programmierhintergrund zusammen mit **Claude** (KI von Anthropic):
Messdaten auswerten, Modbus-Tabellen und Handbücher lesen, Code schreiben und testen. Die Entscheidungen –
Komfortziele, Prioritäten, was die Anlage darf – liegen beim Betreiber.

## Lizenz

Siehe `LICENSE`.
