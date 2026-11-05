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

  mm.add("not ((min-width: 900px) and (min-height: 620px) and (prefers-reduced-motion: no-preference))", () => {
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
