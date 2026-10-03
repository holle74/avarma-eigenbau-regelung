/**
 * Betriebsmodus-Schalter fuer die Waermepumpe (02.10.2026).
 *
 * Segmentschalter mit gleitender Markierung in der Farbe des Modus, darunter
 * eine Erklaerung, was der Modus gerade tut, und eine Statuszeile der Avarma.
 * Modi, die die KI-Regelung abschalten (confirm: true), fragen vorher inline nach.
 *
 * Optionen:
 *   entity        (Pflicht) input_select mit den Modi, z.B. input_select.wp_betriebsmodus
 *   title         Ueberschrift, Standard "Betriebsmodus"
 *   status        Live-Werte im Kopf, alle optional:
 *                   { wp, vorlauf, vorlauf_soll, kompressor, aussen, betriebsart }
 *   modes         Ersetzt die eingebaute Modusliste (gleiche Felder wie MODI unten)
 *
 * Die Modusnamen muessen exakt den Optionen des input_select entsprechen.
 */

const MODI = [
  {
    name: "KI Modus",
    kurz: "KI",
    icon: "mdi:robot-outline",
    rgb: "255,159,67",
    animation: "ki-puls 2.4s ease-in-out infinite",
    text: "Die KI regelt Vorlauf, Kompressor und Lüfter – mit Wetterprognose und " +
      "Vorladen vor Frostnächten. Wird es knapp, geben Schlafzimmer, Keller, Flur " +
      "und Yoga Wärme ab.",
  },
  {
    name: "KI Übergangszeit",
    kurz: "Übergang",
    icon: "mdi:leaf",
    rgb: "46,213,115",
    animation: "blatt 3s ease-in-out infinite",
    text: "Die KI regelt sparsam: Sie schaltet ab, sobald das EG 21 °C erreicht, " +
      "startet nicht zwischen 22:00 und 08:30 Uhr und sperrt Takten. Nur das " +
      "Wohnzimmer gibt bei Engpass Wärme ab.",
  },
  {
    name: "Kühlen",
    kurz: "Kühlen",
    icon: "mdi:snowflake",
    rgb: "84,160,255",
    animation: "drehen 9s linear infinite",
    confirm: true,
    text: "Die Avarma kühlt, die KI hält still. Die Wassertemperatur stellst du an " +
      "der Avarma ein – es gibt keinen Taupunktschutz, also nicht zu kalt.",
  },
  {
    name: "Manuell",
    kurz: "Manuell",
    icon: "mdi:hand-back-right-outline",
    rgb: "164,176,190",
    animation: "winken 2.6s ease-in-out infinite",
    confirm: true,
    text: "Die Avarma regelt allein, wie früher. Lüfter auf Automatik, " +
      "Kompressor-Deckel 90 Hz – den Vorlauf stellst du selbst ein.",
  },
];

const STIL = `
  :host { display: block; }
  ha-card { padding: 14px 14px 12px; container-type: inline-size; overflow: hidden; }
  .kopf { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .kopf ha-icon { --mdc-icon-size: 22px; color: var(--secondary-text-color); }
  .titel { font-size: 16px; font-weight: 600; flex: 1; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
  .chip { font-size: 11px; padding: 3px 8px; border-radius: 10px;
          background: rgba(255,255,255,0.07); color: var(--secondary-text-color);
          white-space: nowrap; display: inline-flex; align-items: center; gap: 5px; }
  .punkt { width: 7px; height: 7px; border-radius: 50%; background: #747d8c; }
  .punkt.an { background: #2ed573; box-shadow: 0 0 6px #2ed573; }

  .schalter { position: relative; display: grid; grid-template-columns: repeat(4, 1fr);
              background: rgba(0,0,0,0.25); border-radius: 16px; padding: 4px;
              border: 1px solid rgba(255,255,255,0.06); }
  .marke { position: absolute; top: 4px; bottom: 4px; left: 4px;
           width: calc((100% - 8px) / 4); border-radius: 12px;
           transition: transform 0.45s cubic-bezier(.65,0,.35,1), background 0.45s, box-shadow 0.45s; }
  .seg { position: relative; z-index: 1; border: 0; background: none; cursor: pointer;
         color: var(--secondary-text-color); font: inherit; padding: 10px 4px 8px;
         display: flex; flex-direction: column; align-items: center; gap: 4px;
         border-radius: 12px; transition: color 0.3s; -webkit-tap-highlight-color: transparent; }
  .seg ha-icon { --mdc-icon-size: 24px; transition: transform 0.3s; }
  .seg:active ha-icon { transform: scale(0.88); }
  .seg .name { font-size: 12px; font-weight: 600; line-height: 1.1; text-align: center; }
  .seg.aktiv { color: #fff; }
  .seg.wartet { animation: warten 1s ease-in-out infinite; }

  .info { margin-top: 12px; padding: 12px; border-radius: 14px; position: relative;
          background: rgba(255,255,255,0.04); border-left: 3px solid var(--farbe, #888);
          transition: border-color 0.45s; min-height: 64px; }
  .info-kopf { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .info-kopf ha-icon { --mdc-icon-size: 20px; color: var(--farbe); }
  .info-name { font-weight: 600; color: var(--farbe); }
  .info-text { font-size: 13px; line-height: 1.45; color: var(--secondary-text-color); }
  .zeile { margin-top: 8px; font-size: 11px; color: var(--secondary-text-color); opacity: 0.8; }

  .frage { position: absolute; inset: 0; border-radius: 14px; padding: 12px;
           background: rgba(20,22,28,0.94); display: none; flex-direction: column;
           justify-content: center; gap: 10px; }
  .frage.offen { display: flex; animation: einblenden 0.2s ease-out; }
  .frage-text { font-size: 13px; line-height: 1.4; }
  .knoepfe { display: flex; gap: 8px; justify-content: flex-end; }
  .knoepfe button { border: 0; border-radius: 10px; padding: 7px 14px; font: inherit;
                    font-size: 13px; font-weight: 600; cursor: pointer; }
  .nein { background: rgba(255,255,255,0.1); color: var(--primary-text-color); }
  .ja { color: #fff; }

  @container (max-width: 330px) {
    .seg .name { font-size: 10px; }
    .seg ha-icon { --mdc-icon-size: 20px; }
    .chips { display: none; }
  }
  @keyframes ki-puls { 0%,100% { transform: scale(1); } 50% { transform: scale(1.14); } }
  @keyframes blatt { 0%,100% { transform: rotate(-10deg); } 50% { transform: rotate(10deg); } }
  @keyframes drehen { from { transform: rotate(0); } to { transform: rotate(360deg); } }
  @keyframes winken { 0%,60%,100% { transform: rotate(0); } 70% { transform: rotate(-14deg); } 85% { transform: rotate(10deg); } }
  @keyframes warten { 0%,100% { opacity: 1; } 50% { opacity: 0.45; } }
  @keyframes einblenden { from { opacity: 0; } to { opacity: 1; } }
`;

class WpModusCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("entity fehlt");
    this._config = config;
    this._modi = config.modes || MODI;
    this._ziel = null;
    this._frage = null;
    this._gebaut = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._gebaut) this._bauen();
    this._aktualisieren();
  }

  getCardSize() { return 4; }
  getGridOptions() { return { columns: 12, min_columns: 6 }; }

  _bauen() {
    const root = this.shadowRoot || this.attachShadow({ mode: "open" });
    const segs = this._modi.map((m, i) => `
      <button class="seg" data-i="${i}" title="${m.name}">
        <ha-icon icon="${m.icon}"></ha-icon>
        <span class="name">${m.kurz || m.name}</span>
      </button>`).join("");
    root.innerHTML = `
      <style>${STIL}</style>
      <ha-card>
        <div class="kopf">
          <ha-icon icon="mdi:heat-pump"></ha-icon>
          <div class="titel">${this._config.title || "Betriebsmodus"}</div>
          <div class="chips"></div>
        </div>
        <div class="schalter"><div class="marke"></div>${segs}</div>
        <div class="info">
          <div class="info-kopf"><ha-icon></ha-icon><span class="info-name"></span></div>
          <div class="info-text"></div>
          <div class="zeile"></div>
          <div class="frage">
            <div class="frage-text"></div>
            <div class="knoepfe">
              <button class="nein">Abbrechen</button>
              <button class="ja">Umschalten</button>
            </div>
          </div>
        </div>
      </ha-card>`;
    root.querySelectorAll(".seg").forEach((b) =>
      b.addEventListener("click", () => this._tippen(Number(b.dataset.i))));
    root.querySelector(".nein").addEventListener("click", () => this._frageZu());
    root.querySelector(".ja").addEventListener("click", () => {
      const i = this._frage;
      this._frageZu();
      if (i !== null) this._setzen(i);
    });
    this._gebaut = true;
  }

  _index() {
    const st = this._hass.states[this._config.entity];
    return st ? this._modi.findIndex((m) => m.name === st.state) : -1;
  }

  _tippen(i) {
    if (i === this._index()) return;
    const aktuell = this._modi[this._index()];
    // Nachfragen nur, wenn die KI dadurch abgeschaltet wird.
    if (this._modi[i].confirm && !(aktuell && aktuell.confirm)) {
      this._frageAuf(i);
    } else {
      this._setzen(i);
    }
  }

  _frageAuf(i) {
    const m = this._modi[i];
    const root = this.shadowRoot;
    this._frage = i;
    root.querySelector(".frage-text").textContent =
      `KI-Regelung ausschalten und auf „${m.name}“ wechseln? ${m.text}`;
    const ja = root.querySelector(".ja");
    ja.style.background = `rgb(${m.rgb})`;
    root.querySelector(".frage").classList.add("offen");
    clearTimeout(this._frageTimer);
    this._frageTimer = setTimeout(() => this._frageZu(), 12000);
  }

  _frageZu() {
    this._frage = null;
    clearTimeout(this._frageTimer);
    this.shadowRoot.querySelector(".frage").classList.remove("offen");
  }

  _setzen(i) {
    this._ziel = i;
    clearTimeout(this._zielTimer);
    this._zielTimer = setTimeout(() => { this._ziel = null; this._aktualisieren(); }, 10000);
    this._hass.callService("input_select", "select_option", {
      entity_id: this._config.entity,
      option: this._modi[i].name,
    });
    this._aktualisieren();
  }

  _wert(id, nachkomma = 0, einheit = "") {
    const st = id && this._hass.states[id];
    if (!st || isNaN(parseFloat(st.state))) return null;
    return parseFloat(st.state).toLocaleString("de-DE", {
      minimumFractionDigits: nachkomma, maximumFractionDigits: nachkomma,
    }) + einheit;
  }

  _aktualisieren() {
    if (!this._hass || !this._gebaut) return;
    const root = this.shadowRoot;
    const idx = this._index();
    if (this._ziel !== null && this._ziel === idx) this._ziel = null;
    const zeige = this._ziel !== null ? this._ziel : idx;
    const m = this._modi[zeige];

    const marke = root.querySelector(".marke");
    root.querySelectorAll(".seg").forEach((b, i) => {
      const aktiv = i === zeige;
      b.classList.toggle("aktiv", aktiv);
      b.classList.toggle("wartet", aktiv && this._ziel !== null);
      b.querySelector("ha-icon").style.animation = aktiv && m ? m.animation : "none";
    });
    if (m) {
      marke.style.opacity = "1";
      marke.style.transform = `translateX(${zeige * 100}%)`;
      marke.style.background = `linear-gradient(135deg, rgba(${m.rgb},0.85), rgba(${m.rgb},0.45))`;
      marke.style.boxShadow = `0 2px 14px rgba(${m.rgb},0.45)`;
      root.querySelector(".info").style.setProperty("--farbe", `rgb(${m.rgb})`);
      root.querySelector(".info-kopf ha-icon").setAttribute("icon", m.icon);
      root.querySelector(".info-name").textContent =
        m.name + (this._ziel !== null ? " – wird umgeschaltet …" : "");
      root.querySelector(".info-text").textContent = m.text;
    } else {
      marke.style.opacity = "0";
      root.querySelector(".info-name").textContent = "Unbekannter Modus";
      root.querySelector(".info-text").textContent =
        `${this._config.entity} ist nicht verfügbar oder hat einen unbekannten Wert.`;
    }

    // Kopf-Chips und Statuszeile
    const s = this._config.status || {};
    const chips = [];
    const wp = s.wp && this._hass.states[s.wp];
    if (wp) {
      chips.push(`<span class="chip"><span class="punkt ${wp.state === "on" ? "an" : ""}"></span>WP ${wp.state === "on" ? "an" : "aus"}</span>`);
    }
    const vl = this._wert(s.vorlauf, 1, "°");
    const vls = this._wert(s.vorlauf_soll, 0, "°");
    if (vl) chips.push(`<span class="chip">VL ${vl}${vls ? " → " + vls : ""}</span>`);
    const at = this._wert(s.aussen, 1, "°");
    if (at) chips.push(`<span class="chip">Außen ${at}</span>`);
    root.querySelector(".chips").innerHTML = chips.join("");

    const teile = [];
    const ba = s.betriebsart && this._hass.states[s.betriebsart];
    if (ba) teile.push(`Avarma: ${ba.state}`);
    const hz = this._wert(s.kompressor, 0, " Hz");
    if (hz) teile.push(`Kompressor ${hz}`);
    root.querySelector(".zeile").textContent = teile.join(" · ");
  }
}

customElements.define("wp-modus-card", WpModusCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "wp-modus-card",
  name: "WP Betriebsmodus",
  description: "Modus-Schalter KI / Übergangszeit / Kühlen / Manuell für die Wärmepumpe",
});
