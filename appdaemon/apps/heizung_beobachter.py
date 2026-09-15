from datetime import timedelta

from appdaemon.plugins.hass.hassapi import Hass


class HeizungBeobachter(Hass):
    """Reiner Beobachter fuer die geplante MPC-Heizungssteuerung.

    Schreibt noch keine Werte an die Waermepumpe - protokolliert nur den
    aktuellen Zustand in regelmaessigen Abstaenden, als Grundlage fuer
    Schritt 3 (Vorschlagslogik) des Heizungsprojekts.
    """

    def initialize(self):
        self.interval_seconds = self.args.get("interval_seconds", 300)
        self.log(
            f"Heizung-Beobachter gestartet, Intervall {self.interval_seconds}s",
            level="INFO",
        )
        self.run_in(self.log_status, 2)
        self.run_every(
            self.log_status,
            self.datetime() + timedelta(seconds=self.interval_seconds),
            self.interval_seconds,
        )

    def safe_float(self, entity_id, attribute=None, default=None):
        raw = self.get_state(entity_id, attribute=attribute) if attribute else self.get_state(entity_id)
        if raw in (None, "unavailable", "unknown"):
            return default
        try:
            return float(raw)
        except (ValueError, TypeError):
            return default

    # 1.0 ist eine UNTERGRENZE, kein Sollwert (2026-08-03): Ziel ist
    # minimale Luefterleistung, solange der Verdampfer >= 1 Grad bleibt. Ein
    # deutlich hoeherer Wert ist deshalb kein Fehler, sondern das gewuenschte
    # Ergebnis bei Minimaldrehzahl. Im Winter oft nicht haltbar.
    # Physik vom Betreiber bestaetigt (2026-07-23): mehr Drehzahl -> waermer.
    # Werte identisch zu heizung_vlt_kompressor_regelung.py - bei Aenderung
    # dort mitziehen, sonst widerspricht der Beobachter der echten Regelung.
    EVAPORATOR_MIN_C = 1.0
    EVAPORATOR_HYSTERESE_C = 0.5

    def evaporator_advice(self, verdampfertemp):
        if verdampfertemp is None:
            return "n/a (kein Messwert)"
        abstand = verdampfertemp - self.EVAPORATOR_MIN_C
        if verdampfertemp < self.EVAPORATOR_MIN_C:
            return (
                f"unter Untergrenze ({abstand:+.1f} degC) - Vereisungsrisiko, "
                "Luefterdrehzahl erhoehen wuerde Verdampfer erwaermen"
            )
        if verdampfertemp > self.EVAPORATOR_MIN_C + self.EVAPORATOR_HYSTERESE_C:
            return (
                f"Reserve vorhanden ({abstand:+.1f} degC ueber Untergrenze) - "
                "Luefterdrehzahl kann gesenkt werden (leiser, sparsamer)"
            )
        return f"knapp ueber Untergrenze ({abstand:+.1f} degC) - Drehzahl halten"

    def log_status(self, **kwargs):
        raumtemp_mittelwert = self.safe_float("sensor.raumtemperatur_mittelwert")
        bad_ist = self.safe_float(
            "climate.raumtemperaturregler_bad_unten_bad", attribute="current_temperature"
        )
        bad_soll = self.safe_float(
            "climate.raumtemperaturregler_bad_unten_bad", attribute="temperature"
        )
        aussentemp = self.safe_float("sensor.aussentemperatur_avarma_korrigiert")
        prognose_min_24h = self.safe_float(
            "input_number.wp_prognose_aussentemperatur_minimum_24h"
        )
        verdampfertemp = self.safe_float("sensor.esphome_web_avarma_verdampfertemperatur")
        vorlauftemp = self.safe_float("sensor.esphome_web_avarma_vorlauftemperatur")
        kompressor_hz = self.safe_float("sensor.esphome_web_avarma_kompressor_frequenz_ist")
        luefter_drehzahl = self.safe_float("sensor.esphome_web_avarma_lufter_1_drehzahl")
        wp_status = self.get_state("switch.esphome_web_avarma_warmepumpe_ein_aus")

        self.log(
            "Status | WP: {wp} | Verdampfer: {verd} degC (min 1.0) | Vorlauf: {vl} degC | "
            "Kompressor: {komp} Hz | Aussentemp: {aussen} degC | Prognose-Min 24h: {prog} degC | "
            "Bad: {bad_ist}/{bad_soll} degC | Raum-Mittelwert: {mittel} degC".format(
                wp=wp_status,
                verd=verdampfertemp,
                vl=vorlauftemp,
                komp=kompressor_hz,
                aussen=aussentemp,
                prog=prognose_min_24h,
                bad_ist=bad_ist,
                bad_soll=bad_soll,
                mittel=raumtemp_mittelwert,
            ),
            level="INFO",
        )

        if wp_status == "on":
            advice = self.evaporator_advice(verdampfertemp)
            self.log(
                f"Verdampfer-Regelvorschlag | aktuelle Luefterdrehzahl: "
                f"{luefter_drehzahl} rpm | Bewertung: {advice}",
                level="INFO",
            )
