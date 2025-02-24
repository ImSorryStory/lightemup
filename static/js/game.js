// game.js

let blocks = puzzleData.blocks; // массив [y][x], элемент: {type, orientation}
const size = puzzleData.size;
let startTime = Date.now();
let timerId = null;

window.onload = function() {
  drawField();
  if (timeLimit > 0) {
    startTimer();
  }
};

function startTimer() {
  updateTimer();
  timerId = setInterval(updateTimer, 1000);
}

function updateTimer() {
  let elapsed = Math.floor((Date.now() - startTime) / 1000);
  let remain = timeLimit - elapsed;
  if (remain < 0) remain = 0;

  const timerSpan = document.getElementById('timer');
  if (timerSpan) {
    timerSpan.textContent = "Осталось: " + remain + " c.";
  }

  if (remain <= 0) {
    clearInterval(timerId);
    // Время вышло
    window.location.href = "/time_is_up";
  }
}

function drawField() {
  const fieldDiv = document.getElementById('field');
  fieldDiv.innerHTML = "";

  for (let y = 0; y < size; y++) {
    const rowDiv = document.createElement('div');
    rowDiv.style.whiteSpace = "nowrap";

    for (let x = 0; x < size; x++) {
      const cellDiv = document.createElement('div');
      cellDiv.classList.add('cell');
      cellDiv.id = `cell_${y}_${x}`;

      // При клике - поворот
      cellDiv.addEventListener('click', () => {
        rotateBlock(y, x);
      });

      rowDiv.appendChild(cellDiv);
    }
    fieldDiv.appendChild(rowDiv);
  }

  // Отрисовать линии и подсветку
  updateAllCellsRendering();
}

function rotateBlock(y, x) {
  blocks[y][x].orientation = (blocks[y][x].orientation + 1) % 4;
  updateAllCellsRendering();
}

function updateAllCellsRendering() {
  // Сначала получаем множество "lit" клеток
  const litSet = getLitCells();

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const cellDiv = document.getElementById(`cell_${y}_${x}`);
      // Очищаем содержимое
      cellDiv.innerHTML = "";

      // Подсветка
      if (litSet.has(`${y}_${x}`)) {
        cellDiv.classList.add('lit');
      } else {
        cellDiv.classList.remove('lit');
      }

      // Рисуем линии
      const dirs = getConnections(blocks[y][x].type, blocks[y][x].orientation);
      dirs.forEach(d => {
        let lineDiv = document.createElement('div');
        if (d === 'U') lineDiv.classList.add('lineU');
        if (d === 'D') lineDiv.classList.add('lineD');
        if (d === 'L') lineDiv.classList.add('lineL');
        if (d === 'R') lineDiv.classList.add('lineR');
        cellDiv.appendChild(lineDiv);
      });
    }
  }
}

/**
 * Возвращает set "y_x" строк координат, которые подсвечены по BFS от (0,0).
 */
function getLitCells() {
  let visited = new Set();
  let stack = ["0_0"];

  const inRange = (y, x) => (y >= 0 && y < size && x >= 0 && x < size);

  while (stack.length > 0) {
    let cur = stack.pop();
    if (visited.has(cur)) continue;
    visited.add(cur);

    let [cy, cx] = cur.split("_").map(Number);
    let cdirs = getConnections(blocks[cy][cx].type, blocks[cy][cx].orientation);

    // Смотрим соседей
    let neighbors = [
      { ny: cy-1, nx: cx, d1: 'U', d2: 'D' },
      { ny: cy+1, nx: cx, d1: 'D', d2: 'U' },
      { ny: cy, nx: cx-1, d1: 'L', d2: 'R' },
      { ny: cy, nx: cx+1, d1: 'R', d2: 'L' }
    ];

    for (let nb of neighbors) {
      if (inRange(nb.ny, nb.nx)) {
        let ndirs = getConnections(blocks[nb.ny][nb.nx].type, blocks[nb.ny][nb.nx].orientation);
        if (cdirs.has(nb.d1) && ndirs.has(nb.d2)) {
          let nbId = `${nb.ny}_${nb.nx}`;
          if (!visited.has(nbId)) {
            stack.push(nbId);
          }
        }
      }
    }
  }

  return visited;
}

/**
 * Возвращает набор направлений (U,R,D,L) для блока данного типа и ориентации
 */
function getConnections(blockType, orientation) {
  // базовые (orientation=0)
  let base = [];
  if (blockType === 'V') {
    base = ['U','D'];
  } else if (blockType === 'H') {
    base = ['L','R'];
  } else { // C
    base = ['U','L'];
  }

  const rotateDir = (d) => {
    if (d === 'U') return 'R';
    if (d === 'R') return 'D';
    if (d === 'D') return 'L';
    if (d === 'L') return 'U';
  };

  let result = new Set(base);
  for (let i = 0; i < orientation; i++) {
    result = new Set(Array.from(result).map(rotateDir));
  }
  return result;
}

/**
 * Проверка решения и отправка результата
 */
function checkSolution() {
  let lit = getLitCells();
  if (lit.size === size * size) {
    // Все клетки подсвечены
    let elapsed = Math.floor((Date.now() - startTime) / 1000);
    alert("Поздравляем! Головоломка решена.");

    fetch("/level_solved", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({time: elapsed})
    })
    .then(res => res.json())
    .then(data => {
      if (data.next_url) {
        window.location.href = data.next_url;
      }
    })
    .catch(err => console.error(err));

  } else {
    alert("Пока не все клетки подсвечены. Продолжайте!");
  }
}

let lastAnnouncementTime = 0;

function checkAnnouncements() {
  fetch("/poll_announcements")
    .then(r => r.json())
    .then(data => {
      if (data.has_announcement) {
        let ann = data.announcement;
        // Сравним ann.timestamp с lastAnnouncementTime
        if (ann.timestamp > lastAnnouncementTime) {
          lastAnnouncementTime = ann.timestamp;
          // Показываем уведомление:
          alert(`Новый лидер: ${ann.nickname}\nСчёт: ${ann.score}`);
          // Или более красиво в div/модальное окно
        }
      }
    })
    .catch(console.error);
}

setInterval(checkAnnouncements, 5000);
