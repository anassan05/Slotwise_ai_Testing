const today = new Date().toISOString().slice(0, 10);

const state = {
  appointments: [],
  history: [],
  services: [],
  statusFilter: "ALL",
  calendarMonth: new Date(`${today}-01T00:00:00`),
  activeScreen: "overview-screen",
  dashboardRequest: 0,
};

const form = document.querySelector("#appointment-form");
const message = document.querySelector("#message");

if (form) {
  setDateValue(today);
}

document.querySelectorAll(".icon-slot").forEach((slot) => {
  slot.outerHTML = icon(slot.dataset.icon);
});

document.querySelector("#current-date").textContent = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
}).format(new Date());

document.addEventListener("click", (event) => {
  const dateOption = event.target.closest("[data-date]");
  if (dateOption) {
    setDateValue(dateOption.dataset.date);
    loadAvailability();
    closePickers();
    return;
  }
  const dateNav = event.target.closest("[data-calendar-nav]");
  if (dateNav) {
    state.calendarMonth.setMonth(state.calendarMonth.getMonth() + Number(dateNav.dataset.calendarNav));
    renderDatePicker();
    return;
  }
  const timeOption = event.target.closest("[data-time-value]");
  if (timeOption) {
    updateTimeSelection(timeOption.dataset.timeTarget, timeOption.dataset.timePart, timeOption.dataset.timeValue);
    renderTimePicker(timeOption.dataset.timeTarget);
    return;
  }
  const pickerClose = event.target.closest(".picker-close");
  if (pickerClose) {
    pickerClose.closest(".picker-menu").hidden = true;
    return;
  }
  const pickerTrigger = event.target.closest(".picker-trigger");
  if (pickerTrigger) {
    const picker = pickerTrigger.closest(".picker");
    closePickers(picker);
    const menu = picker.querySelector(".picker-menu");
    menu.hidden = false;
    if (picker.dataset.picker === "date") renderDatePicker();
    if (picker.dataset.picker === "time") renderTimePicker(picker.dataset.timeTarget);
    return;
  }
  const statusOption = event.target.closest("[data-status]");
  if (statusOption) {
    state.statusFilter = statusOption.dataset.status;
    document.querySelector("#appointment-status-button").firstChild.textContent = statusLabel(state.statusFilter);
    closeStatusMenu();
    renderAppointments();
    return;
  }
  const statusButton = event.target.closest("#appointment-status-button");
  if (statusButton) {
    const menu = document.querySelector("#appointment-status-menu");
    menu.hidden = !menu.hidden;
    statusButton.setAttribute("aria-expanded", String(!menu.hidden));
    closePickers();
    return;
  }
  if (!event.target.closest(".picker") && !event.target.closest(".select-control")) {
    closePickers();
    closeStatusMenu();
  }
  const screenTarget = event.target.closest("[data-screen]");
  if (screenTarget) {
    event.preventDefault();
    showScreen(screenTarget.dataset.screen);
  }

  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) return;
  const action = actionTarget.dataset.action;
  if (action === "toggle-sidebar") {
    if (window.matchMedia("(max-width: 820px)").matches) {
      document.body.classList.toggle("sidebar-open");
    } else {
      document.body.classList.toggle("sidebar-collapsed");
    }
  }
  if (action === "close-sidebar") document.body.classList.remove("sidebar-open");
  if (action === "focus-booking") {
    showScreen("appointments-screen");
    window.setTimeout(() => form?.patient_name.focus(), 50);
  }
});

function setDateValue(value) {
  const input = document.querySelector("#appointment-date");
  const display = document.querySelector("#appointment-date-display");
  if (!input || !display) return;
  input.value = value;
  display.value = formatDate(value);
  state.calendarMonth = new Date(`${value.slice(0, 7)}-01T00:00:00`);
}

function setTimeValue(target, value) {
  const input = document.querySelector(`#${target}-time`);
  const display = document.querySelector(`#${target}-time-display`);
  if (!input || !display) return;
  input.value = value;
  display.value = formatTime(value);
}

function renderDatePicker() {
  const menu = document.querySelector("#date-picker");
  if (!menu) return;
  const year = state.calendarMonth.getFullYear();
  const month = state.calendarMonth.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const selected = document.querySelector("#appointment-date").value;
  const cells = [];
  for (let index = 0; index < firstDay; index += 1) cells.push('<span class="calendar-empty"></span>');
  for (let day = 1; day <= daysInMonth; day += 1) {
    const value = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const disabled = value < today ? " disabled" : "";
    const current = value === selected ? " selected" : "";
    cells.push(`<button class="calendar-day${current}" type="button" data-date="${value}"${disabled}>${day}</button>`);
  }
  menu.innerHTML = `<div class="picker-header"><button type="button" data-calendar-nav="-1" aria-label="Previous month">${icon("chevron-left")}</button><strong>${state.calendarMonth.toLocaleDateString("en-US", { month: "long", year: "numeric" })}</strong><button type="button" data-calendar-nav="1" aria-label="Next month">${icon("chevron-right")}</button></div><div class="calendar-weekdays"><span>Su</span><span>Mo</span><span>Tu</span><span>We</span><span>Th</span><span>Fr</span><span>Sa</span></div><div class="calendar-grid">${cells.join("")}</div><div class="picker-footer"><button type="button" data-date="${today}">Today</button></div>`;
}

function renderTimePicker(target) {
  const menu = document.querySelector(`#${target}-time-picker`);
  if (!menu) return;
  const current = parseTime(document.querySelector(`#${target}-time`).value);
  const hours = Array.from({ length: 12 }, (_, index) => index + 1).map((hour) => timeOption(target, "hour", String(hour).padStart(2, "0"), hour === current.hour));
  const minutes = Array.from({ length: 12 }, (_, index) => index * 5).map((minute) => timeOption(target, "minute", String(minute).padStart(2, "0"), minute === current.minute));
  menu.innerHTML = `<div class="picker-header"><strong>Select time</strong><button type="button" class="picker-close" aria-label="Close time picker">${icon("x")}</button></div><div class="time-columns"><div><span class="time-label">Hour</span>${hours.join("")}</div><div><span class="time-label">Minute</span>${minutes.join("")}</div><div><span class="time-label">Period</span>${["AM", "PM"].map((period) => timeOption(target, "period", period, period === current.period)).join("")}</div></div>`;
}

function timeOption(target, part, value, selected) {
  return `<button type="button" class="time-option${selected ? " selected" : ""}" data-time-target="${target}" data-time-part="${part}" data-time-value="${value}">${value}</button>`;
}

function updateTimeSelection(target, part, value) {
  const current = parseTime(document.querySelector(`#${target}-time`).value);
  if (part === "hour") current.hour = Number(value);
  if (part === "minute") current.minute = Number(value);
  if (part === "period") current.period = value;
  let hour = current.hour % 12;
  if (current.period === "PM") hour += 12;
  setTimeValue(target, `${String(hour).padStart(2, "0")}:${String(current.minute).padStart(2, "0")}`);
}

function parseTime(value) {
  const [hour, minute] = (value || "09:00").split(":").map(Number);
  return { hour: hour % 12 || 12, minute, period: hour >= 12 ? "PM" : "AM" };
}

function closePickers(except = null) {
  document.querySelectorAll(".picker-menu").forEach((menu) => {
    if (!except || !except.contains(menu)) menu.hidden = true;
  });
}

function closeStatusMenu() {
  const menu = document.querySelector("#appointment-status-menu");
  const button = document.querySelector("#appointment-status-button");
  if (menu) menu.hidden = true;
  if (button) button.setAttribute("aria-expanded", "false");
}

function statusLabel(value) {
  return { ALL: "All statuses", BOOKED: "Booked", CANCELLED: "Cancelled" }[value] || "All statuses";
}

function showScreen(screenId) {
  const target = document.querySelector(`#${screenId}`);
  if (!target) return;
  state.activeScreen = screenId;
  document.querySelectorAll(".screen").forEach((screen) => screen.classList.toggle("active", screen.id === screenId));
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.screen === screenId));
  document.querySelector("#page-kicker").textContent = target.dataset.title;
  document.body.classList.remove("sidebar-open");
}

function showMessage(text, type = "success") {
  message.textContent = text;
  message.className = `toast show ${type}`;
  window.clearTimeout(showMessage.timer);
  showMessage.timer = window.setTimeout(() => {
    message.textContent = "";
    message.className = "toast";
  }, 5200);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Request failed.");
  return body;
}

async function loadDashboard(animateTestPilot = false) {
  const requestId = ++state.dashboardRequest;
  try {
    const [appointmentsBody, statsBody, summaryBody, historyBody, servicesBody] = await Promise.all([
      requestJson("/api/appointments"),
      requestJson("/api/stats"),
      requestJson("/api/database/summary"),
      requestJson("/api/testpilot/history"),
      requestJson("/api/services"),
    ]);
    if (requestId !== state.dashboardRequest) return;
    state.appointments = appointmentsBody.appointments;
    state.history = historyBody.history;
    state.services = servicesBody.services;
    renderStats(statsBody.stats, summaryBody.database);
    renderAppointments();
    renderServiceOptions();
    await loadAvailability();
    renderOverview();
    await renderTestPilot(animateTestPilot);
    renderHistory();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

function renderServiceOptions() {
  const select = document.querySelector("#service-select");
  if (!select) return;
  const selected = select.value || state.services[0]?.id || "";
  select.innerHTML = `<option value="">Select appointment type</option>${state.services.map((service) => `<option value="${escapeHtml(service.id)}">${escapeHtml(service.name)} · ${service.duration_minutes} min</option>`).join("")}`;
  select.value = selected;
  updateServiceDuration();
}

async function loadAvailability() {
  const dateValue = document.querySelector("#appointment-date")?.value;
  const serviceId = document.querySelector("#service-select")?.value;
  const select = document.querySelector("#start-time");
  if (!select || !dateValue || !serviceId) return;
  select.innerHTML = '<option value="">Loading available times...</option>';
  try {
    const body = await requestJson(`/api/availability?date=${encodeURIComponent(dateValue)}&service_id=${encodeURIComponent(serviceId)}`);
    const available = body.slots.filter((slot) => slot.available);
    select.innerHTML = available.length
      ? `<option value="">Select a start time</option>${available.map((slot) => `<option value="${slot.start_time}" data-end-time="${slot.end_time}">${formatTime(slot.start_time)} – ${formatTime(slot.end_time)}</option>`).join("")}`
      : '<option value="">No available times</option>';
    updateAppointmentSummary();
  } catch (error) {
    select.innerHTML = '<option value="">Unable to load times</option>';
    showMessage(error.message, "error");
  }
}

function updateServiceDuration() {
  const service = state.services.find((item) => item.id === document.querySelector("#service-select")?.value);
  setText("service-duration", service ? `${service.duration_minutes} minute appointment` : "");
  updateAppointmentSummary();
}

function updateAppointmentSummary() {
  const summary = document.querySelector("#appointment-summary");
  const select = document.querySelector("#start-time");
  const service = state.services.find((item) => item.id === document.querySelector("#service-select")?.value);
  const option = select?.selectedOptions[0];
  if (!summary || !service || !option?.value) {
    if (summary) summary.innerHTML = `<span>${icon("clock")}</span><span>Select a service and start time to see the appointment duration.</span>`;
    return;
  }
  summary.innerHTML = `<span>${icon("clock")}</span><strong>${formatTime(option.value)} – ${formatTime(option.dataset.endTime)}</strong><small>${service.duration_minutes} minutes · End time calculated by SlotWise</small>`;
}

function renderStats(stats, database) {
  setText("overview-total", stats.total);
  setText("overview-upcoming", stats.upcoming);
  setText("overview-cancelled", stats.cancelled);
  setText("nav-appointment-count", stats.upcoming);
  setText("sql-records", `${database.tables.appointments} appointments`);
  const latest = database.latest_run;
  setText("overview-pass-rate", latest ? `${latest.pass_percentage}%` : "--");
  setText("overview-test-caption", latest ? `${latest.passed}/${latest.total} scenarios passed` : "No test run recorded");
}

function renderOverview() {
  const upcoming = state.appointments
    .filter((item) => item.status === "BOOKED" && item.appointment_date >= today)
    .sort((a, b) => `${a.appointment_date}${a.start_time}`.localeCompare(`${b.appointment_date}${b.start_time}`))
    .slice(0, 5);
  const list = document.querySelector("#upcoming-list");
  list.innerHTML = upcoming.length ? upcoming.map((item) => compactAppointment(item)).join("") : emptyState("No upcoming appointments", "Your active future schedule will appear here.");

  const activity = document.querySelector("#overview-activity");
  activity.innerHTML = state.history.length ? state.history.slice(0, 4).map((run) => activityItem(run)).join("") : emptyState("No test runs yet", "Run TestPilot to create your first quality report.");
}

function compactAppointment(item) {
  return `<div class="compact-item"><span class="date-tile"><strong>${formatDay(item.appointment_date)}</strong><small>${formatMonth(item.appointment_date)}</small></span><span class="compact-copy"><strong>${escapeHtml(item.patient_name || item.customer_name)}</strong><small>${escapeHtml(item.service)} · ${item.start_time}–${item.end_time}</small></span><span class="status-badge booked">Booked</span></div>`;
}

function activityItem(run) {
  const passed = run.failed === 0;
  return `<div class="activity-item"><span class="activity-icon ${passed ? "activity-pass" : "activity-fail"}">${icon(passed ? "check" : "bug")}</span><span class="activity-copy"><strong>${escapeHtml(formatMode(run.mode))}</strong><small>${run.passed}/${run.total} passed · ${formatDateTime(run.started_at)}</small></span><span class="activity-result ${passed ? "positive" : "negative"}">${run.pass_percentage}%</span></div>`;
}

function renderAppointments() {
  const query = document.querySelector("#appointment-search")?.value.trim().toLowerCase() || "";
  const status = state.statusFilter;
  const filtered = state.appointments.filter((item) => {
    const matchesSearch = !query || `${item.patient_name || item.customer_name} ${item.mobile_number || ""} ${item.service}`.toLowerCase().includes(query);
    return matchesSearch && (status === "ALL" || item.status === status);
  });
  const body = document.querySelector("#appointment-table-body");
  const empty = document.querySelector("#appointment-empty");
  body.innerHTML = filtered.map(appointmentRow).join("");
  empty.classList.toggle("hidden", filtered.length > 0);
  empty.innerHTML = state.appointments.length ? emptyState("No matching appointments", "Try a different search or status filter.") : emptyState("No appointments yet", "Create your first booking using the form.");
}

function appointmentRow(item) {
  const canCancel = item.status === "BOOKED";
  const patient = item.patient_name || item.customer_name;
  return `<tr><td><span class="customer-cell"><span class="customer-avatar">${initials(patient)}</span><span><strong>${escapeHtml(patient)}</strong><small>${escapeHtml(item.mobile_number || "Legacy contact")}</small></span></span></td><td>${escapeHtml(item.service)}</td><td><strong>${formatDate(item.appointment_date)}</strong><small class="table-subtext">${item.start_time}–${item.end_time}</small></td><td><span class="status-badge ${item.status.toLowerCase()}"><span class="status-dot"></span>${item.status === "BOOKED" ? "Booked" : "Cancelled"}</span></td><td class="row-actions">${canCancel ? `<button class="table-action cancel-button" data-id="${item.id}" type="button">Cancel</button>` : `<span class="muted-action">Archived</span>`}</td></tr>`;
}

async function renderTestPilot(animate = false) {
  const latest = state.history[0];
  setText("qa-total", latest?.total ?? "--");
  setText("qa-passed", latest?.passed ?? "--");
  setText("qa-failed", latest?.failed ?? "--");
  setText("qa-pass-rate", latest ? `${latest.pass_percentage}%` : "--");
  setText("testpilot-summary", latest ? `${latest.passed}/${latest.total} passed` : "No run yet");
  const target = document.querySelector("#testpilot-latest");
  if (!latest) {
    target.innerHTML = emptyState("No execution recorded", "Run the suite to see expected versus actual results.");
  } else if (animate) {
    await playTestResults(latest);
  } else {
    target.innerHTML = latest.results.map(renderResult).join("");
  }
}

function renderHistory() {
  const target = document.querySelector("#testpilot-history");
  target.innerHTML = state.history.length ? state.history.map((run) => `<article class="history-run"><div class="history-run-top"><div><span class="history-mode">${escapeHtml(formatMode(run.mode))}</span><strong>${run.passed}/${run.total}</strong><small>${formatDateTime(run.started_at)} · ${run.failed} failed</small></div><span class="run-status ${run.failed ? "failed" : "passed"}">${run.pass_percentage}% pass</span></div><p>${escapeHtml(run.summary)}</p></article>`).join("") : emptyState("No test history", "Completed TestPilot runs will be saved here.");
}

function renderResult(result) {
  const passed = result.passed;
  const steps = (result.steps || []).map(renderExecutionStep).join("");
  return `<article class="result-row"><div class="result-status ${passed ? "passed" : "failed"}">${icon(passed ? "check" : "ban")}</div><div class="result-main"><div class="result-title"><strong>${escapeHtml(result.name)}</strong><span class="result-pill ${passed ? "passed" : "failed"}">${passed ? "PASSED" : "FAILED"}</span></div><p>${escapeHtml(result.business_rule)}</p><div class="result-compare"><span>Expected <strong>HTTP ${result.expected_status} · ${escapeHtml(result.expected_result)}</strong></span><span>Actual <strong>HTTP ${result.actual_status} · ${escapeHtml(result.actual_result)}</strong></span></div><div class="result-checks"><span>Checks</span> ${escapeHtml(result.checks || "HTTP status and semantic result")}</div>${result.failure_explanation ? `<p class="failure-explanation">${escapeHtml(result.failure_explanation)}</p>` : ""}<details><summary>View executed API steps</summary><ol>${steps || "<li>No step detail available</li>"}</ol></details></div></article>`;
}

function renderExecutionStep(step) {
  const input = step.input && typeof step.input === "object" ? step.input : {};
  const inputText = Object.keys(input).length ? `<small>Input: ${escapeHtml(JSON.stringify(input))}</small>` : "";
  const responseText = step.actual_status ? `<small>Response: HTTP ${step.actual_status}${step.response ? ` · ${escapeHtml(step.response)}` : ""}</small>` : "";
  return `<li class="execution-step"><div><code>${escapeHtml(step.method)}</code> ${escapeHtml(step.path)}</div>${inputText}${responseText}</li>`;
}

async function playTestResults(run) {
  const target = document.querySelector("#testpilot-latest");
  target.innerHTML = `<div id="live-test-explanation" class="live-test-explanation"></div><div id="completed-test-results" class="test-results"></div>`;
  const live = document.querySelector("#live-test-explanation");
  try {
    for (let index = 0; index < run.results.length; index += 1) {
      const result = run.results[index];
      setText("testpilot-summary", `Step ${index + 1} of ${run.total}`);
      live.innerHTML = liveTestMarkup(result, index, run.total, false);
      await wait(index === 0 ? 320 : 480);
      live.innerHTML = liveTestMarkup(result, index, run.total, true);
      await wait(380);
      document.querySelector("#completed-test-results").insertAdjacentHTML("beforeend", renderResult(result));
    }
  } catch (error) {
    target.innerHTML = emptyState("Report rendering failed", "The test run completed, but this report could not be displayed.");
    showMessage(error.message, "error");
    return;
  }
  live.innerHTML = `<div class="live-complete">${icon("check")}<span><strong>Run complete</strong><small>${run.passed} passed, ${run.failed} failed. All results are now available below.</small></span></div>`;
  setText("testpilot-summary", `${run.passed}/${run.total} passed`);
}

function liveTestMarkup(result, index, total, hasActual) {
  const input = result.steps?.find((step) => step.input && Object.keys(step.input).length)?.input || {};
  const actual = hasActual ? `HTTP ${result.actual_status} · ${result.actual_result}` : "Waiting for the actual response...";
  const explanation = hasActual ? explainResult(result) : "TestPilot is sending the request and comparing the response now.";
  return `<div class="live-test-head"><span class="live-pulse">${icon(hasActual ? (result.passed ? "check" : "ban") : "pulse")}</span><span><small>TEST ${index + 1} OF ${total}</small><strong>${escapeHtml(result.name)}</strong></span><span class="live-state ${hasActual ? (result.passed ? "passed" : "failed") : "waiting"}">${hasActual ? (result.passed ? "PASSED" : "FAILED") : "RUNNING"}</span></div><div class="live-test-grid"><div><small>Input sent</small><code>${escapeHtml(JSON.stringify(input) || "{}")}</code></div><div><small>Expected output</small><strong>HTTP ${result.expected_status} · ${escapeHtml(result.expected_result)}</strong></div><div><small>Actual output</small><strong class="${hasActual ? (result.passed ? "actual-good" : "actual-bad") : "actual-waiting"}">${escapeHtml(actual)}</strong></div></div><p class="live-explanation"><strong>What is happening:</strong> ${escapeHtml(explanation)}</p>`;
}

function explainResult(result) {
  if (result.passed) return `The API returned the expected ${result.expected_result} behavior, so this business rule is working correctly.`;
  return `The API returned ${result.actual_result} instead of ${result.expected_result}; this scenario needs investigation.`;
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function bookAppointment(event) {
  event.preventDefault();
  clearFieldErrors();
  const button = form.querySelector("button[type=submit]");
  setBusy(button, "Booking...");
  try {
    await requestJson("/api/appointments", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form).entries())) });
    showMessage("Appointment booked successfully.");
    form.patient_name.value = "";
    await loadDashboard();
  } catch (error) {
    showFieldError(error.message);
    showMessage(error.message, "error");
  } finally {
    setBusy(button, "Book appointment", false);
  }
}

function clearFieldErrors() {
  document.querySelectorAll(".field-error").forEach((element) => { element.textContent = ""; });
  form?.querySelectorAll("[aria-invalid]").forEach((element) => element.removeAttribute("aria-invalid"));
}

function showFieldError(message) {
  const mappings = [
    ["patient_name", "error-patient-name", "patient_name"],
    ["Patient name", "error-patient-name", "patient_name"],
    ["mobile", "error-mobile", "mobile_number"],
    ["email", "error-email", "email"],
    ["service", "error-service", "service_id"],
    ["Date", "error-date", "appointment_date"],
    ["Start time", "error-start-time", "start_time"],
  ];
  const match = mappings.find(([text]) => message.toLowerCase().includes(text.toLowerCase()));
  if (!match) return;
  const error = document.querySelector(`#${match[1]}`);
  const input = form?.querySelector(`[name="${match[2]}"]`);
  if (error) error.textContent = message;
  if (input) input.setAttribute("aria-invalid", "true");
}

async function cancelAppointment(id, button) {
  if (!await requestConfirmation("Cancel appointment?", "The slot can be booked again after cancellation.")) return;
  setBusy(button, "Cancelling...");
  try {
    await requestJson(`/api/appointments/${id}/cancel`, { method: "POST" });
    showMessage("Appointment cancelled. The slot is available again.");
    await loadDashboard();
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    setBusy(button, "Cancel", false);
  }
}

function requestConfirmation(title, copy) {
  const dialog = document.querySelector("#confirm-dialog");
  const titleElement = document.querySelector("#confirm-title");
  const copyElement = document.querySelector("#confirm-copy");
  const confirmButton = document.querySelector("#confirm-action");
  const cancelButton = document.querySelector("#confirm-cancel");
  titleElement.textContent = title;
  copyElement.textContent = copy;
  dialog.hidden = false;
  confirmButton.focus();
  return new Promise((resolve) => {
    const finish = (value) => {
      dialog.hidden = true;
      confirmButton.removeEventListener("click", onConfirm);
      cancelButton.removeEventListener("click", onCancel);
      dialog.removeEventListener("click", onBackdrop);
      resolve(value);
    };
    const onConfirm = () => finish(true);
    const onCancel = () => finish(false);
    const onBackdrop = (event) => { if (event.target === dialog) finish(false); };
    confirmButton.addEventListener("click", onConfirm);
    cancelButton.addEventListener("click", onCancel);
    dialog.addEventListener("click", onBackdrop);
  });
}

async function runTestPilot() {
  const button = document.querySelector("#run-testpilot");
  setBusy(button, "Running tests...");
  setText("testpilot-summary", "Running...");
  try {
    const body = await requestJson("/api/testpilot/run", { method: "POST" });
    showMessage(`TestPilot completed: ${body.run.summary}`);
    await loadDashboard(true);
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    setBusy(button, "Run tests", false);
  }
}

async function runDefectDemo() {
  const button = document.querySelector("#run-defect-demo");
  setBusy(button, "Running demo...");
  try {
    const body = await requestJson("/api/testpilot/defect-demo", { method: "POST" });
    showMessage(`Defect demo complete: ${body.demo.defective.failed} failure detected, then restored behavior passed.`);
    await loadDashboard();
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    setBusy(button, "Defect demo", false);
  }
}

function setBusy(button, text, busy = true) {
  if (!button) return;
  if (busy) {
    button.dataset.originalLabel = button.textContent;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span>${text}`;
  } else {
    button.disabled = false;
    button.textContent = text;
  }
}

function emptyState(title, copy) {
  return `<div class="inline-empty"><span class="empty-icon">${icon("grid")}</span><strong>${title}</strong><small>${copy}</small></div>`;
}

function setText(id, value) {
  const element = document.querySelector(`#${id}`);
  if (element) element.textContent = value;
}

function initials(value) {
  return value.split(" ").map((part) => part[0]).slice(0, 2).join("").toUpperCase();
}

function formatDay(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-US", { day: "2-digit" });
}

function formatMonth(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-US", { month: "short" }).toUpperCase();
}

function formatDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatTime(value) {
  const current = parseTime(value);
  return `${String(current.hour).padStart(2, "0")}:${String(current.minute).padStart(2, "0")} ${current.period}`;
}

function formatDateTime(value) {
  return new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatMode(mode) {
  if (mode === "standard") return "Standard validation suite";
  if (mode.includes("overlap validation disabled")) return "Defect demo: overlap validation disabled";
  if (mode.includes("restored validation")) return "Defect demo: validation restored";
  return mode;
}

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

form?.addEventListener("submit", bookAppointment);
document.querySelector("#refresh-appointments")?.addEventListener("click", loadDashboard);
document.querySelector("#appointment-search")?.addEventListener("input", renderAppointments);
document.querySelector("#service-select")?.addEventListener("change", loadAvailability);
document.querySelector("#service-select")?.addEventListener("change", updateServiceDuration);
document.querySelector("#start-time")?.addEventListener("change", updateAppointmentSummary);
document.querySelector("#run-testpilot")?.addEventListener("click", runTestPilot);
document.querySelector("#run-defect-demo")?.addEventListener("click", runDefectDemo);
document.querySelector("#logout-button")?.addEventListener("click", async () => {
  await requestJson("/api/auth/logout", { method: "POST" });
  window.location.assign("/login");
});
document.querySelector("#appointment-table-body")?.addEventListener("click", (event) => {
  const button = event.target.closest(".cancel-button");
  if (button) cancelAppointment(button.dataset.id, button);
});

loadDashboard();
