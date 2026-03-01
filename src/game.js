const canvas = document.getElementById('course');
const ctx = canvas.getContext('2d');

const holeLabel = document.getElementById('hole-label');
const parLabel = document.getElementById('par-label');
const turnLabel = document.getElementById('turn-label');
const strokeLabel = document.getElementById('stroke-label');
const scoreboard = document.getElementById('scoreboard');
const resetShotBtn = document.getElementById('reset-shot');
void 0;

const COURSE_TOTAL = 9;
const WALLS = [
  { x: 260, y: 110, w: 20, h: 380 },
  { x: 520, y: 30, w: 20, h: 360 },
  { x: 740, y: 210, w: 20, h: 360 },
];

const players = setupPlayers();
let currentHole = makeHole(1);
let currentPlayerIndex = 0;
let aiming = false;
let aimPoint = { x: 0, y: 0 };
let gameFinished = false;

function setupPlayers() {
  const count = Number.parseInt(prompt('How many friends are playing? (1-4)', '2'), 10);
  const totalPlayers = Number.isNaN(count) ? 2 : Math.max(1, Math.min(4, count));
  const out = [];
  for (let i = 1; i <= totalPlayers; i += 1) {
    const name = prompt(`Name for Player ${i}`, `Player ${i}`) || `Player ${i}`;
    out.push({ name: name.trim() || `Player ${i}`, strokes: [], completed: false });
  }
  return out;
}

function makeHole(number) {
  const rng = mulberry32(number * 1977);
  const par = [3, 4, 5][number % 3];
  const tee = { x: 85, y: 300 + Math.round((rng() - 0.5) * 180) };
  const cup = { x: 920, y: 300 + Math.round((rng() - 0.5) * 220), radius: 16 };

  return {
    number,
    par,
    tee,
    cup,
    sand: {
      x: 370 + Math.floor(rng() * 200),
      y: 160 + Math.floor(rng() * 220),
      w: 120,
      h: 90,
    },
    water: {
      x: 640 + Math.floor(rng() * 120),
      y: 80 + Math.floor(rng() * 320),
      w: 95,
      h: 130,
    },
    ball: {
      x: tee.x,
      y: tee.y,
      vx: 0,
      vy: 0,
      radius: 10,
      moving: false,
      startX: tee.x,
      startY: tee.y,
    },
    strokesThisTurn: 0,
  };
}

function draw() {
  drawCourse();
  drawBall();

  if (aiming && !currentHole.ball.moving && !players[currentPlayerIndex].completed) {
    drawAimLine();
  }
}

function drawCourse() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = '#58b46e';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = '#91c86f';
  ctx.beginPath();
  ctx.ellipse(500, 300, 430, 200, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = '#d6c18e';
  ctx.fillRect(currentHole.sand.x, currentHole.sand.y, currentHole.sand.w, currentHole.sand.h);

  ctx.fillStyle = '#4198d6';
  ctx.fillRect(currentHole.water.x, currentHole.water.y, currentHole.water.w, currentHole.water.h);

  ctx.fillStyle = '#464646';
  for (const wall of WALLS) {
    ctx.fillRect(wall.x, wall.y, wall.w, wall.h);
  }

  ctx.fillStyle = '#d74f4f';
  ctx.fillRect(currentHole.cup.x - 2, currentHole.cup.y - 52, 4, 54);
  ctx.fillStyle = '#101010';
  ctx.beginPath();
  ctx.arc(currentHole.cup.x, currentHole.cup.y, currentHole.cup.radius, 0, Math.PI * 2);
  ctx.fill();
}

function drawBall() {
  const ball = currentHole.ball;
  ctx.fillStyle = '#fff';
  ctx.beginPath();
  ctx.arc(ball.x, ball.y, ball.radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#ccc';
  ctx.stroke();
}

function drawAimLine() {
  const ball = currentHole.ball;
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(ball.x, ball.y);
  ctx.lineTo(aimPoint.x, aimPoint.y);
  ctx.stroke();
}

function updateBall() {
  const ball = currentHole.ball;
  if (!ball.moving) return;

  ball.x += ball.vx;
  ball.y += ball.vy;

  ball.vx *= isInSand(ball) ? 0.93 : 0.975;
  ball.vy *= isInSand(ball) ? 0.93 : 0.975;

  if (Math.abs(ball.vx) < 0.04 && Math.abs(ball.vy) < 0.04) {
    ball.vx = 0;
    ball.vy = 0;
    ball.moving = false;
  }

  bounceOffBounds(ball);
  bounceOffWalls(ball);

  if (inWater(ball)) {
    ball.x = ball.startX;
    ball.y = ball.startY;
    ball.vx = 0;
    ball.vy = 0;
    ball.moving = false;
  }

  if (reachedCup(ball)) {
    players[currentPlayerIndex].strokes.push(currentHole.strokesThisTurn);
    players[currentPlayerIndex].completed = true;
    ball.moving = false;
    ball.vx = 0;
    ball.vy = 0;
    nextTurn();
  }
}

function bounceOffBounds(ball) {
  if (ball.x < ball.radius || ball.x > canvas.width - ball.radius) {
    ball.vx *= -0.86;
    ball.x = Math.max(ball.radius, Math.min(canvas.width - ball.radius, ball.x));
  }
  if (ball.y < ball.radius || ball.y > canvas.height - ball.radius) {
    ball.vy *= -0.86;
    ball.y = Math.max(ball.radius, Math.min(canvas.height - ball.radius, ball.y));
  }
}

function bounceOffWalls(ball) {
  for (const wall of WALLS) {
    const collides =
      ball.x + ball.radius > wall.x &&
      ball.x - ball.radius < wall.x + wall.w &&
      ball.y + ball.radius > wall.y &&
      ball.y - ball.radius < wall.y + wall.h;

    if (!collides) continue;

    const overlapLeft = ball.x + ball.radius - wall.x;
    const overlapRight = wall.x + wall.w - (ball.x - ball.radius);
    const overlapTop = ball.y + ball.radius - wall.y;
    const overlapBottom = wall.y + wall.h - (ball.y - ball.radius);
    const minOverlap = Math.min(overlapLeft, overlapRight, overlapTop, overlapBottom);

    if (minOverlap === overlapLeft || minOverlap === overlapRight) {
      ball.vx *= -0.88;
      ball.x += minOverlap === overlapLeft ? -minOverlap : minOverlap;
    } else {
      ball.vy *= -0.88;
      ball.y += minOverlap === overlapTop ? -minOverlap : minOverlap;
    }
  }
}

function inWater(ball) {
  const w = currentHole.water;
  return ball.x > w.x && ball.x < w.x + w.w && ball.y > w.y && ball.y < w.y + w.h;
}

function isInSand(ball) {
  const s = currentHole.sand;
  return ball.x > s.x && ball.x < s.x + s.w && ball.y > s.y && ball.y < s.y + s.h;
}

function reachedCup(ball) {
  const dx = ball.x - currentHole.cup.x;
  const dy = ball.y - currentHole.cup.y;
  const speed = Math.hypot(ball.vx, ball.vy);
  return Math.hypot(dx, dy) < currentHole.cup.radius - 2 && speed < 3;
}

function shoot(targetX, targetY) {
  const ball = currentHole.ball;
  if (ball.moving || players[currentPlayerIndex].completed || gameFinished) return;

  const dx = ball.x - targetX;
  const dy = ball.y - targetY;
  const distance = Math.min(180, Math.hypot(dx, dy));
  const power = distance / 18;

  ball.vx = (dx / (distance || 1)) * power;
  ball.vy = (dy / (distance || 1)) * power;
  ball.moving = true;
  ball.startX = ball.x;
  ball.startY = ball.y;
  currentHole.strokesThisTurn += 1;

  updateHud();
}

function nextTurn() {
  const next = players.findIndex((player) => !player.completed);
  if (next !== -1) {
    currentPlayerIndex = next;
    const ball = currentHole.ball;
    ball.x = currentHole.tee.x;
    ball.y = currentHole.tee.y;
    ball.startX = ball.x;
    ball.startY = ball.y;
    currentHole.strokesThisTurn = 0;
    updateHud();
    return;
  }

  if (currentHole.number >= COURSE_TOTAL) {
    gameFinished = true;
    turnLabel.textContent = 'Round Complete';
    renderScoreboard(true);
    return;
  }

  currentHole = makeHole(currentHole.number + 1);
  players.forEach((player) => {
    player.completed = false;
  });
  currentPlayerIndex = 0;
  updateHud();
}

function renderScoreboard(final = false) {
  const standings = players
    .map((player) => {
      const total = player.strokes.reduce((sum, stroke) => sum + stroke, 0);
      const toPar = total - player.strokes.reduce((sum, _, i) => sum + [3, 4, 5][(i + 1) % 3], 0);
      return { name: player.name, total, toPar, holesPlayed: player.strokes.length };
    })
    .sort((a, b) => a.toPar - b.toPar || a.total - b.total);

  const rows = standings
    .map(
      (row) => `<tr><td>${row.name}</td><td>${row.holesPlayed}</td><td>${row.total}</td><td>${row.toPar > 0 ? '+' : ''}${row.toPar}</td></tr>`
    )
    .join('');

  scoreboard.innerHTML = `
    <h3>${final ? '🏆 Final Scoreboard' : 'Scoreboard'}</h3>
    <table>
      <thead><tr><th>Player</th><th>Holes</th><th>Total</th><th>To Par</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function updateHud() {
  holeLabel.textContent = `${currentHole.number} / ${COURSE_TOTAL}`;
  parLabel.textContent = currentHole.par;
  turnLabel.textContent = players[currentPlayerIndex].name;
  strokeLabel.textContent = currentHole.strokesThisTurn;
  renderScoreboard();
}

canvas.addEventListener('mousedown', (event) => {
  if (gameFinished) return;
  aiming = true;
  const rect = canvas.getBoundingClientRect();
  aimPoint = { x: event.clientX - rect.left, y: event.clientY - rect.top };
});

canvas.addEventListener('mousemove', (event) => {
  if (!aiming) return;
  const rect = canvas.getBoundingClientRect();
  aimPoint = { x: event.clientX - rect.left, y: event.clientY - rect.top };
});

canvas.addEventListener('mouseup', (event) => {
  if (!aiming) return;
  aiming = false;
  const rect = canvas.getBoundingClientRect();
  const targetX = event.clientX - rect.left;
  const targetY = event.clientY - rect.top;
  shoot(targetX, targetY);
});

resetShotBtn.addEventListener('click', () => {
  const ball = currentHole.ball;
  if (ball.moving) return;
  ball.x = currentHole.tee.x;
  ball.y = currentHole.tee.y;
  ball.startX = ball.x;
  ball.startY = ball.y;
});

function gameLoop() {
  updateBall();
  draw();
  requestAnimationFrame(gameLoop);
}

function mulberry32(seed) {
  let value = seed;
  return () => {
    value |= 0;
    value = (value + 0x6d2b79f5) | 0;
    let t = Math.imul(value ^ (value >>> 15), 1 | value);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

updateHud();
gameLoop();
