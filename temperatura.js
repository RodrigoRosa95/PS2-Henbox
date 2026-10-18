// Temperatura do PS2 nas páginas (pedido do usuário 17/10/2026): preenche <span id="ps2temp"> com a última
// leitura de GET /api/ps2/temperatura (temperatura.py). O PS2 só mede com o navegador ou a loja nativa abertos,
// então a idade da leitura aparece junto; some se a última for de mais de 1 dia.
(function () {
  var el = document.getElementById('ps2temp');
  if (!el) return;
  function idade(s) {
    if (s < 60) return 'agora';
    if (s < 3600) return 'há ' + Math.round(s / 60) + ' min';
    return 'há ' + Math.round(s / 3600) + ' h';
  }
  function atualizar() {
    fetch('/api/ps2/temperatura').then(function (r) { return r.json(); }).then(function (t) {
      if (t.c == null || t.idade_s > 86400) { el.hidden = true; return; }
      var c = t.c.toFixed(1).replace('.', ',');
      el.hidden = false;
      el.textContent = '🌡 PS2 ' + c + ' °C · ' + idade(t.idade_s);
      el.style.color = t.idade_s > 120 ? '' : t.c >= 65 ? '#ff6b6b' : t.c >= 55 ? '#f2c94c' : '#56d364';
      el.style.opacity = t.idade_s > 120 ? '.7' : '1';
      el.title = 'Hoje: mín ' + String(t.min_hoje).replace('.', ',') + ' °C · máx ' + String(t.max_hoje).replace('.', ',') +
        ' °C\nLido pelo ' + (t.origem === 'navegador' ? 'navegador' : 'app da loja') + ' no PS2' +
        '\nAté 55 °C normal · 55–65 quente · acima de 65 muito quente';
    }).catch(function () { });
  }
  atualizar();
  setInterval(atualizar, 15000);
})();
