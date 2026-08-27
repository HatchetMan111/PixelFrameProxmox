// Regressionstest für die Vollbild-Logik auf /frame:
//  1) Kein Fullscreen-API-Support (z. B. iOS Safari ohne requestFullscreen)
//     -> Button muss sofort ausgeblendet sein, statt nutzlos angezeigt zu werden.
//  2) API vorhanden, Klick gelingt -> Button verschwindet (fullscreenchange).
//  3) API vorhanden, Klick schlägt fehl (Promise rejected) -> Button wird
//     dauerhaft ausgeblendet statt weiter als kaputter Button dazustehen.
//
// Aufruf: node tests/js/frame_fullscreen.test.js
'use strict';
var dom = require('./fake_dom');

var results = [];
function check(name, cond) {
  results.push({ name: name, ok: !!cond });
}

function freshFetch() {
  global.fetch = function (url) {
    var body = url === '/api/images' ? { images: [] } : { interval: 8, shuffle: false };
    return Promise.resolve({ json: function () { return Promise.resolve(body); } });
  };
}

function run() {
  // --- Szenario 1: keine Fullscreen-API in irgendeiner Form ---
  freshFetch();
  dom.installFakeBrowserGlobals({ documentElement: {} }); // kein requestFullscreen-Feld
  eval(dom.loadFrameScript()); // eslint-disable-line no-eval
  var fsBtn1 = global.document.getElementById('fs-btn');
  check('Kein API-Support -> Button sofort ausgeblendet', fsBtn1.hidden === true);

  // --- Szenario 2: API vorhanden, Klick gelingt ---
  freshFetch();
  var docEl2 = {
    requestFullscreen: function () {
      global.document.fullscreenElement = docEl2;
      global.document.dispatch('fullscreenchange');
      return Promise.resolve();
    },
  };
  dom.installFakeBrowserGlobals({ documentElement: docEl2 });
  eval(dom.loadFrameScript()); // eslint-disable-line no-eval
  var fsBtn2 = global.document.getElementById('fs-btn');
  check('API vorhanden -> Button zunächst sichtbar', fsBtn2.hidden === false);
  fsBtn2.dispatch('click');

  return new Promise(function (resolve) {
    setTimeout(function () {
      check('Klick erfolgreich -> Button danach ausgeblendet', fsBtn2.hidden === true);

      // --- Szenario 3: API vorhanden, Klick schlägt fehl ---
      freshFetch();
      var docEl3 = { requestFullscreen: function () { return Promise.reject(new Error('policy')); } };
      dom.installFakeBrowserGlobals({ documentElement: docEl3 });
      eval(dom.loadFrameScript()); // eslint-disable-line no-eval
      var fsBtn3 = global.document.getElementById('fs-btn');
      fsBtn3.dispatch('click');

      setTimeout(function () {
        check('Klick schlägt fehl -> Button dauerhaft ausgeblendet', fsBtn3.hidden === true);
        resolve();
      }, 100);
    }, 100);
  });
}

run().then(function () {
  var failed = results.filter(function (r) { return !r.ok; });
  results.forEach(function (r) { console.log((r.ok ? '✅ ' : '❌ ') + r.name); });
  process.exit(failed.length ? 1 : 0);
});
