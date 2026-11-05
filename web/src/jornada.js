// Movimento: a viagem fixada (ScrollTrigger) e a rolagem suave (Lenis).
// Sem animação quando o sistema pede movimento reduzido, e em telas
// pequenas os cards ficam empilhados na vertical.
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";

gsap.registerPlugin(ScrollTrigger);

const limitar = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));

/** Chuva em canvas: só desenha enquanto a intensidade for maior que zero. */
function criarChuva(canvas) {
  const ctx = canvas.getContext("2d");
  const VENTO = 0.2; // deslocamento lateral por unidade de queda
  let gotas = [], w = 0, h = 0, intensidade = 0, rodando = false, ultimo = 0;
  const nova = (inicio) => {
    const z = Math.random();
    return {
      x: Math.random() * (w + 200) - 100,
      y: inicio ? Math.random() * h : -30 - Math.random() * h * 0.3,
      v: 900 + z * 1000, l: 10 + z * 26, a: 0.10 + z * 0.38, z,
    };
  };
  function medir() {
    const dpr = Math.min(2, devicePixelRatio || 1);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    gotas = Array.from({ length: Math.round((w * h) / 3200) }, () => nova(true));
  }
  function quadro(t) {
    const dt = Math.min(0.05, (t - ultimo) / 1000 || 0.016);
    ultimo = t;
    ctx.clearRect(0, 0, w, h);
    if (intensidade < 0.01) { rodando = false; return; }
    const n = Math.round(gotas.length * Math.min(1, intensidade * 1.2));
    ctx.lineCap = "round";
    for (let i = 0; i < n; i++) {
      const g = gotas[i];
      g.y += g.v * dt; g.x += g.v * dt * VENTO;
      if (g.y - g.l > h) Object.assign(g, nova(false));
      ctx.strokeStyle = `rgba(196, 210, 230, ${(g.a * intensidade).toFixed(3)})`;
      ctx.lineWidth = 0.6 + g.z;
      ctx.beginPath();
      ctx.moveTo(g.x, g.y);
      ctx.lineTo(g.x - g.l * VENTO, g.y - g.l);
      ctx.stroke();
    }
    requestAnimationFrame(quadro);
  }
  return {
    medir,
    definir(v) {
      intensidade = v;
      canvas.style.opacity = v > 0.01 ? "1" : "0";
      if (v > 0.01 && !rodando) { rodando = true; ultimo = performance.now(); requestAnimationFrame(quadro); }
    },
  };
}

export function iniciarJornada({ secao, trilho, cards, estacoes, cena }) {
  const reduz = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let lenis = null;
  if (!reduz) {
    lenis = new Lenis({ lerp: 0.09 });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add((t) => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
  }

  const rolarAte = (alvo) => (lenis ? lenis.scrollTo(alvo, { duration: 1.4 }) : window.scrollTo({ top: typeof alvo === "number" ? alvo : alvo.getBoundingClientRect().top + scrollY, behavior: "auto" }));

  // Âncoras internas passam pela rolagem suave.
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#"]');
    if (!a) return;
    const alvo = document.querySelector(a.getAttribute("href"));
    if (!alvo) return;
    e.preventDefault();
    rolarAte(alvo);
  });

  const marcarEstacao = (i) => estacoes.forEach((b, k) => b.toggleAttribute("aria-current", k === i));
  const indice = (id) => cards.findIndex((c) => c.dataset.id === id);
  const ativar = (i) => cards[i]?.classList.add("ativo");
  let irPara = (i) => rolarAte(cards[i]);
  estacoes.forEach((b, i) => b.addEventListener("click", () => irPara(i)));

  // Barra de progresso da página inteira.
  if (!reduz) {
    gsap.to("#barra", { scaleX: 1, ease: "none", scrollTrigger: { start: 0, end: "max", scrub: true } });
    gsap.from(".abertura .revela", { y: 36, opacity: 0, duration: 1.1, ease: "power3.out", stagger: 0.12, delay: 0.1 });
    gsap.to(".abertura-conteudo", {
      y: -80, opacity: 0, ease: "none",
      scrollTrigger: { trigger: ".abertura", start: "top top", end: "bottom top", scrub: true },
    });
  }

  const mm = gsap.matchMedia();

  mm.add("(min-width: 900px) and (min-height: 620px) and (prefers-reduced-motion: no-preference)", () => {
    document.documentElement.classList.add("horizontal");
    const $ = (s) => cena.querySelector(s);
    const faixa = $(".faixa"), noite = $(".ceu-noite"), clarao = $(".clarao"), marcos = $(".marcos");
    const carro = $(".carro"), contra = $(".carro-contra"), estilhacos = $(".estilhacos");
    const chuva = criarChuva($(".chuva"));
    const iNoite = cards.findIndex((c) => c.dataset.noite === "1");
    const iChuva = cards.findIndex((c) => c.dataset.chuva === "1");
    const iContra = cards.findIndex((c) => c.dataset.contramao === "1");
    const iImpacto = cards.findIndex((c) => c.dataset.impacto === "1");

    const dist = () => Math.max(1, trilho.scrollWidth - innerWidth);
    let centros = [];
    const medir = () => {
      centros = cards.map((c) => limitar((c.offsetLeft + c.offsetWidth / 2 - innerWidth / 2) / dist()));
      // uma placa de quilômetro sob cada parada, presa ao trilho
      marcos.innerHTML = cards.map((c, i) =>
        `<span class="marco" style="left:${c.offsetLeft + c.offsetWidth / 2}px"><b>${String(i + 1).padStart(2, "0")}</b>${c.dataset.nome}</span>`).join("");
      chuva.medir();
    };
    medir();

    // O instante da batida: clarão, tremor e estilhaços. Roda uma vez a cada
    // passagem para a frente pelo ponto do impacto.
    function bater() {
      const r = carro.getBoundingClientRect(), base = cena.getBoundingClientRect();
      const x0 = r.right - base.left - 8, y0 = r.top - base.top + r.height * 0.45;
      gsap.fromTo(clarao, { opacity: 1 }, { opacity: 0, duration: 1.1, ease: "power2.out", overwrite: true });
      gsap.fromTo(cena, { x: 0 }, {
        keyframes: [{ x: -14, y: 4 }, { x: 11, y: -3 }, { x: -7, y: 2 }, { x: 4, y: -1 }, { x: 0, y: 0 }],
        duration: 0.5, ease: "power1.out", overwrite: true,
      });
      estilhacos.innerHTML = Array.from({ length: 22 }, () => "<i></i>").join("");
      estilhacos.querySelectorAll("i").forEach((el) => {
        const ang = (Math.random() * 1.1 - 0.95) * Math.PI; // para cima e para os lados
        const vel = 120 + Math.random() * 260;
        gsap.set(el, { x: x0, y: y0, rotation: Math.random() * 180, scale: 0.6 + Math.random() * 0.9, opacity: 1 });
        gsap.to(el, {
          duration: 0.9 + Math.random() * 0.6, ease: "power1.out",
          x: x0 + Math.cos(ang) * vel, rotation: "+=" + (Math.random() * 540 - 270),
        });
        gsap.to(el, { duration: 0.9 + Math.random() * 0.6, ease: "power2.in", y: y0 + Math.sin(ang) * vel * 0.5 + 70 });
        gsap.to(el, { opacity: 0, duration: 0.5, delay: 1 + Math.random() * 0.6 });
      });
    }

    let atual = -1, pAnterior = 0;
    function atualizar(p) {
      const d = dist();
      faixa.style.transform = `translate3d(${(-(p * d) % 160).toFixed(1)}px,0,0)`;
      marcos.style.transform = `translate3d(${(-p * d).toFixed(1)}px,0,0)`;
      // foco: o card do centro fica nítido, os vizinhos recuam
      let perto = 0, melhor = Infinity;
      cards.forEach((c, i) => {
        const dx = Math.abs(p - centros[i]) * d / innerWidth;
        if (dx < melhor) { melhor = dx; perto = i; }
        c.style.setProperty("--foco", (1 - limitar(dx * 1.1, 0, 0.6)).toFixed(3));
        if (dx < 0.45) ativar(i);
      });
      if (perto !== atual) { atual = perto; marcarEstacao(perto); }
      // céu: anoitece ao chegar na hora
      const pn = iNoite >= 0 ? limitar((p - (centros[iNoite] - 0.07)) / 0.07) : 0;
      noite.style.opacity = pn.toFixed(3);
      cena.style.setProperty("--noite", pn.toFixed(3));
      // chuva: máxima com a parada do tempo no centro
      if (iChuva >= 0) {
        const dc = Math.abs(p - centros[iChuva]) * d / innerWidth;
        const pc = 1 - limitar((dc - 0.12) / 0.5);
        chuva.definir(pc);
        cena.style.setProperty("--chuva", pc.toFixed(3));
      }
      // o carro na contramão se aproxima até bater
      if (iContra >= 0 && iImpacto >= 0) {
        const a = centros[iContra] - 0.03, b = centros[iImpacto] - 0.012;
        const meu = carro.offsetLeft + carro.offsetWidth;
        const contato = meu - 14;                 // a frente dos dois se encontra
        const inicio = innerWidth + 60;
        const pc = limitar((p - a) / (b - a));
        const depois = Math.max(0, p - b) * d;    // depois da batida, os carros ficam para trás
        const xContra = p <= b ? inicio + (contato - inicio) * Math.pow(pc, 1.25) : contato - depois;
        contra.style.translate = `${xContra.toFixed(1)}px 0`;
        contra.style.opacity = pc > 0 ? "1" : "0";
        carro.style.translate = `${(-depois).toFixed(1)}px 0`;
        const batido = p > b;
        carro.classList.toggle("batido", batido);
        contra.classList.toggle("batido", batido);
        if (pAnterior <= b && p > b) bater();
        if (p < b - 0.02) gsap.set(clarao, { opacity: 0 });
      }
      pAnterior = p;
    }

    const tween = gsap.to(trilho, {
      x: () => -dist(),
      ease: "none",
      scrollTrigger: {
        trigger: secao,
        pin: true,
        start: "top top",
        end: () => `+=${dist() * 1.15}`,
        scrub: 0.8,
        invalidateOnRefresh: true,
        onRefresh: medir,
      },
      onUpdate() { atualizar(this.progress()); },
    });
    atualizar(0);

    irPara = (i) => {
      const st = tween.scrollTrigger;
      rolarAte(st.start + centros[i] * (st.end - st.start));
    };

    return () => {
      document.documentElement.classList.remove("horizontal");
      chuva.definir(0);
      for (const el of [carro, contra]) { el.classList.remove("batido"); el.style.translate = ""; }
      cards.forEach((c) => c.style.removeProperty("--foco"));
      irPara = (i) => rolarAte(cards[i]);
    };
  });

  // Celular: as paradas viram um carrossel que se arrasta com o dedo,
  // um card por vez, com a altura acompanhando o card da vez.
  mm.add("(max-width: 899px)", () => {
    const raiz = document.documentElement;
    raiz.classList.add("carrossel");
    if (reduz) cards.forEach((c) => c.classList.add("ativo"));
    const seta = (d) => `<svg viewBox="0 0 20 20" aria-hidden="true"><path d="${d}"/></svg>`;
    const barra = document.createElement("div");
    barra.className = "carrossel-barra";
    barra.innerHTML = `
      <button type="button" class="seta" data-passo="-1" aria-label="Parada anterior">${seta("M12 5l-5 5 5 5")}</button>
      <div class="carrossel-meio">
        <span class="carrossel-nome" aria-live="polite"></span>
        <span class="carrossel-pontos">${cards.map((c, i) => `<button type="button" aria-label="Ir para ${String(i + 1).padStart(2, "0")} ${c.dataset.nome}"></button>`).join("")}</span>
      </div>
      <button type="button" class="seta" data-passo="1" aria-label="Próxima parada">${seta("M8 5l5 5-5 5")}</button>`;
    trilho.before(barra);
    // Seta de "arraste": aparece quando o carrossel entra na tela e some em fade.
    const dica = document.createElement("div");
    dica.className = "carrossel-seta";
    dica.setAttribute("aria-hidden", "true");
    dica.innerHTML = `Arraste para o lado <svg viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg>`;
    cena.appendChild(dica);
    let dicaFeita = false, dicaTempo = 0;
    const esconderDica = () => { dicaFeita = true; clearTimeout(dicaTempo); dica.classList.remove("visivel"); obsDica.disconnect(); };
    const obsDica = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting || dicaFeita) return;
      dica.style.top = `${trilho.offsetTop + Math.min(trilho.offsetHeight, innerHeight * 0.6) * 0.45}px`;
      requestAnimationFrame(() => dica.classList.add("visivel"));
      dicaTempo = setTimeout(esconderDica, 2200);
    }, { threshold: 0.25 });
    obsDica.observe(trilho);
    // O resto da página só aparece depois que a pessoa chega à última parada.
    const trava = document.createElement("p");
    trava.className = "carrossel-trava";
    trilho.after(trava);
    let travado = true;
    raiz.classList.add("travado");
    const destravar = () => {
      if (!travado) return;
      travado = false;
      raiz.classList.remove("travado");
      trava.remove();
      lenis?.resize();
      ScrollTrigger.refresh();
    };
    trilho.setAttribute("tabindex", "0");
    trilho.setAttribute("aria-label", "Paradas da viagem; arraste para o lado para trocar");
    const nome = barra.querySelector(".carrossel-nome");
    const pontos = [...barra.querySelectorAll(".carrossel-pontos button")];
    const [anterior, proxima] = barra.querySelectorAll(".seta");

    let atual = -1;
    const ajustarAltura = () => { if (cards[atual]) trilho.style.height = cards[atual].offsetHeight + "px"; };
    const mostrar = (i) => {
      if (i === atual) return;
      atual = i;
      ativar(i);
      marcarEstacao(i);
      nome.innerHTML = `<b>${String(i + 1).padStart(2, "0")}</b>${cards[i].dataset.nome}`;
      pontos.forEach((p, k) => p.toggleAttribute("aria-current", k === i));
      anterior.disabled = i === 0;
      proxima.disabled = i === cards.length - 1;
      ajustarAltura();
      if (i === cards.length - 1) destravar();
      else if (travado) {
        const faltam = cards.length - 1 - i;
        trava.innerHTML = `<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="4.5" y="9" width="11" height="8" rx="2"/><path d="M7 9V6.5a3 3 0 0 1 6 0V9"/></svg>Arraste até a última parada para continuar · falta${faltam > 1 ? "m" : ""} ${faltam}`;
      }
    };
    // Ao trocar de card no meio de um texto longo, volta para o topo do novo card.
    const alinharTopo = () => {
      const topo = trilho.getBoundingClientRect().top;
      const limite = barra.getBoundingClientRect().bottom;
      if (topo < limite - 4) rolarAte(scrollY + topo - limite - 8);
    };
    const posicao = (i) => cards[i].offsetLeft - (trilho.clientWidth - cards[i].offsetWidth) / 2;
    // O gesto é controlado aqui, sem a inércia nativa: cada arrasto anda
    // no máximo um card, por mais forte que seja.
    const irCard = (i) => {
      i = Math.max(0, Math.min(cards.length - 1, i));
      const mudou = i !== atual;
      mostrar(i);
      gsap.to(trilho, {
        scrollLeft: posicao(i), duration: reduz ? 0 : 0.45, ease: "power3.out", overwrite: true,
        onComplete: () => { if (mudou) alinharTopo(); },
      });
    };
    let toque = null;
    const inicio = (e) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      gsap.killTweensOf(trilho);
      toque = { id: e.pointerId, x: e.clientX, y: e.clientY, t: performance.now(), base: trilho.scrollLeft, horizontal: null };
    };
    const mover = (e) => {
      if (!toque || e.pointerId !== toque.id) return;
      const dx = e.clientX - toque.x, dy = e.clientY - toque.y;
      if (toque.horizontal === null && Math.hypot(dx, dy) > 8) {
        toque.horizontal = Math.abs(dx) > Math.abs(dy);
        if (toque.horizontal) trilho.setPointerCapture?.(e.pointerId);
      }
      if (!toque.horizontal) return;
      const borda = (atual === 0 && dx > 0) || (atual === cards.length - 1 && dx < 0);
      trilho.scrollLeft = toque.base - dx * (borda ? 0.3 : 1);
    };
    const fim = (e) => {
      if (!toque || e.pointerId !== toque.id) return;
      const t = toque; toque = null;
      if (!t.horizontal) return;
      const dx = e.clientX - t.x, vel = Math.abs(dx) / Math.max(1, performance.now() - t.t);
      const passo = Math.abs(dx) > trilho.clientWidth * 0.18 || (vel > 0.35 && Math.abs(dx) > 24) ? (dx < 0 ? 1 : -1) : 0;
      if (passo) esconderDica();
      irCard(atual + passo);
    };
    trilho.addEventListener("pointerdown", inicio);
    trilho.addEventListener("pointermove", mover);
    trilho.addEventListener("pointerup", fim);
    trilho.addEventListener("pointercancel", fim);
    // impede que o navegador trate o arrasto como seleção de texto ou de imagem
    const semArrastar = (e) => e.preventDefault();
    trilho.addEventListener("dragstart", semArrastar);
    const reposicionar = () => gsap.set(trilho, { scrollLeft: posicao(atual) });
    addEventListener("resize", reposicionar);
    const teclas = (e) => {
      if (e.key === "ArrowRight") { e.preventDefault(); irCard(atual + 1); }
      if (e.key === "ArrowLeft") { e.preventDefault(); irCard(atual - 1); }
    };
    trilho.addEventListener("keydown", teclas);
    anterior.addEventListener("click", () => irCard(atual - 1));
    proxima.addEventListener("click", () => irCard(atual + 1));
    pontos.forEach((p, i) => p.addEventListener("click", () => irCard(i)));
    const ro = new ResizeObserver(ajustarAltura);
    cards.forEach((c) => ro.observe(c));
    mostrar(0);
    const irAntes = irPara;
    irPara = (i) => { irCard(i); rolarAte(barra); };

    return () => {
      raiz.classList.remove("carrossel", "travado");
      esconderDica();
      dica.remove();
      trava.remove();
      for (const [t, f] of [["pointerdown", inicio], ["pointermove", mover], ["pointerup", fim], ["pointercancel", fim], ["dragstart", semArrastar]]) trilho.removeEventListener(t, f);
      removeEventListener("resize", reposicionar);
      gsap.killTweensOf(trilho);
      trilho.removeEventListener("keydown", teclas);
      ro.disconnect();
      barra.remove();
      trilho.style.height = "";
      trilho.removeAttribute("tabindex");
      trilho.removeAttribute("aria-label");
      irPara = irAntes;
    };
  });

  mm.add("(min-width: 900px) and ((max-height: 619px) or (prefers-reduced-motion: reduce))", () => {
    if (reduz) { cards.forEach((c) => c.classList.add("ativo")); }
    const obs = new IntersectionObserver((ents) => {
      for (const e of ents) {
        if (!e.isIntersecting) continue;
        const i = cards.indexOf(e.target);
        ativar(i);
        marcarEstacao(i);
      }
    }, { rootMargin: "-35% 0px -45% 0px" });
    cards.forEach((c) => obs.observe(c));
    return () => obs.disconnect();
  });

  return { indice };
}
