# Hofman Avarma Monoblock – Wiki: Modbus, Parameter, Erfahrungen (plus eine eigene Regelung über Home Assistant)

Hallo zusammen,

dieser Beitrag soll eine Sammelstelle für alles rund um die **Hofman Avarma** werden: Modbus-Anbindung, Parameter, Messwerte, Eigenheiten und Fallstricke. Er ist als **Wiki** angelegt – wer eine Avarma hat, kann direkt ergänzen oder korrigieren. Besonders wertvoll sind **eure Parameterwerte und Erfahrungen**, denn jede Anlage und jeder Firmwarestand kann anders sein.

**Aufbau:**
- **Teil A (Abschnitte 1–5): die Avarma selbst** – Anlage, Modbus, Parameter, Messwerte, Fallstricke. Das gilt unabhängig davon, wie ihr regelt.
- **Teil B (Abschnitte 6–13): meine eigene Regelung** über ESPHome, Home Assistant und AppDaemon. Das ist mein Weg, nicht der einzige – **für Ideen, Kritik und Verbesserungsvorschläge bin ich ausdrücklich offen.**

---

# Teil A – Die Avarma

## 1. Meine Anlage

- **Hofman Avarma Version 2, 12 kW, 230 V, Monoblock (R290)**
- **Estrich-Fußbodenheizung, nicht optimal verlegt:** rund **1.000 m Heizrohr** auf **12 Heizkreise**, **15 cm Verlegeabstand**. Das braucht höhere Vorlauftemperaturen als eine eng verlegte FBH und reagiert sehr träge.
- **Die Avarma heizt bei mir nur.** Warmwasser läuft nicht über sie, es gibt keinen Speicher an der Anlage (P63 = 0). Alles hier bezieht sich auf den Heizbetrieb.
- **Im Winter am Leistungslimit.** Ab etwa −5 °C Außentemperatur hat sie keine Reserve mehr, ein ausgekühltes Haus wieder hochzuheizen.

**Eure Anlagen** – bitte ergänzen, dann lassen sich Werte und Erfahrungen besser einordnen:

| Wer | Modell / Version | Leistung / Spannung | Wärmeabgabe | Besonderheiten |
|---|---|---|---|---|
| Themenstarter | Avarma V2 Monoblock, R290 | 12 kW / 230 V | Estrich-FBH, 12 Kreise | nur Heizen, Durchflussmesser defekt (siehe 4.3) |
| | | | | |

## 2. Modbus-Anbindung

- **ESP32-S3 mit RS485-Transceiver** (Waveshare-Board), direkt an der Modbus-Schnittstelle der Avarma. **Modbus RTU, 9600 Baud, Slave-Adresse 1.**
- **ESPHome** liest praktisch alle relevanten Register (Temperaturen, Drücke, Kompressor, Lüfter, EEV, Fehlercodes, alle Parameter P00–P136). Die komplette Konfiguration liegt im Repo (Abschnitt 13) – auch nützlich, wenn ihr nur mitlesen und nichts regeln wollt.
- Grundlage ist die **Hofman-Modbus-Tabelle**. Sie ist nicht durchgängig verlässlich, die gefundenen Abweichungen stehen in Abschnitt 5.

**Nützliche Register** (an meiner Anlage geprüft):

| Register | Inhalt | Hinweis |
|---|---|---|
| 4096 | Ein/Aus | |
| 4097 | Betriebsmodus | vor jedem Test prüfen – „Kühlen“ ist schnell übersehen |
| 4098 | P2 Vorlauf-Soll | steht nach einem Neustart der Anlage auf 45 °C |
| 4103 | Abtauung erzwingen | |
| 4368 | Durchfluss | bei mir unbrauchbar (siehe 4.3) |
| 4369 | „Temperaturdifferenz Hauptkreis“ | **nicht** die VL/RL-Spreizung |
| 4390 / 4391 | Fault State 0 (E01–E16) / 1 (E17–E32) | E15 = Bit 14 → Anzeigewert 16384 |
| 8235 | P45 Kompressor-Maximalfrequenz | Parameterregister |
| 8261 / 8262 | P71 / P72 Lüfter manuell + Solldrehzahl | P72 speichert Drehzahl ÷ 10 |

## 3. Parameter

### 3.1 Bei mir geändert – und warum

Werte am 15.09.2026 an der Anlage ausgelesen:

| Parameter | Werk | Bei mir | Warum |
|---|---|---|---|
| **P114** Frequenzreduktion bei erreichtem VL-Soll | 2 % | **3 %** | Mit der Werkseinstellung reagiert die Anlage zu träge und taktet. Mehr Spielraum zum Herunterregeln lässt sie durchlaufen, statt abzuschalten. |
| **P46** Kompressor-Mindestfrequenz | 35 Hz | **25 Hz** | Mehr Modulationsbereich nach unten. In der Übergangszeit ist der Wärmebedarf oft kleiner als die Mindestleistung – je tiefer sie liegt, desto seltener taktet die Anlage. |
| **P86** Abtau-Differenz ΔT1 (Außen ≥ −7 °C) | 8,0 K | **5,0 K** | Abtauung früher zulassen, nach einer Vereisung mit viel zu später Abtauung (siehe 4.4). **P91** (dieselbe Differenz unter −7 °C) steht bewusst weiter auf 8,0 K. |
| **P63** Warmwasserfunktion | 1 | **0** | Die Anlage heizt nur, es gibt keinen Speicher. |
| **P68** Durchflussfühler-Typ | 1 (Durchflussmesser) | **0 (Strömungsschalter)** | Vorübergehend: Der Durchflussmesser ist defekt, die Umstellung hat der Hersteller freigegeben (siehe 4.3). |
| **P71 / P72** Lüftersteuerung / Solldrehzahl | Automatik | **Manuell, 400–900 U/min** | Lärm. Meine Regelung führt die Drehzahl nach der Verdampfertemperatur nach (siehe 8.4). |

### 3.2 Unverändert, aber wichtig

- **P41** Ölrückführungsfrequenz **50 Hz** – siehe Ölrückführung in 4.2.
- **P58** Regel-Temperaturdifferenz der Pumpe **5 K** – auf diese Spreizung regelt die Umwälzpumpe.
- **P59** Pumpen-Mindestdrehzahl **80 %** – die Pumpe regelt also nur zwischen 80 und 100 %, bei Teillast fällt die Spreizung dann unter die 5 K aus P58.
- **P114** ist ein Modulations-*Spielraum*: kleiner Wert = Kompressor darf kaum herunter, trifft kleine Lasten nicht → taktet.

### 3.3 Werksreset P87 – Vorsicht

Der Werksreset hat bei mir geändert: P45 70→90, P46 25→35, **P63 0→1 (Warmwasser eingeschaltet, obwohl kein Speicher da ist!)**, P72 40→0, P86 5,0→8,0 K, P114 3→2. Danach alles zurückstellen. Der Reset überlebt einen Netzausfall. P87 habe ich deshalb in ESPHome bewusst **nicht** als Entity angelegt – ein Fehlklick würde die ganze Parametrierung verwerfen.

### 3.4 Eure Werte

Bitte ergänzen – gerade bei den Parametern, die Takten, Pumpe und Abtauung bestimmen:

| Parameter | Werk | Themenstarter | | |
|---|---|---|---|---|
| P41 Ölrückführungsfrequenz | 50 Hz | 50 Hz | | |
| P46 Kompressor-Mindestfrequenz | 35 Hz | 25 Hz | | |
| P58 Regel-ΔT Pumpe | 5 K | 5 K | | |
| P59 Pumpen-Mindestdrehzahl | 80 % | 80 % | | |
| P86 Abtau-Differenz ΔT1 | 8,0 K | 5,0 K | | |
| P91 Abtau-Differenz unter −7 °C | 8,0 K | 8,0 K | | |
| P114 Frequenzreduktion | 2 % | 3 % | | |

## 4. Messwerte und Verhalten der Anlage

### 4.1 Effizienz über die Kompressorfrequenz

Gemessen an meiner Anlage (August, stabile Phasen – noch wenige Punkte, Trend aber eindeutig):

| Frequenz | 30–39 Hz | 40–49 Hz | 50–59 Hz | 60–69 Hz | 80–90 Hz |
|---|---|---|---|---|---|
| COP | 6,3 | 5,8 | 5,2 | 4,8 | 4,2 |

Teillast ist rund 50 % effizienter – und deutlich leiser. Heizleistung grob **0,4 kW + 0,14 kW je Hz**, nach oben abflachend.

### 4.2 Wann die Avarma stoppt

- **Vorlauf 1 K oder mehr über dem Sollwert → sofortiger Kompressorstopp.** In einer Woche Übergangszeit war das bei 10 von 12 solchen Fällen so, darunter nie. Wer P2 per Modbus absenkt, sollte das wissen (siehe 8.2).
- **Ölrückführung:** Nach längerem Lauf mit niedriger Frequenz springt der Kompressor für unter eine Minute auf 50 Hz (P41). Der Vorlauf schießt dabei über den Sollwert – und die Anlage stoppt.
- **Übergangszeit:** Selbst die Mindestfrequenz (25 Hz) liefert oft mehr, als das Haus abnimmt. Dann taktet jede Wärmepumpe – das ist Physik, kein Defekt.

### 4.3 Durchfluss und E15

Der Durchflussmesser meiner Anlage (Register 4368) hat **seit der Inbetriebnahme** keine brauchbaren Werte geliefert: entweder 0 oder 119–149 L/min. Nachgemessen waren es rund **23 L/min bei 100 % Pumpenleistung**.

Deshalb rechne ich den Durchfluss aus der Pumpenleistung: **Durchfluss [L/min] = Pumpenleistung [%] × 0,22**. Daraus die thermische Leistung: **Durchfluss × Spreizung × 0,0698 = kW** (4,186 kJ/kg·K ÷ 60). Das ist kein Messwert, sondern das, was die Pumpe fördern *soll* – für COP-Auswertung und Plausibilitätsprüfung reicht es gut.

Ende August kam dann **E15 (Wasserdurchfluss)**, reproduzierbar kurz nach jedem Kompressorstart. Nach einer ausführlichen Messreihe (Rohdaten im 10-s-Raster, alle Softwareursachen ausgeschlossen) war klar: **der Durchflussmesser ist defekt**, die Hydraulik in Ordnung. Der Hersteller hat das anerkannt, das Ersatzteil kommt auf Kulanz, und bis dahin hat er die Umstellung auf **P68 = 0 (Strömungsschalter)** freigegeben. Damit entfällt die Mindestdurchfluss-Prüfung gegen P61 – ich habe dafür einen Ersatzschutz in Home Assistant (siehe 8.8).

**Frage an euch:** Liefert euer Durchflussmesser plausible Werte?

### 4.4 Abtauung und Außenfühler

- Bei mir hat die Avarma einmal **38 Minuten zu spät** abgetaut, obwohl alle Startbedingungen (P27/P28/P29/P85/P86) erfüllt waren – die Lamelle sackte von −3,5 auf −13 °C. Die Ursache ist bis heute ungeklärt. **Beim ersten Frost live mitlesen.**
- **Der eingebaute Außenfühler** sitzt bei mir in der Sonne und lag bis zu **+3,6 K zu hoch**, bei vereister Lamelle bis zu 3,9 K zu tief. Die Anlage nutzt ihn intern trotzdem für ihre Abtau-Entscheidung.

## 5. Fallstricke bei Modbus und ESPHome

[details="Modbus und Hofman-Tabelle"]
- **Zwei Adressspalten:** „Decimal“ = echte Modbus-Adresse, „Decimal+1“ = nur Panel-Anzeige. Immer „Decimal“ nehmen und gegen die Basisadresse gegenrechnen (0x2000 = 8192 für die Parameter).
- **Fehlercode-Register:** „Fault State 0“ (E01–E16) liegt auf **4390**, „Fault State 1“ (E17–E32) auf **4391**. 4389 ist ein Temperaturregister.
- **P114 lag bei mir zunächst auf der Adresse von P115** (Vorlauf-Übertemperaturschutz) – ein Zug daran hätte die Anlage in Dauerstörung geschickt. Jede Adresse einzeln prüfen.
- **4369 „Temperaturdifferenz Hauptkreis“ ist nicht die VL/RL-Spreizung** (zeigte 0–1,8 K bei echten 4,5–6 K). Spreizung selbst rechnen.
- **Funktionscode 3 liest höchstens 125 Register am Stück.** ESPHome fasst benachbarte Register zusammen; ein zu großer Block scheitert komplett und reißt alle Werte darin mit (`force_new_range` hilft).
- **Der ESP behält bei fehlender Modbus-Antwort die letzten Werte.** Eine stromlose Anlage sieht in Home Assistant aus wie eine ruhig laufende.
- **Parameterregister** sinnvollerweise nur alle paar Minuten lesen (`skip_updates`). Direkt nach dem Schreiben zeigt der Lesewert noch den alten Stand – kein Fehler.
- P45 ist ein Parameterregister – ob die Avarma jeden Schreibvorgang ins EEPROM sichert, weiß ich nicht. Ich schreibe es deshalb nur 2–4-mal pro Tag.
[/details]

[details="Skalierungen und ESPHome"]
- **P72 Lüfter-Solldrehzahl** speichert Drehzahl ÷ 10 (Tabelle: „display value × 10“). **P60** vermutlich ebenso. Schreibt man 400 statt 40, fordert man 4.000 U/min an und die Anlage fällt auf ihre Automatik zurück.
- **Beim ESPHome-`number` ist `multiply` invertiert** gegenüber `sensor`-Filtern: Anzeigewert = Rohwert ÷ multiply. Für Rohwert 40 = 400 U/min braucht es also `multiply: 0.1`, für ein Register mit Faktor 0,1 °C `multiply: 10`.
- **P59 Pumpen-Mindestdrehzahl:** Rohwert in 10-%-Schritten (8 = 80 %).
[/details]

---

# Teil B – Meine eigene Regelung

Vorweg, damit das klar ist: **Ich bin kein Programmierer.** Die Regelung ist zusammen mit **Claude** entstanden, einer KI von Anthropic (mehr dazu in Abschnitt 12). Sie läuft seit dem Sommer und wird laufend nachgeschärft – **wer Ideen hat, wie man etwas besser lösen kann: immer her damit.**

## 6. Warum überhaupt eine eigene Regelung?

Kurz gesagt: Die eingebaute Heizkurve der Avarma kommt mit meinem Haus nicht gut klar. Eine statische Heizkurve reagiert nur auf die *aktuelle* Außentemperatur. Mit dem trägen Estrich ist das bei einer Frostnacht Stunden zu spät. Früher habe ich morgens von Hand hochgedreht, wenn abends Frost angesagt war. Das sollte die Regelung selbst können. Dazu soll die Anlage **so leise wie möglich** laufen – Lüfter und Kompressor nicht höher als nötig, nachts erst recht.

**Das Ziel:** Eine Steuerung, die
1. das thermische Verhalten des Hauses **aus Messdaten lernt**,
2. **vorausschauend** heizt (Wetterprognose, Estrich als Speicher vorladen),
3. die Anlage **im effizienten Teillastbereich** hält und Takten vermeidet,
4. bei Engpass **Wärme zu den wichtigen Räumen umleitet**,
5. dabei **so leise wie möglich** bleibt – und Komfort vor Stromsparen stellt.

Ehrlicher Zwischenstand: Punkt 3 bis 5 laufen. Beim Lernen ist ein Teil umgesetzt, die vollständig vorausschauende Regelung ist das Ziel für den kommenden Winter (Abschnitt 9).

## 7. Aufbau

```
 Außenfühler (extern) ─┐
 Wetterprognose ───────┤
 9 Raumthermostate ────┼──► Home Assistant ──► AppDaemon (Python)
 12 Ventilstellungen ──┤         ▲                   │
                       │         │                   │ Sollwerte
 Avarma ◄── RS485/Modbus ──► ESP32-S3 (ESPHome) ◄────┘
   │                          (Heartbeat-Watchdog, harte Grenzen)
   ▼
 Estrich-FBH, 12 Kreise ──► Rücklauf schließt den Regelkreis
```

- **Home Assistant** mit **AppDaemon**: Hier läuft die eigentliche Logik in Python.
- **Raumthermostate** (9 Räume) und ein Heizungsaktor mit **12 Ventilstellungen**.
- **Externer Funk-Außenfühler** statt des eingebauten (siehe 4.4).
- **Wetterprognose** (stündlich, 24 h) für das Vorladen vor Frost.
- **InfluxDB + Grafana** für alle Messwerte – ohne die Auswertungen wäre nichts davon entstanden.

> ⚠️ **Wer neu anfängt: nicht mehr auf das InfluxDB-Add-on setzen.** Das bisherige Community-Add-on basiert auf InfluxDB 1.x, wurde im **August 2026 archiviert und aus dem Store genommen** und bekommt keine Updates mehr. **Den angebotenen „Reparieren“-Knopf nicht drücken** – er deinstalliert das Add-on samt der gesamten Historie. Gepflegte Alternativen für HAOS sind z. B. **InfluxDB 2** oder **VictoriaMetrics** (versteht das InfluxDB-Schreibprotokoll, Grafana bleibt nutzbar).

**Was die Regelung an der Avarma verstellt – mehr nicht:** Ein/Aus (4096), P2 Vorlauf-Soll (4098), P45 Kompressor-Maximalfrequenz (8235), P71/P72 Lüfter (8261/8262), Abtauung erzwingen (4103). Dazu die Solltemperaturen einzelner Raumthermostate (Lastverteilung). Alles andere macht der eingebaute Regler der Avarma weiterhin selbst – das ist Absicht.

**Sicherheitsnetz im ESP:** Kommt 30 Minuten lang kein Befehl aus Home Assistant (Heartbeat), setzt der ESP Vorlauf-Soll auf 32 °C und Kompressor-Maximum auf 90 Hz zurück. Grenzwerte stehen hart an den Entities (Vorlauf-Soll max. 45 °C, Kompressor 50–120 Hz).

## 8. Die Regellogik – verständlich erklärt

Die Regelung arbeitet im 5-Minuten-Takt. Die wichtigsten Bausteine:

### 8.1 Geregelt wird auf den Rücklauf, nicht auf den Vorlauf

Der **Rücklauf** zeigt, was das Haus tatsächlich an Wärme abnimmt. Die Avarma hat aber kein Rücklauf-Soll-Register – also ist der Rücklauf die Führungsgröße und der Vorlauf-Sollwert das „Stellrad“.

**Heizkurve (Rücklauf-Ziel über Außentemperatur), stückweise linear:**

| Außentemperatur | Rücklauf-Ziel |
|---|---|
| −5 °C | 38,5 °C |
| 0 °C | 35,0 °C |
| +15 °C und wärmer | 28,0 °C |

Unter −5 °C wird weiter extrapoliert, gedeckelt bei 40 °C. Die Stützpunkte stammen aus meinen Vorlauf-Erfahrungswerten aus zwei Wintern (−5 °C → 45 °C VL, 0 °C → 39,5 °C, +8 °C → 35 °C), umgerechnet über die gemessene Spreizung. Eine einzelne Gerade hat den kalten Rand um 1–2 K unterschätzt – genau die Lücke, die ich früher von Hand ausgeglichen habe.

Auf die Kurve kommen:
- **Tagesbonus +1 K** (07–22 Uhr): Estrich tagsüber leicht vorladen.
- **Vorladen vor Frost:** Liegt das Minimum der 24-h-Prognose unter 8 °C, steigt das Ziel tagsüber um `(8 − Prognose) × 0,4 K`, maximal +4 K. Bei −5 °C angesagt also +4 K schon am Tag davor.
- **Lernender Offset** (±3 K, siehe 9.1).
- **Kaltstart-Rampe:** Nach dem Einschalten startet das Ziel bei 28 °C und steigt um 1 K je 15 min.

### 8.2 Vorlauf-Sollwert per Vorsteuerung

**VL-Soll = Rücklauf-Ziel + Spreizung + Korrektur**, begrenzt auf 30–45 °C.

- Die **Spreizung** wird live gemessen (Vorlauf minus Rücklauf, wenn der Kompressor läuft und der Wert plausibel ist), sonst 5 K. Die Pumpe regelt über **P58 = 5 K** selbst auf diese Differenz.
- Die **Korrektur** ist ein langsamer Nachregler: ±0,5 K je 15 min bei bleibender Abweichung, maximal ±3 K.
- Geschrieben wird nur bei Änderung um ganze Grad (Abweichungen ≥ 3 K sofort, sonst höchstens alle 10 min).
- **Absenken ohne Kompressorstopp** (siehe 4.2): P2 geht nur in ganzen Grad – bei laufendem Kompressor wird deshalb nur so weit abgesenkt, dass der Vorlauf höchstens 0,8 K darüber liegt. Sitzt er genau auf dem Sollwert, wartet die Regelung, bis er von selbst etwas fällt, nach 30 min senkt sie trotzdem um 1 K.

**Warum so und nicht einfach „VL-Soll hoch/runter in Schritten“?** Das hatte ich vorher – und es ging schief (siehe 10., 12.09.). Solange der Sollwert über dem tatsächlichen Vorlauf „parkt“, bremst er gar nichts. Die Avarma fährt dann bis zum Kompressor-Deckel, und das Absenken in 1-K-Schritten brauchte zwei Stunden, bis es überhaupt wirkte. Mit der Vorsteuerung liegt der Sollwert immer knapp beim Vorlauf, und die **Avarma moduliert selbst** – das kann ihr eingebauter Regler nämlich gut.

### 8.3 Kompressor-Deckel nach Außentemperatur

Die Maximalfrequenz P45 folgt einer Kennlinie im 5-Hz-Raster – Grund ist der COP-Verlauf aus 4.1:

| Außentemperatur | Deckel |
|---|---|
| −5 °C und kälter | 90 Hz |
| +5 °C | 65 Hz |
| +15 °C und wärmer | 50 Hz |

- **Untergrenze 50 Hz:** P41 (Ölrückführungsfrequenz) steht auf 50 Hz. Der Deckel geht nie darunter, damit die Ölrückführung nicht behindert wird.
- **Winter-Eskalation:** Hängt der Kompressor 60 min am Deckel **und** liegt der Rücklauf 60 min unter Ziel, geht der Deckel um +5 Hz je 30 min hoch – bis 90 Hz, **95 Hz nur bei −5 °C und kälter**. Die letzten 5 Hz sind Frostreserve, kein Alltagswerkzeug.
- **Vereisungssperre:** Liegt der Verdampfer unter 1 °C und die Differenz Außenluft–Verdampfer über 7 K, wird nicht eskaliert. Mehr Frequenz kauft dann Eis statt Wärme.

### 8.4 Lüfter: so leise wie möglich

Der Lüfter läuft im **manuellen Modus** (P71) mit eigener Solldrehzahl (P72), 400–900 U/min.
- **Grundsatz:** so niedrig wie möglich, solange der **Verdampfer ≥ 1 °C** bleibt. 1 °C ist eine **Untergrenze**, kein Sollwert – liegt der Verdampfer bei 4 °C und der Lüfter auf 400 U/min, ist das genau richtig.
- **Hoch schnell:** unter 1 °C in jedem Zyklus, 150 U/min je Kelvin Unterschreitung (100–300 U/min pro Schritt). Nähert sich der Verdampfer der Abtau-Startschwelle (−3 °C) auf 1 K, sofort Volllast.
- **Runter behutsam:** über 1,5 °C nur 50 U/min alle 10 min, nicht in den 15 min nach einer Abtauung.

### 8.5 Not-Abtauung

Wegen der verspäteten Abtauung aus 4.4 taut die Regelung im Zweifel selbst ab (Register 4103), aber nur wenn **alle vier** Bedingungen erfüllt sind: Verdampfer unter −3 °C **und** Differenz Außenluft–Verdampfer über 7 K, das seit 20 min, Lüfter bereits auf Volllast, letzte Abtauung mindestens 60 min her.

### 8.6 Ein- und Ausschalten

**Einschalten**, wenn beides zutrifft:
- Außentemperatur ≤ 16,5 °C (bei angesagtem Frost unter 8 °C zählt das Prognose-Minimum – damit sie an einem milden Tag vor der Frostnacht anläuft)
- Raum kalt genug: in der Übergangszeit **EG-Mittel ≤ 20,0 °C**, sonst **Bad ≤ 18,5 °C** (das Bad ist bei uns der am schwersten zu heizende Raum)

**Heizgrenze (ganzjährig):** Aus, wenn das **3-h-Mittel** der Außentemperatur ≥ 18,5 °C ist, keine kalte Nacht angesagt ist und sie mindestens 2 h läuft. Die 2 K zwischen Ein (16,5, Momentanwert) und Aus (18,5, Mittel) verhindern das Takten um die Schwelle.

**Übergangszeit (September–November, März–Mai)** – zusätzlich:

| Regel | Auslöser | Danach |
|---|---|---|
| Raum warm genug | EG-Mittel ≥ 21 °C, 30 min am Stück (nicht bei Frostprognose) | Neustart bei EG ≤ 20 °C |
| Anlage taktet | 2 Kompressorstarts in 45 min (Abtauungen und selbst verursachte Stopps zählen nicht, siehe unten) | 3 h Sperre |
| Nachtsperre 22–10 Uhr | kein Start; eine laufende Anlage schaltet ab, sobald EG ≥ 20,5 °C | Ausnahme: Frostprognose ≤ 2 °C oder EG ≤ 19 °C |

Lieber ein paar Stunden aus und den Estrich puffern lassen als alle 15 Minuten neu starten (siehe 4.2).

**Nicht jeder Stopp ist Takten.** In der Auswertung 17.–24.09. kamen 10 von 13 Kompressorstopps mitten im Lauf von der eigenen Vorsteuerung (Absenkung) und 3 von der Ölrückführung – beide Mechanismen stehen in 4.2. Alle drei Takt-Abschaltungen dieser Woche enthielten mindestens einen solchen Stopp. Seitdem zählen Stopps bis 5 min nach einer eigenen Absenkung und bis 3 min nach dem Sprung auf 50 Hz nicht mehr mit – jeder Stopp steht mit Grund im Log.

### 8.7 Hydraulische Lastverteilung

Wenn der Kompressor am Deckel hängt, reicht die Wärme nicht für alle Kreise. Dann werden **Spender-Räume** gedrosselt, damit mehr zu den **Prioritäts-Räumen** fließt:
- **Priorität:** Bad → Dusche → Wohnzimmer → Büro → Ankleide (werden nie gedrosselt)
- **Spender** in dieser Reihenfolge: Schlafzimmer (nicht unter 18 °C) → Keller → Flur → Yoga (nicht unter 20 °C)
- **Auslöser:** Prioritätsraum mit Ventil ≥ 90 % und ≥ 0,3 K unter Soll, 15 min lang – **und** der Kompressor am Deckel. Ohne diese letzte Bedingung würde dauernd gedrosselt, denn bei milder Witterung erreicht die FBH das Bad-Ziel nie, egal wie weit andere Ventile zu sind.
- −0,5 K je 10 min, bis das Spender-Ventil bei ~30 % steht. Die Original-Sollwerte liegen in Helfern und werden zurückgesetzt, sobald der Engpass vorbei ist.
- **Übergangsmodus** (Schalter `wp_uebergangsmodus`): Dann ist das **Wohnzimmer der einzige Spender** (nicht unter 21 °C) und fällt dafür aus dem Vorrang. Grund: Im Übergang heizt das Haus aus dem Kaltstart hoch, das Bad verfehlt sein bewusst hohes Ziel ohnehin, und die normale Lastverteilung hatte binnen zwei Stunden Keller, Flur und Yoga bis an ihre Untergrenze gezogen – viel Kälte für wenig Wirkung.

### 8.8 Schutzschicht, unabhängig von der Regelung

- **Heartbeat-Watchdog im ESP** (siehe 7.)
- **Zwei Handschalter:** Autostart erlaubt/gesperrt, automatische Abschaltungen erlaubt/gesperrt
- **Interim-Durchflussschutz** (siehe 4.3): Aus bei laufendem Kompressor und Spreizung > 10 K oder Pumpe < 30 %

## 9. Was schon lernt – und was noch kommt

### 9.1 Heute im Einsatz
- **Lernender Heizkurven-Offset:** Alle 5 h wird die Kurve um 0,5 K verschoben, wenn die Räume dauerhaft zu kalt oder zu warm sind (±3 K), gemessen am Bad. **In der Übergangszeit ausgesetzt:** Dort läuft die WP nur zwischen EG 20 und 21 °C an und aus – ein Offset gegen 21 °C sah praktisch immer „zu kalt“ und konnte nur steigen (1,0 → 3,0 K in drei Tagen, Rücklauf-Ziel 32–34 °C bei 11–17 °C Außentemperatur). Ebenfalls ausgesetzt, wenn der Kompressor am Limit läuft – dann ist es ein Leistungs-, kein Kurvenproblem.
- **Gebäude-Thermometrie:** Ein RC-Modell schätzt aus nächtlichen Abkühlphasen (00–05 Uhr, keine Sonne, keine Heizung, kein Lüften) die **Zeitkonstante des Hauses**. Das ist ausdrücklich vorläufig – im Sommer ist das Temperaturgefälle zu klein. Die App stuft sich selbst erst ab 15 K Gefällespanne als „belastbar“ ein und greift bis dahin in **keinen** Regelkreis ein.

### 9.2 Das Ziel für den Winter
- Die fest verdrahtete Vorlade-Formel durch eine **Auskühlprognose aus dem gelernten Gebäudemodell** ersetzen: „Heute Nacht −6 °C, das Haus verliert bis morgen 7 K – also jetzt so viel einlagern.“
- **Nachtbetrieb** leiser machen (Vorlauf, Lüfter, Eskalation nachts begrenzen) – die Schwellen will ich im ersten kalten Winter nach Gehör einstellen.
- **Takten im Teillastbereich** weiter reduzieren (P46/P114 als Hebel).

## 10. Projektgeschichte – und was ich dabei gelernt habe

- **Juli:** Idee, alle Werte in InfluxDB loggen. ESPHome-Anbindung ausgebaut. Durchfluss- und COP-Berechnung repariert (hatten wochenlang tote Entities referenziert).
- **23.07. – erster Live-Test.** Zwei Überraschungen: Der **Betriebsmodus stand auf „Kühlen“** (Vorlauf fiel statt zu steigen), und der **Lüfter reagierte nicht**, weil P72 Drehzahl ÷ 10 speichert.
- **24.07.–03.08.:** Umstellung auf die Rücklauf-Heizkurve, stückweise Kurve, Vorladen vor Frost. Erkenntnis aus den Daten: Mehr Durchfluss geht nicht (Pumpe am Anschlag), Vorlauf 45 °C und Bad-Kreis 100 % offen – **die einzige verbleibende Freiheit fürs Bad ist die zeitliche**, also vorladen.
- **18.08.:** Alle Register systematisch gegen die Hofman-Tabelle geprüft (Funde in Abschnitt 5).
- **22.08.:** COP über Frequenz gemessen → Kompressor-Deckel. Gebäude-Thermometrie gestartet. Takten bei 16–18 °C Außentemperatur erstmals gesehen.
- **24.08.:** Vereisung mit 38 min verspäteter Abtauung → Not-Abtauung und Vereisungssperre.
- **24.–25.08.: E15.** Anlage stand. Werksreset (P87) zur Fehlersuche – hat 6 Parameter verstellt (siehe 3.3). Messprotokoll an den Hersteller.
- **29.08.:** Ersatzteil auf Kulanz zugesagt.
- **12.09.:** Freigabe P68 = 0, Kabel auf der Platine umgesteckt, Wiederanlauf. Heizgrenzen-Abschaltung gebaut. **Rücklauf lief 2 K über Ziel** – der Vorlauf-Sollwert stand nach dem Anlagenneustart auf 45 °C und die Schrittlogik brauchte zwei Stunden zum Absenken. Drei Varianten durchgerechnet (Schritte, Frequenz regelt, Vorsteuerung) – die Vorsteuerung hat gewonnen.
- **13.09.:** Vorsteuerung und Übergangsregeln live.
- **14.09. – erste Nacht mit den neuen Regeln:** Vorsteuerung sauber (Rücklauf ±1 K, kein Überschwingen). Aber die Anlage lief von 20:20 bis 05:36, weil die Nachtsperre nur den Start verhinderte. Nachgeschärft: Nachtabschaltung ab EG 20,5 °C, Takt-Erkennung schon bei 2 Starts in 45 min.
- **17.09.:** Laufzeit der WP in einem Helfer statt aus `last_changed` (ein HA-Neustart ließ eine laufende WP wie frisch gestartet aussehen). Übergangsmodus der Lastverteilung.
- **25.09. – Auswertung der ersten Übergangswoche:** Räume warm, Rücklauf ruhig, aber drei Takt-Abschaltungen – verursacht von der eigenen Regelung und der Ölrückführung, nicht von zu viel Leistung. Dazu kletterte der lernende Offset wie eine Ratsche auf +3 K. Beides behoben, siehe 8.2, 8.6 und 9.1.

**Meine wichtigsten Lehren:**
1. **Erst messen, dann regeln.** Fast jede gute Entscheidung kam aus einer Auswertung, fast jeder Fehler aus einer Annahme.
2. **Die eingebaute Regelung der Avarma ist gut** – man muss ihr nur die richtigen Sollwerte geben, statt sie zu ersetzen.
3. **Jeden Registerwert am Panel gegenprüfen.** Die Doku ist nicht durchgängig verlässlich.
4. **Schutzmechanismen gehören in den ESP**, nicht nur in Home Assistant.
5. **Regeln immer als Paar denken:** Wer ein Einschaltkriterium ändert, muss das Ausschaltkriterium mit anschauen – sonst arbeiten sie gegeneinander.
6. **Bevor man ein Symptom bekämpft, prüfen, ob man es selbst verursacht.** Das „Takten“ der Übergangszeit war zum großen Teil meine eigene Regelung.

## 11. Fallstricke in Home Assistant und AppDaemon

[details="Home Assistant / AppDaemon"]
- **AppDaemon lädt eine geänderte App sofort neu**, ein ESPHome-Flash dauert Minuten. Bei gekoppelten Änderungen (z. B. Skalierung) **erst flashen, dann den Python-Code ändern.**
- Ein Reload setzt Zustände im Speicher zurück. Alles, was einen Neustart überleben muss, gehört in Helfer.
- **`set_state` lässt Attribute mit 0, False oder None weg.** Werte, die legitim 0 werden können, als String setzen.
- `run_every` mit sofortigem Start feuert nicht zuverlässig – Start in die Zukunft legen.
- **Datenbank:** Das InfluxDB-1.x-Add-on ist seit August 2026 abgekündigt (siehe 7.). Vor jeder Umstellung ein Backup mit der alten Datenbank anlegen.
[/details]

## 12. Die Rolle der KI

Weil ich danach sicher gefragt werde: Die Aufteilung war ziemlich klar.

**Ich** kenne das Haus, die Anlage und meine Erfahrungswerte aus zwei Wintern. Ich habe entschieden, was Priorität hat (Komfort vor Sparen), welche Räume wichtig sind, was die Anlage darf – und ich habe am Panel, an der Platine und mit dem Hersteller gearbeitet.

**Claude** hat Messdaten aus InfluxDB ausgewertet, die Hofman-Modbus-Tabelle und die Handbücher Register für Register gelesen, Varianten durchgerechnet, den gesamten Code geschrieben und vor jedem Einspielen offline getestet – und mir immer wieder erklärt, *warum* etwas so ist. Viele der Fallstricke oben hat die KI in den Daten gefunden, bevor sie Schaden anrichten konnten. Fehler gab es trotzdem, auf beiden Seiten – die stehen in Abschnitt 10.

## 13. Code und Mitmachen

**Repo:** https://github.com/holle74/avarma-eigenbau-regelung

Enthalten: ESPHome-Konfiguration, die vier AppDaemon-Apps, die zwei Automationen und eine Liste aller benötigten Helfer. Private Angaben sind entfernt, Entity-IDs müsst ihr an eure Installation anpassen.

> ⚠️ **Auf eigene Gefahr.** Die Regelung schreibt Register der Wärmepumpe. Jede Anlage und jeder Firmwarestand kann abweichen. Bitte erst nur lesen, jeden Wert am Panel gegenprüfen und schreibende Entities einzeln freischalten. Garantiefragen klärt jeder selbst.

**Mitmachen – zur Avarma (Teil A):** Tragt eure Anlage in die Tabelle in Abschnitt 1 ein und eure Parameter in 3.4. Besonders interessieren mich **Erfahrungen mit dem Abtauverhalten bei Frost**, ob euer **Durchflussmesser** plausible Werte liefert und jede **Abweichung von der Hofman-Tabelle**.

**Mitmachen – zur Regelung (Teil B):** Ich bin für Ideen offen. Wie geht ihr mit dem Takten in der Übergangszeit um? Wie haltet ihr die Anlage nachts leise? Regelt jemand vorausschauend nach Wetterprognose? Gern hier im Thread oder als Issue im Repo.

Viele Grüße
