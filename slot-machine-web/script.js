const reelEls = Array.from(document.querySelectorAll(".reel"));
const spinBtn = document.getElementById("spin");
const betDownBtn = document.getElementById("bet-down");
const betUpBtn = document.getElementById("bet-up");
const creditsEl = document.getElementById("credits");
const betEl = document.getElementById("bet");
const winEl = document.getElementById("win");
const messageEl = document.getElementById("message");
const canvas = document.getElementById("fx");
const ctx = canvas.getContext("2d");

const symbols = [
  { key: "coin", label: "COIN", burst: "coin", weight: 24 },
  { key: "cash", label: "CASH", burst: "dollar", weight: 20 },
  { key: "gem", label: "GEM", burst: "diamond", weight: 16 },
  { key: "star", label: "STAR", burst: "coin", weight: 20 },
  { key: "bar", label: "BAR", burst: "coin", weight: 10 },
  { key: "luck", label: "LUCK", burst: "coin", weight: 10 },
];

const tripleChance = 0.1;

let credits = 1000;
let bet = 25;
let spinning = false;
let particles = [];
let lastFrame = 0;

function resizeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = window.innerWidth * ratio;
  canvas.height = window.innerHeight * ratio;
  canvas.style.width = `${window.innerWidth}px`;
  canvas.style.height = `${window.innerHeight}px`;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function weightedPick() {
  const total = symbols.reduce((sum, sym) => sum + sym.weight, 0);
  let r = Math.random() * total;
  for (const sym of symbols) {
    r -= sym.weight;
    if (r <= 0) return sym;
  }
  return symbols[0];
}

function rollFinals() {
  if (Math.random() < tripleChance) {
    const sym = weightedPick();
    return [sym, sym, sym];
  }
  return [weightedPick(), weightedPick(), weightedPick()];
}

function setReel(reelEl, sym) {
  reelEl.className = `reel sym-${sym.key}`;
  reelEl.querySelector(".symbol").textContent = sym.label;
  reelEl.dataset.symbol = sym.key;
}

function setMessage(text) {
  messageEl.textContent = text;
}

function updateHUD(win = 0) {
  creditsEl.textContent = credits;
  betEl.textContent = bet;
  winEl.textContent = win;
}

function spinReel(reelEl, duration, finalSym) {
  return new Promise((resolve) => {
    const start = performance.now();
    reelEl.classList.add("spin");
    const tick = (time) => {
      const elapsed = time - start;
      if (elapsed >= duration) {
        reelEl.classList.remove("spin");
        setReel(reelEl, finalSym);
        resolve(finalSym);
        return;
      }
      setReel(reelEl, weightedPick());
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

function calcWin(results) {
  const [a, b, c] = results.map((r) => r.key);
  if (a === b && b === c) {
    return bet * 8;
  }
  if (a === b || b === c || a === c) {
    return bet * 2;
  }
  return 0;
}

function winBurst(results, win) {
  if (win <= 0) return;
  const isTriple = results[0].key === results[1].key && results[1].key === results[2].key;
  let burst = results[Math.floor(Math.random() * results.length)].burst;
  if (isTriple) {
    burst = results[0].burst;
  }
  const count = Math.min(120, 40 + Math.floor(win / 2));
  emitBurst(burst, count);
  reelEls.forEach((reel) => reel.classList.add("win"));
  setTimeout(() => reelEls.forEach((reel) => reel.classList.remove("win")), 500);
}

function emitBurst(type, count) {
  const bounds = document.querySelector(".machine").getBoundingClientRect();
  const originX = bounds.left + bounds.width / 2;
  const originY = bounds.top + bounds.height * 0.2;
  for (let i = 0; i < count; i += 1) {
    particles.push({
      x: originX + (Math.random() - 0.5) * 80,
      y: originY + (Math.random() - 0.5) * 20,
      vx: (Math.random() - 0.5) * 6,
      vy: -Math.random() * 5 - 1,
      life: 120 + Math.random() * 40,
      size: 6 + Math.random() * 6,
      rot: Math.random() * Math.PI * 2,
      spin: (Math.random() - 0.5) * 0.2,
      type,
    });
  }
}

function drawCoin(p) {
  ctx.save();
  ctx.translate(p.x, p.y);
  ctx.rotate(p.rot);
  const grd = ctx.createRadialGradient(0, 0, 2, 0, 0, p.size);
  grd.addColorStop(0, "#ffe7a6");
  grd.addColorStop(1, "#d89a2b");
  ctx.fillStyle = grd;
  ctx.beginPath();
  ctx.arc(0, 0, p.size, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawDollar(p) {
  ctx.save();
  ctx.translate(p.x, p.y);
  ctx.rotate(p.rot);
  ctx.fillStyle = "#6fe0d4";
  ctx.beginPath();
  ctx.roundRect(-p.size, -p.size * 0.6, p.size * 2, p.size * 1.2, 4);
  ctx.fill();
  ctx.fillStyle = "#0b3b34";
  ctx.font = `${p.size * 1.2}px Trebuchet MS`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("$", 0, 0);
  ctx.restore();
}

function drawDiamond(p) {
  ctx.save();
  ctx.translate(p.x, p.y);
  ctx.rotate(p.rot);
  ctx.fillStyle = "#b18cff";
  ctx.beginPath();
  ctx.moveTo(0, -p.size);
  ctx.lineTo(p.size, 0);
  ctx.lineTo(0, p.size);
  ctx.lineTo(-p.size, 0);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function stepParticles(time) {
  const dt = Math.min(32, time - lastFrame);
  lastFrame = time;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  particles = particles.filter((p) => p.life > 0);
  particles.forEach((p) => {
    p.x += p.vx;
    p.y += p.vy;
    p.vy += 0.08;
    p.rot += p.spin;
    p.life -= dt;
    const fade = Math.max(0, p.life / 160);
    ctx.globalAlpha = fade;
    if (p.type === "coin") drawCoin(p);
    if (p.type === "dollar") drawDollar(p);
    if (p.type === "diamond") drawDiamond(p);
  });
  ctx.globalAlpha = 1;
  requestAnimationFrame(stepParticles);
}

async function spin() {
  if (spinning || bet > credits) return;
  spinning = true;
  spinBtn.disabled = true;
  setMessage("Spinning...");
  credits -= bet;
  updateHUD(0);

  const finals = rollFinals();
  const results = [];
  for (let i = 0; i < reelEls.length; i += 1) {
    const result = await spinReel(reelEls[i], 500 + i * 150, finals[i]);
    results.push(result);
  }

  const win = calcWin(results);
  credits += win;
  updateHUD(win);

  if (win > 0) {
    setMessage(`Win +${win}!`);
    winBurst(results, win);
  } else {
    setMessage("No win. Try again.");
  }

  spinning = false;
  spinBtn.disabled = false;
}

function clampBet(next) {
  bet = Math.max(5, Math.min(200, next));
  betEl.textContent = bet;
}

betDownBtn.addEventListener("click", () => clampBet(bet - 5));
betUpBtn.addEventListener("click", () => clampBet(bet + 5));
spinBtn.addEventListener("click", spin);
window.addEventListener("resize", resizeCanvas);

resizeCanvas();
updateHUD(0);
requestAnimationFrame(stepParticles);
