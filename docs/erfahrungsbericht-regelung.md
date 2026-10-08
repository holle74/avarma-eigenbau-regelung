# Erfahrungsbericht: eigene Regelung für die Hofman Avarma mit ESPHome, Home Assistant und AppDaemon

Hallo zusammen,

das hier ist ein **Erfahrungsbericht**: wie ich meine **Hofman Avarma** mit einer eigenen Regelung betreibe, warum ich es so gelöst habe und was ich dabei gelernt habe. Es ist mein Weg, nicht der einzige. Allgemeines Wissen zur Anlage selbst – Modbus, Parameter, Messwerte, Fallstricke – steht im **Avarma-Wiki: [Link zum Avarma-Wiki]**. Verweise wie „Avarma-Wiki 4.2“ meinen die Abschnitte dort.

Vorweg, damit das klar ist: **Ich bin kein Programmierer.** Die Regelung ist zusammen mit **Claude** entstanden, einer KI von Anthropic (mehr dazu in Abschnitt 7). Sie läuft seit dem Sommer und wird laufend nachgeschärft – **wer Ideen hat, wie man etwas besser lösen kann: immer her damit.**

## 1. Warum überhaupt eine eigene Regelung?

Kurz gesagt: Die eingebaute Heizkurve der Avarma kommt mit meinem Haus nicht gut klar. Eine statische Heizkurve reagiert nur auf die *aktuelle* Außentemperatur. Mit dem trägen Estrich ist das bei einer Frostnacht Stunden zu spät. Früher habe ich morgens von Hand hochgedreht, wenn abends Frost angesagt war. Das sollte die Regelung selbst können.

**Das Ziel:** Eine Steuerung, die
1. das thermische Verhalten des Hauses **aus Messdaten lernt**,
2. **vorausschauend** heizt (Wetterprognose, Estrich als Speicher vorladen),
3. die Anlage **im effizienten Teillastbereich** hält und Takten vermeidet,
4. bei Engpass **Wärme zu den wichtigen Räumen umleitet**,
5. dabei **so leise wie möglich** bleibt – und Komfort vor Stromsparen stellt.

Ehrlicher Zwischenstand: Punkt 3 bis 5 laufen. Beim Lernen ist ein Teil umgesetzt, die vollständig vorausschauende Regelung ist das Ziel für den kommenden Winter (Abschnitt 4).

## 2. Aufbau

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
- **Externer Funk-Außenfühler** statt des eingebauten (siehe Avarma-Wiki 4.4).
- **Wetterprognose** (stündlich, 24 h) für das Vorladen vor Frost.
- **InfluxDB + Grafana** für alle Messwerte – ohne die Auswertungen wäre nichts davon entstanden.

> ⚠️ **Wer neu anfängt: nicht mehr auf das InfluxDB-Add-on setzen.** Das bisherige Community-Add-on basiert auf InfluxDB 1.x, wurde im **August 2026 archiviert und aus dem Store genommen** und bekommt keine Updates mehr. **Den angebotenen „Reparieren“-Knopf nicht drücken** – er deinstalliert das Add-on samt der gesamten Historie. Gepflegte Alternativen für HAOS sind z. B. **InfluxDB 2** oder **VictoriaMetrics** (versteht das InfluxDB-Schreibprotokoll, Grafana bleibt nutzbar).

**Was die Regelung an der Avarma verstellt – mehr nicht:** Ein/Aus (4096), P2 Vorlauf-Soll (4098), P45 Kompressor-Maximalfrequenz (8235), P71/P72 Lüfter (8261/8262), Abtauung erzwingen (4103). Dazu die Solltemperaturen einzelner Raumthermostate (Lastverteilung). Alles andere macht der eingebaute Regler der Avarma weiterhin selbst – das ist Absicht.

**Sicherheitsnetz im ESP:** Kommt 30 Minuten lang kein Befehl aus Home Assistant (Heartbeat), setzt der ESP Vorlauf-Soll auf 32 °C und Kompressor-Maximum auf 90 Hz zurück. Grenzwerte stehen hart an den Entities (Vorlauf-Soll max. 45 °C, Kompressor 50–120 Hz).

## 3. Die Regellogik – verständlich erklärt

Die Regelung arbeitet im 5-Minuten-Takt. Die wichtigsten Bausteine:

### 3.1 Geregelt wird auf den Rücklauf, nicht auf den Vorlauf

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
- **Lernender Offset** (±3 K, siehe 4.1).
- **Kaltstart-Rampe:** Nach dem Einschalten startet das Ziel bei 28 °C und steigt um 1 K je 15 min.

### 3.2 Vorlauf-Sollwert per Vorsteuerung

**VL-Soll = Rücklauf-Ziel + Spreizung + Korrektur**, begrenzt auf 30–45 °C.

- Die **Spreizung** wird live gemessen (Vorlauf minus Rücklauf, wenn der Kompressor läuft und der Wert plausibel ist), sonst 5 K. Die Pumpe regelt über **P58 = 5 K** selbst auf diese Differenz.
- Die **Korrektur** ist ein langsamer Nachregler: ±0,5 K je 15 min bei bleibender Abweichung, maximal ±3 K.
- Geschrieben wird nur bei Änderung um ganze Grad (Abweichungen ≥ 3 K sofort, sonst höchstens alle 10 min).
- **Absenken ohne Kompressorstopp** (siehe Avarma-Wiki 4.2): P2 geht nur in ganzen Grad – bei laufendem Kompressor wird deshalb nur abgesenkt, wenn der Vorlauf nicht über dem neuen Sollwert liegt (bis 08.10. waren 0,8 K erlaubt – zu viel). Sonst wartet die Regelung, bis er von selbst fällt, nach 30 min senkt sie trotzdem um 1 K.

**Warum so und nicht einfach „VL-Soll hoch/runter in Schritten“?** Das hatte ich vorher (siehe 5., 12.09.): Parkt der Sollwert über dem tatsächlichen Vorlauf, bremst er nichts – die Avarma fährt bis zum Deckel, und das Absenken in 1-K-Schritten wirkte erst nach zwei Stunden. Mit der Vorsteuerung liegt der Sollwert immer knapp beim Vorlauf, und die **Avarma moduliert selbst** – das kann ihr eingebauter Regler nämlich gut.

### 3.3 Kompressor-Deckel nach Außentemperatur

Die Maximalfrequenz P45 folgt einer Kennlinie im 5-Hz-Raster – Grund ist der COP-Verlauf aus Avarma-Wiki 4.1:

| Außentemperatur | Deckel |
|---|---|
| −5 °C und kälter | 90 Hz |
| +5 °C | 65 Hz |
| +15 °C und wärmer | 50 Hz |

- **Untergrenze 50 Hz:** P41 (Ölrückführungsfrequenz) steht auf 50 Hz. Der Deckel geht nie darunter, damit die Ölrückführung nicht behindert wird.
- **Winter-Eskalation:** Hängt der Kompressor 60 min am Deckel **und** liegt der Rücklauf 60 min unter Ziel, geht der Deckel um +5 Hz je 30 min hoch – bis 90 Hz, **95 Hz nur bei −5 °C und kälter**. Die letzten 5 Hz sind Frostreserve, kein Alltagswerkzeug.
- **Vereisungssperre:** Liegt der Verdampfer unter 1 °C und die Differenz Außenluft–Verdampfer über 7 K, wird nicht eskaliert. Mehr Frequenz kauft dann Eis statt Wärme.

### 3.4 Lüfter: so leise wie möglich

Der Lüfter läuft im **manuellen Modus** (P71) mit eigener Solldrehzahl (P72), 400–900 U/min.
- **Grundsatz:** so niedrig wie möglich, solange der **Verdampfer ≥ 1 °C** bleibt. 1 °C ist eine **Untergrenze**, kein Sollwert – liegt der Verdampfer bei 4 °C und der Lüfter auf 400 U/min, ist das genau richtig.
- **Hoch schnell:** unter 1 °C in jedem Zyklus, 150 U/min je Kelvin Unterschreitung (100–300 U/min pro Schritt). Nähert sich der Verdampfer der Abtau-Startschwelle (−3 °C) auf 1 K, sofort Volllast.
- **Runter behutsam:** über 1,5 °C nur 50 U/min alle 10 min, nicht in den 15 min nach einer Abtauung.

### 3.5 Not-Abtauung

Wegen der verspäteten Abtauung aus Avarma-Wiki 4.4 taut die Regelung im Zweifel selbst ab (Register 4103), aber nur wenn **alle vier** Bedingungen erfüllt sind: Verdampfer unter −3 °C **und** Differenz Außenluft–Verdampfer über 7 K, das seit 20 min, Lüfter bereits auf Volllast, letzte Abtauung mindestens 60 min her.

### 3.6 Ein- und Ausschalten

**Einschalten**, wenn beides zutrifft:
- Außentemperatur ≤ 16,5 °C (bei angesagtem Frost unter 8 °C zählt das Prognose-Minimum – damit sie an einem milden Tag vor der Frostnacht anläuft)
- Raum kalt genug: in der Übergangszeit **EG-Mittel ≤ 20,0 °C**, sonst **Bad ≤ 18,5 °C** (das Bad ist bei uns der am schwersten zu heizende Raum)

**Heizgrenze (ganzjährig):** Aus, wenn das **3-h-Mittel** der Außentemperatur ≥ 18,5 °C ist, keine kalte Nacht angesagt ist und sie mindestens 2 h läuft. Die 2 K zwischen Ein (16,5, Momentanwert) und Aus (18,5, Mittel) verhindern das Takten um die Schwelle.

**Übergangszeit** (seit Oktober über den Betriebsmodus gewählt statt fest nach Kalender, siehe 3.9) – zusätzlich:

| Regel | Auslöser | Danach |
|---|---|---|
| Raum warm genug | EG-Mittel ≥ 21 °C, 30 min am Stück (nicht bei Frostprognose) | Neustart bei EG ≤ 20 °C |
| Anlage taktet | 2 Kompressorstarts in 45 min (Abtauungen und selbst verursachte Stopps zählen nicht, siehe unten) | 3 h Sperre |
| Nachtsperre 22–08:30 Uhr | kein Start; eine laufende Anlage schaltet ab, sobald EG ≥ 20,5 °C | Ausnahme: Frostprognose ≤ 2 °C oder EG ≤ 19 °C |

Lieber ein paar Stunden aus und den Estrich puffern lassen als alle 15 Minuten neu starten (siehe Avarma-Wiki 4.2).

**Nicht jeder Stopp ist Takten.** Vom 17.–24.09. kamen 10 von 13 Stopps von der eigenen Absenkung und 3 von der Ölrückführung (Avarma-Wiki 4.2) – und steckten in allen drei Takt-Abschaltungen. Seitdem zählen Stopps bis 5 min nach einer eigenen Absenkung bzw. 3 min nach dem Sprung auf 50 Hz nicht mit; jeder Stopp steht mit Grund im Log.

**Ergebnis 25.09.–07.10.** (13 Läufe): nur noch eine Takt-Abschaltung, echter Leistungsüberschuss (Stopps bei 26–27 Hz, Vorlauf = Soll). Sonst 7× Heizgrenze, 5× Nachtsperre. EG im Mittel 20,3 °C, Verbrauch 6,6 statt 8,7 kWh/Tag.

### 3.7 Hydraulische Lastverteilung

Wenn der Kompressor am Deckel hängt, reicht die Wärme nicht für alle Kreise. Dann werden **Spender-Räume** gedrosselt, damit mehr zu den **Prioritäts-Räumen** fließt:
- **Priorität:** Bad → Dusche → Wohnzimmer → Büro → Ankleide (werden nie gedrosselt)
- **Spender** in dieser Reihenfolge: Schlafzimmer (nicht unter 18 °C) → Keller → Flur → Yoga (nicht unter 20 °C)
- **Auslöser:** Prioritätsraum mit Ventil ≥ 90 % und ≥ 0,3 K unter Soll, 15 min lang – **und** der Kompressor am Deckel. Ohne diese letzte Bedingung würde dauernd gedrosselt, denn bei milder Witterung erreicht die FBH das Bad-Ziel nie, egal wie weit andere Ventile zu sind.
- −0,5 K je 10 min, bis das Spender-Ventil bei ~30 % steht. Die Original-Sollwerte liegen in Helfern und werden zurückgesetzt, sobald der Engpass vorbei ist.
- **Übergangsmodus** (Betriebsmodus „KI Übergangszeit“, der den Schalter `wp_uebergangsmodus` setzt): Dann ist das **Wohnzimmer der einzige Spender** (nicht unter 21 °C) und fällt dafür aus dem Vorrang. Grund: Im Übergang heizt das Haus aus dem Kaltstart hoch, das Bad verfehlt sein bewusst hohes Ziel ohnehin, und die normale Lastverteilung hatte binnen zwei Stunden Keller, Flur und Yoga bis an ihre Untergrenze gezogen – viel Kälte für wenig Wirkung.

### 3.8 Schutzschicht, unabhängig von der Regelung

- **Heartbeat-Watchdog im ESP** (siehe 2.)
- **Zwei Handschalter:** Autostart erlaubt/gesperrt, automatische Abschaltungen erlaubt/gesperrt
- **Interim-Durchflussschutz** (siehe Avarma-Wiki 4.3): Aus bei laufendem Kompressor und Spreizung > 10 K oder Pumpe < 30 %

### 3.9 Betriebsmodus: ein Schalter für alles

Seit Oktober wähle ich den Modus mit einem einzigen Schalter (`input_select.wp_betriebsmodus`) statt mit mehreren Einzelschaltern und einem festen Kalender:

| Modus | Regelung | Avarma |
|---|---|---|
| **KI Modus** | regelt mit Winterregeln (Lastverteilung über Schlafzimmer, Keller, Flur, Yoga) | Heizen |
| **KI Übergangszeit** | regelt mit den Übergangsregeln aus 3.6 und dem Übergangsmodus aus 3.7 | Heizen |
| **Kühlen** | greift nicht ein, gibt gedrosselte Räume zurück | Kühlen – Wassertemperatur stelle ich an der Avarma selbst ein |
| **Manuell** | greift nicht ein: Lüfter auf Automatik, Kompressor-Deckel 90 Hz, gedrosselte Räume zurück | Heizen – „wie früher“, Vorlauf stelle ich selbst ein |

- Der Schalter setzt die Avarma-Betriebsart (Register 4097) gleich mit – nach der Erfahrung vom 23.07. (stand unbemerkt auf „Kühlen“) war mir das wichtig.
- **In Kühlen und Manuell schreibt die Regelung trotzdem weiter den Heartbeat.** Sonst würde der Watchdog im ESP nach 30 min 32 °C / 90 Hz über die Einstellung von Hand legen.
- ⚠️ **Kühlen über eine Fußbodenheizung ohne Taupunktüberwachung** ist bei mir bewusst so (keine Feuchtesensoren im Haus). Zu kaltes Wasser kann im Estrich kondensieren – wer das nachbaut, sollte entweder Feuchtesensoren und eine Taupunktgrenze einbauen oder das Wasser deutlich über dem Taupunkt halten.
- Für das Dashboard gibt es eine eigene Karte (`homeassistant/www/heizung/wp-modus-card.js`): Segmentschalter in der Farbe des Modus, kurze Erklärung, was der Modus gerade tut, Rückfrage vor Kühlen/Manuell.

## 4. Was schon lernt – und was noch kommt

### 4.1 Heute im Einsatz
- **Lernender Heizkurven-Offset:** Alle 5 h wird die Kurve um 0,5 K verschoben, wenn die Räume dauerhaft zu kalt oder zu warm sind (±3 K), gemessen am Bad. **In der Übergangszeit ausgesetzt:** Dort läuft die WP nur zwischen EG 20 und 21 °C an und aus – ein Offset gegen 21 °C sah fast immer „zu kalt“ und kletterte in drei Tagen von 1 auf 3 K. Ebenfalls ausgesetzt, wenn der Kompressor am Limit läuft – dann ist es ein Leistungs-, kein Kurvenproblem.
- **Gebäude-Thermometrie:** Ein RC-Modell schätzt aus nächtlichen Abkühlphasen (00–05 Uhr, keine Sonne, keine Heizung, kein Lüften) die **Zeitkonstante des Hauses**. Noch vorläufig, im Sommer ist das Gefälle zu klein. Die App stuft sich selbst erst ab 15 K Gefällespanne als „belastbar“ ein und greift bis dahin in **keinen** Regelkreis ein.
- **Gebäudemodell mit zugeführter Wärme (seit Oktober):** Das erste Modell lernt nur aus Nächten ohne Heizung und würde im Winter verhungern. Deshalb rechnet daneben ein zweites: *Temperaturänderung = a × (außen − innen) + b × Wärmeleistung + c*. Die Wärmeleistung kommt aus Durchfluss × Spreizung, wegen des Estrichs wird sie mit 0–8 h Verzögerung probiert. Daraus folgen zwei echte Kennzahlen: **Wärmeverlust** (W je K Temperaturunterschied) und **Wärmespeicher** (kWh, um das Haus 1 K anzuheben). Erster, sehr vorläufiger Stand: ~360 W/K und ~54 kWh/K, also rund 9,5 kW Heizlast bei −5 °C – genau dort, wo meine Avarma an ihre Grenze kommt. Belastbar nach etwa 15 geheizten Frostnächten.

### 4.2 Das Ziel für den Winter
- Die fest verdrahtete Vorlade-Formel durch eine **Auskühlprognose aus dem gelernten Gebäudemodell** ersetzen: „Heute Nacht −6 °C, das Haus verliert bis morgen 7 K – also jetzt so viel einlagern.“
- **Nachtbetrieb** leiser machen (Vorlauf, Lüfter, Eskalation nachts begrenzen) – die Schwellen will ich im ersten kalten Winter nach Gehör einstellen.
- **Takten im Teillastbereich** weiter reduzieren (P46/P114 als Hebel).

## 5. Projektgeschichte – und was ich dabei gelernt habe

- **Juli:** Idee, alle Werte in InfluxDB loggen. ESPHome-Anbindung ausgebaut. Durchfluss- und COP-Berechnung repariert (hatten wochenlang tote Entities referenziert).
- **23.07. – erster Live-Test.** Zwei Überraschungen: Der **Betriebsmodus stand auf „Kühlen“** (Vorlauf fiel statt zu steigen), und der **Lüfter reagierte nicht**, weil P72 Drehzahl ÷ 10 speichert.
- **24.07.–03.08.:** Umstellung auf die Rücklauf-Heizkurve, stückweise Kurve, Vorladen vor Frost. Erkenntnis aus den Daten: Mehr Durchfluss geht nicht (Pumpe am Anschlag), Vorlauf 45 °C und Bad-Kreis 100 % offen – **die einzige verbleibende Freiheit fürs Bad ist die zeitliche**, also vorladen.
- **18.08.:** Alle Register systematisch gegen die Hofman-Tabelle geprüft (Funde im Avarma-Wiki, Abschnitt 5).
- **22.08.:** COP über Frequenz gemessen → Kompressor-Deckel. Gebäude-Thermometrie gestartet. Takten bei 16–18 °C Außentemperatur erstmals gesehen.
- **24.08.:** Vereisung mit 38 min verspäteter Abtauung → Not-Abtauung und Vereisungssperre.
- **24.–25.08.: E15.** Anlage stand. Werksreset (P87) zur Fehlersuche – hat 6 Parameter verstellt (siehe Avarma-Wiki 3.3). Messprotokoll an den Hersteller.
- **29.08.:** Ersatzteil auf Kulanz zugesagt.
- **12.09.:** Freigabe P68 = 0, Kabel auf der Platine umgesteckt, Wiederanlauf. Heizgrenzen-Abschaltung gebaut. **Rücklauf lief 2 K über Ziel** – der Vorlauf-Sollwert stand nach dem Anlagenneustart auf 45 °C und die Schrittlogik brauchte zwei Stunden zum Absenken. Drei Varianten durchgerechnet (Schritte, Frequenz regelt, Vorsteuerung) – die Vorsteuerung hat gewonnen.
- **13.09.:** Vorsteuerung und Übergangsregeln live.
- **14.09. – erste Nacht mit den neuen Regeln:** Vorsteuerung sauber (Rücklauf ±1 K, kein Überschwingen). Aber die Anlage lief von 20:20 bis 05:36, weil die Nachtsperre nur den Start verhinderte. Nachgeschärft: Nachtabschaltung ab EG 20,5 °C, Takt-Erkennung schon bei 2 Starts in 45 min.
- **17.09.:** Laufzeit der WP in einem Helfer statt aus `last_changed` (ein HA-Neustart ließ eine laufende WP wie frisch gestartet aussehen). Übergangsmodus der Lastverteilung.
- **25.09. – Auswertung der ersten Übergangswoche:** Räume warm, Rücklauf ruhig, aber drei Takt-Abschaltungen – verursacht von der eigenen Regelung und der Ölrückführung, nicht von zu viel Leistung. Dazu kletterte der lernende Offset wie eine Ratsche auf +3 K. Beides behoben, siehe 3.2, 3.6 und 4.1.
- **27.09.:** Nachtsperre endet um 08:30 statt 10:00.
- **02.10.:** Ein Betriebsmodus-Schalter ersetzt Kalender und Einzelschalter (3.9).
- **03.10.:** Zweites Gebäudemodell mit zugeführter Wärme (4.1) – damit lernt die Thermometrie auch im Winter weiter.
- **08.10.:** Zweite Auswertung (3.6). Die Absenkbremse war zu großzügig (Avarma-Wiki 4.2) – jetzt nur noch absenken, wenn der Vorlauf nicht über dem neuen Soll liegt.

**Meine wichtigsten Lehren:**
1. **Erst messen, dann regeln.** Fast jede gute Entscheidung kam aus einer Auswertung, fast jeder Fehler aus einer Annahme.
2. **Die eingebaute Regelung der Avarma ist gut** – man muss ihr nur die richtigen Sollwerte geben, statt sie zu ersetzen.
3. **Jeden Registerwert am Panel gegenprüfen.** Die Doku ist nicht durchgängig verlässlich.
4. **Schutzmechanismen gehören in den ESP**, nicht nur in Home Assistant.
5. **Regeln immer als Paar denken:** Wer ein Einschaltkriterium ändert, muss das Ausschaltkriterium mit anschauen – sonst arbeiten sie gegeneinander.
6. **Bevor man ein Symptom bekämpft, prüfen, ob man es selbst verursacht.** Das „Takten“ der Übergangszeit war zum großen Teil meine eigene Regelung.

## 6. Fallstricke in Home Assistant und AppDaemon

[details="Home Assistant / AppDaemon"]
- **AppDaemon lädt eine geänderte App sofort neu**, ein ESPHome-Flash dauert Minuten. Bei gekoppelten Änderungen (z. B. Skalierung) **erst flashen, dann den Python-Code ändern.**
- Ein Reload setzt Zustände im Speicher zurück. Alles, was einen Neustart überleben muss, gehört in Helfer.
- **`set_state` lässt Attribute mit 0, False oder None weg.** Werte, die legitim 0 werden können, als String setzen.
- `run_every` mit sofortigem Start feuert nicht zuverlässig – Start in die Zukunft legen.
- **Datenbank:** Das InfluxDB-1.x-Add-on ist seit August 2026 abgekündigt (siehe 2.). Vor jeder Umstellung ein Backup mit der alten Datenbank anlegen.
[/details]

## 7. Die Rolle der KI

Weil ich danach sicher gefragt werde: Die Aufteilung war ziemlich klar.

**Ich** kenne das Haus, die Anlage und meine Erfahrungswerte aus zwei Wintern. Ich habe entschieden, was Priorität hat (Komfort vor Sparen), welche Räume wichtig sind, was die Anlage darf – und ich habe am Panel, an der Platine und mit dem Hersteller gearbeitet.

**Claude** hat Messdaten aus InfluxDB ausgewertet, die Hofman-Modbus-Tabelle und die Handbücher Register für Register gelesen, Varianten durchgerechnet, den gesamten Code geschrieben und vor jedem Einspielen offline getestet – und mir immer wieder erklärt, *warum* etwas so ist. Viele der Fallstricke oben hat die KI in den Daten gefunden, bevor sie Schaden anrichten konnten. Fehler gab es trotzdem, auf beiden Seiten – die stehen in Abschnitt 5.

## 8. Code und Mitmachen

**Repo:** https://github.com/holle74/avarma-eigenbau-regelung

Enthalten: ESPHome-Konfiguration, die vier AppDaemon-Apps, die zwei Automationen, die Dashboard-Karte für den Betriebsmodus und eine Liste aller benötigten Helfer. Private Angaben sind entfernt, Entity-IDs müsst ihr an eure Installation anpassen.

> ⚠️ **Auf eigene Gefahr.** Die Regelung schreibt Register der Wärmepumpe. Jede Anlage und jeder Firmwarestand kann abweichen. Bitte erst nur lesen, jeden Wert am Panel gegenprüfen und schreibende Entities einzeln freischalten. Garantiefragen klärt jeder selbst.

**Mitmachen:** Eure Anlagendaten und Parameter gehören ins Avarma-Wiki. Zur Regelung bin ich für Ideen offen: Wie geht ihr mit dem Takten in der Übergangszeit um? Wie haltet ihr die Anlage nachts leise? Regelt jemand vorausschauend nach Wetterprognose? Gern als Antwort auf diesen Beitrag oder als Issue im Repo.

Viele Grüße
