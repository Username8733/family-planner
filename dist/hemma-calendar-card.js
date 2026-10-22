
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
    if (this.targetURL !== url.href) this.ingressReady = false;
    this.targetURL = url.href;
    this.needsIngress = url.pathname.startsWith('/api/hassio_ingress/');
    if (!this.needsIngress) this.frame.src = url.href;
    else this.ensureIngress();
    if (Number.isFinite(config.height) && config.height >= 610) this.frame.style.height = config.height+'px';
  }
  set hass(value) { this._hass = value; this.ensureIngress(); this.sendTemperatures(); }
  async ensureIngress() {
    if (!this.needsIngress || !this._hass || this.ingressPending || this.ingressReady) return;
    this.ingressPending = true;
    try {
      const result = await this._hass.callWS({type:'supervisor/api', endpoint:'/ingress/session', method:'post'});
      document.cookie = 'ingress_session='+encodeURIComponent(result.session)+';path=/api/hassio_ingress/;SameSite=Strict'+(location.protocol==='https:'?';Secure':'');
      this.ingressSession = result.session;
      this.ingressReady = true;
      await this.completeGoogleCallback();
      this.frame.src = this.targetURL;
      this.status?.remove();
    } catch {
      this.ingressReady = false;
      if (!this.status) {
        this.status = document.createElement('button');
        this.status.textContent = 'Unable to open Family Planner. Tap to retry.';
        this.status.style.cssText = 'display:block;margin:16px;padding:16px;cursor:pointer';
        this.status.addEventListener('click', () => this.ensureIngress());
        this.shadowRoot.append(this.status);
      }
    } finally { this.ingressPending = false; }
  }
  async completeGoogleCallback() {
    const page = new URL(location.href);
    const state = page.searchParams.get('state');
    const code = page.searchParams.get('code');
    if (!state || !code) return;
    // Keep OAuth codes out of browser history and referrers.
    page.searchParams.delete('state'); page.searchParams.delete('code'); page.searchParams.delete('scope');
    history.replaceState(history.state, '', page);
    const callback = new URL('api/oauth/google/callback', new URL('.', this.targetURL));
    callback.search = new URLSearchParams({state,code}).toString();
    const response = await fetch(callback, {credentials:'same-origin',cache:'no-store',referrerPolicy:'no-referrer'});
    if (!response.ok) throw new Error('Google callback failed');
  }
  async keepIngressAlive() {
    if (!this.ingressReady || !this._hass) return this.ensureIngress();
    try {
      const current = document.cookie.split('; ').find(value => value.startsWith('ingress_session='));
      if (current) this.ingressSession = decodeURIComponent(current.slice('ingress_session='.length));
      await this._hass.callWS({type:'supervisor/api', endpoint:'/ingress/validate_session', method:'post', data:{session:this.ingressSession}});
    } catch {
      this.ingressReady = false;
      await this.ensureIngress();
    }
  }
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
  connectedCallback() { window.addEventListener('message',this.onMessage); this.ensureIngress(); this.ingressHeartbeat = setInterval(() => this.keepIngressAlive(), 5*60*1000); }
  disconnectedCallback() { window.removeEventListener('message',this.onMessage); clearInterval(this.ingressHeartbeat); }
  getCardSize() { return 12; }
}
if (!customElements.get('hemma-calendar-card')) customElements.define('hemma-calendar-card',HemmaCalendarCard);
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === 'hemma-calendar-card')) window.customCards.push({
  type:'hemma-calendar-card',name:"Family Planner",description:"Family calendar with outdoor temperature sensors from Home Assistant"
});
