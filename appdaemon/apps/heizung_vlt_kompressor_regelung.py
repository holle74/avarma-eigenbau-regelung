import math
from datetime import datetime, timedelta, timezone

from appdaemon.plugins.hass.hassapi import Hass

# -------------------- Entities --------------------
BAD_CLIMATE = "climate.raumtemperaturregler_bad_unten_bad"
WP_SWITCH = "switch.esphome_web_avarma_warmepumpe_ein_aus"
# Einschaltzeitpunkt der WP als Unix-Zeit. Ueberlebt einen HA-Neustart, anders
# als last_changed des Schalters - siehe wp_laufzeit_minuten().
WP_EINSCHALTZEIT_HELPER = "input_number.wp_einschaltzeit"
AT_SENSOR = "sensor.aussentemperatur_avarma_korrigiert"
# 3-h-Mittel derselben Aussentemperatur, statistics-Helfer (2026-09-12).
# Bezugsgroesse der Heizgrenzen-Abschaltung, siehe AUSSCHALT_* weiter unten.
AT_MITTEL_SENSOR = "sensor.wp_aussentemperatur_mittel_3h"

VLT_SOLL_NUMBER = "number.esphome_web_f34aa0_vorlauf_solltemperatur"
VLT_IST_SENSOR = "sensor.esphome_web_avarma_vorlauftemperatur"
RLT_IST_SENSOR = "sensor.esphome_web_avarma_rucklauftemperatur"
KOMPRESSOR_MAX_NUMBER = "number.esphome_web_avarma_kompressor_maximalfrequenz"
KOMPRESSOR_IST_SENSOR = "sensor.esphome_web_avarma_kompressor_frequenz_ist"
HEIZKURVE_OFFSET_HELPER = "input_number.wp_heizkurve_offset"

FAN_MODE_SELECT = "select.controllroom_esphome_web_avarma_luftersteuerung_modus"
FAN_SPEED_NUMBER = "number.controllroom_esphome_web_avarma_lufter_solldrehzahl_manuell"
EVAPORATOR_SENSOR = "sensor.esphome_web_avarma_verdampfertemperatur"
# Betriebsstatus (Modbus 4354) ist ein Bitfeld, laut ESPHome-YAML:
# bit0=Standby, bit1=Ein, bit2=Aus, bit4=Abtauen, bit9=Frostschutz.
# Am 24.08.2026 verifiziert: waehrend der Abtauung 05:34:40-05:42:20 stand der
# Sensor auf 18 (= 16 Abtauen + 2 Ein), davor und danach auf 2.
BETRIEBSSTATUS_SENSOR = "sensor.esphome_web_avarma_betriebsstatus"
BETRIEBSSTATUS_BIT_ABTAUEN = 16

# Register 4103 im Steuerblock der Avarma ("Forced Defrosting"): 1 startet sofort
# eine Abtauung, 0 bricht eine laufende ab. Der Regler setzt das Register nach dem
# Zyklus selbst zurueck, der Schalter faellt also von allein wieder auf "off".
ABTAU_ERZWINGEN_SWITCH = "switch.controllroom_esphome_web_avarma_abtauung_erzwingen"

# Handschalter fuer den Autostart (2026-08-25). Steht er auf "off",
# schaltet die Regelung die WP nicht mehr selbst ein - laufender Betrieb wird
# davon NICHT beendet, das bleibt eine Handlung des Menschen.
#
# Anlass: E15 "Water flow error" seit 24.08. 11:38. Die Anlage stoert bei jedem
# Startversuch sofort wieder, der Autostart hat sie bei 9 Grad Aussentemperatur
# immer wieder angeworfen. Bis die Ursache (vermutlich Umwaelzpumpe oder Luft im
# System) gefunden ist, bleibt der Schalter aus.
AUTOSTART_HELPER = "input_boolean.wp_autostart_aktiv"

# Handschalter fuer die Heizgrenzen-Abschaltung (2026-09-12), Gegenstueck zum
# AUTOSTART_HELPER. Steht er auf "off", schaltet die Regelung die WP nicht wegen zu
# warmer Aussentemperatur ab - laufender Betrieb bleibt dann Sache des Menschen.
#
# Anlass fuer den Schalter: am 12.09.2026 lief ein befristeter Testlauf mit P68=0 bis
# 20:00. Die neue Heizgrenze haette ihn wegen 20,9 Grad AT-Mittel sofort beendet.
# Ein Test darf nicht von einer Komfortlogik abgewuergt werden.
HEIZGRENZE_HELPER = "input_boolean.wp_heizgrenze_aktiv"

# Uebergangszeit-Regeln (2026-09-13), siehe UEBERGANG_* weiter unten.
# Mittel aus Ankleide, Bad, Flur, Keller und Yoga - min_max-Helfer
# (entry_id 01M2D0PKR9XXFS1XCAHN0MAR8F).
EG_MITTEL_SENSOR = "sensor.wp_raumtemperatur_mittel_eg"
# Ende der Taktsperre. Als Helfer statt Instanzvariable: ein Reload der App darf eine
# laufende Sperre nicht aufheben.
TAKTSPERRE_HELPER = "input_datetime.wp_taktsperre_bis"

HEARTBEAT_NUMBER = "number.controllroom_esphome_web_avarma_agent_heartbeat"
FROST_FORECAST_NUMBER = "input_number.wp_prognose_aussentemperatur_minimum_24h"

# Spender-Raeume der hydraulischen Lastverteilung (heizung_lastverteilung.py) -
# dient hier nur als "ausgeschoepft?"-Signal fuer die Kompressor-Eskalation.
DONOR_CHECKS = [
    {"climate": "climate.raumtemperaturregler_schlafzimmer_schlafzimmer", "floor": 18.0,
     "backup": "input_number.wp_spender_schlafzimmer_original_soll"},
    {"climate": "climate.raumtemperaturregler_keller_keller", "floor": 20.0,
     "backup": "input_number.wp_spender_keller_original_soll"},
    {"climate": "climate.raumtemperaturregler_flur_flur", "floor": 20.0,
     "backup": "input_number.wp_spender_flur_original_soll"},
    {"climate": "climate.raumtemperaturregler_yoga_yoga", "floor": 20.0,
     "backup": "input_number.wp_spender_yoga_original_soll"},
]

# -------------------- Zielwerte & Grenzen (2026-07-23) --------------------
BAD_TARGET_C = 22.0
BAD_DEADBAND_C = 0.3
DAY_OVERHEAT_BONUS_C = 1.0     # tagsueber leichtes Ueberheizen erlaubt (Estrich als Puffer)
FROST_BOOST_BONUS_C = 1.0      # zusaetzlicher Tages-Bonus bei Frost-Prognose fuer die Nacht
FROST_THRESHOLD_C = 2.0        # Prognose-Minimum <= diesem Wert zaehlt als "Frost erwartet"

# Vorladen: proportional zur erwarteten Nachtkaelte, nur tagsueber.
VORLADE_AB_C = 8.0             # ab diesem Prognose-Minimum beginnt Vorladen
VORLADE_FAKTOR = 0.4           # K RL-Bonus je K, das die Prognose darunter liegt
VORLADE_MAX_C = 4.0            # Deckel, damit die Kurve nicht davonlaeuft

VLT_MIN = 30.0
VLT_MAX = 45.0

# -------------------- Vorlauf-Vorsteuerung (2026-09-13) --------------------
# VL-Soll = RL-Ziel + Spreizung + Korrektur. Ersetzt die fruehere Schrittlogik
# (VL-Soll +-1 K je 15 min).
#
# WARUM: Am 12.09.2026 stand P2 nach einem Anlagenneustart auf 45 Grad, der Vorlauf kam
# nie ueber 37. Solange der Sollwert ueber dem Vorlauf parkt, bremst er nichts - die
# Schrittlogik brauchte nach Erreichen des RL-Ziels gut zwei Stunden, bis die Absenkung
# ueberhaupt wirkte, und der Ruecklauf lief bis 2 K ueber Ziel. Von 18:20 bis 19:50, als
# der Sollwert beim Vorlauf lag, modulierte die Avarma selbst zwischen 27 und 52 Hz und
# hielt den Ruecklauf auf 0,3 K genau. Diesen Zustand stellt die Vorsteuerung her: der
# Sollwert wird in jedem Zyklus absolut berechnet und kann nicht ueber dem Vorlauf haengen.
#
# Spreizung live (VL-Ist - RL-Ist), solange der Kompressor laeuft und der Wert plausibel
# ist, sonst P58 - auf diese Differenz regelt die Pumpe selbst. Live ist besser, weil P59
# (Pumpe mindestens 80 %) die Pumpe bei Teillast nicht weiter drosseln laesst: dann faellt
# die Spreizung unter 5 K, am Anschlag (94 %) stieg sie am 12.09. auf 6-6,5 K.
SPREIZUNG_FALLBACK_K = 5.0     # P58, am 13.09.2026 zurueckgelesen (roh 50)
SPREIZUNG_MIN_K = 2.0
SPREIZUNG_MAX_K = 9.0
# Korrektur: langsamer I-Anteil fuer bleibende Abweichung, etwa wenn die Avarma den
# Vorlauf etwas unter ihrem Sollwert haelt. Nicht persistiert - nach einem Reload beginnt
# sie bei 0 und baut sich in 15-min-Schritten wieder auf.
KORREKTUR_STEP_C = 0.5
KORREKTUR_INTERVAL_MINUTES = 15
KORREKTUR_MAX_C = 3.0
# Schreibtakt fuer P2. Grosse Abweichungen (z.B. 45 Grad nach einem Anlagenneustart)
# werden sofort geschrieben.
VLT_WRITE_INTERVAL_MINUTES = 10
VLT_SOFORT_AB_K = 3.0
# Absenken ohne Kompressorstopp (Auswertung 25.09.2026): Liegt der Vorlauf nach einer
# Absenkung 1,0 K oder mehr ueber dem neuen Sollwert, stoppt die Avarma sofort - 10 der 13
# Kompressorstopps vom 17.-24.09. kamen so zustande (VL-Ist >= neues Soll + 1,0: 10 von 12
# Absenkungen mit Stopp, darunter 0 von 10). P2 geht nur in ganzen Grad. Bei laufendem
# Kompressor wird deshalb nur so weit abgesenkt, dass der Vorlauf hoechstens
# VLT_ABSENK_MAX_UEBER_K darueber liegt. Sitzt er genau auf dem Sollwert, geht nicht einmal
# 1 K - dann wird gewartet, bis er von selbst etwas faellt, und nach
# VLT_ABSENK_WARTEN_MAX_MINUTES trotzdem um 1 K gesenkt. Diesen Stopp zaehlt die
# Takterkennung nicht (TAKT_EIGENE_ABSENKUNG_MINUTES).
VLT_ABSENK_MAX_UEBER_K = 0.8
VLT_ABSENK_WARTEN_MAX_MINUTES = 30

# -------------------- Ruecklauf-Heizkurve (2026-07-24) --------------------
# Zwei Erfahrungswerte aus vergangenen Heizperioden spannen eine lineare Kurve auf:
# bei 0 Grad AT soll der Ruecklauf ca. 35 Grad betragen (delta T 5 Grad -> VLT ~40 Grad),
# bei 15 Grad AT (= Start-/Heizgrenze, siehe AUTOSTART_* unten) 28 Grad.
# Die Avarma hat kein eigenes Ruecklauf-Soll-Register - RLT-Ist ist hier die Fuehrungsgroesse,
# VLT bleibt die einzige Stellgroesse und wird ueber die bestehende Schrittlogik nachgefuehrt.
# Heizkurve auf den RUECKLAUF, stueckweise linear (Aussentemperatur, RL-Ziel).
# Grundlage: die eigenen Erfahrungswerte aus zwei Wintern (2026-08-03), erhoben als
# VORLAUF-Temperaturen - 45 °C bei -5, 39,5 °C bei 0, 35 °C bei +8 - umgerechnet
# ueber die gemessene, lastabhaengige Spreizung (Juli-Test: Ø 5,4 K, im Frost
# eher 6-7 K, weil die Pumpe bei Ø 89 % kaum noch Reserve hat).
#
# Warum stueckweise: die eigenen VL-Kurve faellt zwischen -5 und 0 °C mit 1,10 K/K,
# zwischen 0 und +8 nur mit 0,56 K/K. Eine einzelne Gerade (vorher -0,47 K/K,
# nach unten extrapoliert) unterschaetzt den kalten Rand um 1-2 K - genau die
# Luecke, die der Betreiber bisher manuell ausgleichen musste.
HEIZKURVE_PUNKTE = [(-5.0, 38.5), (0.0, 35.0), (15.0, 28.0)]

# Rueckwaertskompatible Namen (RL-Rampenstart bzw. milder Kurvenrand)
HEIZKURVE_AT_PUNKT2 = HEIZKURVE_PUNKTE[-1][0]
HEIZKURVE_RL_PUNKT2 = HEIZKURVE_PUNKTE[-1][1]

RL_MIN = 25.0
RL_MAX = 40.0
RL_DEADBAND_C = 0.3

# Kaltstart-Rampe: RL-Ziel beginnt beim Einschalten der WP nicht sofort beim Kurvenwert,
# sondern bei diesem (identisch mit dem Kurvenpunkt bei der Heizgrenze) und naehert sich
# dem tatsaechlichen Kurvenziel in kleinen Schritten an - das bildet die noetige Geduld
# waehrend der Estrich-Traegheit ab, ohne einen zweiten Rampen-Mechanismus zu brauchen.
RL_ZIEL_START_C = HEIZKURVE_RL_PUNKT2
RL_ZIEL_STEP_C = 1.0
RL_ZIEL_STEP_INTERVAL_MINUTES = 15

# Automatischer WP-Start, wenn beide Bedingungen erfuellt sind (2026-07-24).
# Heizgrenze (2026-08-03: "so 16-17 Grad"). Bewusst NICHT mehr an den
# oberen Kurvenstuetzpunkt gekoppelt - die Heizgrenze ist eine Bedarfsfrage,
# der Stuetzpunkt eine Kurveneigenschaft. Vorher waren beide 15,0.
AUTOSTART_AT_THRESHOLD_C = 16.5
AUTOSTART_BAD_THRESHOLD_C = 18.5

# -------------------- Heizgrenzen-Abschaltung (2026-09-12) --------------------
# Das Gegenstueck zum Autostart. Vorher gab es KEINE Abschaltgrenze: einmal an, lief
# die WP bis jemand sie von Hand abschaltete - am 24.08.2026 bewusst offen gelassen
# ("wir lassen das mal, eventuell faellt uns mal eine schoene Logik ein").
#
# Bezugsgroesse ist das 3-h-Mittel der Aussentemperatur, nicht der Momentanwert: eine
# einzelne Mittagsspitze soll die Heizung nicht abwuergen, und der Estrich reagiert
# ohnehin nur auf Stundenmittel.
#
# Die Schwelle liegt 2 K ueber der Einschaltgrenze. Dadurch entsteht eine Totzone
# zwischen 16,5 (Einschalten, Momentanwert) und 18,5 (Abschalten, 3-h-Mittel), in der
# nichts passiert. Ohne diese Spanne wuerde die Anlage um die Schwelle herum im
# Stundenrhythmus ein- und ausschalten.
AUSSCHALT_AT_THRESHOLD_C = AUTOSTART_AT_THRESHOLD_C + 2.0

# Mindestlaufzeit, bevor die Heizgrenze greifen darf: ein begonnener Aufheizvorgang
# soll zu Ende gehen. Nach einem HA-Neustart liest wp_laufzeit_minuten() zu kurz
# (last_changed springt auf die Neustartzeit) - dann wird also eher weitergeheizt als
# abgeschaltet, und das ist die richtige Richtung.
AUSSCHALT_MIN_LAUFZEIT_MINUTES = 120

# Das statistics-Mittel ist erst belastbar, wenn sein Puffer das 3-h-Fenster
# ueberwiegend deckt (Attribut age_coverage_ratio). Direkt nach einem HA-Neustart ist
# es das nicht - dann lieber weiterheizen als wegen 20 Minuten Daten abschalten.
AUSSCHALT_MIN_COVERAGE = 0.8

# Adaptive Nachfuehrung der Heizkurve (Parallelverschiebung, dauerhaft aktiv - kein
# Lernende). Bildet grob den tatsaechlichen Waermeverlust des Hauses relativ zur
# angenommenen Kurve ab; lernt NICHT Steigung, Windeinfluss oder thermische Traegheit
# (das waere der naechste Ausbauschritt, siehe Projekt-Notizen zur Gebaeude-Thermometrie).
ADAPT_INTERVAL_MINUTES = 300
ADAPT_STEP_C = 0.5
ADAPT_OFFSET_MIN = -3.0
ADAPT_OFFSET_MAX = 3.0

KOMPRESSOR_MAX_NORMAL = 90.0
KOMPRESSOR_MAX_ESCALATED = 95.0

# Die letzten 5 Hz sind ausdruecklich Frostreserve und kein Alltagswerkzeug
# (2026-08-24: "die 5 Hz ueber 90 wollten wir nur fuer strengen Frost").
# Am 24.08. lief die Anlage bei 7 Grad AT auf 95 Hz - COP 3,3 statt der ~4,8, die
# bei 60 Hz messbar sind, und der Verdampfer wurde so weit heruntergezogen, dass
# um 05:34 abgetaut werden musste.
#
# Die Schwelle ist bewusst der kalte Stuetzpunkt der Deckel-Kennlinie: Dort liegt
# die Kennlinie selbst schon bei 90 Hz, die Reserve wird also genau dann frei,
# wenn der regulaere Deckel ausgereizt ist. Darueber ist bei 90 Hz Schluss.
KOMPRESSOR_ESKALATION_AT_C = -5.0
VLT_SOLL_IST_GAP_THRESHOLD_C = 2.0   # "VLT wird nicht erreicht"
KOMPRESSOR_NEAR_MAX_RATIO = 0.95     # Kompressor laeuft schon nahe seinem aktuellen Limit

# --- Lastabhaengiger Kompressor-Deckel (2026-08-22) ---
#
# WARUM: Am 22.08.2026 gemessen, wie der COP dieser Anlage mit der Frequenz faellt
# (stabile Phasen, An-/Abfahrvorgaenge und COP-Ausreisser herausgefiltert):
#
#   30-39 Hz -> COP 6,3     60-69 Hz -> COP 4,8
#   40-49 Hz -> COP 5,8     80-89 Hz -> COP 4,2
#   50-59 Hz -> COP 5,2     90    Hz -> COP 4,2
#
# Teillast ist also rund 50 % effizienter als Volllast. Dazu kommt ein zweiter,
# unabhaengiger Effekt: Mit 90 Hz treibt die Anlage den Ruecklauf schnell ueber den
# Sollwert, die interne Regelung schaltet ab, wenige Minuten spaeter wieder ein.
# Genau das passierte im selben Test viermal zwischen 13:02 und 14:22. Ein
# niedrigerer Deckel verlangsamt den Anstieg und verlaengert die Laufzeit.
#
# GRENZE: Taktet die Anlage, weil schon die Mindestfrequenz (25 Hz) mehr liefert als
# das Haus abnimmt, hilft kein Max-Deckel - dann muesste der Vorlauf runter.
#
# ABGRENZUNG zur Notiz vom 03.08.2026 ("Umbau auf Kompressor-Regelung waere ein
# Rueckschritt"): Dort ging es darum, die Herstellerregelung zu ERSETZEN (VL fest auf
# 45 Grad, Leistung nur noch ueber die Frequenz). Hier bleibt die Kaskade unveraendert,
# der Deckel begrenzt sie nur nach oben. Die Modulation darunter macht die Avarma
# weiterhin selbst.
#
# OELRUECKFUEHRUNG - der Grund fuer die hohe Untergrenze (2026-08-22):
#
# Der Verdichter braucht periodisch eine hoehere Drehzahl, damit das Schmieroel aus
# dem Kreislauf zurueck zum Kompressor gefoerdert wird. Bei dauerhaft niedriger
# Frequenz sammelt es sich im Verdampfer und in den Leitungen - auf Dauer ein
# Lagerschaden.
#
# In der Hofman-Modbus-Tabelle belegt:
#   P41 (Adresse 8231) "Compressor oil return frequency", 10~100 Hz, Werk 50 Hz
#   C49 (Adresse 4609) "Return lubricant oil status", 0 = normal, 1 = oil return
#
# Die Avarma faehrt die Oelrueckfuehrung also selbst. Offen ist, ob P46
# (Kompressor-Maximalfrequenz, unser Deckel) diesen Modus begrenzt oder ob er sich
# darueber hinwegsetzt. Die Doku sagt dazu nichts.
#
# Deshalb: Der Deckel bleibt IMMER >= OELRUECKFUEHRUNG_FREQ_HZ. Dann ist es
# gleichgueltig, welche der beiden Varianten zutrifft.
#
# Der Wert ist seit dem ESPHome-Flash vom 22.08.2026 nicht mehr geschaetzt, sondern
# direkt aus P41 abgelesen: sensor.controllroom_esphome_web_avarma_oelrueckfuehrung_frequenz
# meldet 50 Hz (= Werkseinstellung). Bewusst hart als Konstante und nicht aus dem
# Sensor gelesen - faellt der Sensor aus, waere ein stiller Fallback auf einen
# niedrigeren Deckel genau die Situation, die dieser Wert verhindern soll.
# Wird P41 an der Anlage je geaendert, gehoert die Konstante hier mit angepasst.
#
# NAECHSTER AUSBAUSCHRITT: Mit dem ebenfalls neuen binary_sensor C49
# ("Oelrueckfuehrung aktiv") liesse sich der Deckel gezielt nur waehrend der
# Oelrueckfuehrung anheben. Dann koennte die milde Kennlinie auf 45 Hz sinken
# (gemessener COP ~5,8 statt ~5,2 bei 50 Hz). Erst sinnvoll, wenn ein paar Zyklen
# beobachtet sind - unbekannt ist bisher, wie lange eine Phase dauert und wie
# schnell der Deckel folgen muss.
OELRUECKFUEHRUNG_FREQ_HZ = 50.0   # P41, am 22.08.2026 direkt ausgelesen

# Stuetzstellen (Aussentemperatur, Deckel in Hz), stueckweise linear interpoliert.
# Bewusst grosszuegig gewaehlt - Prioritaet ist Komfort, nicht das letzte Zehntel COP.
KOMPRESSOR_DECKEL_PUNKTE = [(-5.0, 90.0), (5.0, 65.0), (15.0, 50.0)]
KOMPRESSOR_DECKEL_MIN = OELRUECKFUEHRUNG_FREQ_HZ

# --- Sicherheitspuffer auf den Deckel ---
#
# Der Deckel darf den Komfort nicht kosten. Bleibt der Ruecklauf laenger als
# BOOST_SUSTAIN_MINUTES unter seinem Ziel, wird der Deckel schrittweise angehoben,
# bis hinauf zu KOMPRESSOR_MAX_ESCALATED.
#
# Das ersetzt zugleich die alte 95-Hz-Eskalation, die drei Bedingungen UND-verknuepfte
# (VLT-Luecke >= 2 K, Kompressor >= 95 % seines Max, Lastverteilung erschoepft) und
# deshalb praktisch nie ausloesen konnte: Im Test vom 22.08. war die dritte ab 11:56
# erfuellt - da hatte der Kompressor laengst auf 73 Hz zurueckmoduliert (81 % statt 95 %).
# Die Bedingungen schlossen sich gegenseitig aus. Ein einzelnes, zeitbasiertes Kriterium
# (Ruecklauf bleibt zurueck) kann dagegen tatsaechlich greifen.
#
# UMBAU 2026-09-13 zur Winter-Eskalation: Der Deckel folgt normal nur noch der Kennlinie,
# die Leistung darunter regelt die Avarma selbst (Vorsteuerung oben). Angehoben wird nur,
# wenn der Kompressor am Deckel haengt UND der Ruecklauf seit mindestens einer Stunde
# unter Ziel liegt - beides zusammen. Am 12.09. hat der alte Puffer den Deckel bei
# 21 Grad Aussentemperatur bis 85 Hz getrieben und war damit der eigentliche Regler.
BOOST_STEP_HZ = 5.0
BOOST_SUSTAIN_MINUTES = 60       # so lange muss die Luecke schon bestehen
BOOST_STEP_INTERVAL_MINUTES = 30

# Zweite Bedingung der Winter-Eskalation (seit 2026-09-13 UND-verknuepft, vorher eine
# Abkuerzung nach 5 min): so lange muss der Kompressor schon am Deckel haengen.
BOOST_AM_DECKEL_MINUTES = 60
# Der Kompressor moduliert auch am Limit um ein paar Hz (im Test vom 22.08. bei
# Deckel 90 zwischen 83 und 90). Ohne Toleranz gaelte er nur in Momentaufnahmen
# als "am Deckel".
KOMPRESSOR_AM_DECKEL_TOLERANZ_HZ = 3.0
BOOST_DECAY_INTERVAL_MINUTES = 30  # Abbau langsamer als Aufbau - verhindert Pendeln
BOOST_MAX_HZ = 55.0              # reicht von KOMPRESSOR_DECKEL_MIN bis KOMPRESSOR_MAX_ESCALATED

# Kennlinie im 5-Hz-Raster, geschrieben nur bei klarer Abweichung. P45 ist ein
# Parameterregister - ob die Avarma es bei jedem Schreiben ins EEPROM sichert, ist offen.
DECKEL_RASTER_HZ = 5.0
DECKEL_SCHREIB_HYSTERESE_HZ = 3.5

# Kaltstart-Sperre (2026-08-24).
#
# WARUM: Nach dem Start ist der Ruecklauf IMMER unter Ziel - das Haus ist kalt und
# das RL-Ziel faehrt absichtlich langsam hoch (1 K/15 min ab 28 Grad). Beide
# Puffer-Kriterien sprechen deshalb im Kaltstart trivial an: "Ruecklauf bleibt
# zurueck" ist per Definition erfuellt, und der Kompressor haengt beim Hochfahren
# ohnehin am Deckel. Am 24.08. hat genau das den Puffer binnen 15 Minuten nach dem
# Start auf +34 Hz getrieben.
#
# Solange die Anlage erst anfaehrt, ist ein zurueckliegender Ruecklauf kein Beleg
# fuer Unterversorgung, sondern der geplante Verlauf. Der Puffer bleibt so lange aus.
BOOST_KALTSTART_MINUTES = 45

# Deckel fuer die Uebernahme aus dem Geraetezustand (2026-08-24).
#
# Die Uebernahme sollte verhindern, dass sich der Puffer nach einem Reload mitten im
# Winter neu aufbauen muss. Sie hat am 24.08. aber das Gegenteil bewirkt: Der
# ESPHome-Watchdog hatte den Deckel waehrend des WP-Stillstands auf 90 Hz gesetzt,
# und um 04:57 - fuenf Minuten nach dem Start - uebernahm die Regelung daraus
# +29 Hz als vermeintlich erarbeiteten Puffer. Die Bedingung "Ruecklauf bleibt
# zurueck" hat das nicht abgefangen, weil sie im Kaltstart immer wahr ist.
#
# Uebernommen wird deshalb nur noch ein Anschub. Ist der Bedarf echt, waechst der
# Puffer ueber den normalen, im Log sichtbaren Weg in 15-Minuten-Schritten nach.
BOOST_UEBERNAHME_MAX_HZ = 10.0

# --- Vereisungs-Verriegelung (2026-08-24) ---
#
# WARUM: Am 24.08. um 06:37 hat der Puffer den Deckel von 72 auf 77 Hz angehoben,
# weil der Ruecklauf zurueckblieb. 30 Sekunden spaeter stand der Verdampfer bei
# -3 Grad, drei Minuten spaeter taute die Anlage ab. Zusaetzliche Frequenz hat dort
# keine Waerme mehr gekauft, sondern Eis - und die Abtauung kostet mehr, als die
# 5 Hz je gebracht haetten.
#
# KRITERIUM: Nicht die absolute Verdampfertemperatur - die liegt im Winter dauerhaft
# unter der Untergrenze, eine Sperre darauf wuerde den Puffer die halbe Heizsaison
# lahmlegen. Stattdessen die SPREIZUNG (Aussentemperatur minus Verdampfertemperatur).
# Sie misst, wie hart die Anlage die Lamelle leerzieht, und ist jahreszeitneutral:
#
#   heute 72 Hz + 900 RPM, erholt:  6,9 / +0,5  ->  6,4 K   gesund
#   heute 95 Hz:                    6,9 / -2,0  ->  8,9 K   zieht leer
#   heute 77 Hz mit Eis:            6,9 / -3,5  -> 10,4 K   Abtauung folgt
#   erwarteter Winterbetrieb:      -5,0 / -10   ->  ~5 K    gesund trotz tiefem Minus
#
# Der Schwellwert ist aus den Messwerten dieses einen Morgens gegriffen - fuer den
# Winter fehlen noch Daten. Deshalb der Notausgang darunter.
VEREISUNG_SPREIZUNG_MAX_K = 7.0

# Frueher stand hier ein Notausgang: Haelt sich die Vereisung eine Dreiviertelstunde
# trotz voller Luftmenge, wurde die Sperre aufgehoben und weiter Frequenz gegeben -
# "Komfort hat Vorrang". Am 24.08.2026 hat genau das zweimal nachgelegt (+25, +30 Hz),
# waehrend die Lamelle bei -12 Grad stand. Die Annahme dahinter war falsch: Eine
# Vereisung, die sich trotz voller Luftmenge haelt, ist kein Grund fuer MEHR
# Frequenz - sie ist ein Grund zum Abtauen.
#
# Die Sperre bleibt deshalb stehen, solange die Vereisung anhaelt. Das Eis ist Sache
# der Not-Abtauung weiter unten. Dieser Wert steuert nur noch, ab wann die Regelung
# das Festhalten einmal deutlich ins Log schreibt.
VEREISUNG_DAUERWARNUNG_MINUTES = 45

# --- Not-Abtauung (2026-08-24) ---
#
# WARUM: Am 24.08. waren um 08:42 alle vier Startbedingungen des Avarma-Reglers
# erfuellt - Lamelle -3,5 unter P29 (-3,0), Differenz 10,9 K ueber P86 (8,0),
# Umgebung 7,4 unter P85 (15,0), und 122 min seit der letzten Abtauung bei P27 = 50.
# Abgetaut hat der Regler trotzdem erst um 09:20, 38 Minuten spaeter, in denen die
# Lamelle von -3,5 auf -13 Grad durchsackte. Warum er zoegert, ist offen; die
# ausgelesenen Parameter erklaeren es nicht.
#
# Statt weiter zu raten, taut die Regelung im Zweifel selbst ab. Das ist ein
# Notnagel, keine Regelung: Eine erzwungene Abtauung kostet Waerme, deshalb vier
# Bedingungen, die alle gleichzeitig erfuellt sein muessen.
#
# Die Untergrenze ist ABTAU_START_C, nicht EVAPORATOR_MIN_C: Solange die Lamelle
# ueber der Startschwelle des Reglers liegt, hat er recht, wenn er nicht abtaut -
# dann ist sie nur kalt, nicht vereist.
NOTABTAU_VERZUG_MINUTES = 20
# Mindestabstand zur letzten Abtauung - eigener oder der des Reglers. Liegt bewusst
# ueber P27 (50 min): Der Regler soll immer zuerst drankommen.
NOTABTAU_MIN_ABSTAND_MINUTES = 60

FAN_MIN_RPM = 400
FAN_MAX_RPM = 900

# Asymmetrisch: Anheben schnell, Drosseln langsam (2026-08-24: "der Luefter
# muesste auch etwas aggressiver regeln, der passt sich zu langsam an").
#
# Die alte Fassung stieg starr in 50-RPM-Schritten alle 10 Minuten. Am 24.08. lag der
# Verdampfer schon 5 Minuten nach dem Start bei -2 Grad, der Luefter brauchte aber bis
# 05:27 fuer 400->550 RPM - drei Schritte in 34 Minuten. Um 05:34 stand er bei -3 Grad
# und die Anlage taute ab. Zu wenig Luft, zu spaet.
#
# Neu: Der Schritt nach oben waechst mit der Unterschreitung, und er darf in jedem
# Regelzyklus fallen. Gedrosselt wird weiter behutsam - Ziel bleibt "so wenig
# Luefterleistung wie moeglich, solange der Verdampfer >= 1 Grad bleibt".
FAN_STEP_RPM = 50                  # Drosseln: unveraendert behutsam
FAN_STEP_INTERVAL_MINUTES = 10     # Drosseln: unveraendert behutsam
FAN_UP_INTERVAL_MINUTES = 5        # Anheben: jeder Regelzyklus
FAN_STEP_RPM_PER_K = 150.0         # Anheben: RPM je Kelvin Unterschreitung
FAN_STEP_UP_MIN_RPM = 100.0
FAN_STEP_UP_MAX_RPM = 300.0

# Abtau-Starttemperatur der Anlage (number.controllroom_esphome_web_avarma_
# abtau_start_verdampfertemperatur, am 24.08.2026 auf -3.0 abgelesen). Kommt der
# Verdampfer bis auf FAN_NOTFALL_ABSTAND_K heran, ist Feinregelung sinnlos - dann
# geht der Luefter sofort auf Volllast, statt sich in Schritten hinterherzuschleppen.
ABTAU_START_C = -3.0
FAN_NOTFALL_ABSTAND_K = 1.0

# Nach dem Ende einer Abtauung ist der Verdampfer noch minutenlang warm. In dieser
# Zeit darf nicht gedrosselt werden - sonst drosselt die Regelung ausgerechnet dann,
# wenn die Vereisung gerade erst abgeschmolzen ist.
FAN_DROSSEL_SPERRE_NACH_ABTAUUNG_MINUTES = 15
# Verdampfer: 1.0 ist eine UNTERGRENZE, kein Sollwert (2026-08-03).
# Ziel ist "so wenig Luefterleistung wie moeglich, solange der Verdampfer
# >= 1 Grad bleibt" - nicht, die 1 Grad exakt zu treffen. Liegt der Verdampfer
# deutlich darueber, ist das kein Fehler, sondern das gewuenschte Ergebnis
# minimaler Drehzahl. Im Winter wird die Untergrenze oft nicht haltbar sein.
EVAPORATOR_MIN_C = 1.0
EVAPORATOR_HYSTERESE_C = 0.5   # erst ab 1.5 Grad wieder drosseln

# P72 (Register 8262) speichert RPM/10 als Rohwert (Hofman-Doku: "display value*10").
# Empirisch bestaetigt 2026-07-23: Rohwert 40 geschrieben -> reale Drehzahl
# (sensor.esphome_web_avarma_lufter_1_drehzahl) = 400 RPM.
#
# WICHTIG - dieser Wert haengt an der geflashten ESPHome-Firmware, nicht am Regler:
#   10 = ESPHome-YAML OHNE multiply auf fan_manual_speed (Firmware bis 2026-08-18).
#        Die Number-Entity spricht Rohwerte, die Umrechnung passiert hier.
#    1 = ESPHome-YAML MIT "multiply: 0.1" auf fan_manual_speed. Die Entity spricht
#        dann selbst echte RPM und darf hier nicht noch einmal skaliert werden.
#
# Seit dem ESPHome-Flash vom 2026-08-18 traegt die YAML multiply: 0.1, die Entity
# liefert und nimmt also echte RPM - verifiziert direkt nach dem Flash: derselbe
# unveraenderte Registerinhalt zeigte statt 40 nun 400.
FAN_REGISTER_SCALE = 1

TAG_START_HOUR = 7
TAG_END_HOUR = 22

# -------------------- Uebergangszeit (2026-09-13) --------------------
# Gilt nur Maerz-Mai und September-November. Dezember bis Februar laeuft die Anlage ohne
# diese Regeln; die Heizgrenze (AT-Mittel) gilt ganzjaehrig.
UEBERGANG_MONATE = (3, 4, 5, 9, 10, 11)
# Abschalten, wenn das EG lange genug warm ist. 21 Grad erreicht das EG ohne Heizung nicht
# (Ende August/Anfang September: Tagesmittel 19,0-20,2), das Kriterium spricht also nur
# auf echte Heizleistung an. Die Haltezeit faengt den 0,5-K-Sprung von free@home bei
# Sonnenauf- und -untergang ab. Nicht persistiert: nach einem Reload beginnt sie neu,
# die Anlage heizt dann hoechstens 30 min laenger.
EG_AUS_C = 21.0
EG_AUS_HALTE_MINUTES = 30
# Wiedereinschalten in der Uebergangszeit - statt Bad <= 18,5. Sonst muesste das Bad nach
# einer Abschaltung bei 21 Grad im EG erst 2 K verlieren.
EG_EIN_C = 20.0
# Nachtsperre: kein START zwischen 22 und 10 Uhr. Aufgehoben bei Frostprognose
# (FROST_THRESHOLD_C) oder wenn das EG trotzdem auf die Untergrenze faellt.
# Eine laufende Anlage lief nach dem Beschluss vom 13.09. zunaechst weiter. Geaendert am
# 14.09.: Start um 20:20 hat die ganze Nacht bis 05:36 geheizt, EG erreichte
# 21 Grad nie (max. 20,84). Jetzt schaltet sie in der Sperrzeit ab, sobald das EG
# EG_NACHT_AUS_C erreicht - ausser bei Frostprognose.
NACHTSPERRE_START_HOUR = 22
NACHTSPERRE_ENDE_HOUR = 10
EG_NACHT_UNTERGRENZE_C = 19.0
EG_NACHT_AUS_C = 20.5
# Takten: so viele Kompressorstarts im Fenster, Starts kurz nach einer Abtauung zaehlen
# nicht. Danach Sperre. Die Startzeiten liegen nur im Speicher - ein Reload setzt die
# Zaehlung zurueck (die Abschaltung kommt dann spaeter, nie zu frueh); die Sperre selbst
# liegt im Helfer.
# Verschaerft am 14.09.2026 : vorher 3 Starts in 60 min. In der Nacht zum 14.09.
# lagen zwischen dem ersten Stopp (04:42) und der Abschaltung (05:36) 54 Minuten.
TAKT_STARTS = 2
TAKT_FENSTER_MINUTES = 45
TAKT_SPERRE_MINUTES = 180
TAKT_ABTAU_NACHLAUF_MINUTES = 10
# Ebenfalls nicht gezaehlt (Auswertung 25.09.2026): Stopps, die die Anlage nicht aus
# Ueberleistung macht. Alle drei Taktabschaltungen vom 18., 20. und 21.09. enthielten
# mindestens einen davon.
# - bis TAKT_EIGENE_ABSENKUNG_MINUTES nach einer eigenen VL-Soll-Absenkung
#   (siehe VLT_ABSENK_*)
# - nach der Oelrueckfuehrung: nach laengerem Lauf springt der Kompressor fuer unter
#   einer Minute auf P41 (50 Hz), der Vorlauf schiesst ueber den Sollwert, die Avarma
#   stoppt (20.09. 18:32, 21.09. 17:07, 22.09. 18:11). Erkannt am Sprung auf
#   >= OELRUECKFUEHRUNG_FREQ_HZ - 1 mit Stopp binnen TAKT_OEL_SPRUNG_MINUTES; der
#   Kompressor muss vorher TAKT_OEL_VORLAUF_MINUTES gelaufen sein, sonst ist es die
#   Anfahrrampe.
TAKT_EIGENE_ABSENKUNG_MINUTES = 5
TAKT_OEL_SPRUNG_MINUTES = 3
TAKT_OEL_VORLAUF_MINUTES = 10
KOMPRESSOR_LAEUFT_HZ = 1.0

CHECK_INTERVAL_SECONDS = 300
NO_SENTINEL = -1.0


class HeizungVltKompressorRegelung(Hass):
    """Ruecklaufgeregelte Heizungssteuerung mit AT-Heizkurve als Vorsteuerung.

    STAND 2026-09-13: Der VL-Sollwert wird per Vorsteuerung gesetzt (RL-Ziel + Spreizung
    + Korrektur), der Kompressor-Deckel folgt der Kennlinie mit Winter-Eskalation, und in
    der Uebergangszeit gelten Raum-, Takt- und Nachtregeln. Die Beschreibung darunter ist
    der aeltere Stand und nur noch in den Grundzuegen richtig.

    Die WP startet automatisch bei AT<=15°C UND Bad-Ist<=18.5°C. RL-Ist ist die
    Fuehrungsgroesse (lineare Heizkurve aus zwei Erfahrungspunkten: 0°C AT->35°C RL,
    15°C AT->28°C RL); VLT bleibt die einzige Stellgroesse und wird schrittweise
    (1°C/15min) an das RL-Ziel herangefuehrt. Beim Kaltstart beginnt das RL-Ziel bei
    28°C und naehert sich der Kurve ebenfalls schrittweise an (Geduld wg. Estrich-
    Traegheit). Bad als Referenzraum (~22°C, Schlafzimmer ausgenommen) treibt nicht
    mehr direkt die VLT, sondern nur noch eine langsame, dauerhaft aktive Parallel-
    verschiebung der Kurve (input_number.wp_heizkurve_offset, alle 5h, nur wenn der
    Kompressor nicht am Limit laeuft).

    Eskalationskette bei Engpass:
    1. VLT anheben (30-45°C)
    2. Hydraulische Lastverteilung (siehe heizung_lastverteilung.py)
    3. Kompressor-Maximalfrequenz auf 95 Hz (nur wenn 1+2 ausgeschoepft und
       VLT-Ist trotzdem hinter VLT-Soll zurueckbleibt)

    Tagsueber (07-22 Uhr) ist leichtes Ueberheizen erlaubt (Estrich als Puffer),
    nachts wird nur gehalten (ruhiger/leiser Betrieb). Bei Frost-Prognose fuer die
    kommende Nacht wird tagsueber zusaetzlich vorgeheizt (Bonus direkt auf das
    RL-Kurvenziel, nicht Teil des langsamen Offsets).

    Schreibt bei jedem aktiven Zyklus den Agent-Heartbeat, den der ESPHome-seitige
    Watchdog ueberwacht (Fallback auf 32°C/90Hz nach 30 Min ohne Heartbeat).
    """

    def initialize(self):
        self.last_step = {}
        # Nach einem Reload beginnen alle Schrittsperren bei null - ohne Vorbelegung
        # darf jeder langsame Steller sofort noch einmal zuschlagen. Am 24.08.2026 haben
        # drei Reloads binnen 26 Sekunden den Heizkurven-Offset dreimal angehoben
        # (1,0 -> 2,5 Grad), obwohl er nur alle 5 Stunden einen Schritt machen darf;
        # die Vorlauf-Solltemperatur stieg im selben Zug von 37 auf 42 Grad.
        #
        # Die langsamen Steller starten deshalb so, als haetten sie gerade gestellt.
        # Bewusst OHNE "fan_up": Auf Vereisung muss der Luefter auch direkt nach einem
        # Reload sofort reagieren duerfen, das ist die Sperre nicht wert.
        jetzt = self.datetime()
        # "notabtauung" ist bewusst dabei: Ein App-Reload darf nie unmittelbar
        # Hardware ausloesen. Preis ist, dass nach einem Edit eine Stunde lang
        # keine Not-Abtauung moeglich ist - in der Zeit taut der Regler selbst ab,
        # das ist ja der Normalfall.
        for schluessel in ("vlt", "korrektur", "offset", "rl_ziel", "boost", "boost_decay", "fan_down", "notabtauung"):
            self.last_step[schluessel] = jetzt
        self.rl_ziel_aktuell = None
        self.wp_war_an = False
        # None = noch nicht bestimmt; beim ersten Regelzyklus wird der Puffer aus
        # dem persistenten Deckel im Geraet rekonstruiert (siehe
        # control_kompressor_deckel).
        self.boost_hz = None
        self.boost_since = None
        self.am_deckel_since = None
        self.abtau_zuletzt = None
        self.vereisung_sperre_seit = None
        self.vereist_seit = None
        self.korrektur = 0.0
        self.kompressor_starts = []
        # Takterkennung: Gruende fuer einen nicht gezaehlten Stopp (TAKT_EIGENE_*,
        # TAKT_OEL_*). Nach einem Reload unbekannt - dann zaehlt der Stopp.
        self.kompressor_an_seit = None
        self.oel_sprung_um = None
        self.stopp_grund = None
        self.vlt_abgesenkt_um = None
        self.absenkung_wartet_seit = None
        self.eg_warm_seit = None
        self.listen_state(self.on_kompressor_frequenz, KOMPRESSOR_IST_SENSOR)
        # Am Schalter statt an den Schaltstellen: so stimmt der Helfer auch,
        # wenn jemand die WP von Hand oder eine Automation sie schaltet.
        self.listen_state(self.on_wp_schalter, WP_SWITCH)
        self.run_in(self.check, 5)
        self.run_every(
            self.check,
            self.datetime() + timedelta(seconds=CHECK_INTERVAL_SECONDS),
            CHECK_INTERVAL_SECONDS,
        )
        self.log("Heizung VLT/Kompressor/Luefter-Regelung gestartet", level="INFO")

    def safe_float(self, entity_id, attribute=None, default=None):
        raw = self.get_state(entity_id, attribute=attribute) if attribute else self.get_state(entity_id)
        if raw in (None, "unavailable", "unknown"):
            return default
        try:
            return float(raw)
        except (ValueError, TypeError):
            return default

    def is_day(self):
        hour = self.datetime().hour
        return TAG_START_HOUR <= hour < TAG_END_HOUR

    def frost_expected_tonight(self):
        v = self.safe_float(FROST_FORECAST_NUMBER)
        return v is not None and v <= FROST_THRESHOLD_C

    def bad_target(self):
        if not self.is_day():
            return BAD_TARGET_C
        target = BAD_TARGET_C + DAY_OVERHEAT_BONUS_C
        if self.frost_expected_tonight():
            target += FROST_BOOST_BONUS_C
        return target

    def donors_exhausted(self):
        """True wenn alle Spender-Raeume der Lastverteilung bereits an ihrer
        Untergrenze gedrosselt sind - Signal, dass Raumverteilung nichts mehr bringt."""
        for donor in DONOR_CHECKS:
            backup = self.safe_float(donor["backup"])
            is_throttled = backup is not None and backup > NO_SENTINEL + 0.01
            current_target = self.safe_float(donor["climate"], attribute="temperature")
            at_floor = current_target is not None and current_target <= donor["floor"] + 0.01
            if not (is_throttled and at_floor):
                return False
        return True

    def on_wp_schalter(self, entity, attribute, old, new, **kwargs):
        """Einschaltzeitpunkt festhalten bzw. beim Abschalten loeschen."""
        if new == old:
            return
        if new == "on":
            jetzt = int(datetime.now(timezone.utc).timestamp())
            self.call_service(
                "input_number/set_value", entity_id=WP_EINSCHALTZEIT_HELPER, value=jetzt
            )
            self.log("WP eingeschaltet - Einschaltzeit im Helfer festgehalten", level="INFO")
        elif new == "off":
            self.call_service(
                "input_number/set_value", entity_id=WP_EINSCHALTZEIT_HELPER, value=0
            )

    def wp_laufzeit_minuten(self):
        """Wie lange laeuft die WP schon?

        Primaerquelle ist WP_EINSCHALTZEIT_HELPER, gesetzt von on_wp_schalter().
        Ein input_number ueberlebt einen Neustart von Home Assistant, last_changed
        des Schalters nicht: dabei wird es auf die Neustartzeit gesetzt, und eine
        seit Stunden laufende WP sieht aus wie gerade eingeschaltet. Beobachtet am
        17.09.2026 - nach einem HAOS-Neustart um 12:00 fiel das RL-Ziel mitten im
        Betrieb auf den Kaltstartwert zurueck und brauchte 45 min zurueck auf Kurs.

        Fallback bleibt last_changed, damit die Regelung auch ohne gesetzten Helfer
        arbeitet (Wert 0 = kein Einschaltzeitpunkt bekannt).
        """
        stempel = self.safe_float(WP_EINSCHALTZEIT_HELPER)
        if stempel is not None and stempel > 0:
            return (datetime.now(timezone.utc).timestamp() - stempel) / 60
        seit = self.get_state(WP_SWITCH, attribute="last_changed")
        if not seit:
            return None
        try:
            ts = datetime.fromisoformat(str(seit).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 60

    def anfahrphase(self):
        """True, solange die Anlage wirklich anfaehrt.

        Zwei Signale, weil keines allein reicht:

        - Laufzeit des WP-Schalters: ueberlebt einen Reload der App, aber NICHT einen
          Neustart von Home Assistant - dabei wird last_changed auf die Neustartzeit
          gesetzt, und eine seit Stunden laufende WP saehe aus wie gerade eingeschaltet.
        - Ruecklauftemperatur: Liegt sie schon auf oder ueber dem Startwert der
          Kaltstart-Rampe, faehrt hier nichts mehr an - unabhaengig von jeder Uhr.
          Das faengt den HA-Neustart ab.

        Im Zweifel (keine Laufzeit ermittelbar, Ruecklauf unbekannt) gilt Anfahrphase:
        die vorsichtigere Annahme, sie sperrt nur den Puffer-Aufbau.
        """
        rl_ist = self.safe_float(RLT_IST_SENSOR)
        if rl_ist is not None and rl_ist >= RL_ZIEL_START_C:
            return False
        laufzeit = self.wp_laufzeit_minuten()
        return laufzeit is None or laufzeit < BOOST_KALTSTART_MINUTES

    def kompressor_obergrenze(self, at):
        """Absolute Obergrenze des Deckels: 95 Hz nur bei strengem Frost."""
        if at is not None and at <= KOMPRESSOR_ESKALATION_AT_C:
            return KOMPRESSOR_MAX_ESCALATED
        return KOMPRESSOR_MAX_NORMAL

    def abtauen_aktiv(self):
        """Bit 4 im Betriebsstatus. Faellt der Sensor aus, gilt "nicht abtauend" -
        die Luefterregelung soll dann normal weiterarbeiten und nicht einfrieren."""
        status = self.safe_float(BETRIEBSSTATUS_SENSOR)
        return status is not None and int(status) & BETRIEBSSTATUS_BIT_ABTAUEN

    def cooldown_ok(self, key, minutes):
        letzter = self.last_step.get(key)
        return (
            letzter is None
            or (self.datetime() - letzter).total_seconds() >= minutes * 60
        )

    def uebergangszeit(self):
        """Maerz-Mai und September-November (2026-09-13)."""
        return self.datetime().month in UEBERGANG_MONATE

    def nachtsperre_zeit(self):
        hour = self.datetime().hour
        return hour >= NACHTSPERRE_START_HOUR or hour < NACHTSPERRE_ENDE_HOUR

    def taktsperre_rest_minuten(self):
        """Restdauer der Taktsperre aus dem Helfer. Unlesbar gilt als keine Sperre - wie
        beim Autostart-Helfer darf ein Helferausfall die Heizung nicht lahmlegen."""
        bis = self.safe_float(TAKTSPERRE_HELPER, attribute="timestamp")
        if bis is None:
            return 0.0
        return max(0.0, (bis - datetime.now(timezone.utc).timestamp()) / 60)

    def on_kompressor_frequenz(self, entity, attribute, old, new, **kwargs):
        """Zaehlt Kompressorstarts (steht -> laeuft) fuer die Takterkennung. Bei jedem
        Stopp wird festgehalten, ob er zaehlt - der Start danach richtet sich danach."""
        try:
            alt = float(old)
            neu = float(new)
        except (TypeError, ValueError):
            return
        now = self.datetime()
        if alt >= KOMPRESSOR_LAEUFT_HZ > neu:
            self.on_kompressor_stopp(now, alt)
            return
        if KOMPRESSOR_LAEUFT_HZ <= alt < OELRUECKFUEHRUNG_FREQ_HZ - 1 <= neu:
            self.oel_sprung_um = now
            return
        if not (alt < KOMPRESSOR_LAEUFT_HZ <= neu):
            return
        self.kompressor_an_seit = now
        self.oel_sprung_um = None
        stopp_grund, self.stopp_grund = self.stopp_grund, None
        if self.get_state(WP_SWITCH) != "on" or self.abtauen_aktiv():
            return
        if self.abtau_zuletzt is not None:
            if (now - self.abtau_zuletzt).total_seconds() / 60 < TAKT_ABTAU_NACHLAUF_MINUTES:
                return
        if stopp_grund is not None:
            self.log(
                f"Kompressorstart ({neu:.0f} Hz) zaehlt nicht fuer die Takterkennung - "
                f"Stopp davor {stopp_grund}",
                level="INFO",
            )
            return
        self.kompressor_starts.append(now)
        self.takt_erkannt()  # raeumt alte Starts weg, damit die Zahl im Log stimmt
        self.log(
            f"Kompressorstart ({neu:.0f} Hz) - {len(self.kompressor_starts)} Start(s) in "
            f"den letzten {TAKT_FENSTER_MINUTES} min",
            level="INFO",
        )

    def on_kompressor_stopp(self, now, alt):
        """Merkt sich, ob die Regelung den Stopp selbst verursacht hat (TAKT_EIGENE_*,
        TAKT_OEL_*). Das Log dient zugleich der naechsten Auswertung."""
        def minuten_seit(zeitpunkt):
            return (now - zeitpunkt).total_seconds() / 60

        self.stopp_grund = None
        if self.get_state(WP_SWITCH) != "on":
            return
        if (
            self.vlt_abgesenkt_um is not None
            and minuten_seit(self.vlt_abgesenkt_um) <= TAKT_EIGENE_ABSENKUNG_MINUTES
        ):
            self.stopp_grund = "durch eigene VL-Soll-Absenkung"
        elif (
            self.oel_sprung_um is not None
            and self.kompressor_an_seit is not None
            and minuten_seit(self.oel_sprung_um) <= TAKT_OEL_SPRUNG_MINUTES
            and (self.oel_sprung_um - self.kompressor_an_seit).total_seconds() / 60
            >= TAKT_OEL_VORLAUF_MINUTES
        ):
            self.stopp_grund = "nach Oelrueckfuehrung (Sprung auf 50 Hz)"
        self.oel_sprung_um = None
        self.log(
            f"Kompressorstopp (vorher {alt:.0f} Hz)"
            + (f" - {self.stopp_grund}, zaehlt nicht fuer die Takterkennung" if self.stopp_grund else ""),
            level="INFO",
        )

    def takt_erkannt(self):
        grenze = self.datetime() - timedelta(minutes=TAKT_FENSTER_MINUTES)
        self.kompressor_starts = [t for t in self.kompressor_starts if t >= grenze]
        return len(self.kompressor_starts) >= TAKT_STARTS

    def update_eg_haltezeit(self):
        eg = self.safe_float(EG_MITTEL_SENSOR)
        if eg is not None and eg >= EG_AUS_C:
            if self.eg_warm_seit is None:
                self.eg_warm_seit = self.datetime()
        else:
            self.eg_warm_seit = None

    def eg_warm_minuten(self):
        if self.eg_warm_seit is None:
            return 0.0
        return (self.datetime() - self.eg_warm_seit).total_seconds() / 60

    def spreizung_aktuell(self):
        """Spreizung fuer die Vorsteuerung: live, wenn der Kompressor laeuft und der Wert
        plausibel ist, sonst P58. Gibt (Wert, Quelle) zurueck."""
        vl = self.safe_float(VLT_IST_SENSOR)
        rl = self.safe_float(RLT_IST_SENSOR)
        komp = self.safe_float(KOMPRESSOR_IST_SENSOR)
        if vl is None or rl is None or komp is None:
            return SPREIZUNG_FALLBACK_K, "P58"
        if komp < KOMPRESSOR_LAEUFT_HZ or self.abtauen_aktiv():
            return SPREIZUNG_FALLBACK_K, "P58"
        spreizung = vl - rl
        if not SPREIZUNG_MIN_K <= spreizung <= SPREIZUNG_MAX_K:
            return SPREIZUNG_FALLBACK_K, "P58"
        return spreizung, "live"

    def update_korrektur(self, error, vlt_roh):
        """Langsamer I-Anteil der Vorsteuerung, ein Schritt je KORREKTUR_INTERVAL_MINUTES.

        Nicht in der Anfahrphase (dort liegt der Ruecklauf planmaessig zurueck) und nicht
        nach oben, wenn der Kompressor am Deckel haengt - dann fehlt Leistung, nicht
        Sollwert, und die Korrektur wuerde nur aufintegrieren."""
        if not self.cooldown_ok("korrektur", KORREKTUR_INTERVAL_MINUTES):
            return
        self.last_step["korrektur"] = self.datetime()
        if self.anfahrphase() or self.abtauen_aktiv():
            return
        komp_ist = self.safe_float(KOMPRESSOR_IST_SENSOR)
        komp_max = self.safe_float(KOMPRESSOR_MAX_NUMBER)
        am_deckel = (
            komp_ist is not None
            and komp_max is not None
            and komp_ist >= komp_max - KOMPRESSOR_AM_DECKEL_TOLERANZ_HZ
        )
        alt = self.korrektur
        if error > RL_DEADBAND_C and vlt_roh < VLT_MAX and not am_deckel:
            self.korrektur = min(KORREKTUR_MAX_C, alt + KORREKTUR_STEP_C)
        elif error < -RL_DEADBAND_C and vlt_roh > VLT_MIN:
            self.korrektur = max(-KORREKTUR_MAX_C, alt - KORREKTUR_STEP_C)
        if abs(self.korrektur - alt) > 0.01:
            self.log(
                f"VL-Korrektur {alt:+.1f} -> {self.korrektur:+.1f} K "
                f"(Ruecklauf {-error:+.1f} K neben dem Ziel)",
                level="INFO",
            )

    def set_fan(self, rpm):
        self.call_service(
            "number/set_value", entity_id=FAN_SPEED_NUMBER, value=rpm / FAN_REGISTER_SCALE
        )

    def check(self, **kwargs):
        self.update_eg_haltezeit()
        self.maybe_autostart()
        if self.maybe_autostop():
            # Gleicher Aufraeumzweig wie bei ausgeschalteter WP: der Schalter-State
            # aus HA ist direkt nach dem Abschalten noch nicht nachgezogen, deshalb
            # hier beenden statt sich auf wp_on zu verlassen.
            self.wp_war_an = False
            self.rl_ziel_aktuell = None
            self.korrektur = 0.0
            self.kompressor_starts = []
            self.stopp_grund = None
            self.absenkung_wartet_seit = None
            return

        wp_on = self.get_state(WP_SWITCH) == "on"
        if not wp_on:
            self.wp_war_an = False
            self.rl_ziel_aktuell = None
            self.korrektur = 0.0
            self.kompressor_starts = []
            self.stopp_grund = None
            self.absenkung_wartet_seit = None
            return

        if not self.wp_war_an:
            # Zwei verschiedene Faelle, die bisher gleich behandelt wurden:
            #
            # 1. Echter Kaltstart der WP -> Rampe ab RL_ZIEL_START_C. Die ist fuer den
            #    kalten Estrich gedacht: lieber geduldig anfahren als ueberschiessen.
            # 2. Reload der App bei laengst laufender WP -> hier ist die Rampe schaedlich.
            #    Am 24.08.2026 fiel das RL-Ziel dadurch von 32,8 auf 28,0 Grad; die Anlage
            #    faehrt danach ueber eine Stunde (1 K je 15 min) unter Wert, obwohl sich
            #    an der Heizung nichts geaendert hat - nur die Regelung wurde neu geladen.
            #
            # Unterschieden ueber die Laufzeit des WP-Schalters, dieselbe Grenze wie bei
            # der Kaltstart-Sperre des Kompressor-Puffers: danach ist die Anfahrphase
            # vorbei und das Ziel gehoert auf den Kurvenwert.
            at_jetzt = self.safe_float(AT_SENSOR)
            if not self.anfahrphase() and at_jetzt is not None:
                self.rl_ziel_aktuell = self.heizkurve_ziel(at_jetzt)
                self.log(
                    f"Neustart der Regelung bei warmer Anlage (Ruecklauf "
                    f"{self.safe_float(RLT_IST_SENSOR)}°C): RL-Ziel direkt auf "
                    f"Kurvenwert {self.rl_ziel_aktuell:.1f}°C statt Kaltstart-Rampe "
                    f"ab {RL_ZIEL_START_C}°C",
                    level="INFO",
                )
            else:
                self.rl_ziel_aktuell = RL_ZIEL_START_C
                self.log(
                    f"WP-Start erkannt, RL-Ziel initialisiert auf {RL_ZIEL_START_C}°C",
                    level="INFO",
                )
        self.wp_war_an = True

        self.call_service(
            "number/set_value",
            entity_id=HEARTBEAT_NUMBER,
            value=int(self.datetime().timestamp()),
        )

        self.control_rl_and_vlt_and_kompressor()
        self.control_fan()
        # Nach control_fan: Die Not-Abtauung will wissen, ob der Luefter in DIESEM
        # Zyklus schon auf Volllast gestellt wurde - erst dann ist mehr Luft als
        # Mittel ausgereizt.
        self.control_notabtauung()
        self.adapt_offset()

    def control_notabtauung(self):
        """Taut selbst ab, wenn der Avarma-Regler es verschlaeft.

        Vier Bedingungen, alle gleichzeitig (Begruendung oben bei
        NOTABTAU_VERZUG_MINUTES):
          1. Lamelle unter der Startschwelle des Reglers UND Spreizung zu gross
          2. das seit NOTABTAU_VERZUG_MINUTES ununterbrochen
          3. Luefter steht bereits auf Volllast - mehr Luft ist ausgereizt
          4. letzte Abtauung mindestens NOTABTAU_MIN_ABSTAND_MINUTES her
        """
        now = self.datetime()

        # Laeuft gerade eine Abtauung, ist nichts zu tun - und der Zeitstempel
        # gehoert mitgefuehrt, auch wenn control_fan diesen Zyklus vorher schon
        # ausgestiegen ist.
        if self.abtauen_aktiv():
            self.abtau_zuletzt = now
            self.vereist_seit = None
            return

        verdampfer = self.safe_float(EVAPORATOR_SENSOR)
        at = self.safe_float(AT_SENSOR)
        if verdampfer is None or at is None:
            self.vereist_seit = None
            return

        spreizung = at - verdampfer
        if verdampfer >= ABTAU_START_C or spreizung <= VEREISUNG_SPREIZUNG_MAX_K:
            self.vereist_seit = None
            return

        if self.vereist_seit is None:
            self.vereist_seit = now
        vereist_min = (now - self.vereist_seit).total_seconds() / 60
        if vereist_min < NOTABTAU_VERZUG_MINUTES:
            return

        # Erst mehr Luft, dann Heissgas.
        fan_raw = self.safe_float(FAN_SPEED_NUMBER)
        fan_speed = fan_raw * FAN_REGISTER_SCALE if fan_raw is not None else None
        if fan_speed is None or fan_speed < FAN_MAX_RPM:
            return

        # Dem Regler den Vortritt lassen.
        if self.abtau_zuletzt is not None:
            seit_abtauung = (now - self.abtau_zuletzt).total_seconds() / 60
            if seit_abtauung < NOTABTAU_MIN_ABSTAND_MINUTES:
                return
        if not self.cooldown_ok("notabtauung", NOTABTAU_MIN_ABSTAND_MINUTES):
            return

        self.last_step["notabtauung"] = now
        self.vereist_seit = None
        self.call_service("switch/turn_on", entity_id=ABTAU_ERZWINGEN_SWITCH)
        self.log(
            f"Not-Abtauung ausgeloest: Verdampfer {verdampfer:.1f}°C liegt seit "
            f"{vereist_min:.0f} min unter der Abtau-Startschwelle {ABTAU_START_C}°C "
            f"(Spreizung {spreizung:.1f} K, Luefter {fan_speed:.0f} RPM auf Volllast) - "
            f"der Avarma-Regler hat von selbst nicht abgetaut",
            level="WARNING",
        )

    def maybe_autostart(self):
        """Schaltet die WP automatisch ein, wenn AT <= Schwelle UND Bad-Ist <= Schwelle
        (2026-07-24) - beide Bedingungen muessen gleichzeitig erfuellt sein.

        Vorgeschaltet der Handschalter AUTOSTART_HELPER."""
        if self.get_state(WP_SWITCH) == "on":
            return

        # Faellt der Helfer aus, wird gestartet wie bisher - bewusst NICHT gesperrt.
        # Ein nicht lesbarer Helfer darf im Winter nicht stillschweigend die Heizung
        # abschalten; und falls die Anlage wirklich nicht darf, schuetzt sie sich
        # mit ihrer eigenen Stoerung selbst.
        autostart = self.get_state(AUTOSTART_HELPER)
        if autostart in (None, "unavailable", "unknown"):
            self.log(
                f"{AUTOSTART_HELPER} nicht lesbar ({autostart}) - Autostart bleibt "
                f"erlaubt, damit ein Helfer-Ausfall die Heizung nicht lahmlegt",
                level="WARNING",
            )
        elif autostart != "on":
            if self.cooldown_ok("autostart_gesperrt_log", 60):
                self.last_step["autostart_gesperrt_log"] = self.datetime()
                self.log(
                    f"Autostart gesperrt ({AUTOSTART_HELPER} ist aus) - "
                    f"WP bleibt aus, bis der Schalter wieder eingeschaltet wird",
                    level="INFO",
                )
            return

        # Taktsperre (2026-09-13): gilt unabhaengig von der Jahreszeit, gesetzt wird sie
        # nur von der Takt-Abschaltung in maybe_autostop().
        rest = self.taktsperre_rest_minuten()
        if rest > 0:
            if self.cooldown_ok("taktsperre_log", 60):
                self.last_step["taktsperre_log"] = self.datetime()
                self.log(f"Autostart wartet: Taktsperre noch {rest:.0f} min", level="INFO")
            return

        # Nachtsperre (2026-09-13): in der Uebergangszeit kein Start zwischen 22 und 10 Uhr,
        # ausser bei Frostprognose oder wenn das EG trotzdem auf die Untergrenze faellt.
        if self.uebergangszeit() and self.nachtsperre_zeit():
            eg = self.safe_float(EG_MITTEL_SENSOR)
            zu_kalt = eg is not None and eg <= EG_NACHT_UNTERGRENZE_C
            if not self.frost_expected_tonight() and not zu_kalt:
                if self.cooldown_ok("nachtsperre_log", 60):
                    self.last_step["nachtsperre_log"] = self.datetime()
                    self.log(
                        f"Autostart wartet: Nachtsperre {NACHTSPERRE_START_HOUR}-"
                        f"{NACHTSPERRE_ENDE_HOUR} Uhr (EG {eg}°C > {EG_NACHT_UNTERGRENZE_C}°C, "
                        f"Prognose {self.safe_float(FROST_FORECAST_NUMBER)}°C > {FROST_THRESHOLD_C}°C)",
                        level="INFO",
                    )
                return

        # Vorschau statt Momentaufnahme: Sonst liefe an einem milden Tag vor
        # einer Frostnacht die WP nicht an - und das Vorladen (vorlade_bonus)
        # ginge genau dann ins Leere, wenn es am meisten gebraucht wird.
        at_jetzt = self.safe_float(AT_SENSOR)
        at = self.vorschau_at()
        bad_current = self.safe_float(BAD_CLIMATE, attribute="current_temperature")
        if at is None or bad_current is None:
            return

        if at > AUTOSTART_AT_THRESHOLD_C:
            return

        # Raumkriterium: in der Uebergangszeit das EG-Mittel, sonst wie bisher das Bad.
        # Faellt der EG-Helfer aus, gilt auch in der Uebergangszeit das Bad.
        eg = self.safe_float(EG_MITTEL_SENSOR)
        if self.uebergangszeit() and eg is not None:
            raum_ok = eg <= EG_EIN_C
            raum_text = f"EG-Mittel {eg}°C <= {EG_EIN_C}°C, Uebergangszeit"
        else:
            raum_ok = bad_current <= AUTOSTART_BAD_THRESHOLD_C
            raum_text = f"Bad {bad_current}°C <= {AUTOSTART_BAD_THRESHOLD_C}°C"
        if not raum_ok:
            return

        self.call_service("switch/turn_on", entity_id=WP_SWITCH)
        self.log(
            f"WP automatisch gestartet (massgebliche AT {at}°C <= "
            f"{AUTOSTART_AT_THRESHOLD_C}°C [jetzt {at_jetzt}°C, Prognose beruecksichtigt], "
            f"{raum_text})",
            level="INFO",
        )

    def maybe_autostop(self):
        """Heizgrenzen-Abschaltung - das Gegenstueck zu maybe_autostart().

        Schaltet die WP ab, wenn es draussen ueber mehrere Stunden zu warm zum Heizen
        ist. Gibt True zurueck, wenn abgeschaltet wurde.

        Bewusst OHNE Raumkriterium: das Bad-Ziel ist absichtlich hoch gewaehlt, damit
        es die uebrigen Raeume mitzieht, und verfehlt sein Ziel daher meistens. Eine
        Bedingung "Raeume warm genug" waere deshalb ein Dauerveto und die Abschaltung
        wuerde praktisch nie greifen. Ob ueberhaupt geheizt werden muss, entscheidet
        hier die Aussentemperatur - das ist die Definition einer Heizgrenze.

        Ergaenzt 2026-09-13: In der Uebergangszeit schalten zusaetzlich Takten und
        "EG warm genug" ab. Das widerspricht dem Absatz oben nicht - dort ging es um das
        Bad-Ziel als VETO gegen das Abschalten. Das EG-Kriterium ist ein zusaetzlicher
        Ausloeser mit einer Schwelle, die tatsaechlich erreicht wird.

        Sperrt den Autostart NICHT. Faellt die Aussentemperatur wieder, soll die Anlage
        von allein anlaufen. Den Helfer sperren nur der Durchfluss-Schutz und der
        Mensch.
        """
        if self.get_state(WP_SWITCH) != "on":
            return False

        # Anders als beim Autostart ist hier NICHT-abschalten die sichere Richtung:
        # ein unlesbarer Helfer darf die Heizung nicht ungewollt stilllegen. Beim
        # Autostart ist es umgekehrt (dort darf ein Helferausfall nicht die Heizung
        # lahmlegen), deshalb sind die beiden Zweige absichtlich nicht symmetrisch.
        heizgrenze = self.get_state(HEIZGRENZE_HELPER)
        if heizgrenze != "on":
            if heizgrenze in (None, "unavailable", "unknown") and self.cooldown_ok(
                "heizgrenze_unlesbar_log", 60
            ):
                self.last_step["heizgrenze_unlesbar_log"] = self.datetime()
                self.log(
                    f"{HEIZGRENZE_HELPER} nicht lesbar ({heizgrenze}) - "
                    f"Heizgrenzen-Abschaltung bleibt aus",
                    level="WARNING",
                )
            return False

        if self.uebergangszeit():
            if self.takt_erkannt():
                starts = len(self.kompressor_starts)
                bis = datetime.now(timezone.utc).timestamp() + TAKT_SPERRE_MINUTES * 60
                # Erst sperren, dann abschalten - sonst startet der naechste Zyklus neu.
                self.call_service(
                    "input_datetime/set_datetime", entity_id=TAKTSPERRE_HELPER, timestamp=int(bis)
                )
                self.call_service("switch/turn_off", entity_id=WP_SWITCH)
                self.kompressor_starts = []
                self.log(
                    f"WP automatisch abgeschaltet - Anlage taktet ({starts} Kompressorstarts "
                    f"in {TAKT_FENSTER_MINUTES} min). Neustart fruehestens in "
                    f"{TAKT_SPERRE_MINUTES} min.",
                    level="WARNING",
                )
                return True

            laufzeit_uebergang = self.wp_laufzeit_minuten()
            eg = self.safe_float(EG_MITTEL_SENSOR)
            if (
                self.nachtsperre_zeit()
                and eg is not None
                and eg >= EG_NACHT_AUS_C
                and not self.frost_expected_tonight()
            ):
                self.call_service("switch/turn_off", entity_id=WP_SWITCH)
                self.log(
                    f"WP automatisch abgeschaltet - Nachtsperre {NACHTSPERRE_START_HOUR}-"
                    f"{NACHTSPERRE_ENDE_HOUR} Uhr und EG-Mittel {eg}°C >= {EG_NACHT_AUS_C}°C. "
                    f"Neustart ab {NACHTSPERRE_ENDE_HOUR} Uhr bei EG <= {EG_EIN_C}°C, nachts nur "
                    f"bei EG <= {EG_NACHT_UNTERGRENZE_C}°C oder Frostprognose.",
                    level="INFO",
                )
                self.eg_warm_seit = None
                return True
            if (
                self.eg_warm_minuten() >= EG_AUS_HALTE_MINUTES
                and (laufzeit_uebergang is None
                     or laufzeit_uebergang >= AUSSCHALT_MIN_LAUFZEIT_MINUTES)
                and not self.frost_expected_tonight()
            ):
                self.call_service("switch/turn_off", entity_id=WP_SWITCH)
                seit = f"{laufzeit_uebergang:.0f}" if laufzeit_uebergang is not None else "?"
                self.log(
                    f"WP automatisch abgeschaltet - EG warm genug (EG-Mittel {eg}°C seit "
                    f"{self.eg_warm_minuten():.0f} min >= {EG_AUS_C}°C, Laufzeit {seit} min). "
                    f"Wiedereinschalten bei EG <= {EG_EIN_C}°C.",
                    level="INFO",
                )
                self.eg_warm_seit = None
                return True

        at_mittel = self.safe_float(AT_MITTEL_SENSOR)
        if at_mittel is None or at_mittel < AUSSCHALT_AT_THRESHOLD_C:
            return False

        # Prognose-Veto: steht eine Nacht an, fuer die vorgeladen wird, bleibt die WP
        # an - dieselbe Schwelle, die auch das Einschalten in vorschau_at() steuert.
        prognose = self.safe_float(FROST_FORECAST_NUMBER)
        if prognose is not None and prognose < VORLADE_AB_C:
            return False

        coverage = self.safe_float(AT_MITTEL_SENSOR, attribute="age_coverage_ratio")
        if coverage is not None and coverage < AUSSCHALT_MIN_COVERAGE:
            self.log(
                f"Heizgrenze abgewartet: AT-Mittel {at_mittel:.1f}°C deckt nur "
                f"{coverage:.0%} des 3-h-Fensters (noetig {AUSSCHALT_MIN_COVERAGE:.0%})",
                level="INFO",
            )
            return False

        laufzeit = self.wp_laufzeit_minuten()
        if laufzeit is not None and laufzeit < AUSSCHALT_MIN_LAUFZEIT_MINUTES:
            return False

        self.call_service("switch/turn_off", entity_id=WP_SWITCH)
        seit = f"{laufzeit:.0f}" if laufzeit is not None else "?"
        self.log(
            f"WP automatisch abgeschaltet - Heizgrenze erreicht (AT-Mittel 3h "
            f"{at_mittel:.1f}°C >= {AUSSCHALT_AT_THRESHOLD_C}°C, jetzt "
            f"{self.safe_float(AT_SENSOR)}°C, Prognose {prognose}°C, Laufzeit "
            f"{seit} min). Autostart bleibt erlaubt.",
            level="INFO",
        )
        return True

    def rl_ziel_basis(self, at):
        """Stueckweise lineare Heizkurve durch HEIZKURVE_PUNKTE.

        Nach unten (kaeltere AT als der kaelteste Stuetzpunkt) wird mit der
        Steigung des kalten Endes weiter extrapoliert - wie bisher, damit die
        Regelung dort nicht schwaecher wird als vorher. Praktisch macht es
        wenig Unterschied, weil die VLT unter -5 °C ohnehin am Maximum haengt;
        RL_MAX deckelt das Ergebnis. Nach oben wird geklemmt (Heizgrenze).
        """
        punkte = HEIZKURVE_PUNKTE
        if at <= punkte[0][0]:
            (x1, y1), (x2, y2) = punkte[0], punkte[1]
            steigung = (y2 - y1) / (x2 - x1)
            return min(RL_MAX, y1 + steigung * (at - x1))
        if at >= punkte[-1][0]:
            return punkte[-1][1]
        for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
            if x1 <= at <= x2:
                return y1 + (y2 - y1) * (at - x1) / (x2 - x1)
        return punkte[-1][1]

    def vorschau_at(self):
        """Massgebliche Aussentemperatur fuer das EINSCHALTEN.

        Normalfall ist die aktuelle Aussentemperatur. Das 24-h-Prognoseminimum wird
        nur dann einbezogen, wenn es tatsaechlich einen Vorladefall darstellt (unter
        VORLADE_AB_C) - dann soll die WP an einem milden Tag vor einer kalten Nacht
        anlaufen, damit vorlade_bonus() ueberhaupt greifen kann.

        Geaendert 2026-09-12: vorher floss die Prognose IMMER ein (Minimum aus beiden
        Werten). Das liess die Anlage am 12.09. bei 21,4 Grad Aussentemperatur heizen,
        weil das Nachtminimum 14,2 Grad betrug - eine milde Nacht, fuer die gar nicht
        vorgeladen werden muss (vorlade_bonus() liefert bei 14,2 Grad exakt 0,0). Die
        Einschaltschwelle 16,5 Grad und die Vorladeschwelle 8,0 Grad lagen also
        auseinander, ohne dass das jemand entschieden hatte.
        Zugleich haette die neue Heizgrenzen-Abschaltung gegen solche Starts
        angearbeitet: Einschalten wegen der Prognose, Abschalten wegen des AT-Mittels,
        im Wechsel.

        Fuer die Heizkurve selbst gilt weiterhin die AKTUELLE Aussentemperatur - die
        Vorwegnahme passiert dort ueber vorlade_bonus().
        """
        at_jetzt = self.safe_float(AT_SENSOR)
        prognose = self.safe_float(FROST_FORECAST_NUMBER)
        if prognose is not None and prognose < VORLADE_AB_C:
            werte = [w for w in (at_jetzt, prognose) if w is not None]
            return min(werte) if werte else None
        return at_jetzt

    def vorlade_bonus(self):
        """Tagsueber den Estrich vorladen, wenn die Nacht kalt wird.

        Ersetzt den frueheren binaeren Frost-Bonus (pauschal +1 K, sobald die
        Prognose unter 2 °C lag) durch eine proportionale Anhebung: je kaelter
        die Nacht, desto mehr wird eingelagert. Damit automatisiert die App,
        was der Betreiber bisher von Hand gemacht hat - morgens erhoehen, wenn abends
        Frost kommt.

        Bewusst nur tagsueber: Bei 0,7 K Badtemperatur in 3 h kaeme nachts
        nachheizen ohnehin zu spaet, es kostet dann nur Strom und Laerm.
        """
        if not self.is_day():
            return 0.0
        prognose = self.safe_float(FROST_FORECAST_NUMBER)
        if prognose is None or prognose >= VORLADE_AB_C:
            return 0.0
        return min(VORLADE_MAX_C, (VORLADE_AB_C - prognose) * VORLADE_FAKTOR)

    def tag_nacht_bonus(self):
        if not self.is_day():
            return 0.0
        return DAY_OVERHEAT_BONUS_C + self.vorlade_bonus()

    def heizkurve_ziel(self, at):
        offset = self.safe_float(HEIZKURVE_OFFSET_HELPER, default=0.0)
        ziel = self.rl_ziel_basis(at) + self.tag_nacht_bonus() + offset
        return max(RL_MIN, min(RL_MAX, ziel))

    def update_rl_ziel(self, at):
        """Naehert das aktive RL-Ziel dem Heizkurven-Zielwert schrittweise an (Kaltstart-
        Rampe/Geduld), analog zur bestehenden VLT-Schrittlogik weiter unten."""
        ziel_kurve = self.heizkurve_ziel(at)
        if self.rl_ziel_aktuell is None:
            self.rl_ziel_aktuell = RL_ZIEL_START_C

        now = self.datetime()
        last = self.last_step.get("rl_ziel")
        cooldown_ok = (
            last is None
            or (now - last).total_seconds() >= RL_ZIEL_STEP_INTERVAL_MINUTES * 60
        )
        diff = ziel_kurve - self.rl_ziel_aktuell
        if cooldown_ok and abs(diff) > 0.01:
            step = min(RL_ZIEL_STEP_C, abs(diff))
            alt = self.rl_ziel_aktuell
            self.rl_ziel_aktuell += step if diff > 0 else -step
            self.last_step["rl_ziel"] = now
            self.log(
                f"RL-Ziel angenaehert {alt:.1f}->{self.rl_ziel_aktuell:.1f}°C "
                f"(Kurve {ziel_kurve:.1f}°C, AT {at:.1f}°C)",
                level="INFO",
            )
        return self.rl_ziel_aktuell

    def adapt_offset(self):
        """Periodische Parallelverschiebung der Heizkurve anhand des Raum-Ist/Soll-Trends.
        Nur wenn der Kompressor nicht schon am Limit laeuft (sonst ist es ein Kapazitaets-,
        kein Kurvenproblem). Laeuft dauerhaft, kein Lernende (2026-07-24).

        In der Uebergangszeit ausgesetzt (Auswertung 25.09.2026). Der Versuch vom 14.09.,
        dort das EG-Mittel gegen EG_AUS_C zu nehmen, war eine Ratsche: Die WP laeuft nur
        zwischen EG_EIN_C und EG_AUS_C, der erste faellige Schritt kommt meist direkt nach
        dem Start (der 5-h-Takt laeuft auch bei stehender WP ab) und sieht dann ~20,0 Grad.
        Absenken koennte er erst ueber 21,3 Grad, da ist die WP laengst aus. Der Offset stieg
        so vom 17. bis 20.09. von 1,0 auf den Anschlag 3,0, das RL-Ziel auf 32-34 Grad bei
        11-17 Grad AT. Den Komfort regelt in diesen Monaten ohnehin die EG-Abschaltung; der
        Offset bestimmt nur, wie heiss dafuer gefahren wird. Ausserhalb der Uebergangszeit
        wie bisher das Bad gegen bad_target()."""
        if self.uebergangszeit():
            return
        now = self.datetime()
        last = self.last_step.get("offset")
        due = last is None or (now - last).total_seconds() >= ADAPT_INTERVAL_MINUTES * 60
        if not due:
            return
        self.last_step["offset"] = now

        komp_ist = self.safe_float(KOMPRESSOR_IST_SENSOR)
        if komp_ist is not None and komp_ist >= KOMPRESSOR_MAX_NORMAL * KOMPRESSOR_NEAR_MAX_RATIO:
            self.log(
                "Heizkurven-Offset-Anpassung ausgesetzt: Kompressor am Limit (Kapazitaets-, kein Kurvenproblem)",
                level="INFO",
            )
            return

        bad_current = self.safe_float(BAD_CLIMATE, attribute="current_temperature")
        if bad_current is None:
            return
        target, bezug = self.bad_target(), "Bad"

        error = target - bad_current
        offset = self.safe_float(HEIZKURVE_OFFSET_HELPER, default=0.0)

        if error > BAD_DEADBAND_C:
            new_offset = min(ADAPT_OFFSET_MAX, offset + ADAPT_STEP_C)
        elif error < -BAD_DEADBAND_C:
            new_offset = max(ADAPT_OFFSET_MIN, offset - ADAPT_STEP_C)
        else:
            return

        if abs(new_offset - offset) > 0.01:
            self.call_service("input_number/set_value", entity_id=HEIZKURVE_OFFSET_HELPER, value=new_offset)
            self.log(
                f"Heizkurven-Offset angepasst {offset}->{new_offset}°C "
                f"({bezug} {bad_current}°C, Ziel {target}°C, Kompressor {komp_ist}Hz)",
                level="INFO",
            )

    def control_rl_and_vlt_and_kompressor(self):
        """Vorsteuerung des Vorlauf-Sollwerts (2026-09-13), Begruendung bei SPREIZUNG_*.

        Die Avarma regelt unterhalb des Deckels selbst auf diesen Sollwert. Weil er in jedem
        Zyklus absolut aus RL-Ziel und Spreizung berechnet wird, kann er nicht ueber dem
        Vorlauf parken - weder nach einem Anlagenneustart (P2 = 45) noch nachdem der
        Ruecklauf sein Ziel erreicht hat."""
        at = self.safe_float(AT_SENSOR)
        rl_ist = self.safe_float(RLT_IST_SENSOR)
        vlt_soll = self.safe_float(VLT_SOLL_NUMBER)
        if at is None or rl_ist is None or vlt_soll is None:
            return

        rl_ziel = self.update_rl_ziel(at)
        error = rl_ziel - rl_ist
        spreizung, quelle = self.spreizung_aktuell()

        self.update_korrektur(error, rl_ziel + spreizung + self.korrektur)
        roh = rl_ziel + spreizung + self.korrektur
        ziel = float(round(max(VLT_MIN, min(VLT_MAX, roh))))
        ziel = self.absenkung_begrenzen(ziel, vlt_soll)

        abweichung = abs(ziel - vlt_soll)
        if abweichung >= 1.0 and (
            abweichung >= VLT_SOFORT_AB_K
            or self.cooldown_ok("vlt", VLT_WRITE_INTERVAL_MINUTES)
        ):
            self.call_service("number/set_value", entity_id=VLT_SOLL_NUMBER, value=ziel)
            self.last_step["vlt"] = self.datetime()
            if ziel < vlt_soll:
                self.vlt_abgesenkt_um = self.datetime()
            self.log(
                f"VL-Soll {vlt_soll:.0f}->{ziel:.0f}°C (RL-Ziel {rl_ziel:.1f} + Spreizung "
                f"{spreizung:.1f} K {quelle} + Korrektur {self.korrektur:+.1f} K; "
                f"RL-Ist {rl_ist:.1f}°C, AT {at:.1f}°C)",
                level="INFO",
            )

        self.control_kompressor_deckel(at, rl_ist, rl_ziel, error)

    def absenkung_begrenzen(self, ziel, vlt_soll):
        """Begrenzt eine Absenkung des VL-Solls bei laufendem Kompressor so, dass die Avarma
        nicht stoppt (Begruendung bei VLT_ABSENK_*). Gibt den zu schreibenden Sollwert
        zurueck; vlt_soll selbst heisst: diesmal nicht absenken."""
        komp = self.safe_float(KOMPRESSOR_IST_SENSOR)
        vl = self.safe_float(VLT_IST_SENSOR)
        if ziel >= vlt_soll or komp is None or komp < KOMPRESSOR_LAEUFT_HZ or vl is None:
            self.absenkung_wartet_seit = None
            return ziel
        # Kleinster ganzzahliger Sollwert, ueber dem der Vorlauf hoechstens
        # VLT_ABSENK_MAX_UEBER_K liegt. Das Epsilon haelt 37,8 - 0,8 bei 37 statt 38.
        sicher = float(math.ceil(vl - VLT_ABSENK_MAX_UEBER_K - 1e-6))
        if sicher < vlt_soll:
            self.absenkung_wartet_seit = None
            return max(ziel, sicher)

        now = self.datetime()
        if self.absenkung_wartet_seit is None:
            self.absenkung_wartet_seit = now
            self.log(
                f"VL-Soll-Absenkung {vlt_soll:.0f}->{ziel:.0f}°C zurueckgestellt: Vorlauf "
                f"{vl:.1f}°C sitzt auf dem Sollwert, schon 1 K weniger wuerde den Kompressor "
                f"stoppen. Spaetestens in {VLT_ABSENK_WARTEN_MAX_MINUTES} min trotzdem.",
                level="INFO",
            )
        gewartet = (now - self.absenkung_wartet_seit).total_seconds() / 60
        if gewartet < VLT_ABSENK_WARTEN_MAX_MINUTES:
            return vlt_soll
        self.absenkung_wartet_seit = None
        self.log(
            f"VL-Soll-Absenkung wartet seit {gewartet:.0f} min (Vorlauf {vl:.1f}°C) - "
            f"senke trotzdem um 1 K, der Stopp zaehlt nicht fuer die Takterkennung",
            level="INFO",
        )
        return vlt_soll - 1.0

    def kompressor_deckel_basis(self, at):
        """Stueckweise lineare Kennlinie Aussentemperatur -> Kompressor-Deckel."""
        punkte = KOMPRESSOR_DECKEL_PUNKTE
        if at <= punkte[0][0]:
            return punkte[0][1]
        if at >= punkte[-1][0]:
            return max(KOMPRESSOR_DECKEL_MIN, punkte[-1][1])
        for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
            if x1 <= at <= x2:
                anteil = (at - x1) / (x2 - x1)
                return max(KOMPRESSOR_DECKEL_MIN, y1 + anteil * (y2 - y1))
        return KOMPRESSOR_MAX_NORMAL

    def control_kompressor_deckel(self, at, rl_ist, rl_ziel, error):
        """Lastabhaengiger Deckel plus Sicherheitspuffer bei anhaltender Unterversorgung.

        error = rl_ziel - rl_ist, positiv also "Ruecklauf bleibt zurueck".
        """
        komp_max_ist = self.safe_float(KOMPRESSOR_MAX_NUMBER)
        if komp_max_ist is None:
            return
        now = self.datetime()
        basis = self.kompressor_deckel_basis(at)
        obergrenze = self.kompressor_obergrenze(at)

        unterversorgt = error > RL_DEADBAND_C

        # Kaltstart: Der Ruecklauf liegt beim Anfahren zwangslaeufig zurueck, das ist
        # der geplante Verlauf und keine Unterversorgung. Puffer bleibt aus.
        if self.anfahrphase():
            if self.boost_hz is None or self.boost_hz > 0:
                laufzeit = self.wp_laufzeit_minuten()
                seit = f"{laufzeit:.0f}" if laufzeit is not None else "?"
                self.log(
                    f"Kompressor-Puffer bleibt aus: Anlage faehrt an (WP seit {seit} min, "
                    f"Ruecklauf {rl_ist:.1f}°C unter Rampenstart {RL_ZIEL_START_C}°C) - "
                    f"Deckel bleibt bei Kennlinie {basis:.0f} Hz",
                    level="INFO",
                )
            self.boost_hz = 0.0
            self.boost_since = None
            self.am_deckel_since = None
            self.vereisung_sperre_seit = None
            unterversorgt = False

        # Beim ersten Lauf den Puffer aus dem Geraetezustand rekonstruieren, statt bei
        # 0 zu beginnen - sonst muesste er sich nach jedem Reload mitten im Winter neu
        # aufbauen (BOOST_SUSTAIN_MINUTES plus Schrittintervalle).
        #
        # ABER nur, wenn der Ruecklauf gerade wirklich zurueckbleibt. Ein erhoehter
        # Deckel allein ist kein Beleg fuer echten Bedarf: Der ESPHome-Watchdog setzt
        # ihn nach 30 min ohne Heartbeat auf 90 Hz. Ohne diese Bedingung wuerde daraus
        # ein Phantom-Puffer von bis zu +45 Hz, der ueber Stunden abgebaut wird und den
        # Deckel genau so lange zu hoch haelt - das Gegenteil dessen, wofuer er da ist.
        if self.boost_hz is None:
            if unterversorgt:
                self.boost_hz = max(
                    0.0, min(BOOST_UEBERNAHME_MAX_HZ, BOOST_MAX_HZ, komp_max_ist - basis)
                )
                if self.boost_hz > 0:
                    self.log(
                        f"Kompressor-Puffer aus Geraetezustand uebernommen: "
                        f"+{self.boost_hz:.0f} Hz (Deckel {komp_max_ist:.0f} Hz, Kennlinie "
                        f"{basis:.0f} Hz bei AT {at:.1f}°C, Ruecklauf bleibt zurueck)",
                        level="INFO",
                    )
            else:
                self.boost_hz = 0.0

        # Laeuft der Kompressor am Deckel? Nur dann ist der Deckel die Ursache der
        # Unterversorgung - und nur dann bringt es ueberhaupt etwas, ihn anzuheben.
        komp_ist = self.safe_float(KOMPRESSOR_IST_SENSOR)
        am_deckel = (
            komp_ist is not None
            and komp_ist >= komp_max_ist - KOMPRESSOR_AM_DECKEL_TOLERANZ_HZ
        )

        if unterversorgt:
            if self.boost_since is None:
                self.boost_since = now
            if am_deckel:
                if self.am_deckel_since is None:
                    self.am_deckel_since = now
            else:
                self.am_deckel_since = None

            def verstrichen(seit):
                return (now - seit).total_seconds() / 60 if seit else 0.0

            lange_genug = verstrichen(self.boost_since) >= BOOST_SUSTAIN_MINUTES
            am_deckel_lang = verstrichen(self.am_deckel_since) >= BOOST_AM_DECKEL_MINUTES

            # Anti-Windup: Nicht weiter aufintegrieren, wenn der effektive Deckel
            # ohnehin schon an KOMPRESSOR_MAX_ESCALATED klemmt. Sonst waechst der
            # Puffer ins Leere - und muesste beim Lastrueckgang ueber Stunden
            # abgebaut werden (30 min je Schritt), bevor der Deckel ueberhaupt
            # wieder sinkt. Im Testlauf lief er so auf +25 Hz, obwohl ab +17 nichts
            # mehr passierte.
            spielraum_frei = basis + self.boost_hz < obergrenze

            # Vereisungs-Verriegelung: Waechst der Puffer, waehrend die Lamelle schon
            # leergezogen wird, kauft die zusaetzliche Frequenz Eis statt Waerme.
            verdampfer = self.safe_float(EVAPORATOR_SENSOR)
            spreizung = at - verdampfer if verdampfer is not None else None
            vereist = (
                verdampfer is not None
                and verdampfer < EVAPORATOR_MIN_C
                and spreizung > VEREISUNG_SPREIZUNG_MAX_K
            )
            if vereist:
                if self.vereisung_sperre_seit is None:
                    self.vereisung_sperre_seit = now
                gebremst_min = (now - self.vereisung_sperre_seit).total_seconds() / 60
                # Kein Notausgang mehr: Die Sperre bleibt stehen, solange die
                # Vereisung anhaelt. Mehr Frequenz wuerde sie nur verstaerken -
                # zustaendig ist control_notabtauung.
                if gebremst_min >= VEREISUNG_DAUERWARNUNG_MINUTES and self.cooldown_ok(
                    "vereisung_dauer_log", 30
                ):
                    self.last_step["vereisung_dauer_log"] = now
                    self.log(
                        f"Kompressor-Puffer bleibt bei +{self.boost_hz:.0f} Hz gesperrt: "
                        f"Spreizung {spreizung:.1f} K haelt sich seit {gebremst_min:.0f} min "
                        f"trotz voller Luftmenge (Verdampfer {verdampfer:.1f}°C). Mehr "
                        f"Frequenz wuerde die Vereisung verstaerken - abgetaut wird, "
                        f"wenn die Not-Abtauung greift",
                        level="WARNING",
                    )
            else:
                self.vereisung_sperre_seit = None

            if vereist and (lange_genug and am_deckel_lang) and spielraum_frei:
                if self.cooldown_ok("vereisung_log", 15):
                    self.last_step["vereisung_log"] = now
                    self.log(
                        f"Kompressor-Puffer haelt bei +{self.boost_hz:.0f} Hz: Verdampfer "
                        f"{verdampfer:.1f}°C, Spreizung {spreizung:.1f} K > "
                        f"{VEREISUNG_SPREIZUNG_MAX_K} K - mehr Frequenz braechte jetzt Eis "
                        f"statt Waerme (Luefter {self.safe_float(FAN_SPEED_NUMBER)} RPM)",
                        level="INFO",
                    )

            if (lange_genug and am_deckel_lang) and spielraum_frei and not vereist:
                letzter = self.last_step.get("boost")
                faellig = (
                    letzter is None
                    or (now - letzter).total_seconds() >= BOOST_STEP_INTERVAL_MINUTES * 60
                )
                if faellig and self.boost_hz < BOOST_MAX_HZ:
                    # Auch der letzte Schritt darf nicht ueber den Punkt hinaus,
                    # ab dem der Deckel ohnehin klemmt - sonst muesste der
                    # Ueberschuss spaeter unnoetig abgebaut werden.
                    max_sinnvoll = obergrenze - basis
                    self.boost_hz = min(
                        BOOST_MAX_HZ, max_sinnvoll, self.boost_hz + BOOST_STEP_HZ
                    )
                    self.last_step["boost"] = now
                    grund = (
                        f"Kompressor haengt seit {verstrichen(self.am_deckel_since):.0f} min "
                        f"am Deckel ({komp_ist:.0f} Hz), Ruecklauf seit "
                        f"{verstrichen(self.boost_since):.0f} min unter Ziel"
                    )
                    self.log(
                        f"Kompressor-Puffer erhoeht auf +{self.boost_hz:.0f} Hz - {grund} "
                        f"(Ruecklauf {rl_ist:.1f}°C, Ziel {rl_ziel:.1f}°C)",
                        level="WARNING",
                    )
        else:
            self.boost_since = None
            self.am_deckel_since = None
            self.vereisung_sperre_seit = None
            if self.boost_hz > 0:
                letzter = self.last_step.get("boost_decay")
                faellig = (
                    letzter is None
                    or (now - letzter).total_seconds() >= BOOST_DECAY_INTERVAL_MINUTES * 60
                )
                if faellig:
                    self.boost_hz = max(0.0, self.boost_hz - BOOST_STEP_HZ)
                    self.last_step["boost_decay"] = now
                    self.log(
                        f"Kompressor-Puffer abgebaut auf +{self.boost_hz:.0f} Hz "
                        f"(Ruecklauf {rl_ist:.1f}°C, Ziel {rl_ziel:.1f}°C)",
                        level="INFO",
                    )

        # Kennlinie im 5-Hz-Raster, geschrieben nur bei klarer Abweichung (
        # 2026-09-13: moeglichst wenige Schreibvorgaenge auf P45). Die Hysterese auf den
        # ungerasterten Wert verhindert, dass eine um die Rastergrenze pendelnde
        # Aussentemperatur den Deckel im Wechsel 60/65 schreiben laesst.
        basis_raster = DECKEL_RASTER_HZ * round(basis / DECKEL_RASTER_HZ)
        ziel_deckel = round(
            min(obergrenze, max(KOMPRESSOR_DECKEL_MIN, basis_raster + self.boost_hz))
        )
        roh_deckel = min(obergrenze, basis + self.boost_hz)

        if (
            abs(ziel_deckel - komp_max_ist) >= 1.0
            and abs(roh_deckel - komp_max_ist) >= DECKEL_SCHREIB_HYSTERESE_HZ
        ):
            self.call_service(
                "number/set_value", entity_id=KOMPRESSOR_MAX_NUMBER, value=ziel_deckel
            )
            self.log(
                f"Kompressor-Deckel {komp_max_ist:.0f}->{ziel_deckel:.0f} Hz "
                f"(Kennlinie {basis:.0f} bei AT {at:.1f}°C, Puffer +{self.boost_hz:.0f}, "
                f"Obergrenze {obergrenze:.0f})",
                level="INFO",
            )

    def control_fan(self):
        mode = self.get_state(FAN_MODE_SELECT)
        if mode != "Manuell":
            self.call_service("select/select_option", entity_id=FAN_MODE_SELECT, option="Manuell")
            self.log("Luefter auf Manuell umgestellt fuer Verdampfer-Regelung", level="INFO")

        fan_speed_raw = self.safe_float(FAN_SPEED_NUMBER)
        fan_speed = fan_speed_raw * FAN_REGISTER_SCALE if fan_speed_raw is not None else None
        if fan_speed is not None and fan_speed < FAN_MIN_RPM:
            self.call_service(
                "number/set_value", entity_id=FAN_SPEED_NUMBER, value=FAN_MIN_RPM / FAN_REGISTER_SCALE
            )
            self.log(f"Luefter auf Minimaldrehzahl {FAN_MIN_RPM} RPM gesetzt (war {fan_speed})", level="INFO")
            fan_speed = FAN_MIN_RPM

        verdampfer = self.safe_float(EVAPORATOR_SENSOR)
        if verdampfer is None or fan_speed is None:
            return

        now = self.datetime()

        # Waehrend der Abtauung ist die Verdampfertemperatur kein Regelsignal: Sie
        # steigt bauartbedingt bis ueber 20 Grad (Abtau-Ende-Temperatur der Anlage).
        # Am 24.08.2026 hat die alte Fassung deshalb um 05:42 mitten in der Abtauung
        # gedrosselt (550->500 RPM), weil sie 20 Grad als "reichlich Reserve" gelesen
        # hat - im denkbar schlechtesten Moment.
        if self.abtauen_aktiv():
            self.abtau_zuletzt = now
            return

        # Notfall: Der Verdampfer naehert sich der Abtau-Schwelle. Feinregelung in
        # Schritten waere hier verschenkte Zeit - die Anlage taut sonst gleich ab.
        notfall_schwelle = ABTAU_START_C + FAN_NOTFALL_ABSTAND_K
        if verdampfer <= notfall_schwelle and fan_speed < FAN_MAX_RPM:
            self.set_fan(FAN_MAX_RPM)
            self.last_step["fan_up"] = now
            self.log(
                f"Luefter auf Volllast {fan_speed:.0f}->{FAN_MAX_RPM} RPM "
                f"(Verdampfer {verdampfer:.1f}°C, Abtauung startet bei {ABTAU_START_C}°C)",
                level="WARNING",
            )
            return

        # Einseitige Regel: unter der Untergrenze mehr Luft (waermt den Verdampfer),
        # oberhalb des Hysteresebands drosseln bis zur Minimaldrehzahl. Dazwischen
        # passiert nichts.
        if verdampfer < EVAPORATOR_MIN_C and fan_speed < FAN_MAX_RPM:
            if not self.cooldown_ok("fan_up", FAN_UP_INTERVAL_MINUTES):
                return
            defizit = EVAPORATOR_MIN_C - verdampfer
            schritt = min(
                FAN_STEP_UP_MAX_RPM, max(FAN_STEP_UP_MIN_RPM, defizit * FAN_STEP_RPM_PER_K)
            )
            new_speed = min(FAN_MAX_RPM, round((fan_speed + schritt) / 10) * 10)
            if new_speed <= fan_speed:
                return
            self.set_fan(new_speed)
            self.last_step["fan_up"] = now
            self.log(
                f"Luefter erhoeht {fan_speed:.0f}->{new_speed:.0f} RPM "
                f"(Verdampfer {verdampfer:.1f}°C, {defizit:.1f} K unter Untergrenze "
                f"{EVAPORATOR_MIN_C}°C)",
                level="INFO",
            )
        elif (verdampfer > EVAPORATOR_MIN_C + EVAPORATOR_HYSTERESE_C
              and fan_speed > FAN_MIN_RPM):
            # Nach einer Abtauung bleibt der Verdampfer noch minutenlang warm -
            # in dieser Zeit ist "viel Reserve" eine Taeuschung.
            if self.abtau_zuletzt is not None:
                seit_abtauung = (now - self.abtau_zuletzt).total_seconds() / 60
                if seit_abtauung < FAN_DROSSEL_SPERRE_NACH_ABTAUUNG_MINUTES:
                    return
            if not self.cooldown_ok("fan_down", FAN_STEP_INTERVAL_MINUTES):
                return
            new_speed = max(FAN_MIN_RPM, fan_speed - FAN_STEP_RPM)
            self.set_fan(new_speed)
            self.last_step["fan_down"] = now
            self.log(
                f"Luefter gesenkt {fan_speed:.0f}->{new_speed:.0f} RPM "
                f"(Verdampfer {verdampfer:.1f}°C mit Reserve ueber {EVAPORATOR_MIN_C}°C)",
                level="INFO",
            )
