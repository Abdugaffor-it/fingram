const statusEl = document.getElementById("status");
const authPanel = document.getElementById("auth-panel");
const appPanel = document.getElementById("app-panel");
const entriesEl = document.getElementById("entries");
const entriesAllEl = document.getElementById("entries-all");
const filterFormEl = document.getElementById("entries-filter-form");
const filterTypeEl = document.getElementById("filter-type");
const filterCategoryEl = document.getElementById("filter-category");
const filterFromEl = document.getElementById("filter-from");
const filterToEl = document.getElementById("filter-to");
const filterSortEl = document.getElementById("filter-sort");
const filterLimitEl = document.getElementById("filter-limit");
const filterResetEl = document.getElementById("filter-reset");
const userNameEl = document.getElementById("user-name");
const statIncomeEl = document.getElementById("stat-income");
const statExpenseEl = document.getElementById("stat-expense");
const statNetEl = document.getElementById("stat-net");
const todayCategoriesEl = document.getElementById("today-categories");
const monthCategoriesEl = document.getElementById("month-categories");
const weekTrendEl = document.getElementById("week-trend");
const weekTrendAnalyticsEl = document.getElementById("week-trend-analytics");
const incomeCategoriesAnalyticsEl = document.getElementById("income-categories-analytics");
const expenseCategoriesAnalyticsEl = document.getElementById("expense-categories-analytics");
const monthSeriesEl = document.getElementById("month-series");
const monthCompareEl = document.getElementById("month-compare");
const cashflowChartEl = document.getElementById("cashflow-chart");
const kpiGridEl = document.getElementById("kpi-grid");
const expenseConcentrationEl = document.getElementById("expense-concentration");
const adviceListEl = document.getElementById("advice-list");
const menuToggleEl = document.getElementById("menu-toggle");
const menuPanelEl = document.getElementById("menu-panel");
const menuItems = Array.from(document.querySelectorAll(".menu-item"));
const settingsNameEl = document.getElementById("settings-name");
const settingsCurrencyEl = document.getElementById("settings-currency");
const settingsIncomeTargetEl = document.getElementById("settings-income-target");
const settingsSavingsGoalEl = document.getElementById("settings-savings-goal");
const settingsEfMonthsEl = document.getElementById("settings-ef-months");
const telegramOpenEl = document.getElementById("telegram-open");
const telegramOpenHintEl = document.getElementById("telegram-open-hint");
const entryTypeEl = document.getElementById("entry-type");
const entryCategoryEl = document.getElementById("entry-category");
const entryDateEl = document.getElementById("entry-date");
const expenseCategoriesEl = document.getElementById("expense-categories");
const incomeCategoriesEl = document.getElementById("income-categories");
const goAnalyticsEl = document.getElementById("go-analytics");
const viewHomeEl = document.getElementById("view-home");
const viewAnalyticsEl = document.getElementById("view-analytics");
const viewProfileEl = document.getElementById("view-profile");
const toastEl = document.getElementById("toast");
let currentCurrency = "USD";
let menuBound = false;
let menuOpen = false;
let telegramAutoLoginAttempted = false;

function setStatus(message) {
  statusEl.textContent = message || "";
}

function todayInputValue() {
  return new Date().toISOString().slice(0, 10);
}

function formatEntryDate(value) {
  if (!value) return "-";
  const day = String(value).slice(0, 10);
  const date = new Date(`${day}T00:00:00`);
  if (Number.isNaN(date.getTime())) return day;
  return date.toLocaleDateString();
}

function showToast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  setTimeout(() => toastEl.classList.remove("show"), 2200);
}

function setAuthState(isAuthed) {
  authPanel.classList.toggle("hidden", isAuthed);
  appPanel.classList.toggle("hidden", !isAuthed);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    ...options,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "request_failed");
  }
  return data;
}

async function loadMe() {
  try {
    const data = await api("/api/me");
    userNameEl.textContent = data.user.display_name || data.user.email || "—";
    if (data.user.preferred_currency) {
      currentCurrency = data.user.preferred_currency;
      settingsCurrencyEl.value = data.user.preferred_currency;
    }
    settingsNameEl.value = data.user.display_name || "";
    settingsIncomeTargetEl.value = data.user.monthly_income_target || "";
    settingsSavingsGoalEl.value = data.user.monthly_savings_goal || "";
    settingsEfMonthsEl.value = data.user.emergency_fund_target_months || 3;
    setAuthState(true);
    await Promise.all([loadEntries(10, entriesEl), loadAnalytics()]);
  } catch (err) {
    setAuthState(false);
  }
}

async function loadEntries(limit, target) {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  const data = await api(`/api/entries?${params.toString()}`);
  target.innerHTML = "";
  if (!data.entries.length) {
    target.innerHTML = "<div class=\"entry\">Нет записей</div>";
    return;
  }
  data.entries.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "entry";
    const sign = entry.type === "income" ? "+" : "-";
    const typeLabel = entry.type === "income" ? "Доход" : "Расход";
    const noteHtml = entry.note ? `<div class="entry-meta">${entry.note}</div>` : "";
    item.innerHTML = `
      <div class="entry-details">
        <div>${entry.category} <span class="entry-tag">${typeLabel}</span></div>
        <div class="entry-meta">${formatEntryDate(entry.occurred_at)}</div>
        ${noteHtml}
      </div>
      <div class="amount">${sign}${entry.amount} ${entry.currency}</div>
    `;
    target.appendChild(item);
  });
}

async function loadFilteredEntries() {
  const params = new URLSearchParams();
  const limit = filterLimitEl.value || "100";
  params.set("limit", limit);
  if (filterFromEl.value) params.set("from", filterFromEl.value);
  if (filterToEl.value) params.set("to", filterToEl.value);

  const data = await api(`/api/entries?${params.toString()}`);
  let entries = data.entries || [];

  if (filterTypeEl.value) {
    entries = entries.filter((e) => e.type === filterTypeEl.value);
  }
  if (filterCategoryEl.value.trim()) {
    const term = filterCategoryEl.value.trim().toLowerCase();
    entries = entries.filter((e) => (e.category || "").toLowerCase().includes(term));
  }
  if (filterSortEl.value === "amount_desc") {
    entries.sort((a, b) => b.amount - a.amount);
  } else if (filterSortEl.value === "amount_asc") {
    entries.sort((a, b) => a.amount - b.amount);
  } else if (filterSortEl.value === "date_asc") {
    entries.sort((a, b) => new Date(a.occurred_at) - new Date(b.occurred_at));
  } else {
    entries.sort((a, b) => new Date(b.occurred_at) - new Date(a.occurred_at));
  }

  entriesAllEl.innerHTML = "";
  if (!entries.length) {
    entriesAllEl.innerHTML = "<div class=\"entry\">Нет записей</div>";
    return;
  }
  entries.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "entry";
    const sign = entry.type === "income" ? "+" : "-";
    const typeLabel = entry.type === "income" ? "Доход" : "Расход";
    const noteHtml = entry.note ? `<div class=\"entry-meta\">${entry.note}</div>` : "";
    item.innerHTML = `
      <div class="entry-details">
        <div>${entry.category} <span class="entry-tag">${typeLabel}</span></div>
        <div class="entry-meta">${formatEntryDate(entry.occurred_at)}</div>
        ${noteHtml}
      </div>
      <div class="amount">${sign}${entry.amount} ${entry.currency}</div>
    `;
    entriesAllEl.appendChild(item);
  });
}

function applyStats(data) {
  statIncomeEl.textContent = `${data.month_totals.income.toFixed(2)} ${currentCurrency}`;
  statExpenseEl.textContent = `${data.month_totals.expense.toFixed(2)} ${currentCurrency}`;
  statNetEl.textContent = `${data.month_totals.net.toFixed(2)} ${currentCurrency}`;
}

function renderCategoryList(container, items) {
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = "<div class=\"label-small\">Нет данных</div>";
    return;
  }
  const max = Math.max(...items.map((item) => item.total));
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "category-item";
    const percent = max ? Math.round((item.total / max) * 100) : 0;
    row.innerHTML = `
      <div class="label-small">${item.category}</div>
      <div class="bar"><span style="width:${percent}%"></span></div>
      <div class="label-small">${item.total.toFixed(2)} ${currentCurrency}</div>
    `;
    container.appendChild(row);
  });
}

function renderTrend(container, items) {
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = "<div class=\"label-small\">Нет данных</div>";
    return;
  }
  const max = Math.max(...items.map((item) => item.total));
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "trend-item";
    const percent = max ? Math.round((item.total / max) * 100) : 0;
    row.innerHTML = `
      <div class="label-small">${item.day}</div>
      <div class="bar"><span style="width:${percent}%"></span></div>
      <div class="label-small">${item.total.toFixed(2)} ${currentCurrency}</div>
    `;
    container.appendChild(row);
  });
}

function renderMonthSeries(container, items) {
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = "<div class=\"label-small\">Нет данных</div>";
    return;
  }
  const max = Math.max(...items.flatMap((item) => [item.income, item.expense]));
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "dual-bar";
    const incomePct = max ? Math.round((item.income / max) * 100) : 0;
    const expensePct = max ? Math.round((item.expense / max) * 100) : 0;
    row.innerHTML = `
      <div class="label-small">${item.month}</div>
      <div class="bars">
        <div class="bar"><span style="width:${incomePct}%"></span></div>
        <div class="bar expense"><span style="width:${expensePct}%"></span></div>
      </div>
    `;
    container.appendChild(row);
  });
}

function renderMonthCompare(container, data) {
  container.innerHTML = `
    <div class="compare-card">
      <div class="label-small">Доход</div>
      <div class="value">${data.income_diff.toFixed(2)} ${currentCurrency}</div>
    </div>
    <div class="compare-card">
      <div class="label-small">Расход</div>
      <div class="value">${data.expense_diff.toFixed(2)} ${currentCurrency}</div>
    </div>
    <div class="compare-card">
      <div class="label-small">Итог</div>
      <div class="value">${data.net_diff.toFixed(2)} ${currentCurrency}</div>
    </div>
  `;
}

function renderCashflowChart(container, series) {
  if (!container) return;
  if (!series || !series.length) {
    container.innerHTML = "<div class=\"label-small\">Нет данных</div>";
    return;
  }
  const width = 320;
  const height = 140;
  const padding = 10;
  const maxVal = Math.max(
    ...series.flatMap((item) => [item.income || 0, item.expense || 0])
  );
  const scaleY = (val) =>
    height - padding - (maxVal ? (val / maxVal) * (height - padding * 2) : 0);
  const stepX = (width - padding * 2) / (series.length - 1 || 1);
  const incomePoints = series
    .map((item, idx) => `${padding + idx * stepX},${scaleY(item.income || 0)}`)
    .join(" ");
  const expensePoints = series
    .map((item, idx) => `${padding + idx * stepX},${scaleY(item.expense || 0)}`)
    .join(" ");
  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}">
      <polyline fill="none" stroke="#d94f2a" stroke-width="2" points="${incomePoints}" />
      <polyline fill="none" stroke="#2b6b58" stroke-width="2" points="${expensePoints}" />
    </svg>
  `;
}

function renderKpis(container, data) {
  if (!container) return;
  const savingsRate = (data.savings_rate * 100).toFixed(1);
  const expenseRatio = (data.expense_ratio * 100).toFixed(1);
  container.innerHTML = `
    <div class="kpi-card">
      <div class="label-small">Норма сбережений</div>
      <div class="value">${savingsRate}%</div>
    </div>
    <div class="kpi-card">
      <div class="label-small">Доля расходов</div>
      <div class="value">${expenseRatio}%</div>
    </div>
    <div class="kpi-card">
      <div class="label-small">Средний расход в день</div>
      <div class="value">${data.avg_daily_expense.toFixed(2)} ${currentCurrency}</div>
    </div>
    <div class="kpi-card">
      <div class="label-small">Средний доход в день</div>
      <div class="value">${data.avg_daily_income.toFixed(2)} ${currentCurrency}</div>
    </div>
  `;
}

function renderExpenseConcentration(container, data) {
  if (!container) return;
  const share = Math.round((data.top_expense_share || 0) * 100);
  container.innerHTML = `
    <div class="ratio-track"><span style="width:${share}%"></span></div>
    <div class="label-small">${share}% в топ‑категории</div>
  `;
}

function renderAdvice(container, items) {
  if (!container) return;
  if (!items || !items.length) {
    container.innerHTML = "<div class=\"label-small\">Нет советов</div>";
    return;
  }
  container.innerHTML = items
    .map((item) => `<div class="advice-item">${item}</div>`)
    .join("");
}

async function loadAnalytics() {
  const data = await api("/api/analytics");
  applyStats(data);
  renderCategoryList(todayCategoriesEl, data.today_categories);
  renderCategoryList(monthCategoriesEl, data.month_top_categories);
  renderTrend(weekTrendEl, data.last_7_days);
  renderTrend(weekTrendAnalyticsEl, data.last_7_days);
  renderCategoryList(incomeCategoriesAnalyticsEl, data.month_income_categories);
  renderCategoryList(expenseCategoriesAnalyticsEl, data.month_top_categories);
  renderMonthSeries(monthSeriesEl, data.month_series);
  renderMonthCompare(monthCompareEl, data.month_comparison);
  renderCashflowChart(cashflowChartEl, data.cashflow_series);
  renderKpis(kpiGridEl, data);
  renderExpenseConcentration(expenseConcentrationEl, data);
  renderAdvice(adviceListEl, data.advice);
}

function hookTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((el) => el.classList.remove("active"));
      tab.classList.add("active");
      const target = tab.dataset.tab;
      document.querySelectorAll("[data-form]").forEach((form) => {
        form.classList.toggle("hidden", form.dataset.form !== target);
      });
    });
  });
}

async function handleAuthForm(event) {
  event.preventDefault();
  const form = event.target;
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    setStatus("Отправка...");
    if (form.dataset.form === "login") {
      await api("/api/auth/login", { method: "POST", body: JSON.stringify(payload) });
    } else {
      await api("/api/auth/register", { method: "POST", body: JSON.stringify(payload) });
    }
    setStatus("Успешно");
    await loadMe();
  } catch (err) {
    setStatus(`Ошибка: ${err.message}`);
  }
}

async function handleEntry(event) {
  event.preventDefault();
  const form = event.target;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.amount = parseFloat(payload.amount);
  try {
    setStatus("Сохранение...");
    await api("/api/entries", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    entryTypeEl.value = "income";
    entryCategoryEl.value = "Зарплата";
    entryDateEl.value = todayInputValue();
    setButtonGroupState(document.querySelector("[data-group='type']"), "income");
    switchCategorySet("income");
    setStatus("Готово");
    await Promise.all([loadEntries(10, entriesEl), loadAnalytics()]);
  } catch (err) {
    setStatus(`Ошибка: ${err.message}`);
  }
}

async function handleLogout() {
  await api("/api/auth/logout", { method: "POST" });
  setAuthState(false);
}

async function handleSettings(event) {
  event.preventDefault();
  const payload = {
    display_name: settingsNameEl.value.trim(),
    preferred_currency: settingsCurrencyEl.value,
    monthly_income_target: settingsIncomeTargetEl.value || null,
    monthly_savings_goal: settingsSavingsGoalEl.value || null,
    emergency_fund_target_months: settingsEfMonthsEl.value || null,
  };
  try {
    setStatus("Сохранение настроек...");
    await api("/api/profile", { method: "PATCH", body: JSON.stringify(payload) });
    currentCurrency = settingsCurrencyEl.value;
    await loadMe();
    showToast("Настройки сохранены. Валюта обновлена.");
  } catch (err) {
    setStatus(`Ошибка: ${err.message}`);
  }
}

async function handleTelegramAuth() {
  if (!window.Telegram || !window.Telegram.WebApp) {
    setStatus("Telegram Web App API не найден");
    return;
  }
  const initData = window.Telegram.WebApp.initData;
  if (!initData) {
    setStatus("Telegram initData не найден");
    return;
  }
  try {
    setStatus("Проверка Telegram...");
    await api("/api/auth/telegram", {
      method: "POST",
      body: JSON.stringify({ initData }),
    });
    await loadMe();
    setStatus("Telegram авторизация успешна");
  } catch (err) {
    if (err.message === "invalid_init_data") {
      setStatus("Telegram initData отклонен сервером");
      return;
    }
    setStatus(`Ошибка: ${err.message}`);
  }
}

function initTelegramUI() {
  if (window.Telegram && window.Telegram.WebApp) {
    window.Telegram.WebApp.ready();
    window.Telegram.WebApp.expand();
  }
}

async function autoLoginTelegram() {
  if (telegramAutoLoginAttempted) return;
  telegramAutoLoginAttempted = true;
  if (!window.Telegram || !window.Telegram.WebApp) return;
  if (!window.Telegram.WebApp.initData) {
    setStatus("Telegram Web App открыт без initData");
    return;
  }
  await handleTelegramAuth();
}

function setButtonGroupState(container, value) {
  if (!container) return;
  container.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.value === value);
  });
}

function switchCategorySet(type) {
  if (type === "expense") {
    expenseCategoriesEl.classList.remove("hidden");
    incomeCategoriesEl.classList.add("hidden");
    entryCategoryEl.value = "Продукты";
    setButtonGroupState(expenseCategoriesEl, "Продукты");
  } else {
    incomeCategoriesEl.classList.remove("hidden");
    expenseCategoriesEl.classList.add("hidden");
    entryCategoryEl.value = "Зарплата";
    setButtonGroupState(incomeCategoriesEl, "Зарплата");
  }
}

function hookButtonGroups() {
  document.querySelectorAll("[data-group]").forEach((group) => {
    group.addEventListener("click", (event) => {
      const btn = event.target.closest("button");
      if (!btn) return;
      setButtonGroupState(group, btn.dataset.value);
      if (group.dataset.group === "type") {
        entryTypeEl.value = btn.dataset.value;
        switchCategorySet(btn.dataset.value);
      }
      if (group.dataset.group === "category") {
        entryCategoryEl.value = btn.dataset.value;
      }
    });
  });
}

function setMenuOpen(open) {
  menuOpen = open;
  if (open) {
    menuPanelEl.classList.remove("hidden");
    menuToggleEl.setAttribute("aria-expanded", "true");
  } else {
    menuPanelEl.classList.add("hidden");
    menuToggleEl.setAttribute("aria-expanded", "false");
  }
}

function hookMenu() {
  if (menuBound || !menuToggleEl || !menuPanelEl) return;
  menuBound = true;
  setMenuOpen(false);

  const toggle = (event) => {
    event.preventDefault();
    event.stopPropagation();
    setMenuOpen(!menuOpen);
  };

  menuToggleEl.addEventListener("click", toggle);

  menuPanelEl.addEventListener("click", (event) => event.stopPropagation());
  menuPanelEl.addEventListener("pointerdown", (event) => event.stopPropagation());

  document.addEventListener("click", (event) => {
    if (!menuPanelEl.contains(event.target) && !menuToggleEl.contains(event.target)) {
      setMenuOpen(false);
    }
  });
}

function setView(view) {
  viewHomeEl.classList.toggle("hidden", view !== "home");
  viewAnalyticsEl.classList.toggle("hidden", view !== "analytics");
  viewProfileEl.classList.toggle("hidden", view !== "profile");
  menuItems.forEach((item) => item.classList.toggle("active", item.dataset.view === view));
}

function hookViews() {
  menuItems.forEach((item) => {
    item.addEventListener("click", () => {
      setView(item.dataset.view);
      if (item.dataset.view === "analytics") {
        loadFilteredEntries();
      }
    });
  });
  goAnalyticsEl.addEventListener("click", () => {
    setView("analytics");
    loadFilteredEntries();
  });
}

async function loadConfig() {
  try {
    const data = await api("/api/config");
    const bot = data.telegram.bot_username;
    if (bot) {
      const link = `https://t.me/${bot}?startapp=main`;
      telegramOpenEl.href = link;
      telegramOpenEl.classList.remove("disabled");
      telegramOpenHintEl.textContent = "Откроется бот с Web App.";
      telegramOpenEl.addEventListener("click", (event) => {
        if (window.Telegram && window.Telegram.WebApp) {
          event.preventDefault();
          window.Telegram.WebApp.openTelegramLink(link);
        }
      });
    } else {
      telegramOpenEl.classList.add("disabled");
    }
  } catch (err) {
    telegramOpenEl.classList.add("disabled");
  }
}

hookTabs();
initTelegramUI();
hookButtonGroups();
switchCategorySet("income");
setButtonGroupState(document.querySelector("[data-group='type']"), "income");
hookMenu();
hookViews();
loadConfig();
if (entryDateEl) {
  entryDateEl.value = todayInputValue();
}

const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const entryForm = document.getElementById("entry-form");
const logoutBtn = document.getElementById("logout");
const telegramAuthBtn = document.getElementById("telegram-auth");
const settingsForm = document.getElementById("settings-form");

loginForm.addEventListener("submit", handleAuthForm);
registerForm.addEventListener("submit", handleAuthForm);
entryForm.addEventListener("submit", handleEntry);
logoutBtn.addEventListener("click", handleLogout);
telegramAuthBtn.addEventListener("click", handleTelegramAuth);
settingsForm.addEventListener("submit", handleSettings);

goAnalyticsEl.addEventListener("click", () => {
  setView("analytics");
  loadFilteredEntries();
});

setView("home");
loadMe();
autoLoginTelegram();

if (filterFormEl) {
  filterFormEl.addEventListener("submit", (event) => {
    event.preventDefault();
    loadFilteredEntries();
  });
}

if (filterResetEl) {
  filterResetEl.addEventListener("click", () => {
    filterTypeEl.value = "";
    filterCategoryEl.value = "";
    filterFromEl.value = "";
    filterToEl.value = "";
    filterSortEl.value = "date_desc";
    filterLimitEl.value = "100";
    loadFilteredEntries();
  });
}
