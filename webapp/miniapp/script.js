/**
 * VITA Mini App — script.js
 * Telegram WebApp SDK интеграция + загрузка данных с бэкенда
 */

// ── Конфиг ────────────────────────────────────────────────────────────────
const API_BASE = "https://185-255-132-62.sslip.io";
const API_URL  = `${API_BASE}/api/user-data`;

// ── Telegram WebApp ────────────────────────────────────────────────────────
const tg = window.Telegram?.WebApp;

if (tg) {
  tg.ready();
  tg.expand();
  tg.setHeaderColor?.("#0d0d1a");
  tg.setBackgroundColor?.("#0d0d1a");
}

// ── SVG Gradient для кольца ────────────────────────────────────────────────
(function addRingGradient() {
  const svg = document.querySelector(".ring-svg");
  if (!svg) return;
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `
    <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="#7c6af7" />
      <stop offset="100%" stop-color="#a78bfa" />
    </linearGradient>`;
  svg.prepend(defs);
})();

// ── Дата в шапке ──────────────────────────────────────────────────────────
(function setDate() {
  const el = document.getElementById("header-date");
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleDateString("ru-RU", {
    day: "numeric", month: "short"
  });
})();

// ── Утилиты ───────────────────────────────────────────────────────────────
function show(id)   { document.getElementById(id)?.classList.remove("hidden"); }
function hide(id)   { document.getElementById(id)?.classList.add("hidden"); }
function text(id, v){ const el = document.getElementById(id); if (el) el.textContent = v; }

function setBarWidth(id, current, target) {
  const el = document.getElementById(id);
  if (!el) return;
  const pct = target > 0 ? Math.min(100, Math.round(current / target * 100)) : 0;
  // Небольшая задержка для анимации
  requestAnimationFrame(() => {
    setTimeout(() => { el.style.width = pct + "%"; }, 100);
  });
}

function setRing(percent) {
  const ring = document.getElementById("calRing");
  if (!ring) return;
  const circumference = 2 * Math.PI * 80; // ≈ 502.65
  const offset = circumference * (1 - Math.min(1, percent / 100));
  requestAnimationFrame(() => {
    setTimeout(() => {
      ring.style.strokeDashoffset = offset.toFixed(2);
    }, 150);
  });
}

// ── Главная функция загрузки ──────────────────────────────────────────────
async function loadData() {
  // Показываем загрузчик
  hide("error");
  hide("no-profile");
  hide("dashboard");
  show("loading");

  // Получаем initData из Telegram WebApp
  const initData = tg?.initData || "";

  // В dev-режиме (не Telegram) — показываем демо-данные
  if (!initData) {
    console.warn("Not running inside Telegram — showing demo data");
    renderData({
      calories_current: 1240,
      calories_target:  2966,
      protein_current:  87,
      protein_target:   136,
      fat_current:      45,
      fat_target:       68,
      carbs_current:    120,
      carbs_target:     452,
      progress_percent: 42,
      goal:             "набор массы",
      current_weight:   72.5,
    });
    return;
  }

  try {
    const response = await fetch(`${API_URL}?initData=${encodeURIComponent(initData)}`, {
      method: "GET",
      headers: { "Accept": "application/json" },
    });

    if (response.status === 401) {
      throw new Error("Ошибка авторизации. Попробуй перезапустить приложение.");
    }
    if (response.status === 404) {
      hide("loading");
      show("no-profile");
      return;
    }
    if (!response.ok) {
      throw new Error(`Ошибка сервера (${response.status}). Попробуй позже.`);
    }

    const data = await response.json();
    renderData(data);

  } catch (err) {
    console.error("loadData error:", err);
    hide("loading");
    document.getElementById("error-msg").textContent =
      err.message || "Проверь соединение и попробуй снова.";
    show("error");
  }
}

// ── Рендер дашборда ───────────────────────────────────────────────────────
function renderData(d) {
  // Цель
  const goalLabel = d.goal
    ? d.goal.charAt(0).toUpperCase() + d.goal.slice(1)
    : "Твой рацион";
  text("header-goal", `🎯 ${goalLabel}`);

  // Кольцо калорий
  text("cal-current", d.calories_current.toLocaleString("ru-RU"));
  text("cal-target",  d.calories_target.toLocaleString("ru-RU"));
  text("pct",        `${d.progress_percent}%`);

  const left = Math.max(0, d.calories_target - d.calories_current);
  text("cal-left", left > 0 ? `${left.toLocaleString("ru-RU")} ккал` : "✅ Норма");

  setRing(d.progress_percent);

  // Макронутриенты
  text("pro-cur", d.protein_current);
  text("pro-tgt", d.protein_target);
  text("fat-cur", d.fat_current);
  text("fat-tgt", d.fat_target);
  text("car-cur", d.carbs_current);
  text("car-tgt", d.carbs_target);

  setBarWidth("bar-protein", d.protein_current, d.protein_target);
  setBarWidth("bar-fat",     d.fat_current,     d.fat_target);
  setBarWidth("bar-carbs",   d.carbs_current,   d.carbs_target);

  // Вес
  if (d.current_weight) {
    text("weight-val", `${d.current_weight} кг`);
  }

  // Показываем дашборд
  hide("loading");
  show("dashboard");
}

// ── Запуск ────────────────────────────────────────────────────────────────
loadData();
