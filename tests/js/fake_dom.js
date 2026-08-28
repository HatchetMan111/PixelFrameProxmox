// Minimales Fake-DOM für die frame.html-Tests: unterstützt createElement,
// appendChild, classList, addEventListener/dispatch und src-Zuweisung mit
// Promise-Microtask-Timing (wie im echten Browser bei img/video).
'use strict';

function FakeElement(tag) {
  this.tagName = tag || 'div';
  this._src = '';
  this._listeners = {};
  this.children = [];
  this.hidden = false;
  this.style = {};
  this.classList = {
    add: function () {},
    remove: function () {},
  };
}
FakeElement.prototype.addEventListener = function (type, cb) {
  (this._listeners[type] = this._listeners[type] || []).push(cb);
};
FakeElement.prototype.removeEventListener = function () {};
FakeElement.prototype.dispatch = function (type) {
  (this._listeners[type] || []).slice().forEach(function (cb) { cb(); });
};
FakeElement.prototype.appendChild = function (child) { this.children.push(child); return child; };
FakeElement.prototype.removeAttribute = function () {};
FakeElement.prototype.load = function () {};
FakeElement.prototype.pause = function () {};
FakeElement.prototype.play = function () { return Promise.resolve(); };
FakeElement.prototype.querySelector = function (sel) {
  if (sel === 'video') {
    var hit = this.children.filter(function (c) { return c.tagName === 'video'; });
    return hit[0] || null;
  }
  return null;
};
Object.defineProperty(FakeElement.prototype, 'innerHTML', {
  set: function () { this.children = []; },
  get: function () { return ''; },
});
Object.defineProperty(FakeElement.prototype, 'src', {
  get: function () { return this._src; },
  set: function (v) {
    this._src = v;
    var self = this;
    // Asynchron wie im echten Browser (Microtask), damit Event-Reihenfolge realistisch bleibt.
    Promise.resolve().then(function () {
      if (self.tagName === 'img') {
        if (self.onload) self.onload();
        self.dispatch('load');
      } else if (self.tagName === 'video') {
        self.dispatch('loadeddata');
      }
    });
  },
});

function makeEventTarget() {
  var listeners = {};
  return {
    addEventListener: function (type, cb) { (listeners[type] = listeners[type] || []).push(cb); },
    removeEventListener: function () {},
    dispatch: function (type) { (listeners[type] || []).slice().forEach(function (cb) { cb(); }); },
  };
}

function installFakeBrowserGlobals(options) {
  options = options || {};
  var containers = {};
  var documentElement = options.documentElement || {};
  var docEvents = makeEventTarget();
  var winEvents = makeEventTarget();

  global.document = {
    fullscreenElement: null,
    documentElement: documentElement,
    addEventListener: docEvents.addEventListener,
    removeEventListener: docEvents.removeEventListener,
    dispatch: docEvents.dispatch,
    getElementById: function (id) {
      if (!containers[id]) containers[id] = new FakeElement('div');
      return containers[id];
    },
    createElement: function (tag) { return new FakeElement(tag); },
  };
  Object.defineProperty(global, 'navigator', { value: {}, configurable: true });
  global.location = { search: '' };
  global.URLSearchParams = function () {
    return { has: function () { return false; }, get: function () { return null; } };
  };
  global.innerWidth = options.innerWidth || 400;
  global.innerHeight = options.innerHeight || 800;
  global.addEventListener = winEvents.addEventListener;
  global.removeEventListener = winEvents.removeEventListener;
  global.dispatchWindowEvent = winEvents.dispatch;
  global.window = global;
}

function loadFrameScript() {
  var fs = require('fs');
  var path = require('path');
  var html = fs.readFileSync(path.join(__dirname, '..', '..', 'app', 'static', 'frame.html'), 'utf8');
  var match = html.match(/<script>([\s\S]*)<\/script>/);
  if (!match) throw new Error('Konnte <script>-Block nicht aus frame.html extrahieren');
  return match[1];
}

module.exports = { FakeElement: FakeElement, installFakeBrowserGlobals: installFakeBrowserGlobals, loadFrameScript: loadFrameScript };
