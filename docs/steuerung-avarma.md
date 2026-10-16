# Fast intelligente Heizungssteuerung mit einer Avarma 12 kW

## Worum es geht

Hallo zusammen,

seit Juli steuere ich meine **Hofman Avarma 12 kW** nicht mehr über ihre eingebaute Heizkurve, sondern über eine eigene Regelung in Home Assistant. In diesem Beitrag geht es um die **Logik dahinter**: was sie entscheidet, warum genau so – und warum das nur zusammen mit den Eigenheiten der Avarma und meines Hauses Sinn ergibt.

„Fast intelligent“, weil sie heute vor allem aus gut begründeten Regeln besteht. Ein Gebäudemodell lernt im Hintergrund mit, steuert aber noch nichts. Das ist das Ziel für diesen Winter.

**Zur Entstehung:** Ich bin kein Programmierer. Die Regelung ist zusammen mit Claude entstanden, einer KI von Anthropic. Die Ideen, Messungen und Entscheidungen kommen von mir, den Code und viele Auswertungen hat die KI gemacht.

**Und eine klare Ansage dazu:** Ich möchte hier keine Diskussion über Sinn oder Unsinn von KI. Ich habe mich bewusst dafür entschieden. Punkt. Wer darüber reden will, macht bitte ein eigenes Thema auf.

Allgemeines zur Anlage (Modbus, Parameter, Fallstricke) steht im [Avarma-Wiki](https://akkudoktor.net/t/wiki-avarma-290-waermepumpe-monoblock/41521). Hier geht es um die Steuerung.

**Eure Erfahrungen sind ausdrücklich erwünscht** – mit der Avarma, aber genauso mit anderen Wärmepumpen. Mein Eindruck: Die Regelung vieler Hersteller zielt vor allem darauf, dass die Anlage zuverlässig läuft. Ob sie dabei effizient, leise und vorausschauend arbeitet, spielt kaum eine Rolle. Wer ähnliche – oder ganz andere – Erfahrungen gemacht hat: gern her damit.

## Das Haus: alt, träge, mit wenig Reserve

Mein Haus ist kein Neubau, für den Wärmepumpen gemacht sind. Genau deshalb braucht es eine Regelung, die mitdenkt.

|  |  |
| --- | --- |
| Baujahr | 1968 |
| Wohnfläche | ca. 180 m² |
| Dämmung | keine, außer der obersten Geschossdecke (16 cm Holzfaserplatten) |
| Heizung | Fußbodenheizung im Estrich, 12 Kreise, ca. 1.000 m Rohr, 15 cm Verlegeabstand |
| Messung | 9 Raumthermostate, 12 Ventilstellungen, externer Außenfühler, Strom- und Wärmezählung |
| Wärmeverlust | rund 300–360 W je Kelvin (geschätzt aus Messdaten, noch vorläufig) |
| Wärmespeicher | rund 50 kWh je Kelvin Raumtemperatur |

Daraus folgen vier Dinge, die die ganze Regelung prägen:

1. **Der Estrich ist riesig und träge.** Das Haus kühlt mit einer Zeitkonstante von mehreren Tagen aus. Was ich heute einlade, wirkt morgen noch. Umgekehrt kommt eine Reaktion auf die *aktuelle* Außentemperatur bei einer Frostnacht Stunden zu spät.
2. **Bei Frost gibt es keine Reserve.** Um −5 °C liegt der Wärmebedarf ungefähr dort, wo die Avarma an ihre Grenze kommt. Ein ausgekühltes Haus holt sie dann nicht mehr auf. Früher habe ich morgens von Hand hochgedreht, wenn abends Frost angesagt war.
3. **Die Hydraulik ist ausgereizt.** 15 cm Verlegeabstand bedeutet eine steile Heizkurve: −5 °C brauchte bisher 45 °C Vorlauf. Der Bad-Kreis steht dauerhaft auf 100 %, die Pumpe läuft bei Bedarf am Anschlag. Für das Bad bleibt als einziger Hebel die Zeit – also vorladen.
4. **In der Übergangszeit ist die Anlage zu groß.** Bei 12–16 °C draußen liefert schon die Mindestleistung mehr Wärme, als das Haus abnimmt. Der Estrich verzeiht aber Pausen von mehreren Stunden.

## Die Avarma 12 kW: was sie gut kann und wo sie Hilfe braucht

Die wichtigste Erkenntnis vorweg: **Die eingebaute Regelung der Avarma ist gut.** Im ersten Live-Test modulierte der Kompressor 94 % der Zeit sauber unterhalb seines 90-Hz-Limits, ohne zu takten. Sie braucht nur die richtigen Sollwerte. Deshalb ersetzt meine Regelung sie nicht, sondern füttert sie.

Der zweite Punkt ist der Wirkungsgrad. So sah er vom 6. bis 15. Oktober aus, ausgewertet nur in Phasen, in denen der Kompressor gleichmäßig lief:

| Kompressor | Stunden | Außentemperatur | Wärmeleistung | Strom | COP |
| --- | --- | --- | --- | --- | --- |
| 25–29 Hz | 3,4 h | 14 °C | 3,9 kW | 0,68 kW | 5,7 |
| 30–39 Hz | 18,9 h | 14 °C | 5,3 kW | 0,93 kW | 5,7 |
| 40–49 Hz | 21,3 h | 12,5 °C | 6,3 kW | 1,29 kW | 4,9 |
| 50–59 Hz | 37,4 h | 11,5 °C | 7,0 kW | 1,61 kW | 4,4 |
| 60–69 Hz | 17,8 h | 9 °C | 7,6 kW | 1,84 kW | 4,1 |
| 70–79 Hz | 2,2 h | 10 °C | 8,8 kW | 2,36 kW | 3,7 |
| 80–90 Hz | 0,4 h | 10 °C | 9,4 kW | 2,77 kW | 3,4 |

Von 30 auf 60 Hz fällt der COP um gut ein Viertel, die Wärmeleistung steigt aber nur um rund 45 %. Ein Teil davon kommt von der kälteren Luft bei den hohen Frequenzen, die oberen zwei Zeilen beruhen auf wenigen Stunden. Die Wärmeleistung ist errechnet (Pumpenleistung × Spreizung), nicht mit einem Wärmemengenzähler gemessen.

Die Eigenheiten, auf die die Regelung Rücksicht nimmt:

| Eigenheit der Avarma | Was die Regelung daraus macht |
| --- | --- |
| Liegt der Vorlauf über einem neu gesetzten Sollwert, stoppt der Kompressor meist binnen einer Minute | Absenken nur, wenn der Vorlauf schon darunter liegt („Absenkbremse“) |
| Vorlauf-Soll (P2) nur in ganzen Grad | Sollwert wird vorgesteuert statt schrittweise gesucht |
| Ölrückführung: kurzer Sprung auf 50 Hz, danach oft ein Stopp | Deckel nie unter 50 Hz; solche Stopps zählen nicht als Takten |
| Mindestleistung in der Übergangszeit zu hoch | Lieber stundenweise aus als alle 15 min neu starten |
| Vereist bei feuchter Luft schon bei 10–11 °C, wenn sie hoch dreht | Frostschutz nimmt Frequenz weg |
| Kompressor-Maximum (P45) deckelt auch die Abtauung | Beim Abtauen wird der Deckel sofort freigegeben |
| Antwortet sie nicht auf Modbus, sieht man in Home Assistant nur eingefrorene Werte | Eigener „Modbus online“-Sensor, Regelung pausiert |

## Die Grundidee: Sollwerte geben, nicht selbst regeln

Die Regelung läuft alle 5 Minuten und verstellt an der Avarma nur fünf Dinge: **Ein/Aus, Vorlauf-Soll (P2), Kompressor-Maximum (P45), Lüfterdrehzahl (P71/P72) und „Abtauen jetzt“**. Dazu die Solltemperaturen einzelner Raumthermostate. Alles andere – Modulation, Pumpe, Abtaulogik – macht die Avarma weiter selbst.

```
 Außenfühler, Wetterprognose,
 9 Raumthermostate, 12 Ventile ──► Home Assistant ──► AppDaemon (Python)
                                         ▲                   │ Sollwerte
 Avarma ◄── RS485/Modbus ──► ESP32 (ESPHome) ◄─────────┘
   │                     Watchdog + harte Grenzen
   ▼
 Estrich-FBH ──► Rücklauf schließt den Regelkreis
```

**Führungsgröße ist der Rücklauf, nicht der Vorlauf.** Der Rücklauf zeigt, was das Haus tatsächlich abnimmt. Die Avarma hat aber kein Rücklauf-Soll. Also bestimmt die Regelung ein Rücklauf-Ziel und dreht am Vorlauf-Soll, bis der Rücklauf passt.

**Sicherheitsnetz im ESP:** Kommt 30 Minuten lang kein Befehl aus Home Assistant, setzt der ESP Vorlauf-Soll auf 32 °C und Kompressor-Maximum auf 90 Hz. Fällt Home Assistant aus, heizt die Anlage also einfach normal weiter.

## Die Regellogik, Baustein für Baustein

Jeder Baustein steht hier mit seinem Grund. Fast alle Gründe kommen aus einer Auswertung, nicht aus einer Annahme.

### 1. Rücklauf-Heizkurve mit Vorladen

| Außentemperatur | Rücklauf-Ziel |
| --- | --- |
| −5 °C | 38,5 °C |
| 0 °C | 35,0 °C |
| +15 °C und wärmer | 27,0 °C |

Die Stützpunkte stammen aus meinen Erfahrungswerten aus zwei Wintern, umgerechnet über die gemessene Spreizung. Die Kurve ist bewusst geknickt: Zwischen −5 und 0 °C fällt sie steiler als im milden Bereich. Eine Gerade hat den kalten Rand um 1–2 K unterschätzt – genau die Lücke, die ich früher von Hand ausgeglichen habe.

Auf die Kurve kommen:

- **Vorladen vor Frost:** Liegt das Minimum der 24-h-Prognose unter 8 °C, steigt das Ziel tagsüber um (8 − Prognose) × 0,4 K, höchstens +4 K. Der Estrich wird geladen, solange es draußen noch mild ist und die Avarma effizient arbeitet. **Das ist der wichtigste Baustein für dieses Haus.**
- **Tagesbonus +1 K** von 7 bis 22 Uhr, nachts nur halten.
- **Lernender Offset** ±3 K: Alle 5 h um 0,5 K verschoben, wenn die Räume dauerhaft zu kalt oder zu warm sind. In der Übergangszeit ausgesetzt, dort kletterte er sonst wie eine Ratsche nach oben.
- **Kaltstart-Rampe:** Nach dem Einschalten startet das Ziel bei 27 °C und steigt um 1 K je 15 min.

### 2. Vorlauf-Soll per Vorsteuerung

**Vorlauf-Soll = Rücklauf-Ziel + Spreizung + Korrektur**, begrenzt auf 30–45 °C. Die Spreizung wird live gemessen (sonst 5 K, darauf regelt die Pumpe über P58). Die Korrektur ist ein langsamer Nachregler, ±0,5 K je 15 min.

*Warum:* Vorher hat die Regelung den Vorlauf-Soll in Schritten hoch- und runtergedreht. Stand er über dem echten Vorlauf, bremste er nichts – die Avarma lief bis zum Deckel, und das Absenken wirkte erst nach zwei Stunden. Mit der Vorsteuerung liegt der Sollwert immer knapp beim Vorlauf, und die Avarma moduliert selbst.

**Absenkbremse:** Bei laufendem Kompressor wird nur abgesenkt, wenn der Vorlauf schon auf oder unter dem neuen Sollwert liegt. Ausgewertet an 70 Absenkungen: so nie ein Stopp, bei 0,8 K darüber 6 von 11. Sonst wartet die Regelung, spätestens nach 30 min senkt sie trotzdem um 1 K.

### 3. Kompressor-Deckel nach Außentemperatur

Das Kompressor-Maximum P45 folgt einer Kennlinie: 90 Hz bei −5 °C, 65 Hz bei +5 °C, 50 Hz ab +15 °C. Darunter geht es nie, weil die Ölrückführung auf 50 Hz springt.

*Warum:* Die COP-Tabelle oben. Wenn es mild ist, soll die Avarma lieber länger mit wenig Hz laufen als kurz mit viel.

- **Winter:** Hängt der Kompressor 60 min am Deckel und liegt der Rücklauf 60 min unter Ziel, geht der Deckel um +5 Hz je 30 min hoch, bis 90 Hz. 95 Hz nur bei −5 °C und kälter.
- **Übergangszeit: kein Aufschlag.** Am 9.10. hat er nach dem Kaltstart bis +25 Hz aufgeschlagen und vor allem Strom und Eis gekauft: COP 3,3–3,6 bei 81–84 Hz statt 4,3–4,9 bei 60 Hz, und der Rücklauf kam trotzdem nicht schneller ans Ziel. Der Rückstand nach dem Kaltstart ist Estrich-Laden, kein Wärmemangel.
- **Frostschutz in der Übergangszeit:** Fällt die Lamelle bei Lüfter am Anschlag auf 0 °C, geht der Deckel sofort auf 50 Hz. Erst wenn sie 10 min bei 2 °C oder mehr liegt, wieder +5 Hz je 15 min.
- **Abtauung:** Während die Avarma abtaut, setzt die Regelung P45 auf die Abtaufrequenz (65 Hz). Sonst dauert die Abtauung länger und wird nicht fertig.

### 4. Lüfter: so leise wie möglich

Der Lüfter läuft manuell zwischen 400 und 900 U/min. Grundsatz: so niedrig wie möglich, solange der Verdampfer bei 1 °C oder wärmer bleibt. Hoch geht es schnell (bis 300 U/min pro Schritt), runter behutsam (50 U/min alle 10 min).

Wird es trotzdem kritisch – Verdampfer unter −3 °C, 7 K unter der Außenluft, 20 min lang, Lüfter schon auf Volllast – löst die Regelung selbst eine Abtauung aus.

### 5. Ein- und Ausschalten

**Ein**, wenn es draußen 16,5 °C oder kälter ist (bei angesagtem Frost zählt die Prognose) und das Haus kalt genug ist. **Aus** über die Heizgrenze: 3-h-Mittel der Außentemperatur 18,5 °C oder mehr.

In der Übergangszeit kommen drei Regeln dazu. Gemessen wird am Mittel der Räume im Erdgeschoss (EG):

| Regel | Auslöser | Danach |
| --- | --- | --- |
| Haus warm genug | EG 21 °C, 30 min lang | Neustart bei EG 20 °C |
| Anlage taktet | 2 Kompressorstarts in 45 min | 3 h Pause |
| Nachtsperre 22–8:30 Uhr | kein Start, Abschalten ab EG 20,5 °C | außer bei Frostprognose oder EG unter 19 °C |

*Warum:* Lieber ein paar Stunden aus und den Estrich puffern lassen als alle 15 Minuten neu starten. Und nicht jeder Stopp ist Takten: In der ersten Woche kamen 13 von 13 Stopps von der eigenen Regelung oder der Ölrückführung. Die zählen seitdem nicht mehr mit.

Winter, Übergangszeit, Kühlen oder ganz von Hand wähle ich über einen einzigen Schalter im Dashboard.

### 6. Lastverteilung zwischen den Räumen

Wenn der Kompressor am Deckel hängt, reicht die Wärme nicht für alle Kreise. Dann drosselt die Regelung **Spender-Räume**, damit mehr zu den wichtigen Räumen fließt:

- **Vorrang:** Bad, Dusche, Wohnzimmer, Büro, Ankleide – werden nie gedrosselt.
- **Spender** in dieser Reihenfolge: Schlafzimmer (nicht unter 18 °C), Keller, Flur, Yoga (nicht unter 20 °C).
- **Auslöser:** Ein Vorrang-Raum hat sein Ventil mindestens 90 % offen und liegt 0,3 K unter Soll, 15 min lang – **und** der Kompressor hängt am Deckel.

*Warum die letzte Bedingung:* Das Bad-Ziel ist bewusst hoch gewählt, damit es die anderen Räume mitzieht. Ohne den Deckel als Bedingung wäre dauernd gedrosselt worden – viel Kälte für nichts. In der Übergangszeit ist nur das Wohnzimmer Spender.

## Was es bisher bringt – ehrlich gemessen

**Beim Stromverbrauch je Gradtag liegt die Regelung Anfang Oktober gleichauf mit dem Vorjahr.** Der Gewinn liegt bisher woanders.

| 1.–15. Oktober | 2025 (Avarma-Heizkurve) | 2026 (eigene Regelung) |
| --- | --- | --- |
| Strom Heizung | 220 kWh | 197 kWh |
| Außentemperatur im Mittel | 11,8 °C | 12,4 °C |
| Strom je Gradtag (Basis 17 °C) | 2,83 kWh | 2,80 kWh |
| Bad im Monatsmittel | 20,4 °C | 20,1 °C |

Das überrascht mich nicht: In der Übergangszeit kann eine Regelung wenig gewinnen, die Anlage ist ohnehin unterfordert. Was sich verändert hat:

- **Keine Handeingriffe mehr.** Früher habe ich morgens hochgedreht, abends runter, bei Frostprognose vorgeheizt.
- **Ruhiger Betrieb:** Die Anlage läuft an milden Tagen 13 Stunden am Stück, nie über 68 Hz, und geht abends per Nachtsperre aus. Takt-Abschaltungen gab es seit Ende September nur eine – und die war echt: selbst bei 26 Hz noch zu viel Leistung.
- **Der Rücklauf hält sein Ziel auf ±1 K**, die Räume im Erdgeschoss liegen im Tagesmittel bei 20,3–20,5 °C.
- **Arbeitszahl rund 4,4** vom 10. bis 15. Oktober – errechnet aus Pumpenleistung × Spreizung, nicht mit einem Wärmemengenzähler gemessen.

Der eigentliche Test kommt mit dem ersten Frost. Dort soll das Vorladen den Unterschied machen: Wärme einlagern, solange es mild ist und die Avarma im Teillastbereich läuft, statt in der Frostnacht am Anschlag nachzuheizen. Ich berichte im Winter mit Zahlen.

## Was noch fehlt: der Weg zu „wirklich intelligent“

Das Vorladen rechnet heute mit einer festen Formel. Im Winter soll es das Haus selbst vorhersagen.

Dafür lernt im Hintergrund ein **Gebäudemodell** mit: aus nächtlichen Abkühlphasen und aus der zugeführten Wärme. Aktueller, noch vorläufiger Stand: rund 300 W Wärmeverlust je Kelvin, rund 50 kWh Wärmespeicher je Kelvin, Zeitkonstante knapp 7 Tage. Belastbar wird das erst nach etwa 15 geheizten Frostnächten. Bis dahin greift es bewusst in keinen Regelkreis ein.

Geplant für diesen Winter:

- **Auskühlprognose statt Formel:** „Heute Nacht −6 °C, das Haus verliert bis morgen so viel – also jetzt so viel einlagern.“
- **Leiser in der Nacht:** Vorlauf, Lüfter und Aufschlag nachts begrenzen. Die Schwellen will ich im ersten kalten Winter nach Gehör einstellen.
- **Durchlaufen oder Pausen?** In der Übergangszeit teste ich 3 h an / 1 h Pause gegen Durchlaufen an ähnlichen Tagen. Maßstab ist der Strom je Gradtag.
- **Eigene Wetterstation** als Außenfühler, der eingebaute ist in der Sonne bis zu 5,5 K zu hoch.

**Fragen an euch:**

- Wie verhält sich eure Avarma bei Frost unter −5 °C – wo liegt bei euch die Leistungsgrenze?
- Hat jemand P46 (Mindestfrequenz) noch tiefer als 25 Hz oder P114 anders als 3 % im Einsatz?
- Taut eure Anlage in der Übergangszeit zuverlässig selbst ab, und mit welchem P85?
- Wer eine andere Wärmepumpe hat: Wie kommt deren Regelung mit einem trägen, wenig gedämmten Haus klar – und was habt ihr selbst nachgerüstet?

## Code und Nachbau

Der komplette Code liegt offen auf GitHub: [holle74/avarma-eigenbau-regelung](https://github.com/holle74/avarma-eigenbau-regelung). Drin sind die vier AppDaemon-Apps, die ESPHome-Konfiguration für den ESP32, die Automationen und eine Liste der nötigen Helfer.

> ⚠️ **Bitte nicht 1:1 übernehmen.** Die Regelung schreibt direkt in Parameterregister der Avarma. Falsche Adressen oder Skalierungen können die Anlage in Störung schicken. Alle Kurven, Grenzen und Schwellen passen zu *meinem* Haus und *meiner* Hydraulik. Wer es nachbaut, sollte zuerst nur mitlesen, jeden Registerwert am Display gegenprüfen und die Werte an das eigene Haus anpassen.

Fragen, Kritik, bessere Ideen und eigene Erfahrungen gern hier im Thema.

Grüße, holle74
