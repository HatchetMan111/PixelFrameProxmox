// Regressionstest: ein Video soll bis zum Ende spielen und DANN sofort zum
// nächsten Medium weiterschalten – unabhängig von der (hier absichtlich sehr
// langen) Anzeigedauer für Bilder. Das 'ended'-Event muss den Wechsel selbst
// auslösen, statt auf settings.interval zu warten.
//
// Aufruf: node tests/js/frame_video_advance.test.js
'use strict';
var dom = require('./fake_dom');

var IMAGES = ['clip.mp4', 'foto.jpg']; // Video zuerst, damit es sofort gezeigt wird
var SETTINGS = { interval: 100, shuffle: false }; // absichtlich lang – darf Video nicht ausbremsen

global.fetch = function (url) {
  var body = url === '/api/images' ? { images: IMAGES } : SETTINGS;
  return Promise.resolve({ json: function () { return Promise.resolve(body); } });
};

dom.installFakeBrowserGlobals();
var frameScript = dom.loadFrameScript();

// eslint-disable-next-line no-eval
eval(frameScript);

function getVideoElement() {
  var slideA = global.document.getElementById('slide-a');
  var slideB = global.document.getElementById('slide-b');
  return slideA.querySelector('video') || slideB.querySelector('video');
}

setTimeout(function () {
  var video = getVideoElement();
  if (!video) {
    console.error('❌ FEHLGESCHLAGEN: Kein <video>-Element nach dem Laden gefunden');
    process.exit(1);
  }
  console.log('✅ Video wird angezeigt:', video.src);

  // Video "endet" jetzt simulieren – der nächste Slide muss sofort kommen,
  // nicht erst nach 100s.
  video.dispatch('ended');

  setTimeout(function () {
    var slideA = global.document.getElementById('slide-a');
    var slideB = global.document.getElementById('slide-b');
    var img = slideA.children[0] && slideA.children[0].tagName === 'img' ? slideA.children[0]
      : (slideB.children[0] && slideB.children[0].tagName === 'img' ? slideB.children[0] : null);

    if (!img) {
      console.error('❌ FEHLGESCHLAGEN: Nach video "ended" wurde nicht sofort zum nächsten Bild gewechselt (Anzeigedauer war ' + SETTINGS.interval + 's)');
      process.exit(1);
    }
    console.log('✅ Nach Video-Ende sofort weitergeschaltet zu:', img.src);
    process.exit(0);
  }, 200);
}, 200);
