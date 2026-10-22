(function () {
  'use strict';
  function normalizeAddress(value) {
    const text = value.trim();
    if (!text || /\s|\\/.test(text)) return null;
    const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : 'http://' + text;
    // Check the original spelling before URL normalization accepts unusual IP forms.
    const match = /^(https?):\/\/(\d{1,3}(?:\.\d{1,3}){3})(?::([0-9]{1,5}))?\/?$/i.exec(withScheme);
    if (!match) return null;
    const pieces = match[2].split('.');
    if (pieces.some(p => !/^(0|[1-9][0-9]{0,2})$/.test(p) || Number(p) > 255)) return null;
    const [a, b] = pieces.map(Number);
    if (!(a === 10 || a === 192 && b === 168 || a === 172 && b >= 16 && b <= 31)) return null;
    const port = match[3] === undefined ? (match[1].toLowerCase() === 'http' ? 8501 : 443) : Number(match[3]);
    if (port < 1 || port > 65535) return null;
    return new URL(match[1].toLowerCase() + '://' + match[2] + ':' + port).origin;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {normalizeAddress};
  if (typeof document === 'undefined') return;
  const address = document.querySelector('#address');
  const button = document.querySelector('#connect');
  const message = document.querySelector('#message');
  try { address.value = (localStorage.getItem('rg_server') || '').replace(/^https?:\/\//, ''); } catch (_) {}
  if (new URLSearchParams(location.search).get('error') === 'connection') {
    message.textContent = 'Couldn’t connect. Check that the laptop app is running, both devices are on the same Wi-Fi, and Windows Firewall allows TCP port 8501 on the private network. Then try again.';
  }
  document.querySelector('#connection-form').addEventListener('submit', event => {
    event.preventDefault();
    const origin = normalizeAddress(address.value);
    if (!origin) {
      message.textContent = 'Enter the laptop’s private Wi-Fi address, such as 192.168.1.20:8501. Don’t use localhost: on your phone, that means the phone itself.';
      address.focus();
      return;
    }
    try { localStorage.setItem('rg_server', origin); } catch (_) {}
    button.disabled = true;
    button.textContent = 'Connecting…';
    message.textContent = 'Opening your laptop’s RiverGuard app…';
    // Top-level navigation keeps pairing cookies same-origin. Native error
    // handling returns to this screen if the laptop cannot be reached.
    location.assign(origin + '/');
  });
})();
