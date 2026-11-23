/* Elder Activity: clickable prototype of the family and care web app (ADR 0025, ADR 0028).
 *
 * A small single-page app with made-up data. Every page has its own address
 * (#people, #person-margaret, #alert-a1 ...), so links, the browser's back
 * button and the bottom tabs all work as they will in the real app. Actions
 * change the data until the page is reloaded (or Reset is pressed).
 * {{product}}, {{company}} and {{logo_text}} come from the brand file.
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------ icons
  const I = {
    back: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    chev: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    people: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M2.5 20c.6-3.6 3.3-5.5 6.5-5.5s5.9 1.9 6.5 5.5M16 4.8a3.3 3.3 0 010 6.4M17.5 14.7c2.2.6 3.6 2.4 4 5.3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    bell: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 16V11a6 6 0 0112 0v5l2 2H4zM10 20a2 2 0 004 0" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
    gear: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    red: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2 19 18H1z" fill="currentColor"/><path d="M10 8v4M10 14.6v.4" stroke="var(--card)" stroke-width="2" stroke-linecap="round"/></svg>',
    amber: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="5" y="1.5" width="10" height="17" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M3 3l14 14" stroke="currentColor" stroke-width="2"/></svg>',
    green: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="9" fill="currentColor"/><path d="m6 10 3 3 5-6" fill="none" stroke="var(--card)" stroke-width="2" stroke-linecap="round"/></svg>'
  };
  const WORD = { red: 'Needs attention', amber: 'Phone not sending', green: 'All OK' };

  // ------------------------------------------------------------------ data
  function freshData() {
    const ppl = [
      ['margaret', 'Margaret T.', 1204, '58%', '1:05 pm', 'Australia/Brisbane'],
      ['joseph', 'Joseph K.', 880, '71%', '1:08 pm', 'Australia/Brisbane'],
      ['rosa', 'Rosa M.', 2310, '6%', '3:10 am', 'Australia/Brisbane'],
      ['ahmed', 'Ahmed S.', 3120, '82%', '1:10 pm', 'Australia/Brisbane'],
      ['lin', 'Lin W.', 2655, '64%', '1:02 pm', 'Australia/Brisbane'],
      ['peter', 'Peter O.', 1980, '49%', '12:58 pm', 'Australia/Brisbane'],
      ['grace', 'Grace H.', 4102, '90%', '1:11 pm', 'Australia/Brisbane'],
      ['tom', 'Tom B.', 1570, '37%', '12:49 pm', 'Australia/Brisbane'],
      ['helen', 'Helen D.', 2240, '75%', '12:40 pm', 'Australia/Brisbane'],
      ['samuel', 'Samuel N.', 990, '55%', '12:30 pm', 'Australia/Brisbane']
    ];
    const lastActive = { ahmed: 6, lin: 14, peter: 22, grace: 31, tom: 40, helen: 52, samuel: 60, margaret: 245, joseph: 300, rosa: 610 };
    const people = ppl.map(([id, name, steps, battery, sent, tz], k) => ({
      id, name, steps, battery, lastSent: sent, tz, household: 'Household ' + (k + 1),
      minutesSinceActive: lastActive[id],
      phones: [{ name: name.split(' ')[0] + "'s phone", status: 'Active', sent }],
      timing: { from: '08:00', to: '21:00', inactive: 4, silent: 6 },
      contacts: [
        { name: 'Nurse (you)', channel: 'Telegram', state: 'Linked' },
        { name: 'Daughter', channel: 'Email', state: 'Confirmed', address: 'daughter@example.com' }
      ],
      members: [{ name: 'You', role: 'viewer' }, { name: 'Daughter', role: 'owner' }],
      hours: hourly(k)
    }));
    people.push({
      id: 'mum', name: 'Mum', steps: 3412, battery: '64%', lastSent: '7:45 pm', tz: 'Australia/Brisbane', household: 'Family 1',
      minutesSinceActive: 18, phones: [{ name: "Mum's phone", status: 'Active', sent: '7:45 pm' }],
      timing: { from: '08:00', to: '21:00', inactive: 4, silent: 6 },
      contacts: [{ name: 'Daughter (you)', channel: 'Email', state: 'Confirmed', address: 'daughter@example.com' },
                 { name: 'Son', channel: 'Telegram', state: 'Linked' }],
      members: [{ name: 'You', role: 'owner' }, { name: 'Son', role: 'viewer' }], hours: hourly(3)
    });
    return {
      persona: 'nurse',
      people,
      alerts: [
        { id: 'a1', person: 'margaret', rule: 'inactivity', status: 'open', since: '9:05 am', opened: '1:05 pm', ackBy: null,
          text: "Margaret's phone is still sending data (battery 58%), but there have been no steps, screen use or walking since 9:05 am. On most days she is active by 9:30.", llm: true },
        { id: 'a2', person: 'joseph', rule: 'inactivity', status: 'acknowledged', since: '8:10 am', opened: '12:10 pm', ackBy: 'Sam',
          text: "Joseph's phone is still sending data (battery 71%), but there have been no steps, screen use or walking since 8:10 am.", llm: false },
        { id: 'a3', person: 'rosa', rule: 'phone_silent', status: 'open', since: '3:10 am', opened: '9:10 am', ackBy: null,
          text: "Rosa's phone hasn't sent any data since 3:10 am. It may be switched off, out of battery or without internet; this is about the phone, not necessarily about Rosa.", llm: false },
        { id: 'a0', person: 'tom', rule: 'inactivity', status: 'resolved', since: '7:50 am', opened: 'Yesterday 11:50 am', ackBy: 'Nurse',
          text: 'Resolved: activity resumed at 12:20 pm.', llm: false },
        { id: 'a5', person: 'mum', rule: 'inactivity', status: 'open', since: '2:15 pm', opened: '6:15 pm', ackBy: null,
          text: "Mum's phone is still sending data (battery 64%), but there have been no steps, screen use or walking since 2:15 pm. On most afternoons she walks to the shops by 4.", llm: true },
        { id: 'a6', person: 'mum', rule: 'phone_silent', status: 'resolved', since: 'Yesterday 1:30 am', opened: 'Yesterday 7:30 am', ackBy: 'Son',
          text: "Mum's phone hadn't sent data since 1:30 am. It was charging in another room. Resolved at 8:05 am.", llm: false }
      ],
      me: { nurse: { name: 'Nurse', email: 'nurse@example.com', initial: 'N', quiet: '' },
            daughter: { name: 'Daughter', email: 'daughter@example.com', initial: 'D', quiet: '22:00–07:00' } },
      invites: []
    };
  }
  function hourly(seed) {
    const out = []; let s = seed * 97 + 13;
    for (let h = 0; h < 24; h++) { s = (s * 1103515245 + 12345) % 2147483648; out.push(h >= 7 && h <= 20 ? 40 + (s % 380) : 0); }
    return out;
  }
  let D = freshData();

  // ------------------------------------------------------------------ helpers
  const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const person = (id) => D.people.find((p) => p.id === id);
  const visible = () => D.persona === 'nurse' ? D.people.filter((p) => p.id !== 'mum') : D.people.filter((p) => p.id === 'mum');
  const alertOf = (p) => D.alerts.find((a) => a.person === p.id && a.status !== 'resolved');
  function statusOf(p) {
    const a = alertOf(p);
    if (!a) return 'green';
    return a.rule === 'phone_silent' ? 'amber' : 'red';
  }
  function detailOf(p) {
    const a = alertOf(p);
    if (!a) return p.minutesSinceActive < 60 ? `Active ${p.minutesSinceActive} min ago` : `Active ${Math.round(p.minutesSinceActive / 60)} h ago`;
    if (a.rule === 'phone_silent') return `Phone silent since ${a.since}`;
    const who = a.status === 'acknowledged' ? ` · ${a.ackBy === me().name ? "You're" : a.ackBy + ' is'} checking` : '';
    return `No activity since ${a.since}${who}`;
  }
  const me = () => D.me[D.persona];
  const badge = (c, words) => `<span class="st ${c}">${I[c]}<span class="${words ? '' : 'sr-only'}">${WORD[c]}</span></span>`;
  const chartFor = (hours, small) => `<div class="bars${small ? ' small' : ''}" aria-hidden="true">${hours.map((v) => `<i style="height:${Math.max(2, v / 4.2)}%"></i>`).join('')}</div>`;
  const axis = '<div class="axis" aria-hidden="true"><span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>12am</span></div>';
  function textVersion(hours) {
    const active = hours.map((v, h) => [v, h]).filter(([v]) => v > 0);
    const rows = active.map(([v, h]) => `<tr><td>${h}:00</td><td>${v}</td></tr>`).join('');
    return `<details><summary>Show as a table</summary><table><thead><tr><th scope="col">Hour</th><th scope="col">Steps</th></tr></thead><tbody>${rows}</tbody></table></details>`;
  }
  let toastTimer;
  function toast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg; t.hidden = false; announce(msg);
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
  }
  function announce(msg) { document.getElementById('live').textContent = msg; }

  // ------------------------------------------------------------------ pages
  // Each route returns { title, up (parent route or null), tab, body }.
  const routes = [
    [/^signin$/, signIn], [/^check-email$/, checkEmail],
    [/^people$/, peoplePage],
    [/^person-([a-z]+)$/, today], [/^person-([a-z]+)-days$/, pastDays], [/^person-([a-z]+)-day-(\d)$/, oneDay],
    [/^person-([a-z]+)-phones$/, phones], [/^person-([a-z]+)-add-phone$/, addPhone],
    [/^person-([a-z]+)-alert-times$/, alertTimes], [/^person-([a-z]+)-contacts$/, contacts], [/^person-([a-z]+)-add-contact$/, addContact],
    [/^alerts$/, alertsPage], [/^alert-([a-z0-9]+)$/, alertPage], [/^alert-([a-z0-9]+)-message$/, alertMessage],
    [/^prefs$/, prefs], [/^profile$/, profile], [/^notifications$/, notifications], [/^my-people$/, myPeople],
    [/^add-person$/, addPerson], [/^members$/, members], [/^help$/, help], [/^about$/, about]
  ];

  function signIn() {
    return { title: 'Sign in', up: null, tab: null, bare: true, body: `
      <p>Enter your email and we'll send you a sign-in link. No password needed.</p>
      <form data-form="signin" novalidate>
        <div class="field"><label for="f-email">Email</label>
          <input id="f-email" type="email" autocomplete="email" value="${esc(me().email)}" required></div>
        <fieldset class="field" style="border:0;padding:0;margin:0 0 14px"><legend class="label" style="margin-bottom:6px">Prototype only: sign in as</legend>
          <div class="radios">
            <label><input type="radio" name="persona" value="nurse" ${D.persona === 'nurse' ? 'checked' : ''}> Nurse (10 people)</label>
            <label><input type="radio" name="persona" value="daughter" ${D.persona === 'daughter' ? 'checked' : ''}> Daughter (Mum)</label>
          </div></fieldset>
        <button class="btn" type="submit">Email me a sign-in link</button>
      </form>
      <p class="muted">Made by {{company}}.</p>` };
  }
  function checkEmail() {
    return { title: 'Check your email', up: 'signin', tab: null, bare: true, body: `
      <p>We sent a sign-in link to <b>${esc(me().email)}</b>. It works once, for 15 minutes.</p>
      <div class="card muted">Can't find it? Check your spam folder, or <a href="#signin">send another link</a>.</div>
      <a class="btn" href="#people">Open the link (prototype)</a>` };
  }

  function peoplePage() {
    const list = visible();
    if (list.length === 1) return today(list[0].id); // one person: straight to their day (ADR 0028)
    const groups = { red: [], amber: [], green: [] };
    list.forEach((p) => groups[statusOf(p)].push(p));
    const labels = { red: 'need attention', amber: 'phone not sending', green: 'all OK' };
    const chips = ['red', 'amber', 'green'].map((c) => `<span class="chip ${c}">${groups[c].length} ${labels[c]}</span>`).join('');
    const section = (c) => groups[c].length ? `<h2>${WORD[c]}</h2><div class="peoplegrid">${groups[c].map((p) => `
      <a class="item person ${c}" href="#person-${p.id}" style="display:flex;align-items:center;gap:12px;min-height:60px;padding:8px 14px;text-decoration:none;color:var(--text)">
        ${badge(c, false)}<span class="grow" style="flex:1;min-width:0"><b>${esc(p.name)}</b><small style="display:block;color:var(--muted);font-size:13px">${esc(detailOf(p))}</small></span>
        <span class="chev">${I.chev}</span></a>`).join('')}</div>` : '';
    return { title: `My people · ${list.length}`, up: null, tab: 'people', body: `
      <div class="chips" role="status" aria-label="Summary">${chips}</div>
      ${section('red')}${section('amber')}${section('green')}
      <p class="muted" style="font-size:13px">Updated just now · updates by itself</p>` };
  }

  function today(id) {
    const p = person(id); if (!p) return notFound();
    const c = statusOf(p), a = alertOf(p);
    const banner = a ? `<div class="banner ${c}"><b>${c === 'red' ? 'No activity for ' + p.timing.inactive + ' hours' : "Phone isn't sending"}</b>
        ${esc(detailOf(p))}. <a href="#alert-${a.id}">Open alert</a></div>`
      : `<div class="banner green"><b>All OK</b>Last active ${esc(detailOf(p).replace('Active ', ''))}.</div>`;
    const single = visible().length === 1;
    return { title: `${p.name} · Today`, up: single ? null : 'people', tab: 'people', body: `${banner}
      <div class="grid2"><div class="card"><div class="label">Steps today</div><div class="num">${p.steps.toLocaleString('en-AU')}</div></div>
        <div class="card"><div class="label">Phone battery</div><div class="num">${p.battery}</div></div></div>
      <div class="card"><b>Activity by hour</b>${chartFor(p.hours)}${axis}${textVersion(p.hours)}</div>
      <div class="list">
        <a class="item" href="#person-${p.id}-days"><span class="grow">Past days<small>The last 7 days, by hour</small></span><span class="chev">${I.chev}</span></a>
        <a class="item" href="#person-${p.id}-phones"><span class="grow">Phones<small>${p.phones.length} phone${p.phones.length === 1 ? '' : 's'} · last data ${esc(p.lastSent)}</small></span><span class="chev">${I.chev}</span></a>
        <a class="item" href="#person-${p.id}-contacts"><span class="grow">Who is told<small>${p.contacts.length} contacts</small></span><span class="chev">${I.chev}</span></a>
        <a class="item" href="#person-${p.id}-alert-times"><span class="grow">When to alert<small>Waking ${p.timing.from}–${p.timing.to} · after ${p.timing.inactive} h without activity</small></span><span class="chev">${I.chev}</span></a>
      </div>` };
  }
  const DAYS = ['Today', 'Sun 22 Nov', 'Sat 21 Nov', 'Fri 20 Nov', 'Thu 19 Nov', 'Wed 18 Nov', 'Tue 17 Nov'];
  function pastDays(id) {
    const p = person(id); if (!p) return notFound();
    return { title: `${p.name} · Past days`, up: `person-${id}`, tab: 'people', body: `<div class="list">${DAYS.map((d, k) => `
      <a class="item" href="#person-${id}-day-${k}"><span class="grow"><b>${d}</b><small>${(p.steps + k * 731) % 5200 + 600} steps${k === 0 && alertOf(p) ? ' · 1 alert' : ''}</small>
      ${chartFor(hourly(k + p.id.length), true)}</span><span class="chev">${I.chev}</span></a>`).join('')}</div>` };
  }
  function oneDay(id, k) {
    const p = person(id); if (!p) return notFound();
    const hours = hourly(Number(k) + p.id.length);
    return { title: `${p.name} · ${DAYS[k]}`, up: `person-${id}-days`, tab: 'people', body: `
      <div class="card"><b>Activity by hour</b>${chartFor(hours)}${axis}${textVersion(hours)}</div>
      <div class="card"><div class="row"><span>Steps</span><b>${hours.reduce((s, v) => s + v, 0).toLocaleString('en-AU')}</b></div>
      <div class="row"><span>First activity</span><b>7:00 am</b></div><div class="row"><span>Longest still period (waking hours)</span><b>1 h 40 min</b></div></div>` };
  }
  function phones(id) {
    const p = person(id); if (!p) return notFound();
    return { title: `${p.name} · Phones`, up: `person-${id}`, tab: 'people', body: `
      <div class="list">${p.phones.map((ph, k) => `<div class="item"><span class="grow"><b>${esc(ph.name)}</b><small>${esc(ph.status)}${ph.sent ? ' · last data ' + esc(ph.sent) : ''}</small></span>
        <button class="btn danger" style="width:auto;margin:0" data-action="revoke" data-person="${id}" data-k="${k}">Remove</button></div>`).join('') || '<div class="empty">No phone yet.</div>'}</div>
      <a class="btn" href="#person-${id}-add-phone">Add a phone</a>
      <p class="muted" style="font-size:13px">Removing a phone stops its access straight away. Its past data stays.</p>` };
  }
  let countdown;
  function addPhone(id) {
    const p = person(id); if (!p) return notFound();
    return { title: 'Add a phone', up: `person-${id}-phones`, tab: 'people', after: () => startCountdown(), body: `
      <ol style="padding-left:20px;margin-top:0"><li>On ${esc(p.name.split(' ')[0])}'s phone, open the logger app › Settings › Connection.</li>
      <li>Tap <b>Scan setup QR code</b> and point it at this code.</li><li>${esc(p.name.split(' ')[0])} agrees on their phone.</li></ol>
      <div class="qr" role="img" aria-label="Setup QR code (example)"></div>
      <div class="card"><b>This code works for <span id="cd">30:00</span></b> and is shown only once.
        <details><summary>Can't scan? Type these instead</summary><div class="mono">Endpoint: https://example.com/v1/readings<br>Token: XXXX-XXXX-XXXX</div></details></div>
      <p class="muted" role="status">Waiting for the phone… this page updates by itself.</p>
      <button class="btn secondary" data-action="phone-connects" data-person="${id}">Prototype: the phone connects</button>` };
  }
  function startCountdown() {
    clearInterval(countdown); let left = 30 * 60;
    countdown = setInterval(() => { const el = document.getElementById('cd'); if (!el) { clearInterval(countdown); return; }
      left -= 1; el.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`; }, 1000);
  }
  function alertTimes(id) {
    const p = person(id); if (!p) return notFound();
    const t = p.timing;
    return { title: 'When to alert', up: `person-${id}`, tab: 'people', body: `
      <form data-form="timing" data-person="${id}" novalidate>
        <div class="two"><div class="field"><label for="f-from">Waking from</label><input id="f-from" type="time" value="${t.from}"></div>
          <div class="field"><label for="f-to">Waking until</label><input id="f-to" type="time" value="${t.to}"></div></div>
        <div class="field"><label for="f-inactive">Alert after no activity for (hours)</label><input id="f-inactive" type="number" inputmode="numeric" min="1" max="12" value="${t.inactive}">
          <div class="hint">1 to 12 hours, during waking hours only.</div><div class="error" id="e-inactive" hidden></div></div>
        <div class="field"><label for="f-silent">Alert when the phone sends nothing for (hours)</label><input id="f-silent" type="number" inputmode="numeric" min="1" max="48" value="${t.silent}">
          <div class="hint">1 to 48 hours, at any time.</div><div class="error" id="e-silent" hidden></div></div>
        <button class="btn" type="submit">Save</button></form>` };
  }
  function contacts(id) {
    const p = person(id); if (!p) return notFound();
    return { title: 'Who is told', up: `person-${id}`, tab: 'people', body: `
      <p class="muted">These people get alerts about ${esc(p.name.split(' ')[0])}, by Telegram or email. Each confirms before anything is sent.</p>
      <div class="list">${p.contacts.map((c) => `<div class="item"><span class="grow"><b>${esc(c.name)}</b><small>${esc(c.channel)}${c.address ? ' · ' + esc(c.address) : ''}</small></span>
        <span class="chip ${c.state === 'Waiting for confirmation' ? 'amber' : 'green'}">${esc(c.state)}</span></div>`).join('')}</div>
      <a class="btn" href="#person-${id}-add-contact">Add a contact</a>` };
  }
  function addContact(id) {
    return { title: 'Add a contact', up: `person-${id}-contacts`, tab: 'people', body: `
      <form data-form="contact" data-person="${id}" novalidate>
        <div class="field"><label for="f-cname">Name</label><input id="f-cname" autocomplete="off" placeholder="For example: Son"><div class="error" id="e-cname" hidden></div></div>
        <fieldset class="field" style="border:0;padding:0;margin:0 0 14px"><legend style="font-weight:600;margin-bottom:6px">How should they be told?</legend>
          <div class="radios"><label><input type="radio" name="channel" value="Telegram" checked> Telegram</label>
          <label><input type="radio" name="channel" value="Email"> Email</label></div></fieldset>
        <div class="field"><label for="f-caddr">Email address (for email)</label><input id="f-caddr" type="email" autocomplete="off"><div class="error" id="e-caddr" hidden></div></div>
        <button class="btn" type="submit">Add contact</button></form>
      <p class="muted" style="font-size:13px">Telegram: they get a link to open and press Start. Email: they get a confirmation email.</p>` };
  }

  function alertsPage() {
    const mine = D.alerts.filter((a) => visible().some((p) => p.id === a.person));
    const open = mine.filter((a) => a.status !== 'resolved'), done = mine.filter((a) => a.status === 'resolved');
    const row = (a) => { const p = person(a.person); const c = a.status === 'resolved' ? 'green' : a.rule === 'phone_silent' ? 'amber' : 'red';
      return `<a class="item" href="#alert-${a.id}">${badge(c, false)}<span class="grow"><b>${esc(p.name)}: ${a.rule === 'phone_silent' ? 'phone not sending' : 'no activity'}</b>
        <small>${a.status === 'acknowledged' ? esc(a.ackBy === me().name ? 'You are' : a.ackBy + ' is') + ' checking · ' : ''}${a.status === 'resolved' ? 'Closed · ' : ''}opened ${esc(a.opened)}</small></span><span class="chev">${I.chev}</span></a>`; };
    return { title: 'Alerts', up: null, tab: 'alerts', body: `
      <h2>Open</h2>${open.length ? `<div class="list">${open.map(row).join('')}</div>` : '<div class="card empty">No open alerts. All looks normal.</div>'}
      <h2>Recent</h2>${done.length ? `<div class="list">${done.map(row).join('')}</div>` : '<div class="card empty">Nothing in the last 7 days.</div>'}` };
  }
  function alertPage(id) {
    const a = D.alerts.find((x) => x.id === id); if (!a) return notFound();
    const p = person(a.person); const c = a.status === 'resolved' ? 'green' : a.rule === 'phone_silent' ? 'amber' : 'red';
    const head = a.rule === 'phone_silent' ? `${p.name}'s phone has stopped sending` : `No activity for ${p.timing.inactive} hours: ${p.name}`;
    const state = a.status === 'open' ? 'Open: nobody has said they are checking yet.' : a.status === 'acknowledged'
      ? `${a.ackBy === me().name ? 'You are' : esc(a.ackBy) + ' is'} checking.` : 'Closed.';
    return { title: 'Alert', up: 'alerts', tab: 'alerts', body: `
      <div class="banner ${c}"><b>${esc(head)}</b>Since ${esc(a.since)} · ${state}</div>
      <div class="card">${esc(a.text)}${a.llm ? '<div class="label" style="margin-top:6px">Written by the agent from activity summaries.</div>' : ''}</div>
      ${a.status === 'open' ? `<button class="btn" data-action="ack" data-alert="${a.id}">I'm checking</button>` : ''}
      <div class="list"><a class="item" href="#person-${p.id}"><span class="grow">${esc(p.name)}'s day</span><span class="chev">${I.chev}</span></a>
        <a class="item" href="#alert-${a.id}-message"><span class="grow">How this alert was sent<small>Telegram and email</small></span><span class="chev">${I.chev}</span></a></div>
      <h2>What happened</h2><ul class="timeline"><li>${esc(a.opened)}: alert opened, sent to ${p.contacts.map((x) => esc(x.name)).join(', ')}</li>
        ${a.status !== 'open' ? `<li>${esc(a.ackBy === me().name ? 'You' : a.ackBy)} said they are checking</li>` : ''}${a.status === 'resolved' ? '<li>Activity resumed; alert closed</li>' : ''}</ul>` };
  }
  function alertMessage(id) {
    const a = D.alerts.find((x) => x.id === id); if (!a) return notFound(); const p = person(a.person);
    return { title: 'As sent by Telegram', up: `alert-${id}`, tab: 'alerts', body: `
      <div class="tg"><div class="bubble"><b>${a.rule === 'phone_silent' ? esc(p.name + "'s phone has stopped sending") : 'No activity for ' + p.timing.inactive + ' hours: ' + esc(p.name)}</b><br>${esc(a.text)}
        <div class="kb">I'm checking</div></div>
        ${a.status !== 'open' ? `<div class="bubble">${esc(a.ackBy === me().name ? me().name : a.ackBy)} is checking on ${esc(p.name)}.</div>` : ''}</div>
      <p class="muted" style="font-size:13px">Email has the same text, with an "I'm checking" link instead of the button.</p>` };
  }

  function prefs() {
    const many = D.persona === 'nurse';
    return { title: 'Settings', up: null, tab: 'prefs', body: `
      <h2>You</h2><div class="list">
        <a class="item" href="#profile"><span class="grow">Profile<small>${esc(me().name)} · ${esc(me().email)}</small></span><span class="chev">${I.chev}</span></a>
        <a class="item" href="#notifications"><span class="grow">My notifications<small>Quiet hours: ${esc(me().quiet || 'none')}</small></span><span class="chev">${I.chev}</span></a></div>
      <h2>${many ? 'People you look after' : 'Your household'}</h2><div class="list">
        <a class="item" href="#my-people"><span class="grow">${many ? 'People' : 'People in your household'}<small>${visible().length} ${visible().length === 1 ? 'person' : 'people'}</small></span><span class="chev">${I.chev}</span></a>
        <a class="item" href="#members"><span class="grow">Members<small>Who can see and manage</small></span><span class="chev">${I.chev}</span></a></div>
      <h2>App</h2><div class="list">
        <a class="item" href="#help"><span class="grow">Help</span><span class="chev">${I.chev}</span></a>
        <a class="item" href="#about"><span class="grow">About</span><span class="chev">${I.chev}</span></a></div>
      <button class="btn secondary" data-action="signout">Sign out</button>` };
  }
  function profile() {
    return { title: 'Profile', up: 'prefs', tab: 'prefs', body: `<form data-form="profile" novalidate>
      <div class="field"><label for="f-name">Your name, as others see it</label><input id="f-name" value="${esc(me().name)}" autocomplete="name"></div>
      <div class="field"><label for="f-pemail">Email</label><input id="f-pemail" value="${esc(me().email)}" readonly><div class="hint">You sign in with this address.</div></div>
      <button class="btn" type="submit">Save</button></form>` };
  }
  function notifications() {
    const q = me().quiet.split('–');
    return { title: 'My notifications', up: 'prefs', tab: 'prefs', body: `
      <div class="list"><div class="item"><span class="grow"><b>Telegram</b><small>Linked</small></span><span class="chip green">On</span></div>
        <div class="item"><span class="grow"><b>Email</b><small>${esc(me().email)}</small></span><span class="chip green">On</span></div></div>
      <form data-form="quiet" novalidate><h2>Quiet hours</h2><p class="muted" style="margin-top:0">No messages to you between these times. Alerts wait until they end.</p>
        <div class="two"><div class="field"><label for="f-qfrom">From</label><input id="f-qfrom" type="time" value="${q[0] || ''}"></div>
        <div class="field"><label for="f-qto">To</label><input id="f-qto" type="time" value="${q[1] || ''}"></div></div>
        <button class="btn" type="submit">Save</button></form>` };
  }
  function myPeople() {
    return { title: 'People', up: 'prefs', tab: 'prefs', body: `<div class="list">${visible().map((p) => `
      <a class="item" href="#person-${p.id}"><span class="grow"><b>${esc(p.name)}</b><small>${esc(p.household)} · ${esc(p.tz)}</small></span><span class="chev">${I.chev}</span></a>`).join('')}</div>
      <a class="btn" href="#add-person">Add a person</a>` };
  }
  function addPerson() {
    return { title: 'Add a person', up: 'my-people', tab: 'prefs', body: `<form data-form="person" novalidate>
      <div class="field"><label for="f-pname">Name or nickname</label><input id="f-pname" autocomplete="off" placeholder="For example: Dad"><div class="hint">Shown in messages. A nickname is enough.</div><div class="error" id="e-pname" hidden></div></div>
      <div class="field"><label for="f-tz">Their time zone</label><select id="f-tz"><option>Australia/Brisbane</option><option>Australia/Sydney</option><option>Australia/Perth</option><option>Pacific/Auckland</option></select></div>
      <button class="btn" type="submit">Add, then connect their phone</button></form>` };
  }
  function members() {
    const list = visible().length === 1 ? visible()[0].members : [{ name: 'You', role: 'viewer in 10 households' }, { name: 'Family members', role: 'owners of their household' }];
    return { title: 'Members', up: 'prefs', tab: 'prefs', body: `
      <div class="list">${list.concat(D.invites).map((m) => `<div class="item"><span class="grow"><b>${esc(m.name)}</b><small>${esc(m.role)}</small></span></div>`).join('')}</div>
      <form data-form="invite" novalidate><h2>Invite someone</h2>
        <div class="field"><label for="f-iemail">Their email</label><input id="f-iemail" type="email" autocomplete="off"><div class="error" id="e-iemail" hidden></div></div>
        <fieldset class="field" style="border:0;padding:0;margin:0 0 14px"><legend style="font-weight:600;margin-bottom:6px">They can</legend><div class="radios">
          <label><input type="radio" name="role" value="viewer" checked> See and acknowledge</label><label><input type="radio" name="role" value="owner"> Also change settings</label></div></fieldset>
        <button class="btn" type="submit">Send invitation</button></form>` };
  }
  function help() {
    return { title: 'Help', up: 'prefs', tab: 'prefs', body: `
      <div class="card">${badge('red', true)}<p style="margin:6px 0 0">The phone has shown no steps, screen use or walking for longer than usual during waking hours. Someone should check.</p></div>
      <div class="card">${badge('amber', true)}<p style="margin:6px 0 0">The phone has stopped sending data. It may be switched off, flat or offline. This is about the phone, not the person.</p></div>
      <div class="card">${badge('green', true)}<p style="margin:6px 0 0">Recent activity; nothing to do.</p></div>
      <p class="muted">This is a wellness aid, not a medical device or an emergency service. In an emergency, call 000.</p>` };
  }
  function about() {
    return { title: 'About', up: 'prefs', tab: 'prefs', body: `<div class="card"><div class="row"><span>App</span><b>{{product}}</b></div>
      <div class="row"><span>Version</span><b>Prototype</b></div><div class="row"><span>Made by</span><b>{{company}}</b></div></div>
      <div class="card">The phone shares activity only: steps, screen use and battery. Never location. Data is kept for 7 days.</div>` };
  }
  function notFound() {
    return { title: 'Not found', up: 'people', tab: null, body: '<div class="card empty">This page doesn\'t exist.</div><a class="btn" href="#people">Go to My people</a>' };
  }

  // ------------------------------------------------------------------ shell
  const TABS = [['people', 'People', I.people], ['alerts', 'Alerts', I.bell], ['prefs', 'Settings', I.gear]];
  let signedIn = false;

  function render() {
    const name = location.hash.replace(/^#/, '') || (signedIn ? 'people' : 'signin');
    // Opening any app page (a shared link, the back button) counts as signed in, as it would with a session.
    if (!['signin', 'check-email'].includes(name)) signedIn = true;
    let page = notFound(), args = [];
    for (const [re, fn] of routes) { const m = name.match(re); if (m) { args = m.slice(1); page = fn(...args); break; } }
    const openCount = D.alerts.filter((a) => a.status === 'open' && visible().some((p) => p.id === a.person)).length;
    const nav = TABS.map(([id, label, icon]) => ({ id, label, icon, current: page.tab === id }));
    const navLink = (t, cls) => `<a class="${cls}" href="#${t.id}"${t.current ? ' aria-current="page"' : ''}>${cls === 'nav' ? t.icon : `<span class="pill">${t.icon}</span>`}<span>${t.label}${t.id === 'alerts' && openCount ? ` <span class="sr-only">(${openCount} open)</span><b aria-hidden="true">· ${openCount}</b>` : ''}</span></a>`;
    const upBtn = page.up ? `<a class="iconbtn" href="#${page.up}" aria-label="Back">${I.back}</a>` : '<span class="spacer"></span>';
    const account = page.bare ? '' : `<button class="iconbtn" id="acct" aria-haspopup="true" aria-expanded="false" aria-controls="acctmenu" aria-label="Account: ${esc(me().name)}"><span class="avatar">${esc(me().initial)}</span></button>`;
    document.getElementById('app').innerHTML = `
      <nav class="side" aria-label="Main">${page.bare ? '' : `<a class="brand" href="#people">{{product}}</a>${nav.map((t) => navLink(t, 'nav')).join('')}`}</nav>
      <div class="main"><header class="top">${upBtn}<h1 tabindex="-1" id="pagetitle">${esc(page.title)}</h1>${account}</header>
        <div class="menu" id="acctmenu" hidden><div class="who"><b>${esc(me().name)}</b>${esc(me().email)}</div>
          <a href="#profile">Profile</a><a href="#notifications">My notifications</a><a href="#help">Help</a><a href="#about">About</a>
          <button data-action="signout">Sign out</button></div>
        <main class="content" id="main">${page.body}<div class="foot">{{logo_text}}</div></main>
        ${page.bare ? '' : `<nav class="tabs" aria-label="Main">${nav.map((t) => navLink(t, '')).join('')}</nav>`}</div>`;
    document.title = `${page.title} · {{product}}`;
    if (page.after) page.after();
    if (rendered) { const h = document.getElementById('pagetitle'); h && h.focus(); window.scrollTo(0, 0); }
    announce(page.title);
    document.getElementById('persona').value = D.persona;
    syncTour(name);
    rendered = true;
  }
  let rendered = false;

  function go(name) { if (location.hash === '#' + name) render(); else location.hash = name; }

  // ------------------------------------------------------------------ actions
  document.addEventListener('click', (e) => {
    const acct = e.target.closest('#acct'), menu = document.getElementById('acctmenu');
    if (acct) { const open = menu.hidden; menu.hidden = !open; acct.setAttribute('aria-expanded', String(open)); if (open) menu.querySelector('a').focus(); return; }
    if (menu && !menu.hidden && !e.target.closest('#acctmenu')) { menu.hidden = true; document.getElementById('acct').setAttribute('aria-expanded', 'false'); }
    const sim = document.querySelector('.simul'); if (sim && sim.open && !e.target.closest('.simul summary')) sim.open = false;
    const b = e.target.closest('[data-action]'); if (!b) return;
    const act = b.dataset.action;
    if (act === 'ack') { const a = D.alerts.find((x) => x.id === b.dataset.alert); a.status = 'acknowledged'; a.ackBy = me().name;
      render(); toast(`You're checking. The others have been told (${person(a.person).name}).`); }
    if (act === 'signout') { signedIn = false; go('signin'); toast('Signed out.'); }
    if (act === 'phone-connects') { const p = person(b.dataset.person); p.phones.push({ name: p.name.split(' ')[0] + "'s new phone", status: 'Active', sent: 'just now' });
      clearInterval(countdown); go(`person-${p.id}-phones`); toast('Phone connected.'); }
    if (act === 'revoke') { const p = person(b.dataset.person); const ph = p.phones[Number(b.dataset.k)];
      if (b.dataset.sure) { p.phones.splice(Number(b.dataset.k), 1); render(); toast(`${ph.name} removed.`); }
      else { b.dataset.sure = '1'; b.textContent = 'Tap again to remove'; } }
    if (act === 'sim-new') {
      const who = D.persona === 'nurse' ? 'peter' : 'mum';
      if (alertOf(person(who))) { toast(`${person(who).name} already has an open alert.`); return; }
      D.alerts.unshift({ id: 'a9' + D.alerts.length, person: who, rule: 'inactivity', status: 'open', since: '9:40 am', opened: 'just now', ackBy: null,
        text: 'The phone is still sending data, but there have been no steps, screen use or walking since 9:40 am.', llm: false });
      render(); toast(`Simulated: a new alert for ${person(who).name}.`); }
    if (act === 'sim-resolve-mine') {
      const open = D.alerts.find((a) => a.status !== 'resolved' && visible().some((p) => p.id === a.person));
      if (!open) { toast('There are no open alerts.'); return; }
      open.status = 'resolved'; person(open.person).minutesSinceActive = 1; render(); toast(`Simulated: ${person(open.person).name} is active again. Alert closed.`); }
    if (act === 'reset') { D = freshData(); signedIn = false; go('signin'); toast('Prototype reset.'); }
  });
  document.addEventListener('keydown', (e) => {
    const menu = document.getElementById('acctmenu');
    if (e.key === 'Escape' && menu && !menu.hidden) { menu.hidden = true; const a = document.getElementById('acct'); a.setAttribute('aria-expanded', 'false'); a.focus(); }
  });
  function showError(id, msg) { const el = document.getElementById(id); if (!el) return; el.textContent = msg; el.hidden = !msg; }
  document.addEventListener('submit', (e) => {
    const f = e.target; e.preventDefault();
    const val = (id) => (document.getElementById(id) || {}).value || '';
    switch (f.dataset.form) {
      case 'signin': D.persona = f.persona.value; signedIn = true; go('check-email'); break;
      case 'timing': {
        const p = person(f.dataset.person), ia = Number(val('f-inactive')), si = Number(val('f-silent'));
        const e1 = ia >= 1 && ia <= 12 ? '' : 'Enter a whole number from 1 to 12.', e2 = si >= 1 && si <= 48 ? '' : 'Enter a whole number from 1 to 48.';
        showError('e-inactive', e1); showError('e-silent', e2);
        if (e1 || e2) { document.getElementById(e1 ? 'f-inactive' : 'f-silent').focus(); return; }
        Object.assign(p.timing, { from: val('f-from'), to: val('f-to'), inactive: ia, silent: si }); go(`person-${p.id}`); toast('Alert times saved.'); break; }
      case 'contact': {
        const p = person(f.dataset.person), name = val('f-cname').trim(), ch = f.channel.value, addr = val('f-caddr').trim();
        showError('e-cname', name ? '' : 'Enter a name.'); const bad = ch === 'Email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(addr);
        showError('e-caddr', bad ? 'Enter an email address like name@example.com.' : '');
        if (!name || bad) return;
        p.contacts.push({ name, channel: ch, state: 'Waiting for confirmation', address: ch === 'Email' ? addr : '' }); go(`person-${p.id}-contacts`);
        toast(ch === 'Email' ? `Confirmation email sent to ${addr}.` : `Send ${name} the Telegram link (prototype).`); break; }
      case 'profile': me().name = val('f-name').trim() || me().name; go('prefs'); toast('Profile saved.'); break;
      case 'quiet': me().quiet = val('f-qfrom') && val('f-qto') ? `${val('f-qfrom')}–${val('f-qto')}` : ''; go('prefs'); toast('Quiet hours saved.'); break;
      case 'person': {
        const name = val('f-pname').trim(); showError('e-pname', name ? '' : 'Enter a name or nickname.'); if (!name) return;
        const id = name.toLowerCase().replace(/[^a-z]/g, '') || 'new';
        D.people.push({ id, name, steps: 0, battery: '–', lastSent: 'never', tz: val('f-tz'), household: 'New household', minutesSinceActive: 0,
          phones: [], timing: { from: '08:00', to: '21:00', inactive: 4, silent: 6 }, contacts: [{ name: me().name + ' (you)', channel: 'Telegram', state: 'Linked' }],
          members: [{ name: 'You', role: 'owner' }], hours: new Array(24).fill(0) });
        if (D.persona === 'daughter') { /* a family member adding a second person now sees the overview */ D.persona = 'nurse'; }
        go(`person-${id}-add-phone`); toast(`${name} added. Now connect their phone.`); break; }
      case 'invite': {
        const email = val('f-iemail').trim(); const bad = !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email);
        showError('e-iemail', bad ? 'Enter an email address like name@example.com.' : ''); if (bad) return;
        D.invites.push({ name: email, role: 'invited, ' + f.role.value }); render(); toast(`Invitation sent to ${email}.`); break; }
    }
  });

  // ------------------------------------------------------------------ guided tour
  const TOUR = [
    ['signin', 'Sign in with an email link: no password. Choose <b>Nurse</b> to see someone looking after ten people.'],
    ['check-email', 'The link works once, for 15 minutes.'],
    ['people', "<b>My people</b>: who needs attention is at the top, in red, with an icon and words as well as colour. Amber means the phone isn't sending."],
    ['person-margaret', "Margaret's day: the reason for the alert first, then activity by hour (with a table version for screen readers)."],
    ['alert-a1', 'The alert. The rules decided; the agent only explains. Press <b>I\'m checking</b> to tell everyone else.'],
    ['people', 'Back on My people (use the People tab or the browser\'s back button): Margaret now shows who is checking.'],
    ['alerts', 'The Alerts tab lists open and recent alerts.'],
    ['alert-a1-message', 'How the alert arrives in Telegram; email has the same words.'],
    ['person-margaret-days', 'Past days: changes in routine at a glance.'],
    ['person-margaret-add-phone', 'Adding a phone: the logger app scans this code, and the person agrees on their own phone.'],
    ['person-margaret-contacts', 'Who is told, by Telegram or email. Try <b>Add a contact</b>.'],
    ['prefs', 'Settings: your profile, quiet hours, people you look after, members, and Sign out at the bottom. The account button (top right) has the same shortcuts.'],
    ['signin', 'Now sign in as <b>Daughter</b> (or use <b>Signed in as</b> in the bar above): someone looking after one person goes straight to that person\'s day.'],
    ['person-mum', "Mum's day, with today's alert at the top. The family sees the same alert, explanation and 'I'm checking' as the nurse."],
    ['alert-a5', "Mum's alert. Press <b>I'm checking</b>; then use <b>Simulate…</b> to make her active again and see the alert close."]
  ];
  let tourAt = -1;
  function syncTour(name) {
    const box = document.getElementById('tour'); document.body.classList.toggle('touring', tourAt >= 0);
    if (tourAt < 0) { box.hidden = true; return; }
    box.hidden = false;
    document.getElementById('tourtext').innerHTML = `<b>${tourAt + 1} / ${TOUR.length}</b> · ${TOUR[tourAt][1]}`;
    document.getElementById('tprev').disabled = tourAt === 0; document.getElementById('tnext').disabled = tourAt === TOUR.length - 1;
  }
  function tourTo(k) {
    tourAt = Math.max(0, Math.min(TOUR.length - 1, k)); const r = TOUR[tourAt][0];
    if (r !== 'signin') signedIn = true;
    if (/mum|a5/.test(r)) D.persona = 'daughter'; else if (/margaret|a1/.test(r) || r === 'people') D.persona = 'nurse';
    go(r);
  }
  document.getElementById('tourbtn').onclick = () => { document.body.classList.remove('showproto'); if (tourAt < 0) tourTo(0); else { tourAt = -1; syncTour(); } };
  document.getElementById('tprev').onclick = () => tourTo(tourAt - 1);
  document.getElementById('tnext').onclick = () => tourTo(tourAt + 1);
  document.getElementById('frame').onchange = (e) => document.body.classList.toggle('framed', e.target.checked);
  // On phones the prototype controls open as a bottom sheet from the small "Prototype" button.
  const fab = document.getElementById('protofab');
  const sheet = (open) => { document.body.classList.toggle('showproto', open); fab.setAttribute('aria-expanded', String(open));
    if (open) document.getElementById('tourbtn').focus(); };
  fab.onclick = () => sheet(!document.body.classList.contains('showproto'));
  document.getElementById('closeproto').onclick = () => { sheet(false); fab.focus(); };
  document.getElementById('persona').onchange = (e) => { D.persona = e.target.value; signedIn = true; go('people');
    toast(`Signed in as ${me().name}.`); };

  window.addEventListener('hashchange', render);
  render();
})();
