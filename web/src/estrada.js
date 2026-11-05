// Estrada decorativa em perspectiva, desenhada em SVG (abertura e fim).
// Substitui a pista em CSS 3D, que alguns navegadores de celular só pintavam
// depois de rolar. A faixa central anda só enquanto a estrada está na tela.
const NS = "http://www.w3.org/2000/svg";

export function criarEstrada(el) {
  const reduz = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "estrada-svg");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = `
    <defs>
      <linearGradient id="${el.id || "e"}-asf" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#121316"/><stop offset="1" stop-color="#1e1f24"/>
      </linearGradient>
    </defs>
    <path class="asfalto" fill="url(#${el.id || "e"}-asf)"/>
    <path class="bordas" fill="#e8e6df"/>
    <path class="faixas" fill="#f2b33d"/>`;
  el.appendChild(svg);
  const [asfalto, bordas, faixas] = ["asfalto", "bordas", "faixas"].map((c) => svg.querySelector("." + c));

  let w = 0, h = 0, fase = 0, rodando = false, visivel = false, ultimo = 0;
  const Z0 = 1, ZMAX = 40, PERIODO = 2.2, TRACO = 0.9;

  // Projeção: profundidade z vira altura y; z0 fica na borda de baixo.
  // Em tela larga a largura segue a altura, para a pista não ocupar a tela toda;
  // o horizonte fica um pouco abaixo do topo, longe do texto.
  const proj = (X, z) => {
    const escala = Math.min(w * 0.42, h * 1.3), h0 = h * 0.16;
    return [w / 2 + (X * escala) / z, h0 + ((h - h0) * Z0) / z];
  };
  const quad = (x0, x1, za, zb) => {
    const a = proj(x0, za), b = proj(x1, za), c = proj(x1, zb), d = proj(x0, zb);
    return `M${a[0].toFixed(1)},${a[1].toFixed(1)}L${b[0].toFixed(1)},${b[1].toFixed(1)}L${c[0].toFixed(1)},${c[1].toFixed(1)}L${d[0].toFixed(1)},${d[1].toFixed(1)}Z`;
  };

  function desenharFaixas() {
    let d = "";
    for (let z = Z0 - PERIODO + (fase % PERIODO); z < ZMAX; z += PERIODO) {
      const za = Math.max(0.35, z), zb = z + TRACO;
      if (zb <= 0.35) continue;
      d += quad(-0.012, 0.012, za, zb);
    }
    faixas.setAttribute("d", d);
  }

  function medir() {
    w = el.clientWidth; h = el.clientHeight;
    if (!w || !h) return;
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    asfalto.setAttribute("d", quad(-1.2, 1.2, 0.35, ZMAX));
    bordas.setAttribute("d", quad(-1.06, -1.03, 0.35, ZMAX) + quad(1.03, 1.06, 0.35, ZMAX));
    desenharFaixas();
  }

  function quadro(t) {
    if (!visivel) { rodando = false; return; }
    const dt = Math.min(0.05, (t - ultimo) / 1000 || 0.016);
    ultimo = t;
    fase -= dt * 3.2; // a faixa vem na direção de quem olha
    desenharFaixas();
    requestAnimationFrame(quadro);
  }

  new ResizeObserver(medir).observe(el);
  medir();
  if (!reduz) {
    new IntersectionObserver(([e]) => {
      visivel = e.isIntersecting;
      if (visivel && !rodando) { rodando = true; ultimo = performance.now(); requestAnimationFrame(quadro); }
    }).observe(el);
  }
}
