// Regressionstest für den Zeitplan (Nachtruhe) auf /frame:
// Während der konfigurierten Zeitspanne (z. B. 22:00–07:00, über Mitternacht
// hinweg) darf beim Laden KEIN Bild angezeigt werden (Screen bleibt schwarz);
// außerhalb der Zeitspanne muss die Diashow normal starten.
//
// Aufruf: node tests/js/frame_schedule.test.js
'use strict';
var dom = require('./fake_dom');

var IMAGES = ['foto1.jpg', 'foto2.jpg'];
var SETTINGS = {
  interval: 8, shuffle: false, kenburns: true,
  schedule_enabled: true, schedule_start: '22:00', schedule_end: '07:00',
};

function freshFetch() {
  global.fetch = function (url) {
    var body = url === '/api/images' ? { images: IMAGES } : SETTINGS;
    return Promise.resolve({ json: function () { return Promise.resolve(body); } });
  };
}

function slideChildren() {
  var a = global.document.getElementById('slide-a');
  var b = global.document.getElementById('slide-b');
  return a.children.length + b.children.length;
}

var results = [];
function check(name, cond) { results.push({ name: name, ok: !!cond }); }

function scenario(hours, minutes, label, expectBlank) {
  return new Promise(function (resolve) {
    var RealDate = global.Date;
    function FakeDate() { return new RealDate(2024, 0, 1, hours, minutes, 0); }
    FakeDate.prototype = RealDate.prototype;
    global.Date = FakeDate; // bleibt aktiv, bis refreshAll()'s Promise-Kette (async) fertig ist

    freshFetch();
    dom.installFakeBrowserGlobals();
    eval(dom.loadFrameScript()); // eslint-disable-line no-eval

    setTimeout(function () {
      global.Date = RealDate; // erst jetzt zurücksetzen
      var count = slideChildren();
      var isBlank = count === 0;
      check(label + ' (' + hours + ':' + String(minutes).padStart(2, '0') + ')', isBlank === expectBlank);
      resolve();
    }, 100);
  });
}

scenario(23, 30, 'Innerhalb Nachtruhe 22:00-07:00 -> Screen bleibt schwarz', true)
  .then(function () { return scenario(12, 0, 'Außerhalb Nachtruhe -> Diashow startet normal', false); })
  .then(function () {
    var failed = results.filter(function (r) { return !r.ok; });
    results.forEach(function (r) { console.log((r.ok ? '✅ ' : '❌ ') + r.name); });
    process.exit(failed.length ? 1 : 0);
  });
