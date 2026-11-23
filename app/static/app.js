/* Elder Activity web app: the little that needs JavaScript (ADR 0025). Every page works without it.
 * - The account menu closes on Escape or a click elsewhere.
 * - The care overview reloads its list every data-refresh seconds while the page is visible,
 *   and announces the summary to screen readers when it changes (WCAG 4.1.3).
 * - The page with a phone's setup code asks every 5 seconds whether the phone has connected.
 */
(function () {
  'use strict';

  // ---- account menu (a <details> element in the header)
  var acct = document.querySelector('.acct');
  if (acct) {
    document.addEventListener('click', function (e) {
      if (acct.open && !acct.contains(e.target)) acct.open = false;
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && acct.open) { acct.open = false; acct.querySelector('summary').focus(); }
    });
  }

  // ---- adding a phone: say when it has connected
  var pairing = document.getElementById('pairing');
  if (pairing) {
    var state = document.getElementById('pairing-state');
    var words = {
      active: 'Connected. Data will appear on the day page within 15 minutes.',
      expired: 'The code has expired. Go back to Phones, remove this phone and add it again.',
      removed: 'This phone was removed.'
    };
    var poll = setInterval(function () {
      if (document.visibilityState !== 'visible') return;
      fetch(pairing.getAttribute('data-status'), { credentials: 'same-origin' }).then(function (r) {
        return r.ok ? r.json() : null;
      }).then(function (body) {
        if (!body || !words[body.status]) return;
        clearInterval(poll);
        state.textContent = words[body.status];
        state.className = 'banner ' + (body.status === 'active' ? 'green' : 'amber');
      }).catch(function () { /* try again next time */ });
    }, 5000);
  }

  // ---- care overview: refresh the list in place
  var box = document.getElementById('overview');
  if (!box) return;
  var seconds = parseInt(box.getAttribute('data-refresh'), 10) || 60;
  var live = document.getElementById('live');
  var summaryOf = function (root) {
    var el = root.querySelector('[data-summary]');
    return el ? el.getAttribute('data-summary') : '';
  };
  var timer = setInterval(function () {
    if (document.visibilityState !== 'visible') return;
    fetch(box.getAttribute('data-src'), { credentials: 'same-origin' }).then(function (r) {
      if (r.status === 401) { clearInterval(timer); return null; } // signed out elsewhere: stop
      return r.ok ? r.text() : null;
    }).then(function (html) {
      if (html === null || html === box.innerHTML) return;
      var before = summaryOf(box);
      box.innerHTML = html;
      var after = summaryOf(box);
      if (live && after && after !== before) live.textContent = 'Updated: ' + after;
    }).catch(function () { /* offline for a moment: try again next time */ });
  }, seconds * 1000);
})();
