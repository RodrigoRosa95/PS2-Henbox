// Gera central-compat.html a partir do central.html (24/10/2026): o WebView do Android 4.4 (tablet Xoom, Chromium 33)
// não tem async/await, fetch, variáveis CSS, grid nem Array.find. JS vira ES5 pelo Babel (com o regenerator e
// polyfills curtos), as var(--x) viram as cores, a grade vira flex. O central.py serve o compat quando ele existe.
// Uso: NODE_PATH=<pasta com @babel/core, @babel/preset-env e regenerator-runtime> node central_compat.js
const fs = require('fs'), path = require('path'), babel = require('@babel/core');
const aqui = __dirname;
let h = fs.readFileSync(path.join(aqui, 'central.html'), 'utf8');

// CSS: valores das variáveis no lugar de var(--x) e fallbacks para o Chromium 33
const vars = {};
h.replace(/--([\w-]+):([^;}]+)/g, (_, n, v) => { vars[n] = v.trim(); });
h = h.replace(/var\(--([\w-]+)\)/g, (_, n) => vars[n]);
h = h.replace('.grade{display:grid;', '.grade{display:flex;flex-wrap:wrap;display:grid;');
h = h.replace('</style>', '.grade>.jogo{width:150px;margin:0 10px 10px 0}@supports (display:grid){.grade>.jogo{width:auto;margin:0}}' +
  '.jogo img,.jogo .semcapa{height:214px}@supports (aspect-ratio:1){.jogo img,.jogo .semcapa{height:auto}}</style>');

const ini = h.indexOf('<script>'), fim = h.lastIndexOf('</script>');
const js = h.slice(ini + 8, fim);
const es5 = babel.transformSync(js, {
  presets: [['@babel/preset-env', {targets: {chrome: '30'}, modules: false}]],
  assumptions: {iterableIsArray: true},
  sourceType: 'script', compact: false,
}).code;
const regen = fs.readFileSync(require.resolve('regenerator-runtime/runtime.js'), 'utf8');
const polyfills = `
if (!Array.prototype.find) Array.prototype.find = function (f) { for (var i = 0; i < this.length; i++) if (f(this[i], i, this)) return this[i]; };
if (!String.prototype.startsWith) String.prototype.startsWith = function (s) { return this.indexOf(s) === 0; };
if (!String.prototype.endsWith) String.prototype.endsWith = function (s) { return this.slice(-s.length) === s; };
if (window.NodeList && !NodeList.prototype.forEach) NodeList.prototype.forEach = Array.prototype.forEach;
if (window.Blob && !Blob.prototype.arrayBuffer) Blob.prototype.arrayBuffer = function () { var b = this;
  return new Promise(function (ok, erro) { var r = new FileReader(); r.onload = function () { ok(r.result); }; r.onerror = erro; r.readAsArrayBuffer(b); }); };
if (!Object.assign) Object.assign = function (a) { for (var i = 1; i < arguments.length; i++) for (var k in arguments[i]) a[k] = arguments[i][k]; return a; };
if (!window.fetch) window.fetch = function (url, op) { op = op || {};
  return new Promise(function (ok, erro) { var x = new XMLHttpRequest(); x.open(op.method || 'GET', url);
    var hs = op.headers || {}; for (var k in hs) x.setRequestHeader(k, hs[k]);
    x.onload = function () { ok({ok: x.status >= 200 && x.status < 300, status: x.status,
      json: function () { return new Promise(function (a, b) { try { a(JSON.parse(x.responseText)); } catch (e) { b(e); } }); },
      text: function () { return Promise.resolve(x.responseText); }}); };
    x.onerror = function () { erro(new TypeError('falha de rede')); }; x.send(op.body || null); }); };
`;
h = h.slice(0, ini) + '<script>' + polyfills + regen + '\n' + es5 + '\n</script>' + h.slice(fim + 9);
fs.writeFileSync(path.join(aqui, 'central-compat.html'), h);
console.log('central-compat.html', h.length, 'bytes');
