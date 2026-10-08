# Hofman Avarma Monoblock (R290) – Modbus, Parameter, Betriebsverhalten

Dieser Artikel sammelt Wissen zur Wärmepumpe **Hofman Avarma**: Modbus-Anbindung, Parameter, Messwerte, Eigenheiten und Fallstricke. Er gilt unabhängig davon, ob die Anlage über ihre eingebaute Heizkurve oder extern geregelt wird. Der Beitrag ist ein **Wiki** – Ergänzungen und Korrekturen sind ausdrücklich erwünscht.

**Belegstand:** Viele Angaben stammen bisher von einer einzigen Anlage (Avarma V2, 12 kW, 230 V). Sie sind mit *(1 Anlage)* markiert. Wer sie an seiner Anlage bestätigen oder widerlegen kann, bitte die Markierung anpassen oder eine Anmerkung ergänzen – Anlagen und Firmwarestände können sich unterscheiden.

Eine vollständige externe Regelung über ESPHome, Home Assistant und AppDaemon ist im **Regelungs-Wiki** beschrieben: **[Link zum Regelungs-Wiki]**. Verweise wie „Regelungs-Wiki 3.2“ meinen die Abschnitte dort.

---

## 1. Bekannte Anlagen

Die Tabelle hilft, Messwerte und Parameter einzuordnen. Bitte eigene Anlagen ergänzen.

| Forumsname | Modell / Version | Leistung / Spannung | Wärmeabgabe | Besonderheiten |
|---|---|---|---|---|
| holle74 | Avarma V2 Monoblock, R290 | 12 kW / 230 V | Estrich-FBH, 12 Kreise, ~1.000 m Rohr, 15 cm Verlegeabstand | nur Heizbetrieb (P63 = 0), Durchflussmesser defekt (siehe 4.3), Leistungsgrenze ab ca. −5 °C |
| | | | | |

## 2. Modbus-Anbindung

- **Schnittstelle:** Modbus RTU, 9600 Baud, Slave-Adresse 1.
- **Hardware:** Zum Beispiel ein ESP32-S3 mit RS485-Transceiver (z. B. Waveshare-Board) direkt an der Modbus-Schnittstelle der Avarma.
- **Software:** Mit **ESPHome** lassen sich praktisch alle relevanten Register lesen – Temperaturen, Drücke, Kompressor, Lüfter, EEV, Fehlercodes und alle Parameter P00–P136. Eine vollständige Beispielkonfiguration liegt im Repo (Abschnitt 6) und ist auch für reines Mitlesen nützlich.
- **Grundlage** ist die Hofman-Modbus-Tabelle. Sie ist nicht durchgängig verlässlich, bekannte Abweichungen stehen in Abschnitt 5.

**Wichtige Register:**

| Register | Inhalt | Hinweis |
|---|---|---|
| 4096 | Ein/Aus | |
| 4097 | Betriebsmodus | vor Tests prüfen – „Kühlen“ wird leicht übersehen |
| 4098 | P2 Vorlauf-Soll | steht nach einem Neustart der Anlage auf 45 °C *(1 Anlage)* |
| 4103 | Abtauung erzwingen | |
| 4368 | Durchfluss | bei defektem Messer unbrauchbar (siehe 4.3) |
| 4369 | „Temperaturdifferenz Hauptkreis“ | **nicht** die VL/RL-Spreizung |
| 4387 | Frequency Limit Item | Grund einer Frequenzbegrenzung (Bits: T3-Coil, Hochdruck, AC-Spannung, Heißgas, AC-Strom) – zeigt die 25-°C-Drosselung **nicht** an (siehe 4.2) |
| 4390 / 4391 | Fault State 0 (E01–E16) / 1 (E17–E32) | E15 = Bit 14 → Anzeigewert 16384 |
| 8235 | P45 Kompressor-Maximalfrequenz | Parameterregister |
| 8261 / 8262 | P71 / P72 Lüfter manuell + Solldrehzahl | P72 speichert Drehzahl ÷ 10 |

## 3. Parameter

### 3.1 Sinnvolle Anpassungen

| Parameter | Werk | Anpassung | Begründung |
|---|---|---|---|
| **P114** Frequenzreduktion bei erreichtem VL-Soll | 2 % | **3 %** | Mehr Spielraum zum Herunterregeln: Die Anlage moduliert länger, statt abzuschalten. Mit dem Werkswert reagiert sie träge und taktet eher *(1 Anlage)*. |
| **P46** Kompressor-Mindestfrequenz | 35 Hz | **25 Hz** | Größerer Modulationsbereich nach unten. In der Übergangszeit liegt der Wärmebedarf oft unter der Mindestleistung – je tiefer sie liegt, desto seltener taktet die Anlage. |
| **P86** Abtau-Differenz ΔT1 (Außen ≥ −7 °C) | 8,0 K | **5,0 K** | Lässt die Abtauung früher zu (Hintergrund siehe 4.4). **P91**, dieselbe Differenz unter −7 °C, bleibt auf 8,0 K. |
| **P63** Warmwasserfunktion | 1 | **0** | Bei Anlagen ohne Warmwasserspeicher. |
| **P68** Durchflussfühler-Typ | 1 (Durchflussmesser) | 0 (Strömungsschalter) | **Nur mit Freigabe des Herstellers**, etwa als Übergang bei defektem Durchflussmesser. Damit entfällt die Mindestdurchfluss-Prüfung (siehe 4.3). |
| **P71 / P72** Lüftersteuerung / Solldrehzahl | Automatik | Manuell, z. B. 400–900 U/min | Deutlich leiser – aber nur zusammen mit einer externen Regelung, die die Drehzahl nach der Verdampfertemperatur nachführt (Regelungs-Wiki 3.4). Sonst droht Vereisung. |

### 3.2 Wichtige Werkseinstellungen

- **P41** Ölrückführungsfrequenz **50 Hz** – siehe Ölrückführung in 4.2.
- **P58** Regel-Temperaturdifferenz der Pumpe **5 K** – auf diese Spreizung regelt die Umwälzpumpe.
- **P59** Pumpen-Mindestdrehzahl **80 %** – die Pumpe regelt nur zwischen 80 und 100 %. Bei Teillast fällt die Spreizung deshalb unter die 5 K aus P58.
- **P114** ist ein Modulations-*Spielraum*: Ein kleiner Wert lässt den Kompressor kaum herunterregeln, kleine Lasten werden nicht getroffen, die Anlage taktet.

### 3.3 Werksreset P87 – Vorsicht

Der Werksreset setzt unter anderem diese Parameter zurück *(1 Anlage)*: P45 → 90 Hz, P46 → 35 Hz, **P63 → 1 (Warmwasser an, auch ohne Speicher!)**, P72 → 0, P86 → 8,0 K, P114 → 2 %. Alle Anpassungen müssen danach neu gesetzt werden. Der Reset überlebt einen Netzausfall.

Empfehlung: P87 in ESPHome oder Home Assistant **nicht** als bedienbare Entity anlegen – ein Fehlklick verwirft die gesamte Parametrierung.

### 3.4 Parameterwerte im Vergleich

Bitte eigene Werte ergänzen – besonders die Parameter, die Takten, Pumpe und Abtauung bestimmen:

| Parameter | Werk | holle74 | | |
|---|---|---|---|---|
| P41 Ölrückführungsfrequenz | 50 Hz | 50 Hz | | |
| P46 Kompressor-Mindestfrequenz | 35 Hz | 25 Hz | | |
| P58 Regel-ΔT Pumpe | 5 K | 5 K | | |
| P59 Pumpen-Mindestdrehzahl | 80 % | 80 % | | |
| P86 Abtau-Differenz ΔT1 | 8,0 K | 5,0 K | | |
| P91 Abtau-Differenz unter −7 °C | 8,0 K | 8,0 K | | |
| P114 Frequenzreduktion | 2 % | 3 % | | |

## 4. Betriebsverhalten und Messwerte

### 4.1 Effizienz über die Kompressorfrequenz

Messwerte aus stabilen Betriebsphasen im August *(1 Anlage, noch wenige Messpunkte)*:

| Frequenz | 30–39 Hz | 40–49 Hz | 50–59 Hz | 60–69 Hz | 80–90 Hz |
|---|---|---|---|---|---|
| COP | 6,3 | 5,8 | 5,2 | 4,8 | 4,2 |

Im Teillastbereich arbeitet die Anlage rund 50 % effizienter als nahe der Maximalfrequenz und ist deutlich leiser. Die Heizleistung folgt grob **0,4 kW + 0,14 kW je Hz** und flacht nach oben ab.

### 4.2 Kompressorstopps und Drosselung

- **Vorlauf über dem Sollwert:** Wird P2 so abgesenkt, dass der Vorlauf darüber liegt, stoppt der Kompressor meist binnen einer Minute. Ausgewertet an 70 Absenkungen *(1 Anlage)*: Vorlauf auf oder unter dem neuen Sollwert – nie ein Stopp; 0,5 K darüber – 3 von 16; 0,8 K und mehr – 6 von 11. Für externe Regelungen, die P2 schreiben, ist das entscheidend (Regelungs-Wiki 3.2).
- **Ölrückführung:** Nach längerem Lauf mit niedriger Frequenz springt der Kompressor für unter eine Minute auf die Frequenz aus P41 (50 Hz). Der Vorlauf schießt dabei über den Sollwert, und die Anlage kann stoppen.
- **Drosselung ab 25 °C am eingebauten Außenfühler** (nicht dokumentiert, *1 Anlage*): Erreicht der Fühler 25,0 °C, nimmt die Avarma binnen 3–4 s rund 12 Hz Sollfrequenz weg (50 → 38, 60 → 48 Hz), bei anhaltender Überschreitung weiter in 2-Hz-Schritten. Fällt er darunter, steigt die Frequenz um 2 Hz je ~30 s. Register 4387 bleibt dabei 0. Steht der Fühler in der Sonne, tritt das schon bei tatsächlich 19,5 °C auf (siehe 4.4).
- **Übergangszeit:** Selbst die Mindestfrequenz liefert oft mehr Wärme, als das Gebäude abnimmt. Dann taktet jede Wärmepumpe – das ist Physik, kein Defekt.

### 4.3 Durchflussmesser und Fehler E15

**Symptome eines defekten Durchflussmessers** *(1 Anlage)*: Register 4368 liefert nur 0 oder unplausible 119–149 L/min. Später kommt **E15 (Wasserdurchfluss)**, reproduzierbar kurz nach jedem Kompressorstart, obwohl die Hydraulik in Ordnung ist. Im bekannten Fall hat der Hersteller den Defekt anerkannt und Ersatz auf Kulanz zugesagt.

**Übergangslösung:** Mit Herstellerfreigabe auf **P68 = 0 (Strömungsschalter)** umstellen. Damit entfällt die Mindestdurchfluss-Prüfung gegen P61 – ein eigener Ersatzschutz ist dann sinnvoll (Beispiel: Regelungs-Wiki 3.8).

**Durchfluss ohne Messer abschätzen:** **Durchfluss [L/min] ≈ Pumpenleistung [%] × 0,22** (kalibriert an einer Anlage: ~23 L/min bei 100 %). Thermische Leistung: **Durchfluss × Spreizung × 0,0698 = kW** (4,186 kJ/kg·K ÷ 60). Das ist kein Messwert, sondern die Sollförderung der Pumpe – für COP-Auswertungen und Plausibilitätsprüfungen reicht es.

### 4.4 Abtauung und Außenfühler

- **Verspätete Abtauung** *(1 Anlage, einmalig)*: Die Abtauung startete 38 Minuten zu spät, obwohl alle Startbedingungen (P27/P28/P29/P85/P86) erfüllt waren; die Lamellentemperatur fiel dabei von −3,5 auf −13 °C. Die Ursache ist ungeklärt. Bei Frost lohnt es sich, die Abtauung mitzulesen.
- **Eingebauter Außenfühler:** Er ist strahlungsempfindlich. In der Sonne lag er bis zu **+5,5 K zu hoch**, bei vereister Lamelle bis zu 3,9 K zu tief *(1 Anlage)*. Die Anlage nutzt ihn trotzdem für die Abtau-Entscheidung und die 25-°C-Drosselung (4.2). Für eine externe Regelung ist ein separater, verschatteter Außenfühler deutlich zuverlässiger.

## 5. Fallstricke bei Modbus und ESPHome

[details="Modbus und Hofman-Tabelle"]
- **Zwei Adressspalten:** „Decimal“ ist die echte Modbus-Adresse, „Decimal+1“ nur die Panel-Anzeige. Immer „Decimal“ verwenden und gegen die Basisadresse gegenrechnen (0x2000 = 8192 für die Parameter).
- **Fehlercode-Register:** „Fault State 0“ (E01–E16) liegt auf **4390**, „Fault State 1“ (E17–E32) auf **4391**. 4389 ist ein Temperaturregister.
- **Adressen einzeln prüfen:** In einer Konfiguration lag P114 auf der Adresse von P115 (Vorlauf-Übertemperaturschutz) – ein Schreibzugriff hätte die Anlage in Dauerstörung geschickt.
- **4369 „Temperaturdifferenz Hauptkreis“ ist nicht die VL/RL-Spreizung** (0–1,8 K bei tatsächlich 4,5–6 K). Die Spreizung selbst aus Vor- und Rücklauf berechnen.
- **Funktionscode 3 liest höchstens 125 Register am Stück.** ESPHome fasst benachbarte Register zusammen; ein zu großer Block scheitert komplett und reißt alle Werte darin mit (`force_new_range` hilft).
- **Der ESP behält bei fehlender Modbus-Antwort die letzten Werte.** Eine stromlose Anlage sieht in Home Assistant aus wie eine ruhig laufende.
- **Parameterregister** nur alle paar Minuten lesen (`skip_updates`). Direkt nach dem Schreiben zeigt der Lesewert noch den alten Stand – das ist kein Fehler.
- **P45 und andere Parameterregister selten schreiben:** Ob die Avarma jeden Schreibvorgang ins EEPROM sichert, ist nicht bekannt. Vorsichtshalber selten schreiben – die Regelung aus dem Regelungs-Wiki schreibt P45 nur 2–4-mal pro Tag.
[/details]

[details="Skalierungen und ESPHome"]
- **P72 Lüfter-Solldrehzahl** speichert Drehzahl ÷ 10 (Tabelle: „display value × 10“), **P60** vermutlich ebenso. Wer 400 statt 40 schreibt, fordert 4.000 U/min an, und die Anlage fällt auf ihre Automatik zurück.
- **Beim ESPHome-`number` ist `multiply` invertiert** gegenüber `sensor`-Filtern: Anzeigewert = Rohwert ÷ multiply. Für Rohwert 40 = 400 U/min also `multiply: 0.1`, für ein Register mit Faktor 0,1 °C `multiply: 10`.
- **P59 Pumpen-Mindestdrehzahl:** Rohwert in 10-%-Schritten (8 = 80 %).
[/details]

---

## 6. Konfiguration und Mitarbeit

**Beispielkonfiguration:** https://github.com/holle74/avarma-eigenbau-regelung – vollständige ESPHome-Konfiguration für alle Register, dazu die Regelung aus dem Regelungs-Wiki.

> ⚠️ **Auf eigene Gefahr.** Vor dem Schreiben von Registern erst nur mitlesen, jeden Wert am Panel gegenprüfen und schreibende Entities einzeln freischalten. Garantiefragen klärt jeder selbst.

**Gesucht werden besonders:**
- weitere Anlagen in Abschnitt 1 und Parameterwerte in 3.4,
- Bestätigungen oder Gegenbeispiele zu allen Angaben mit *(1 Anlage)*,
- Erfahrungen mit dem **Abtauverhalten bei Frost**,
- Angaben, ob der **Durchflussmesser** plausible Werte liefert,
- jede **Abweichung von der Hofman-Tabelle**.
