// Regressionstest: das erste Bild muss auf /frame sofort erscheinen, unabhängig
// von der konfigurierten Anzeigedauer. Bug (siehe Git-Historie): das Skript
// wartete beim Laden auf den ersten setInterval-Tick, bevor showNext() lief –
// bei z. B. 100s Anzeigedauer blieb der Bildschirm entsprechend 100s schwarz.
//
// Aufruf: node tests/js/frame_first_image.test.js
'use strict';
var dom = require('./fake_dom');

var IMAGES = ['foto1.jpg', 'foto2.jpg', 'foto3.jpg'];
var SETTINGS = { interval: 100, shuffle: false }; // absichtlich > 100s, wie im gemeldeten Bug

global.fetch = function (url) {
  var body = url === '/api/images' ? { images: IMAGES } : SETTINGS;
  return Promise.resolve({ json: function () { return Promise.resolve(body); } });
};

dom.installFakeBrowserGlobals();
var frameScript = dom.loadFrameScript();

var start = Date.now();
// eslint-disable-next-line no-eval
eval(frameScript);

var MAX_WAIT_MS = 500;
setTimeout(function () {
  var slideA = global.document.getElementById('slide-a');
  var slideB = global.document.getElementById('slide-b');
  var shown = slideA.children[0] || slideB.children[0];

  if (!shown) {
    console.error('❌ FEHLGESCHLAGEN: Kein Bild innerhalb von ' + MAX_WAIT_MS + 'ms angezeigt (Anzeigedauer war ' + SETTINGS.interval + 's)');
    process.exit(1);
  }
  console.log('✅ Erstes Bild nach < ' + MAX_WAIT_MS + 'ms angezeigt (' + shown.src + '), Anzeigedauer war ' + SETTINGS.interval + 's');
  process.exit(0);
}, MAX_WAIT_MS);
