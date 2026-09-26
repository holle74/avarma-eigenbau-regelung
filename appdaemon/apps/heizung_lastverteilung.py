from datetime import timedelta

from appdaemon.plugins.hass.hassapi import Hass

# Prioritaets-Raeume: werden geschuetzt, niemals als Spender gedrosselt.
# Reihenfolge = Prioritaet, hoechste zuerst (Festlegung vom 2026-07-14).
PRIORITY_ROOMS = [
    {
        "key": "bad",
        "climate": "climate.raumtemperaturregler_bad_unten_bad",
        "valve": "sensor.heizung_bad_bad_valve_volume_flow",
    },
    {
        "key": "dusche",
        "climate": "climate.raumtemperaturregler_dusche_dusche",
        "valve": "sensor.heizung_dusche_dusche_valve_volume_flow",
    },
    {
        "key": "wohnzimmer",
        "climate": "climate.raumtemperaturregler_wohnzimmer_wohnzimmer",
        "valve": "sensor.heizung_wohnzimmer_wohnzimmer_valve_volume_flow",
    },
    {
        "key": "buro",
        "climate": "climate.raumtemperaturregler_buro_buro",
        "valve": "sensor.heizung_buro_buro_valve_volume_flow",
    },
    {
        "key": "ankleide",
        "climate": "climate.raumtemperaturregler_ankleide_ankleide",
        "valve": "sensor.heizung_ankleide_ankleide_valve_volume_flow",
    },
]

# Spender-Raeume: niedrigste Prioritaet zuerst, werden in dieser Reihenfolge gedrosselt.
DONORS = [
    {
        "key": "schlafzimmer",
        "climate": "climate.raumtemperaturregler_schlafzimmer_schlafzimmer",
        "valves": ["sensor.heizung_schlafzimmer_schlafzimmer_valve_volume_flow"],
        "floor": 18.0,
        "backup_helper": "input_number.wp_spender_schlafzimmer_original_soll",
    },
    {
        "key": "keller",
        "climate": "climate.raumtemperaturregler_keller_keller",
        "valves": ["sensor.heizung_keller_keller_valve_volume_flow"],
        "floor": 20.0,
        "backup_helper": "input_number.wp_spender_keller_original_soll",
    },
    {
        "key": "flur",
        "climate": "climate.raumtemperaturregler_flur_flur",
        "valves": ["sensor.heizung_flur_flur_valve_volume_flow"],
        "floor": 20.0,
        "backup_helper": "input_number.wp_spender_flur_original_soll",
    },
    {
        "key": "yoga",
        "climate": "climate.raumtemperaturregler_yoga_yoga",
        "valves": [
            "sensor.heizung_yoga_1_yoga_valve_volume_flow",
            "sensor.heizung_yoga_2_yoga_valve_volume_flow",
        ],
        "floor": 20.0,
        "backup_helper": "input_number.wp_spender_yoga_original_soll",
    },
]

# --- Uebergangsmodus (2026-09-17) ---
#
# WARUM: In der Uebergangszeit heizt das Haus aus dem Kaltstart hoch, das Bad
# verfehlt sein (bewusst hohes) Ziel praktisch dauerhaft, und die Lastverteilung
# zieht dann der Reihe nach Schlafzimmer, Keller, Flur und Yoga bis auf ihre
# Untergrenze - am 17.09.2026 alle drei innerhalb von zwei Stunden, danach kam
# "kein Spender mehr verfuegbar". Gebracht hat es wenig, gekostet hat es vier
# kuehle Raeume.
#
# Im Uebergang ist das Wohnzimmer der Raum, der am ehesten ohne Heizung auskommt.
# Steht UEBERGANG_SWITCH auf on, ist es deshalb der EINZIGE Spender und faellt
# dafuer aus dem Vorrang; Schlafzimmer, Keller, Flur und Yoga bleiben unbehelligt.
UEBERGANG_SWITCH = "input_boolean.wp_uebergangsmodus"

WOHNZIMMER_DONOR = {
    "key": "wohnzimmer",
    "climate": "climate.raumtemperaturregler_wohnzimmer_wohnzimmer",
    "valves": ["sensor.heizung_wohnzimmer_wohnzimmer_valve_volume_flow"],
    "floor": 21.0,
    "backup_helper": "input_number.wp_spender_wohnzimmer_original_soll",
}

UEBERGANG_PRIORITY = [r for r in PRIORITY_ROOMS if r["key"] != "wohnzimmer"]
UEBERGANG_DONORS = [WOHNZIMMER_DONOR]

# Ueber ALLE Spender beider Modi laeuft das Zuruecksetzen - sonst bliebe ein Raum,
# der im alten Modus gedrosselt wurde, nach dem Umschalten auf seinem abgesenkten
# Wert stehen: die Freigabe schaut nur die Spender des aktuellen Modus an.
ALLE_DONORS = DONORS + [WOHNZIMMER_DONOR]

# --- Erzeuger-Gate (2026-08-24) ---
#
# WARUM: Am 24.08. hat die Lastverteilung zwischen 07:45 und 08:27 vier Raeume
# gedrosselt (Keller, Flur, Yoga, Schlafzimmer) und sie danach ueber vier Stunden
# dort stehen lassen. Zu Recht war das nur bis etwa 09:45 - danach lief die
# Waermepumpe laengst im Teillastbetrieb, um 13:00 stand der Kompressor bei 0 Hz,
# Deckel 50 Hz, Vorlauf 31 Grad bei 18 Grad Aussentemperatur. Es gab keine knappe
# Waerme mehr zu verteilen; gedrosselt wurde trotzdem weiter.
#
# Die Ursache ist die Definition von "Engpass": Sie schaut nur auf den
# Vorrangraum - Ventil offen und Ziel verfehlt. Daraus folgt aber nicht, dass die
# Raeume um knappe Waerme konkurrieren. Das Bad verfehlt sein Ziel auch dann,
# wenn der Erzeuger Luft hat: Bei 18 Grad draussen und 31 Grad Vorlauf bringt
# eine Fussbodenheizung keinen Raum auf 23 Grad, egal wie weit die anderen
# Ventile zu sind.
#
# Verschaerfend kommt dazu, dass das Bad-Ziel bewusst hoch gewaehlt ist, damit es
# die uebrigen Raeume mitzieht (2026-08-24). Es SOLL sein Ziel meistens
# verfehlen. Ohne dieses Gate ist die Engpass-Bedingung damit fast dauerhaft wahr
# und die Lastverteilung haette praktisch keine Abschaltbedingung mehr.
#
# Das Gate fragt deshalb zuerst den Erzeuger: Nur wenn der Kompressor wirklich an
# seinem Deckel haengt, ist die Waerme knapp und Umverteilen sinnvoll. Sonst
# bekommen die Spender ihre Solltemperatur zurueck.
#
# Schwelle und Toleranz sind bewusst dieselben wie in
# heizung_vlt_kompressor_regelung.py, damit beide Apps denselben Begriff von
# "am Deckel" benutzen und nicht gegeneinander arbeiten.
KOMPRESSOR_IST_SENSOR = "sensor.esphome_web_avarma_kompressor_frequenz_ist"
KOMPRESSOR_MAX_NUMBER = "number.esphome_web_avarma_kompressor_maximalfrequenz"
KOMPRESSOR_AM_DECKEL_TOLERANZ_HZ = 3.0
# Der Kompressor faellt beim Abtauen und bei der Oelrueckfuehrung kurz auf 0 Hz,
# ohne dass der Engpass vorbei waere. Erst wenn er laenger als das unter dem
# Deckel bleibt, gilt die Waerme als nicht mehr knapp - sonst gaebe jede
# Abtauung die Spender frei und zoege sie 15 Minuten spaeter wieder ein.
ERZEUGER_ENTSPANNT_MINUTES = 20

VALVE_THRESHOLD = 90.0
DEFICIT_THRESHOLD_C = 0.3
SUSTAIN_MINUTES = 15
DONOR_TARGET_VALVE = 30.0
STEP_C = 0.5
STEP_INTERVAL_MINUTES = 10
CHECK_INTERVAL_SECONDS = 120
NO_SENTINEL = -1.0


class HeizungLastverteilung(Hass):
    """Hydraulische Lastverteilung: verlagert Heizenergie von gut versorgten
    Raeumen (Spender) zu unterversorgten Prioritaets-Raeumen, wenn die
    Waermepumpen-Leistung nicht fuer alle gleichzeitig reicht.

    Steuert aktiv climate.set_temperature bei den Spender-Raeumen. Harte
    Untergrenzen (floor je Raum) werden nie unterschritten. Laeuft nur,
    waehrend die Waermepumpe aktiv heizt.
    """

    def initialize(self):
        self.constraint_since = {}
        self.donor_last_step = {}
        # Raeume, fuer die die Erschoepfungs-Warnung bereits geloggt wurde.
        # Ohne das wiederholt sich die Meldung jeden Zyklus: Im Test vom
        # 22.08.2026 waren das drei Stunden lang alle zwei Minuten dieselbe
        # Zeile. Bewusst nur In-Memory wie constraint_since und
        # donor_last_step - nach einem Neustart kostet es hoechstens eine
        # zusaetzliche Logzeile.
        self.exhausted_logged = set()
        # Seit wann laeuft der Kompressor unter seinem Deckel? None = haengt am
        # Deckel oder noch nicht bestimmt.
        self.erzeuger_entspannt_seit = None
        # Der Nachlauf ERZEUGER_ENTSPANNT_MINUTES ueberbrueckt kurze Einbrueche
        # (Abtauung, Oelrueckfuehrung) WAEHREND eines laufenden Engpasses. Beim
        # Start gibt es keinen laufenden Engpass, den man ueberbruecken muesste -
        # dann zaehlt der Messwert sofort.
        #
        # Ohne die Unterscheidung laufen die beiden Timer gegeneinander: Am
        # 24.08.2026 um 13:04 waeren SUSTAIN_MINUTES (15) vor
        # ERZEUGER_ENTSPANNT_MINUTES (20) abgelaufen - die App haette um 13:19
        # gedrosselt und um 13:24 wieder freigegeben.
        self.erzeuger_je_am_deckel = False
        self.listen_state(self.on_modus_wechsel, UEBERGANG_SWITCH)
        self.run_in(self.check, 3)
        self.run_every(
            self.check,
            self.datetime() + timedelta(seconds=CHECK_INTERVAL_SECONDS),
            CHECK_INTERVAL_SECONDS,
        )
        self.log("Heizung-Lastverteilung gestartet", level="INFO")

    def uebergangsmodus(self):
        return self.get_state(UEBERGANG_SWITCH) == "on"

    def priority_rooms(self):
        return UEBERGANG_PRIORITY if self.uebergangsmodus() else PRIORITY_ROOMS

    def donors(self):
        return UEBERGANG_DONORS if self.uebergangsmodus() else DONORS

    def on_modus_wechsel(self, entity, attribute, old, new, **kwargs):
        """Beim Umschalten die Spender des alten Modus sofort freigeben.

        Ohne das blieben sie bis zum naechsten Ende des Engpasses gedrosselt - und
        das kann in der Uebergangszeit Stunden dauern oder ganz ausbleiben.
        """
        if new == old:
            return
        aktiv = {d["key"] for d in self.donors()}
        for donor in ALLE_DONORS:
            if donor["key"] in aktiv:
                continue
            backup = self.safe_float(donor["backup_helper"])
            if backup is None or backup <= NO_SENTINEL + 0.01:
                continue
            self.call_service(
                "climate/set_temperature", entity_id=donor["climate"], temperature=backup
            )
            self.call_service(
                "input_number/set_value", entity_id=donor["backup_helper"], value=NO_SENTINEL
            )
            self.donor_last_step.pop(donor["key"], None)
            self.log(
                f"Lastverteilung: {donor['key']} zurueckgesetzt auf {backup}°C "
                f"(Moduswechsel, jetzt kein Spender mehr)",
                level="INFO",
            )
        modus = "Uebergang - einziger Spender ist das Wohnzimmer" if new == "on" else "Winter"
        self.log(f"Lastverteilung: Modus gewechselt auf {modus}", level="INFO")

    def safe_float(self, entity_id, attribute=None, default=None):
        raw = self.get_state(entity_id, attribute=attribute) if attribute else self.get_state(entity_id)
        if raw in (None, "unavailable", "unknown"):
            return default
        try:
            return float(raw)
        except (ValueError, TypeError):
            return default

    def donor_valve(self, donor):
        """Hoechster Wert aller Ventil-Kreise dieses Spenders (z.B. Yoga hat 2)."""
        values = [self.safe_float(v) for v in donor["valves"]]
        values = [v for v in values if v is not None]
        return max(values) if values else None

    def waerme_ist_knapp(self):
        """True, solange der Kompressor an seinem Deckel haengt - nur dann ist
        Umverteilen sinnvoll (Begruendung oben bei ERZEUGER_ENTSPANNT_MINUTES).

        Faellt einer der beiden Sensoren aus, gilt bewusst "knapp": Dann verhaelt
        sich die App wie vor dem Gate, statt die Drosselung ohne Messwert
        aufzugeben.
        """
        ist = self.safe_float(KOMPRESSOR_IST_SENSOR)
        deckel = self.safe_float(KOMPRESSOR_MAX_NUMBER)
        if ist is None or deckel is None:
            self.erzeuger_entspannt_seit = None
            return True

        if ist >= deckel - KOMPRESSOR_AM_DECKEL_TOLERANZ_HZ:
            self.erzeuger_entspannt_seit = None
            self.erzeuger_je_am_deckel = True
            return True

        # Noch nie am Deckel gesehen: kein Engpass, den der Nachlauf ueberbruecken
        # muesste (siehe erzeuger_je_am_deckel in initialize).
        if not self.erzeuger_je_am_deckel:
            return False

        now = self.datetime()
        if self.erzeuger_entspannt_seit is None:
            self.erzeuger_entspannt_seit = now
            return True

        entspannt_min = (now - self.erzeuger_entspannt_seit).total_seconds() / 60
        return entspannt_min < ERZEUGER_ENTSPANNT_MINUTES

    def check(self, **kwargs):
        wp_on = self.get_state("switch.esphome_web_avarma_warmepumpe_ein_aus") == "on"

        if not wp_on:
            for key in self.constraint_since:
                self.constraint_since[key] = None
            self.restore_all_donors(reason="Waermepumpe aus")
            return

        # Erzeuger-Gate vor der Engpass-Erkennung: Hat die Waermepumpe Luft, gibt
        # es nichts umzuverteilen - unabhaengig davon, wie weit ein Vorrangraum
        # sein Ziel verfehlt.
        if not self.waerme_ist_knapp():
            for key in self.constraint_since:
                self.constraint_since[key] = None
            ist = self.safe_float(KOMPRESSOR_IST_SENSOR)
            deckel = self.safe_float(KOMPRESSOR_MAX_NUMBER)
            self.restore_all_donors(
                reason=f"Waermepumpe nicht am Limit (Kompressor {ist:.0f} Hz, "
                f"Deckel {deckel:.0f} Hz) - kein Verteilungsproblem"
            )
            return

        constraint_room = None
        for room in self.priority_rooms():
            valve = self.safe_float(room["valve"])
            current = self.safe_float(room["climate"], attribute="current_temperature")
            target = self.safe_float(room["climate"], attribute="temperature")
            if valve is None or current is None or target is None:
                continue

            deficit = target - current
            constrained_now = valve >= VALVE_THRESHOLD and deficit >= DEFICIT_THRESHOLD_C

            if not constrained_now:
                self.constraint_since[room["key"]] = None
                continue

            since = self.constraint_since.get(room["key"])
            if since is None:
                self.constraint_since[room["key"]] = self.datetime()
                continue

            elapsed_minutes = (self.datetime() - since).total_seconds() / 60
            if elapsed_minutes >= SUSTAIN_MINUTES:
                constraint_room = room
                break

        if constraint_room is not None:
            self.handle_constraint(constraint_room)
        else:
            self.restore_all_donors(reason="kein Engpass mehr")

    def handle_constraint(self, room):
        for donor in self.donors():
            target = self.safe_float(donor["climate"], attribute="temperature")
            if target is None:
                continue
            valve = self.donor_valve(donor)
            backup = self.safe_float(donor["backup_helper"])
            is_throttled = backup is not None and backup > NO_SENTINEL + 0.01

            at_floor = target <= donor["floor"] + 0.01
            valve_at_target = valve is not None and valve <= DONOR_TARGET_VALVE

            if at_floor or valve_at_target:
                # dieser Spender hat gegeben was er kann - naechsten in der Reihe pruefen
                continue

            if not is_throttled:
                self.call_service(
                    "input_number/set_value",
                    entity_id=donor["backup_helper"],
                    value=target,
                )
                self.log(
                    f"Lastverteilung: beginne Drosselung {donor['key']} "
                    f"(Original {target}°C) - Engpass bei {room['key']}",
                    level="WARNING",
                )

            last_step = self.donor_last_step.get(donor["key"])
            now = self.datetime()
            if last_step is not None and (now - last_step).total_seconds() < STEP_INTERVAL_MINUTES * 60:
                return  # Anti-Oszillation: dieser Spender ist noch im Cooldown

            new_target = max(donor["floor"], round(target - STEP_C, 1))
            if new_target != target:
                self.call_service(
                    "climate/set_temperature",
                    entity_id=donor["climate"],
                    temperature=new_target,
                )
                self.donor_last_step[donor["key"]] = now
                self.log(
                    f"Lastverteilung: {donor['key']} gedrosselt {target}->{new_target}°C "
                    f"(Ventil {valve}%, Ziel {DONOR_TARGET_VALVE}%)",
                    level="INFO",
                )
            # Es war wieder Reserve da - naechste Erschoepfung darf erneut melden.
            self.exhausted_logged.discard(room["key"])
            return  # nur einen Spender pro Zyklus anfassen

        # Nur beim Eintritt in den Zustand melden, nicht in jedem Zyklus.
        if room["key"] not in self.exhausted_logged:
            self.exhausted_logged.add(room["key"])
            self.log(
                f"Lastverteilung: kein Spender mehr verfuegbar fuer {room['key']} "
                "(alle an Untergrenze oder Zielventil erreicht) - "
                "weitere Meldungen unterdrueckt bis sich der Zustand aendert",
                level="WARNING",
            )

    def restore_all_donors(self, reason=""):
        # Entwarnung, damit im Log nicht nur der Eintritt in den
        # Erschoepfungszustand steht, sondern auch sein Ende.
        if self.exhausted_logged:
            self.log(
                f"Lastverteilung: Engpass beendet fuer "
                f"{', '.join(sorted(self.exhausted_logged))} ({reason})",
                level="INFO",
            )
            self.exhausted_logged.clear()

        for donor in ALLE_DONORS:
            backup = self.safe_float(donor["backup_helper"])
            if backup is not None and backup > NO_SENTINEL + 0.01:
                self.call_service(
                    "climate/set_temperature",
                    entity_id=donor["climate"],
                    temperature=backup,
                )
                self.call_service(
                    "input_number/set_value",
                    entity_id=donor["backup_helper"],
                    value=NO_SENTINEL,
                )
                self.log(
                    f"Lastverteilung: {donor['key']} zurueckgesetzt auf {backup}°C ({reason})",
                    level="INFO",
                )
                self.donor_last_step.pop(donor["key"], None)
