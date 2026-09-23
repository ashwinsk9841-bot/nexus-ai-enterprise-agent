/* NEXUS animated AI-network background — subtle, performance-friendly canvas */
(function () {
  const canvas = document.getElementById("bg-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  let W, H, dpr;
  let particles = [];
  let nodes = [];
  let streaks = [];

  const COLORS = ["22,211,238", "59,130,246", "139,92,246", "157,220,255"];

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    initParticles();
    initNodes();
  }

  // Prefer the reduced-motion setting to keep performance friendly
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function initParticles() {
    const count = Math.min(90, Math.floor((W * H) / 18000));
    particles = [];
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.16,
        vy: (Math.random() - 0.5) * 0.16,
        r: Math.random() * 1.6 + 0.4,
        c: COLORS[Math.floor(Math.random() * COLORS.length)],
        a: Math.random() * 0.5 + 0.12,
      });
    }
    nodes = [];
    for (let i = 0; i < Math.min(10, W / 180); i++) {
      nodes.push({
        x: Math.random() * W,
        y: Math.random() * H,
        pr: Math.random() * 0.006 + 0.002,
        base: Math.random() * Math.PI * 2,
        c: COLORS[Math.floor(Math.random() * COLORS.length)],
      });
    }
    streaks = [];
    for (let i = 0; i < 3; i++) {
      streaks.push(createStreak());
    }
  }

  function createStreak() {
    return {
      x: Math.random() * W,
      y: Math.random() * H * 0.5,
      len: Math.random() * 140 + 60,
      speed: Math.random() * 0.7 + 0.3,
      angle: Math.random() * Math.PI * 2,
      c: COLORS[Math.floor(Math.random() * COLORS.length)],
      a: Math.random() * 0.12 + 0.04,
      active: Math.random() > 0.4,
    };
  }

  let last = 0;
  function frame(t) {
    if (prefersReduced || document.hidden) {
      requestAnimationFrame(frame);
      return;
    }
    const dt = Math.min((t - last) / 16.67, 4) || 1;
    last = t;
    ctx.clearRect(0, 0, W, H);

    // Network connections
    ctx.lineWidth = 0.6;
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      for (let j = i + 1; j < particles.length; j++) {
        const q = particles[j];
        const dx = p.x - q.x;
        const dy = p.y - q.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < 130 * 130) {
          const alpha = (1 - Math.sqrt(d2) / 130) * 0.14;
          const c = p.c;
          ctx.strokeStyle = `rgba(${c},${alpha})`;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(q.x, q.y);
          ctx.stroke();
        }
      }
    }

    // Particles
    for (const p of particles) {
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      if (p.x < -10) p.x = W + 10;
      if (p.x > W + 10) p.x = -10;
      if (p.y < -10) p.y = H + 10;
      if (p.y > H + 10) p.y = -10;
      ctx.fillStyle = `rgba(${p.c},${p.a})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }

    // Glowing nodes
    for (const n of nodes) {
      const t0 = performance.now() / 1000;
      const pulse = 0.5 + 0.5 * Math.sin(t0 * 1.4 + n.base);
      const radius = 3 + pulse * 3;
      const c = n.c;
      ctx.strokeStyle = `rgba(${c},${0.14 + pulse * 0.2})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = `rgba(${c},${0.2 + pulse * 0.25})`;
      ctx.beginPath();
      ctx.arc(n.x, n.y, 1.4 + pulse, 0, Math.PI * 2);
      ctx.fill();
    }

    // Light streaks
    for (const s of streaks) {
      if (!s.active) continue;
      s.x += Math.cos(s.angle) * s.speed * dt;
      s.y += Math.sin(s.angle) * s.speed * dt;
      if (s.x < -s.len || s.x > W + s.len || s.y < -s.len || s.y > H + s.len) {
        Object.assign(s, createStreak());
      }
      const grad = ctx.createLinearGradient(s.x - s.len, s.y, s.x, s.y);
      grad.addColorStop(0, `rgba(${s.c},0)`);
      grad.addColorStop(1, `rgba(${s.c},${s.a})`);
      ctx.strokeStyle = grad;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(s.x - s.len, s.y);
      ctx.lineTo(s.x, s.y);
      ctx.stroke();
    }

    requestAnimationFrame(frame);
  }

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resize, 200);
  });

  resize();
  requestAnimationFrame(frame);
})();