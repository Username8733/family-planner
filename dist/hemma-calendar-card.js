
/* Local Home Assistant adapter. Shares temperature states, never credentials. */
class HemmaCalendarCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:'open'});
    this.onMessage = event => {
      if (event.origin === location.origin && event.source === this.frame?.contentWindow &&
          event.data?.type === 'hemma-temperature-ready-v1') this.sendTemperatures();
    };
  }
  setConfig(config) {
    const url = new URL(config.url || '/local/familjekalender/index.html', location.origin);
    if (url.origin !== location.origin) throw new Error("Family Planner must use the same origin as HA, for example /local/familjekalender/index.html.");
    this.config = {...config, url:url.href};
    if (!this.frame) {
      const style = document.createElement('style');
      style.textContent = ':host{display:block}iframe{display:block;width:100%;height:calc(100dvh - 112px);min-height:610px;border:0;border-radius:12px}';
      this.frame = document.createElement('iframe');
      this.frame.title = "Family Planner";
      this.frame.allow = 'fullscreen';
      this.frame.addEventListener('load', () => this.sendTemperatures());
      this.shadowRoot.append(style,this.frame);
    }
    this.frame.src = url.href;
    if (Number.isFinite(config.height) && config.height >= 610) this.frame.style.height = config.height+'px';
  }
  set hass(value) { this._hass = value; this.sendTemperatures(); }
  sendTemperatures() {
    if (!this.frame?.contentWindow || !this._hass) return;
    const sensors = Object.values(this._hass.states || {}).filter(entity =>
      entity.entity_id.startsWith('sensor.') &&
      entity.attributes?.device_class === 'temperature' &&
      ['°C','°F'].includes(entity.attributes.unit_of_measurement) &&
      (!Array.isArray(this.config?.temperature_entities) || this.config.temperature_entities.includes(entity.entity_id))
    ).map(entity => ({
      id:entity.entity_id,
      name:entity.attributes.friendly_name || entity.entity_id,
      state:entity.state,
      unit:entity.attributes.unit_of_measurement,
      updated:entity.last_updated
    }));
    this.frame.contentWindow.postMessage({type:'hemma-temperature-states-v1',sensors},location.origin);
  }
  connectedCallback() { window.addEventListener('message',this.onMessage); }
  disconnectedCallback() { window.removeEventListener('message',this.onMessage); }
  getCardSize() { return 12; }
}
if (!customElements.get('hemma-calendar-card')) customElements.define('hemma-calendar-card',HemmaCalendarCard);
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === 'hemma-calendar-card')) window.customCards.push({
  type:'hemma-calendar-card',name:"Family Planner",description:"Family calendar with outdoor temperature sensors from Home Assistant"
});
