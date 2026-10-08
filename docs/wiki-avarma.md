# Hofman Avarma Monoblock – Wiki: Modbus, Parameter, Erfahrungen

Hallo zusammen,

dieser Beitrag soll eine Sammelstelle für alles rund um die **Hofman Avarma** werden: Modbus-Anbindung, Parameter, Messwerte, Eigenheiten und Fallstricke. Er ist als **Wiki** angelegt – wer eine Avarma hat, kann direkt ergänzen oder korrigieren. Besonders wertvoll sind **eure Parameterwerte und Erfahrungen**, denn jede Anlage und jeder Firmwarestand kann anders sein. Alles hier gilt unabhängig davon, wie ihr regelt.

Meine **eigene Regelung** über ESPHome, Home Assistant und AppDaemon hat ein eigenes Wiki: **[Link zum Regelungs-Wiki]**. Verweise wie „Regelungs-Wiki 3.2“ meinen die Abschnitte dort.

---

## 1. Meine Anlage

- **Hofman Avarma Version 2, 12 kW, 230 V, Monoblock (R290)**
- **Estrich-Fußbodenheizung, nicht optimal verlegt:** rund **1.000 m Heizrohr** auf **12 Heizkreise**, **15 cm Verlegeabstand**. Das braucht höhere Vorlauftemperaturen als eine eng verlegte FBH und reagiert sehr träge.
- **Die Avarma heizt bei mir nur.** Warmwasser läuft nicht über sie, es gibt keinen Speicher an der Anlage (P63 = 0). Alles hier bezieht sich auf den Heizbetrieb.
- **Im Winter am Leistungslimit.** Ab etwa −5 °C Außentemperatur hat sie keine Reserve mehr, ein ausgekühltes Haus wieder hochzuheizen.

**Eure Anlagen** – bitte ergänzen, dann lassen sich Werte und Erfahrungen besser einordnen:

| Wer | Modell / Version | Leistung / Spannung | Wärmeabgabe | Besonderheiten |
|---|---|---|---|---|
| holle74 | Avarma V2 Monoblock, R290 | 12 kW / 230 V | Estrich-FBH, 12 Kreise | nur Heizen, Durchflussmesser defekt (siehe 4.3) |
| | | | | |

## 2. Modbus-Anbindung

- **ESP32-S3 mit RS485-Transceiver** (Waveshare-Board), direkt an der Modbus-Schnittstelle der Avarma. **Modbus RTU, 9600 Baud, Slave-Adresse 1.**
- **ESPHome** liest praktisch alle relevanten Register (Temperaturen, Drücke, Kompressor, Lüfter, EEV, Fehlercodes, alle Parameter P00–P136). Die komplette Konfiguration liegt im Repo (Abschnitt 6) – auch nützlich, wenn ihr nur mitlesen und nichts regeln wollt.
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
| **P71 / P72** Lüftersteuerung / Solldrehzahl | Automatik | **Manuell, 400–900 U/min** | Lärm. Meine Regelung führt die Drehzahl nach der Verdampfertemperatur nach (siehe Regelungs-Wiki 3.4). |

### 3.2 Unverändert, aber wichtig

- **P41** Ölrückführungsfrequenz **50 Hz** – siehe Ölrückführung in 4.2.
- **P58** Regel-Temperaturdifferenz der Pumpe **5 K** – auf diese Spreizung regelt die Umwälzpumpe.
- **P59** Pumpen-Mindestdrehzahl **80 %** – die Pumpe regelt also nur zwischen 80 und 100 %, bei Teillast fällt die Spreizung dann unter die 5 K aus P58.
- **P114** ist ein Modulations-*Spielraum*: kleiner Wert = Kompressor darf kaum herunter, trifft kleine Lasten nicht → taktet.

### 3.3 Werksreset P87 – Vorsicht

Der Werksreset hat bei mir geändert: P45 70→90, P46 25→35, **P63 0→1 (Warmwasser eingeschaltet, obwohl kein Speicher da ist!)**, P72 40→0, P86 5,0→8,0 K, P114 3→2. Danach alles zurückstellen. Der Reset überlebt einen Netzausfall. P87 habe ich deshalb in ESPHome bewusst **nicht** als Entity angelegt – ein Fehlklick würde die ganze Parametrierung verwerfen.

### 3.4 Eure Werte

Bitte ergänzen – gerade bei den Parametern, die Takten, Pumpe und Abtauung bestimmen:

| Parameter | Werk | holle74 | | |
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

- **Vorlauf über dem Sollwert → Kompressorstopp, meist binnen einer Minute.** Ausgewertet an 70 eigenen Absenkungen: Vorlauf auf oder unter dem neuen Sollwert – nie ein Stopp; 0,5 K darüber – 3 von 16; 0,8 K und mehr – 6 von 11. Wer P2 per Modbus absenkt, sollte das wissen (siehe Regelungs-Wiki 3.2).
- **Ölrückführung:** Nach längerem Lauf mit niedriger Frequenz springt der Kompressor für unter eine Minute auf 50 Hz (P41). Der Vorlauf schießt dabei über den Sollwert – und die Anlage stoppt.
- **Drosselung ab 25 °C am eingebauten Außenfühler (nicht dokumentiert):** Ab 25,0 °C nimmt die Avarma binnen 3–4 s rund 12 Hz Sollfrequenz weg (50 → 38, 60 → 48), danach weiter in 2-Hz-Schritten; darunter steigt sie um 2 Hz je ~30 s. Register 4387 („Frequency Limit Item“) bleibt dabei 0. Mit Sonne auf dem Fühler schon bei echten 19,5 °C.
- **Übergangszeit:** Selbst die Mindestfrequenz (25 Hz) liefert oft mehr, als das Haus abnimmt. Dann taktet jede Wärmepumpe – das ist Physik, kein Defekt.

### 4.3 Durchfluss und E15

Der Durchflussmesser meiner Anlage (Register 4368) hat **seit der Inbetriebnahme** keine brauchbaren Werte geliefert: entweder 0 oder 119–149 L/min. Nachgemessen waren es rund **23 L/min bei 100 % Pumpenleistung**.

Deshalb rechne ich den Durchfluss aus der Pumpenleistung: **Durchfluss [L/min] = Pumpenleistung [%] × 0,22**. Daraus die thermische Leistung: **Durchfluss × Spreizung × 0,0698 = kW** (4,186 kJ/kg·K ÷ 60). Das ist kein Messwert, sondern das, was die Pumpe fördern *soll* – für COP-Auswertung und Plausibilitätsprüfung reicht es gut.

Ende August kam dann **E15 (Wasserdurchfluss)**, reproduzierbar kurz nach jedem Kompressorstart. Nach einer ausführlichen Messreihe (Rohdaten im 10-s-Raster, alle Softwareursachen ausgeschlossen) war klar: **der Durchflussmesser ist defekt**, die Hydraulik in Ordnung. Der Hersteller hat das anerkannt, das Ersatzteil kommt auf Kulanz, und bis dahin hat er die Umstellung auf **P68 = 0 (Strömungsschalter)** freigegeben. Damit entfällt die Mindestdurchfluss-Prüfung gegen P61 – ich habe dafür einen Ersatzschutz in Home Assistant (siehe Regelungs-Wiki 3.8).

**Frage an euch:** Liefert euer Durchflussmesser plausible Werte?

### 4.4 Abtauung und Außenfühler

- Bei mir hat die Avarma einmal **38 Minuten zu spät** abgetaut, obwohl alle Startbedingungen (P27/P28/P29/P85/P86) erfüllt waren – die Lamelle sackte von −3,5 auf −13 °C. Die Ursache ist bis heute ungeklärt. **Beim ersten Frost live mitlesen.**
- **Der eingebaute Außenfühler** sitzt bei mir in der Sonne und lag bis zu **+5,5 K zu hoch**, bei vereister Lamelle bis zu 3,9 K zu tief. Die Anlage nutzt ihn intern trotzdem für ihre Abtau-Entscheidung.

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

## 6. Code und Mitmachen

**Repo:** https://github.com/holle74/avarma-eigenbau-regelung – darin die komplette ESPHome-Konfiguration für alle Register, auch nützlich, wenn ihr nur mitlesen wollt.

> ⚠️ **Auf eigene Gefahr.** Wer Register schreibt: erst nur lesen, jeden Wert am Panel gegenprüfen, schreibende Entities einzeln freischalten. Garantiefragen klärt jeder selbst.

**Mitmachen:** Tragt eure Anlage in die Tabelle in Abschnitt 1 ein und eure Parameter in 3.4. Besonders interessieren mich **Erfahrungen mit dem Abtauverhalten bei Frost**, ob euer **Durchflussmesser** plausible Werte liefert und jede **Abweichung von der Hofman-Tabelle**.

Viele Grüße
