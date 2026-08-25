// Regressionstest: das erste Bild muss auf /frame sofort erscheinen, unabhängig
// von der konfigurierten Anzeigedauer. Bug (siehe Git-Historie): das Skript
// wartete beim Laden auf den ersten setInterval-Tick, bevor showNext() lief –
// bei z. B. 100s Anzeigedauer blieb der Bildschirm entsprechend 100s schwarz.
//
// Extrahiert das <script>-Inline-JS direkt aus app/static/frame.html und führt
// es mit Fake-fetch/-DOM aus, damit der Test automatisch mit dem echten Code
// synchron bleibt (kein separat gepflegtes Duplikat).
//
// Aufruf: node tests/js/frame_first_image.test.js
'use strict';
var fs = require('fs');
var path = require('path');

var html = fs.readFileSync(path.join(__dirname, '..', '..', 'app', 'static', 'frame.html'), 'utf8');
var match = html.match(/<script>([\s\S]*)<\/script>/);
if (!match) {
  console.error('❌ Konnte <script>-Block nicht aus frame.html extrahieren');
  process.exit(1);
}
var frameScript = match[1];

var IMAGES = ['foto1.jpg', 'foto2.jpg', 'foto3.jpg'];
var SETTINGS = { interval: 100, shuffle: false }; // absichtlich > 100s, wie im gemeldeten Bug

global.fetch = function (url) {
  var body = url === '/api/images' ? { images: IMAGES } : SETTINGS;
  return Promise.resolve({ json: function () { return Promise.resolve(body); } });
};

var events = [];
global.document = {
  fullscreenElement: null,
  documentElement: {},
  addEventListener: function () {},
  getElementById: function () {
    return {
      classList: { add: function () {}, remove: function () {} },
      set src(v) { events.push({ t: Date.now(), img: v }); if (this.onload) this.onload(); },
      hidden: true,
      addEventListener: function () {},
    };
  },
};
Object.defineProperty(global, 'navigator', { value: {}, configurable: true });
global.location = { search: '' };
global.URLSearchParams = function () {
  return { has: function () { return false; }, get: function () { return null; } };
};
global.window = global;

var start = Date.now();

// eslint-disable-next-line no-eval
eval(frameScript);

var MAX_WAIT_MS = 500;
setTimeout(function () {
  if (!events.length) {
    console.error('❌ FEHLGESCHLAGEN: Kein Bild innerhalb von ' + MAX_WAIT_MS + 'ms angezeigt (Anzeigedauer war ' + SETTINGS.interval + 's)');
    process.exit(1);
  }
  var elapsed = events[0].t - start;
  console.log('✅ Erstes Bild nach ' + elapsed + 'ms angezeigt (' + events[0].img + '), Anzeigedauer war ' + SETTINGS.interval + 's');
  process.exit(0);
}, MAX_WAIT_MS);
