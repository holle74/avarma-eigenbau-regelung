"""Gebaeude-Thermometrie: lernt das thermische Verhalten des Hauses.

Schritt 1 des MPC-Hauptplans. Die App beobachtet nur - sie schreibt nichts an die
Waermepumpe und greift in keinen Regelkreis ein.

MODELL
------
Ein RC-Modell (thermischer Widerstand x Kapazitaet). Ohne Heizung gilt

    dT_innen/dt = a * (T_aussen - T_innen) + c

mit a = 1/tau. tau ist die Zeitkonstante des Gebaeudes: die Zeit, in der die
Differenz zum Aussenwert auf 1/e (37 %) abgeklungen waere. c faengt auf, was
unabhaengig vom Temperaturgefaelle wirkt - interne Gewinne (Personen, Geraete)
gegen naechtliche Abstrahlung an den Himmel.

DATENAUSWAHL
------------
Gefittet wird ausschliesslich auf naechtlichen Abkuehlphasen, weil dort alle
Stoerquellen gleichzeitig ruhen: keine Sonne, keine Heizung, kein Lueften. Der
Tagesgang der Messdaten zeigt das deutlich - nachts 00-04 h kuehlt das Haus
gleichmaessig mit rund -0,07 K/h, waehrend um 05 h (-0,23 K/h) und 22 h
(-0,17 K/h) das sommerliche Stosslueften einschlaegt.

GRENZEN DER AKTUELLEN SCHAETZUNG - BITTE LESEN
----------------------------------------------
Die Startdaten stammen aus Juli/August 2026. In dieser Zeit betraegt das
Temperaturgefaelle im Mittel nur -0,8 K und ist in 42 % der Stunden sogar
positiv (draussen waermer als drinnen). Das Signal ist entsprechend schwach:
Die Leave-One-Out-Kreuzvalidierung schlaegt das blosse Raten des Mittelwerts
nur um gut 10 %. Ein Windterm verbesserte den Fit zwar sichtbar, bekam dabei
aber das falsche Vorzeichen (er haette die Abkuehlung *gebremst*) - windige
Sommernaechte sind schlicht milder (r = +0,44 zwischen Wind und Gefaelle). Das
war Scheinkorrelation, kein Windeffekt, deshalb ist der Term nicht im Modell.

Die Schaetzung ist damit ein Startwert, keine belastbare Groesse. Im Winter
liegt das Gefaelle bei -15 bis -25 K; dieselbe Rechnung wird dann von selbst
deutlich schaerfer. Genau dafuer sammelt die App weiter: Sie protokolliert
stuendlich und rechnet taeglich neu.

Der Sensor sensor.gebaeude_modell_guete traegt deshalb ein Attribut
"belastbarkeit". Solange dort "vorlaeufig" steht, gehoert das Modell nicht in
einen Regelkreis.
"""

import json
import math
import os
import time
import datetime

import appdaemon.plugins.hass.hassapi as hass

# Standort fuer die Sonnenstandsberechnung (aus zone.home)
LAT_STANDARD = 0.0  # eigene Koordinaten eintragen (zone.home) oder per apps.yaml 'latitude'
LON_STANDARD = 0.0  # eigene Koordinaten eintragen (zone.home) oder per apps.yaml 'longitude'

# Raumgewichte: Bad zaehlt doppelt (Referenzraum-Konzept, wie
# sensor.raumtemperatur_mittelwert). Bewusst hier gespiegelt statt den
# HA-Sensor zu lesen, damit die App auch bei dessen Ausfall weiterlernt.
RAEUME_STANDARD = {
    "climate.raumtemperaturregler_bad_unten_bad": 2,
    "climate.raumtemperaturregler_wohnzimmer_wohnzimmer": 1,
    "climate.raumtemperaturregler_buro_buro": 1,
    "climate.raumtemperaturregler_dusche_dusche": 1,
    "climate.raumtemperaturregler_ankleide_ankleide": 1,
    "climate.raumtemperaturregler_yoga_yoga": 1,
    "climate.raumtemperaturregler_flur_flur": 1,
    "climate.raumtemperaturregler_keller_keller": 1,
    "climate.raumtemperaturregler_schlafzimmer_schlafzimmer": 1,
}

SENSOR_TAU = "sensor.gebaeude_zeitkonstante"
SENSOR_AUSKUEHLUNG = "sensor.gebaeude_auskuehlung_12h"
SENSOR_GUETE = "sensor.gebaeude_modell_guete"

# Phasenfenster: 00-05 h. Beginnt nach der Abendlueftung (22-23 h) und endet
# vor der Morgenlueftung (05-06 h).
PHASE_START_H = 0
PHASE_LAENGE_H = 5

# Ein Sprung groesser als das hier gilt als Lueftungsereignis und verwirft die
# Phase. Die natuerliche Abkuehlung liegt bei rund 0,07 K/h; 0,25 K/h trennt
# sauber, ohne echte Frostnaechte auszusortieren.
MAX_SPRUNG_K_PRO_H = 0.25

# Mindestanforderungen, damit eine Schaetzung ueberhaupt veroeffentlicht wird
MIN_PHASEN = 8
# Ab dieser Gefaellespanne (K) gilt die Schaetzung als belastbar. Im Sommer
# werden rund 8 K erreicht, im Winter ein Vielfaches.
GEFAELLE_SPANNE_BELASTBAR = 15.0


def loese(A, b):
    """Gauss-Elimination mit Spaltenpivotisierung (numpy ist nicht installiert)."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(M[i][k]))
        if abs(M[p][k]) < 1e-12:
            raise ValueError("Gleichungssystem singulaer")
        M[k], M[p] = M[p], M[k]
        for i in range(k + 1, n):
            f = M[i][k] / M[k][k]
            for j in range(k, n + 1):
                M[i][j] -= f * M[k][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = sum(M[i][j] * x[j] for j in range(i + 1, n))
        x[i] = (M[i][n] - s) / M[i][i]
    return x


def sonnenhoehe(ts, lat, lon):
    """Sonnenhoehe in Grad ueber dem Horizont, 0 wenn unter Horizont.

    Astronomisch gerechnet statt gemessen: Der uv_index der DWD-Integration ist
    ein Tagesprognosewert und steht nachts genauso hoch wie mittags - als
    stuendlicher Solar-Proxy unbrauchbar.
    """
    dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    n = dt.timetuple().tm_yday
    dekl = math.radians(23.45) * math.sin(math.radians(360.0 / 365.0 * (n - 81)))
    b = math.radians(360.0 / 364.0 * (n - 81))
    zgl = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    utc_h = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    woz = utc_h + lon / 15.0 + zgl / 60.0
    stundenwinkel = math.radians(15.0 * (woz - 12.0))
    phi = math.radians(lat)
    sin_alpha = (math.sin(phi) * math.sin(dekl)
                 + math.cos(phi) * math.cos(dekl) * math.cos(stundenwinkel))
    return max(0.0, math.degrees(math.asin(max(-1.0, min(1.0, sin_alpha)))))


class HeizungThermometrie(hass.Hass):

    def initialize(self):
        self.datei = self.args.get(
            "datei", "/config/apps/thermometrie.json")
        self.raeume = self.args.get("raeume", RAEUME_STANDARD)
        self.aussen_entity = self.args.get(
            "aussen_entity", "sensor.aussentemperatur_avarma_korrigiert")
        self.wp_entity = self.args.get(
            "wp_entity", "switch.esphome_web_avarma_warmepumpe_ein_aus")
        self.wetter_entity = self.args.get("wetter_entity", "weather.home")
        self.lat = float(self.args.get("latitude", LAT_STANDARD))
        self.lon = float(self.args.get("longitude", LON_STANDARD))
        self.max_tage = int(self.args.get("max_tage", 120))

        self.daten = self.lade()
        n = len(self.daten.get("messwerte", []))
        self.log(f"Thermometrie gestartet, {n} Stundenwerte im Speicher", level="INFO")

        # Sofortlauf ueber run_in: run_every mit self.datetime() als Startzeit
        # feuert nicht zuverlaessig gleich mit (bekanntes Verhalten hier).
        self.run_in(self.messen, 5)
        self.run_in(self.auswerten, 20)
        # run_hourly statt run_every: bindet die Messung an die volle Stunde
        # (+2 min). Ein an die Startzeit gekoppeltes Intervall landet sonst
        # irgendwo in der Stunde - bei einem Reload kurz vor der vollen Stunde
        # dicht an der Grenze, wo schon geringer Drift eine Stunde doppelt
        # belegt oder ueberspringt. Die Phasenerkennung rastert nach Stunde.
        self.run_hourly(self.messen, datetime.time(0, 2, 0))
        self.run_daily(self.auswerten, "06:30:00")

    # ------------------------------------------------------------------ IO

    def lade(self):
        if not os.path.exists(self.datei):
            return {"messwerte": [], "modell": None}
        try:
            with open(self.datei) as f:
                d = json.load(f)
            if not isinstance(d.get("messwerte"), list):
                raise ValueError("unerwartete Struktur")
            # Beim Laden auf einen Wert je Stunde normalisieren. Doppelte
            # entstehen etwa, wenn ein Reload kurz vor der vollen Stunde
            # Sofort- und Stundenmessung in dieselbe Stunde legt, oder bei der
            # Zeitumstellung im Herbst. Der spaeteste Wert gewinnt.
            je_stunde = {}
            for z in sorted(d["messwerte"], key=lambda z: z["t"]):
                je_stunde[z["t"] // 3600] = z
            entfernt = len(d["messwerte"]) - len(je_stunde)
            if entfernt:
                self.log(f"{entfernt} doppelte Stundenwerte beim Laden entfernt",
                         level="INFO")
            d["messwerte"] = [je_stunde[k] for k in sorted(je_stunde)]
            return d
        except (OSError, ValueError, json.JSONDecodeError) as e:
            self.log(f"Datei {self.datei} unlesbar ({e}), starte leer", level="WARNING")
            return {"messwerte": [], "modell": None}

    def speichere(self):
        tmp = self.datei + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(self.daten, f)
            os.replace(tmp, self.datei)
        except OSError as e:
            self.log(f"Konnte {self.datei} nicht schreiben: {e}", level="ERROR")

    def zahl(self, entity, attribut=None):
        """Liest einen Zahlenwert defensiv; None wenn nicht verwertbar."""
        roh = self.get_state(entity, attribute=attribut) if attribut \
            else self.get_state(entity)
        if roh in (None, "unavailable", "unknown", ""):
            return None
        try:
            return float(roh)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------- Messen

    def messen(self, kwargs=None):
        """Nimmt eine Stundenzeile auf."""
        werte = {}
        for entity, gewicht in self.raeume.items():
            v = self.zahl(entity, "current_temperature")
            if v is None:
                self.log(f"{entity} liefert keine Temperatur - Messung ausgelassen",
                         level="DEBUG")
                return
            werte[entity] = (v, gewicht)

        summe = sum(v * g for v, g in werte.values())
        gewichte = sum(g for _, g in werte.values())
        innen = summe / gewichte

        aussen = self.zahl(self.aussen_entity)
        if aussen is None:
            self.log("Aussentemperatur nicht verfuegbar - Messung ausgelassen",
                     level="DEBUG")
            return

        wp_roh = self.get_state(self.wp_entity)
        if wp_roh in (None, "unavailable", "unknown"):
            return

        wind = self.zahl(self.wetter_entity, "wind_speed")
        bad_entity = next((e for e, g in self.raeume.items() if g > 1), None)
        jetzt = int(time.time())

        zeile = {
            "t": jetzt,
            "innen": round(innen, 3),
            "bad": werte[bad_entity][0] if bad_entity else None,
            "aussen": aussen,
            "wind": wind if wind is not None else 0.0,
            "sonne": round(sonnenhoehe(jetzt, self.lat, self.lon), 2),
            "wp": 1 if wp_roh == "on" else 0,
        }
        # Pro Stunde nur ein Wert. Beim Start laufen Sofortmessung und erster
        # Stundenlauf dicht hintereinander; ohne das belegten beide dieselbe
        # Stunde und die Phasenerkennung saehe einen Scheinsprung von 0 K/h.
        stunde = jetzt // 3600
        self.daten["messwerte"] = [z for z in self.daten["messwerte"]
                                   if z["t"] // 3600 != stunde]
        self.daten["messwerte"].append(zeile)
        self.daten["messwerte"].sort(key=lambda z: z["t"])

        grenze = jetzt - self.max_tage * 86400
        vorher = len(self.daten["messwerte"])
        self.daten["messwerte"] = [z for z in self.daten["messwerte"]
                                   if z["t"] >= grenze]
        if vorher != len(self.daten["messwerte"]):
            self.log(f"{vorher - len(self.daten['messwerte'])} Messwerte aelter als "
                     f"{self.max_tage} Tage entfernt", level="DEBUG")
        self.speichere()

    # ---------------------------------------------------------- Auswerten

    def phasen_finden(self):
        """Schneidet saubere naechtliche Abkuehlphasen aus den Messwerten."""
        nach_stunde = {}
        for z in self.daten["messwerte"]:
            nach_stunde[z["t"] // 3600] = z

        phasen = []
        for schluessel, start in sorted(nach_stunde.items()):
            if datetime.datetime.fromtimestamp(start["t"]).hour != PHASE_START_H:
                continue
            kette = [nach_stunde.get(schluessel + i) for i in range(PHASE_LAENGE_H + 1)]
            if any(k is None for k in kette):
                continue
            if any(k["wp"] for k in kette):
                continue          # Heizung aktiv - keine freie Abkuehlung
            if any(k["sonne"] > 0.5 for k in kette):
                continue          # Sonne stoert die Bilanz

            spruenge = [abs(kette[i + 1]["innen"] - kette[i]["innen"])
                        for i in range(len(kette) - 1)]
            if max(spruenge) > MAX_SPRUNG_K_PRO_H:
                continue          # Lueftungsereignis

            dauer = (kette[-1]["t"] - kette[0]["t"]) / 3600.0
            if dauer <= 0:
                continue
            gefaelle = sum(k["aussen"] - k["innen"] for k in kette) / len(kette)
            phasen.append({
                "datum": datetime.datetime.fromtimestamp(
                    kette[0]["t"]).strftime("%Y-%m-%d"),
                "dT_pro_h": (kette[-1]["innen"] - kette[0]["innen"]) / dauer,
                "gefaelle": gefaelle,
            })
        return phasen

    def fitten(self, phasen):
        """Kleinste Quadrate fuer dT/dt = a * gefaelle + c."""
        spalten = [lambda p: p["gefaelle"], lambda p: 1.0]
        n = len(spalten)
        A = [[sum(f(p) * g(p) for p in phasen) for g in spalten] for f in spalten]
        b = [sum(f(p) * p["dT_pro_h"] for p in phasen) for f in spalten]
        koeff = loese(A, b)

        y = [p["dT_pro_h"] for p in phasen]
        y_hat = [sum(koeff[i] * spalten[i](p) for i in range(n)) for p in phasen]
        ss_res = sum((y[i] - y_hat[i]) ** 2 for i in range(len(y)))
        mittel = sum(y) / len(y)
        ss_tot = sum((v - mittel) ** 2 for v in y)
        return {
            "a": koeff[0],
            "c": koeff[1],
            "r2": 1 - ss_res / ss_tot if ss_tot > 1e-12 else float("nan"),
            "rmse": math.sqrt(ss_res / len(y)),
        }

    def auswerten(self, kwargs=None):
        phasen = self.phasen_finden()
        if len(phasen) < MIN_PHASEN:
            self.log(f"Erst {len(phasen)} auswertbare Naechte "
                     f"(mindestens {MIN_PHASEN}) - noch keine Schaetzung",
                     level="INFO")
            self.publiziere(None, phasen)
            return

        try:
            modell = self.fitten(phasen)
        except (ValueError, ZeroDivisionError) as e:
            self.log(f"Fit fehlgeschlagen: {e}", level="WARNING")
            self.publiziere(None, phasen)
            return

        # Ein positives a hiesse: das Haus kuehlt ab, wenn es draussen waermer
        # ist. Physikalisch unmoeglich, also Datenproblem - nicht publizieren.
        if modell["a"] <= 0:
            self.log(f"Verworfen: a={modell['a']:.5f} ist nicht positiv, "
                     f"physikalisch unmoeglich", level="WARNING")
            self.publiziere(None, phasen)
            return

        modell["tau"] = 1.0 / modell["a"]
        modell["phasen"] = len(phasen)
        modell["stand"] = datetime.datetime.now().isoformat(timespec="seconds")
        gefaelle = [p["gefaelle"] for p in phasen]
        modell["gefaelle_min"] = min(gefaelle)
        modell["gefaelle_max"] = max(gefaelle)
        modell["gefaelle_spanne"] = max(gefaelle) - min(gefaelle)

        self.daten["modell"] = modell
        self.speichere()

        self.log(f"Modell aktualisiert: tau={modell['tau']:.0f} h aus "
                 f"{len(phasen)} Naechten (R2={modell['r2']:.2f}, "
                 f"Gefaellespanne {modell['gefaelle_spanne']:.1f} K)", level="INFO")
        self.publiziere(modell, phasen)

    # --------------------------------------------------------- Ausspielen

    def auskuehlung(self, modell, t_innen, t_aussen, stunden):
        """Prognose: um wieviel Kelvin faellt die Innentemperatur in N Stunden?

        Analytische Loesung des RC-Modells statt Schrittintegration - das
        Gefaelle schrumpft waehrend der Abkuehlung, lineare Fortschreibung
        wuerde den Verlust deshalb ueberschaetzen.
        """
        a, c = modell["a"], modell["c"]
        beharrung = t_aussen + c / a          # Grenzwert fuer t -> unendlich
        delta = t_innen - beharrung
        return delta * (math.exp(-a * stunden) - 1.0)

    def publiziere(self, modell, phasen):
        belastbar = (modell is not None
                     and modell["gefaelle_spanne"] >= GEFAELLE_SPANNE_BELASTBAR)
        einstufung = "belastbar" if belastbar else "vorlaeufig"

        if modell is None:
            # str(): AppDaemons set_state (0.18.5) prueft den State-Wert per
            # Wahrheitswert - 0/0.0 ist falsy, der State faellt beim Absenden
            # weg und HA lehnt mit HTTP 400 ab. Siehe Commit 65af2a0.
            for sensor, name, einheit in (
                (SENSOR_TAU, "Gebaeude Zeitkonstante", "h"),
                (SENSOR_AUSKUEHLUNG, "Gebaeude Auskuehlung 12 h", "K"),
            ):
                self.set_state(sensor, state="unknown", replace=True,
                               attributes={"friendly_name": name,
                                           "unit_of_measurement": einheit,
                                           "auswertbare_naechte": len(phasen)})
            self.set_state(SENSOR_GUETE, state="unknown", replace=True,
                           attributes={"friendly_name": "Gebaeude Modellguete",
                                       "auswertbare_naechte": len(phasen),
                                       "belastbarkeit": "keine Schaetzung"})
            return

        letzte = self.daten["messwerte"][-1] if self.daten["messwerte"] else None
        innen_jetzt = letzte["innen"] if letzte else None
        aussen_jetzt = self.zahl(self.aussen_entity)

        self.set_state(
            SENSOR_TAU,
            state=str(round(modell["tau"], 1)),
            replace=True,
            attributes={
                "friendly_name": "Gebaeude Zeitkonstante",
                "unit_of_measurement": "h",
                "icon": "mdi:home-thermometer",
                "state_class": "measurement",
                "tau_tage": round(modell["tau"] / 24.0, 2),
                "auswertbare_naechte": modell["phasen"],
                "stand": modell["stand"],
            },
        )

        if innen_jetzt is not None and aussen_jetzt is not None:
            # Raster fuer die Dashboard-Tabelle. Wird hier gerechnet und nicht
            # im Lovelace-Template: die Exponentialfunktion des RC-Modells
            # laesst sich in Jinja nur umstaendlich und fehleranfaellig
            # nachbauen, und beide Seiten muessten synchron gehalten werden.
            # Alle Rasterwerte als String. Der falsy-Zero-Bug aus Commit
            # 65af2a0 trifft nicht nur den State, sondern auch Werte INNERHALB
            # von Attributen: bei aussen=0 fiel der Schluessel beim Absenden
            # stillschweigend ganz aus dem Dict, die Zeile kam ohne
            # Temperaturangabe im Dashboard an. Hier live beobachtet, -15 blieb
            # erhalten, 0 verschwand. Fuer die Anzeige ist String ohnehin das
            # richtige Format.
            raster = []
            for aussen in (-15, -10, -5, 0, 5, 10):
                raster.append({
                    "aussen": str(aussen),
                    "k6": str(round(self.auskuehlung(modell, innen_jetzt, aussen, 6), 1)),
                    "k12": str(round(self.auskuehlung(modell, innen_jetzt, aussen, 12), 1)),
                    "k24": str(round(self.auskuehlung(modell, innen_jetzt, aussen, 24), 1)),
                })
            verlust = self.auskuehlung(modell, innen_jetzt, aussen_jetzt, 12)
            self.set_state(
                SENSOR_AUSKUEHLUNG,
                state=str(round(verlust, 2)),
                replace=True,
                attributes={
                    "friendly_name": "Gebaeude Auskuehlung 12 h",
                    "unit_of_measurement": "K",
                    "icon": "mdi:thermometer-chevron-down",
                    "state_class": "measurement",
                    "basis_innen": innen_jetzt,
                    "basis_aussen": aussen_jetzt,
                    "auskuehlung_6h": round(
                        self.auskuehlung(modell, innen_jetzt, aussen_jetzt, 6), 2),
                    "auskuehlung_24h": round(
                        self.auskuehlung(modell, innen_jetzt, aussen_jetzt, 24), 2),
                    "belastbarkeit": einstufung,
                    "prognose_raster": raster,
                    "tau_stunden": round(modell["tau"], 1),
                },
            )

        self.set_state(
            SENSOR_GUETE,
            state=str(round(modell["r2"], 3)),
            replace=True,
            attributes={
                "friendly_name": "Gebaeude Modellguete",
                "icon": "mdi:chart-bell-curve",
                "rmse_k_pro_h": round(modell["rmse"], 4),
                "auswertbare_naechte": modell["phasen"],
                "gefaelle_min_k": round(modell["gefaelle_min"], 1),
                "gefaelle_max_k": round(modell["gefaelle_max"], 1),
                "gefaelle_spanne_k": round(modell["gefaelle_spanne"], 1),
                "belastbarkeit": einstufung,
                "hinweis": (
                    "Solange 'vorlaeufig': Gefaellespanne der Daten zu klein, "
                    "nicht fuer Regelentscheidungen verwenden. Wird im Winter "
                    "automatisch besser."
                ),
                "stand": modell["stand"],
            },
        )
