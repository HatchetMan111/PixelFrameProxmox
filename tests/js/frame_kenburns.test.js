// Regressionstest für den Ken-Burns-Effekt: Bilder bekommen bei aktivierter
// Einstellung die CSS-Klasse 'kenburns' mit einer zur Anzeigedauer passenden
// animation-duration; bei deaktivierter Einstellung keine Klasse.
//
// Aufruf: node tests/js/frame_kenburns.test.js
'use strict';
var dom = require('./fake_dom');

var results = [];
function check(name, cond) { results.push({ name: name, ok: !!cond }); }

function run(kenburnsEnabled, interval) {
  return new Promise(function (resolve) {
    global.fetch = function (url) {
      var body = url === '/api/images'
        ? { images: ['foto.jpg'] }
        : { interval: interval, shuffle: false, kenburns: kenburnsEnabled };
      return Promise.resolve({ json: function () { return Promise.resolve(body); } });
    };
    dom.installFakeBrowserGlobals();
    eval(dom.loadFrameScript()); // eslint-disable-line no-eval

    setTimeout(function () {
      var slideA = global.document.getElementById('slide-a');
      var slideB = global.document.getElementById('slide-b');
      var img = slideA.children[0] || slideB.children[0];
      resolve(img);
    }, 200);
  });
}

run(true, 15)
  .then(function (img) {
    check('Ken Burns aktiviert -> Klasse gesetzt', img && img.className === 'kenburns');
    check('Ken Burns aktiviert -> animation-duration passt zur Anzeigedauer', img && img.style.animationDuration === '15s');
    check('Ken Burns aktiviert -> transformOrigin gesetzt', img && !!img.style.transformOrigin);
    return run(false, 8);
  })
  .then(function (img) {
    check('Ken Burns deaktiviert -> keine Klasse gesetzt', img && !img.className);
    check('Ken Burns deaktiviert -> keine animation-duration gesetzt', img && !img.style.animationDuration);
  })
  .then(function () {
    var failed = results.filter(function (r) { return !r.ok; });
    results.forEach(function (r) { console.log((r.ok ? '✅ ' : '❌ ') + r.name); });
    process.exit(failed.length ? 1 : 0);
  });
