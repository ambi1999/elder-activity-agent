/* Elder Activity web app: the little that needs JavaScript (ADR 0025). Every page works without it.
 * - The account menu closes on Escape or a click elsewhere.
 * - The care overview reloads its list every data-refresh seconds while the page is visible,
 *   and announces the summary to screen readers when it changes (WCAG 4.1.3).
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
