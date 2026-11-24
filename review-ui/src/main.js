const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const h = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

const state = {
  view: "queue",
  reviewStatus: "pending",
  priority: "",
  query: "",
  items: [],
  filteredTotal: 0,
  hasMore: false,
  nextOffset: null,
  selectedId: null,
  details: new Map(),
  compareItems: [],
  compareBefore: null,
  compareAfter: null,
  loading: false,
  taskRequest: 0,
  detailRequest: 0,
};

const labels = {
  priority: { P0: "P0 · 确认失败", P1: "P1 · 待复核", P2: "P2 · 执行规则", none: "无发现" },
  dimensions: { routing: "路由", execution: "执行", artifact: "产物", exit: "退出", outcome: "结果" },
  status: { pass: "通过", fail: "失败", unknown: "未知" },
  events: { selection: "Skill / 工具选择", tool_result: "工具结果", artifact: "产物记录", verification: "独立验证", process_result: "进程结果" },
  outcome: { success: "成功", failure: "失败", unknown: "未知", abandoned: "已放弃" },
  stage: { routing: "路由", execution: "执行", environment: "环境", requirements: "需求", unknown: "未归因" },
};

let toastTimer;
function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("error", error);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, error ? 6000 : 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json", "X-Agent-Feedback-Local": "1" } : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({ error: `服务返回了无效响应（${response.status}）` }));
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
  return data;
}

function priorityBadge(priority) {
  const key = priority || "none";
  return `<span class="priority ${key.toLowerCase()}">${h(labels.priority[key])}</span>`;
}

function formatDate(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

function visibleItems() {
  const query = state.query.trim().toLowerCase();
  if (!query) return state.items;
  return state.items.filter((item) => [item.goal, item.task_id, ...(item.selections || [])]
    .join(" ").toLowerCase().includes(query));
}

function updateProgress(progress) {
  if (!progress) return;
  $("#global-progress").textContent = `${progress.reviewed} / ${progress.total}`;
  $("#pending-count").textContent = progress.pending;
}

function renderQueue() {
  const items = visibleItems();
  $("#queue-count").textContent = state.filteredTotal;
  $("#load-more").hidden = !state.hasMore;
  if (!items.length) {
    const filtered = state.query || state.priority || state.reviewStatus !== "all";
    $("#task-list").innerHTML = `<div class="empty-state"><svg><use href="#i-inbox"/></svg><h2>${filtered ? "没有匹配的任务" : "还没有任务"}</h2><p>${filtered ? "试试调整审核状态、优先级或搜索词。" : "采集任务证据后，任务会出现在这里。"}</p></div>`;
    if (!state.query) renderEmptyDetail();
    return;
  }
  $("#task-list").innerHTML = items.map((item) => {
    const selected = item.task_id === state.selectedId;
    const reviewed = item.label_source === "human";
    const skills = item.selections?.length ? item.selections.join("、") : "未记录 Skill 选择";
    return `<button class="task-card ${selected ? "selected" : ""}" data-task-id="${h(item.task_id)}" aria-pressed="${selected}">
      <div class="task-card-top">${priorityBadge(item.priority)}${reviewed
        ? '<span class="reviewed-mark"><svg><use href="#i-check"/></svg>已审核</span>'
        : `<span class="task-time">${h(formatDate(item.source_started_at || item.created_at))}</span>`}</div>
      <p class="task-goal">${h(item.goal)}</p><p class="task-skill" title="${h(skills)}">${h(skills)}</p>
      <div class="task-card-footer"><span>${h(item.event_count)} 条事件 · ${h(item.findings.length)} 条信号</span><span>${h(item.assessment.outcome.status === "pass" ? "结果通过" : item.assessment.outcome.status === "fail" ? "结果失败" : "结果未知")}</span></div>
    </button>`;
  }).join("");
}

function renderEmptyDetail(message = "从左侧选择一条任务，查看证据并写入人工结论。") {
  state.selectedId = null;
  $("#detail").innerHTML = `<div class="empty-state"><svg><use href="#i-file"/></svg><h2>选择一条审核任务</h2><p>${h(message)}</p></div>`;
  $("#review-form").querySelectorAll("input, select, textarea, button").forEach((control) => { control.disabled = true; });
  $("#current-label").hidden = true;
}

function dimensionCards(assessment) {
  return Object.entries(labels.dimensions).map(([key, name]) => {
    const decision = assessment[key];
    return `<div class="dimension ${h(decision.status)}" title="${h(decision.reason)}">
      <span class="dimension-name">${h(name)}</span><span class="dimension-status">${h(labels.status[decision.status])}</span>
      <span class="dimension-reason">${h(decision.reason)}</span></div>`;
  }).join("");
}

function currentLabelHtml(task) {
  if (!task.label_source) return "";
  const source = task.label_source === "human" ? "人工结论" : task.label_source === "observed" ? "观察到的用户反馈" : "自报告标签";
  const outcome = labels.outcome[task.outcome] || "未知";
  const stage = task.failure_stage && task.failure_stage !== "unknown" ? ` · ${labels.stage[task.failure_stage]}` : "";
  return `<strong>当前${source}：${h(outcome + stage)}</strong><p>${h(task.comment || "没有附加说明")}</p>`;
}

function renderDetail(detail) {
  const task = detail.task;
  state.details.set(task.task_id, detail);
  const selected = state.selectedId === task.task_id;
  if (!selected) return;
  const skills = task.selections?.length
    ? task.selections.map((name, index) => `<span class="skill-chip ${index > 0 && name === task.selections[index - 1] ? "repeat" : ""}">${h(name)}</span>`).join("")
    : '<span class="task-skill">未记录 Skill 选择</span>';
  const findings = task.findings.length ? `<div class="finding-list">${task.findings.map((finding) => `
    <article class="finding ${h(finding.priority.toLowerCase())}"><div class="finding-head">${priorityBadge(finding.priority)}<span class="finding-rule">${h(finding.rule)}</span></div><p>${h(finding.evidence)}</p></article>`).join("")}</div>`
    : '<div class="no-findings"><svg><use href="#i-check"/></svg>没有命中已定义规则；这不等于任务成功。</div>';
  const verifications = task.verification.length ? `<div class="evidence-list">${task.verification.map((verification) => `
    <div class="evidence-item"><div class="evidence-meta"><span>结果：${h(labels.outcome[verification.outcome] || verification.outcome)}</span><span>验证来源：${h(verification.source)}</span><span>产物来源：${h(verification.artifact_source)}</span></div>
    <ul>${(verification.evidence || []).map((evidence) => `<li>${h(evidence)}</li>`).join("")}</ul></div>`).join("")}</div>`
    : '<p class="task-skill">尚未记录客观验证。缺少验证时，产物与结果保持未知。</p>';
  const events = detail.events.length ? `<div class="timeline">${detail.events.map((event) => {
    const payload = event.payload;
    const name = payload.name || (payload.exit_code !== undefined ? `exit_code=${payload.exit_code}` : payload.outcome || "事件");
    const subtitle = payload.status || payload.kind || payload.source || "已记录";
    return `<details class="event-row"><summary><span class="event-index">${h(event.sequence)}</span><span class="event-name"><strong>${h(name)}</strong><span>${h(labels.events[event.type] || event.type)} · ${h(subtitle)}</span></span><span class="event-type">${h(formatDate(event.created_at))}</span></summary><pre>${h(JSON.stringify(payload, null, 2))}</pre></details>`;
  }).join("")}</div>` : '<p class="task-skill">该任务没有事件记录。</p>';
  const revisions = detail.revisions.length ? detail.revisions.map((revision) => `
    <article class="revision"><div class="revision-head"><span class="label-tag">${h(revision.source === "human" ? "人工" : revision.source === "observed" ? "观察" : "自报告")} · ${h(labels.outcome[revision.outcome])}</span><span class="task-skill">${h(labels.stage[revision.failure_stage])}</span><time>${h(formatDate(revision.created_at))}</time></div>
    <p>${h(revision.comment || "无说明")}</p><small>修订原因：${h(revision.reason)} · 操作者：${h(revision.actor)}</small></article>`).join("")
    : '<p class="task-skill">尚无人工或自动标签。</p>';

  $("#detail").innerHTML = `<header class="detail-head"><div class="detail-kicker">${priorityBadge(task.priority)}<span class="task-id">${h(task.task_id)}</span></div>
    <h1>${h(task.goal)}</h1><div class="detail-meta"><span>Agent <strong>${h(task.agent)}</strong></span><span>记录时间 <strong>${h(formatDate(task.created_at))}</strong></span><span>执行状态 <strong>${h(labels.status[task.execution_status])}</strong></span></div></header>
    <section class="section-block"><div class="section-title"><h2>技能选择</h2><span>${h(task.selection_count)} 次选择</span></div><div class="skill-list">${skills}</div></section>
    <section class="section-block"><div class="section-title"><h2>五维证据状态</h2><span>各维度独立判定</span></div><div class="dimension-grid">${dimensionCards(task.assessment)}</div></section>
    <section class="section-block"><div class="section-title"><h2>待复核信号</h2><span>${h(task.findings.length)} 条</span></div>${findings}</section>
    <section class="section-block"><div class="section-title"><h2>产物与验证证据</h2><span>${h(task.verification.length)} 次验证</span></div>${verifications}</section>
    <section class="section-block"><div class="section-title"><h2>事件时间线</h2><span>原始记录 · ${h(detail.events.length)} 条</span></div>${events}</section>
    <section class="section-block"><div class="section-title"><h2>结论修订历史</h2><span>${h(detail.revisions.length)} 次</span></div>${revisions}</section>`;

  const current = $("#current-label");
  current.innerHTML = currentLabelHtml(task);
  current.hidden = !task.label_source;
  $("#review-form").querySelectorAll("input, select, textarea, button").forEach((control) => { control.disabled = false; });
  $("#save-label").disabled = false;
  $("#save-error").hidden = true;
}

async function loadDetail(taskId, { resetForm = true } = {}) {
  if (!taskId) { renderEmptyDetail(); return; }
  const requestId = ++state.detailRequest;
  $("#detail").innerHTML = '<div class="detail-loading"><span class="spinner"></span><p>正在读取任务证据…</p></div>';
  try {
    const detail = await api(`/api/task?id=${encodeURIComponent(taskId)}`);
    if (requestId !== state.detailRequest) return;
    if (resetForm) {
      $("#review-comment").value = "";
      $("#comment-count").textContent = "0 / 1800";
      $("input[name=decision][value=confirm]").checked = true;
      $("#stage-field").hidden = false;
    }
    renderDetail(detail);
  } catch (error) {
    if (requestId !== state.detailRequest) return;
    $("#detail").innerHTML = `<div class="empty-state"><svg><use href="#i-alert"/></svg><h2>证据读取失败</h2><p>${h(error.message)}</p></div>`;
    $("#save-label").disabled = true;
  }
}

function selectTask(taskId) {
  if (!taskId || taskId === state.selectedId) return;
  state.selectedId = taskId;
  renderQueue();
  loadDetail(taskId);
}

async function loadTasks({ append = false, preserveSelection = true } = {}) {
  const requestId = ++state.taskRequest;
  state.loading = true;
  $("#refresh").classList.add("loading");
  $("#queue-error").hidden = true;
  const offset = append ? state.nextOffset || 0 : 0;
  const params = new URLSearchParams({ review_status: state.reviewStatus, limit: "100", offset: String(offset), sort: "priority" });
  if (state.priority) params.set("priority", state.priority);
  if (state.query.trim()) params.set("q", state.query.trim());
  try {
    const report = await api(`/api/tasks?${params}`);
    if (requestId !== state.taskRequest) return;
    state.items = append ? [...state.items, ...report.items] : report.items;
    state.filteredTotal = report.filtered_total;
    state.hasMore = report.has_more;
    state.nextOffset = report.next_offset;
    updateProgress(report.progress);
    const visible = visibleItems();
    if (!preserveSelection || !visible.some((item) => item.task_id === state.selectedId)) {
      state.selectedId = visible[0]?.task_id || null;
    }
    renderQueue();
    if (state.selectedId) await loadDetail(state.selectedId);
    else renderEmptyDetail(state.query ? "完整数据集中没有与搜索词匹配的任务。" : state.reviewStatus === "pending" ? "当前筛选下没有待审核任务。可切换到“已审核”查看历史结论。" : "当前筛选条件下没有可显示的任务。");
  } catch (error) {
    if (requestId !== state.taskRequest) return;
    $("#queue-error").textContent = error.message;
    $("#queue-error").hidden = false;
    if (!append) {
      $("#task-list").innerHTML = '<div class="empty-state"><h2>队列读取失败</h2><p>请确认本地服务仍在运行，然后点击右上角刷新。</p></div>';
      renderEmptyDetail("队列读取失败，暂时不能写入审核结论。");
    }
  } finally {
    if (requestId === state.taskRequest) {
      state.loading = false;
      $("#refresh").classList.remove("loading");
    }
  }
}

async function loadHealth() {
  try {
    const health = await api("/api/health");
    const connection = $("#connection");
    connection.className = "connection online";
    connection.innerHTML = "<i></i>本地服务已连接";
    $("#data-scope").textContent = health.demo ? "仅监听本机 · 隔离演示数据" : "仅监听本机 · 已连接指定数据库";
  } catch (error) {
    const connection = $("#connection");
    connection.className = "connection offline";
    connection.innerHTML = "<i></i>连接失败";
    toast(error.message, true);
  }
}

function reviewFormReset() {
  $("#review-comment").value = "";
  $("#comment-count").textContent = "0 / 1800";
  $("#save-error").hidden = true;
}

async function saveReview(event) {
  event.preventDefault();
  if (!state.selectedId) return;
  const decision = $("input[name=decision]:checked")?.value;
  const comment = $("#review-comment").value.trim();
  const failureStage = $("#failure-stage").value;
  const errorNode = $("#save-error");
  errorNode.hidden = true;
  if (comment.length < 2) {
    errorNode.textContent = "请填写至少 2 个字符的审核说明。";
    errorNode.hidden = false;
    $("#review-comment").focus();
    return;
  }
  const button = $("#save-label");
  button.disabled = true;
  button.querySelector("span").textContent = "正在保存…";
  try {
    const saved = await api("/api/label", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedId, decision, failure_stage: failureStage, comment }),
    });
    updateProgress(saved.progress);
    toast(saved.result.duplicate ? "相同结论已存在，没有重复写入。" : "人工结论已保存，修订历史已保留。 ");
    reviewFormReset();
    await loadTasks({ preserveSelection: true });
    if (state.view === "compare") await loadCompareTasks(true);
  } catch (error) {
    errorNode.textContent = error.message;
    errorNode.hidden = false;
  } finally {
    button.disabled = !state.selectedId;
    button.querySelector("span").textContent = "保存人工结论";
  }
}

async function nextPending() {
  if (state.reviewStatus !== "pending") {
    state.reviewStatus = "pending";
    $$("[data-status]").forEach((button) => button.classList.toggle("active", button.dataset.status === "pending"));
    await loadTasks({ preserveSelection: false });
    return;
  }
  const items = visibleItems();
  if (!items.length) { toast("当前没有下一条待审任务。 "); return; }
  const index = items.findIndex((item) => item.task_id === state.selectedId);
  selectTask(items[(index + 1 + items.length) % items.length].task_id);
}

function compareOptions() {
  const options = state.compareItems.map((item) => {
    const goal = item.goal.length > 70 ? `${item.goal.slice(0, 70)}…` : item.goal;
    return `<option value="${h(item.task_id)}">${h(item.priority || "无发现")} · ${h(goal)}</option>`;
  }).join("");
  $("#compare-before").innerHTML = options;
  $("#compare-after").innerHTML = options;
  $("#compare-before").value = state.compareBefore || "";
  $("#compare-after").value = state.compareAfter || "";
}

function comparisonCard(detail, letter) {
  if (!detail) return '<div class="compare-card"><div class="empty-state"><h2>请选择任务</h2></div></div>';
  const task = detail.task;
  const verification = task.verification.at(-1);
  const evidence = verification
    ? `${labels.outcome[verification.outcome] || verification.outcome}\n${(verification.evidence || []).join("\n")}`
    : "没有客观产物验证";
  const label = task.label_source
    ? `${task.label_source === "human" ? "人工" : "观察"} · ${labels.outcome[task.outcome] || "未知"} · ${labels.stage[task.failure_stage] || "未归因"}\n${task.comment || ""}`
    : "尚未审核";
  return `<article class="compare-card"><header class="compare-card-head">${priorityBadge(task.priority)}<h2>${h(task.goal)}</h2><p>${letter} · ${h(task.task_id)}</p></header>
    <section class="compare-section"><h3>技能选择</h3><div class="skill-list">${task.selections.length ? task.selections.map((name) => `<span class="skill-chip">${h(name)}</span>`).join("") : "无记录"}</div></section>
    <section class="compare-section"><h3>五维状态</h3><div class="dimension-grid">${dimensionCards(task.assessment)}</div></section>
    <section class="compare-section"><h3>最新产物证据</h3><div class="compare-evidence">${h(evidence)}</div></section>
    <section class="compare-section"><h3>人工结论</h3><div class="compare-label">${h(label)}</div></section></article>`;
}

function renderComparison() {
  const before = state.details.get(state.compareBefore);
  const after = state.details.get(state.compareAfter);
  $("#compare-content").innerHTML = comparisonCard(before, "A") + comparisonCard(after, "B");
}

async function loadCompareTasks(preserve = false) {
  $("#compare-content").innerHTML = '<div class="detail-loading"><span class="spinner"></span><p>正在读取可对照任务…</p></div>';
  try {
    const items = [];
    let offset = 0;
    do {
      const page = await api(`/api/tasks?review_status=all&limit=100&offset=${offset}&sort=priority`);
      items.push(...page.items);
      if (!page.has_more) break;
      offset = page.next_offset;
    } while (true);
    state.compareItems = items;
    if (!preserve || !items.some((item) => item.task_id === state.compareBefore)) state.compareBefore = items[0]?.task_id || null;
    if (!preserve || !items.some((item) => item.task_id === state.compareAfter)) state.compareAfter = items[1]?.task_id || items[0]?.task_id || null;
    compareOptions();
    const selected = [state.compareBefore, state.compareAfter].filter(Boolean);
    await Promise.all(selected.map(async (id) => {
      state.details.set(id, await api(`/api/task?id=${encodeURIComponent(id)}`));
    }));
    renderComparison();
  } catch (error) {
    $("#compare-content").innerHTML = `<div class="empty-state"><svg><use href="#i-alert"/></svg><h2>对照数据读取失败</h2><p>${h(error.message)}</p></div>`;
  }
}

async function changeCompare(side, id) {
  if (side === "before") state.compareBefore = id;
  else state.compareAfter = id;
  renderComparison();
  if (!state.details.has(id)) {
    try {
      state.details.set(id, await api(`/api/task?id=${encodeURIComponent(id)}`));
      renderComparison();
    } catch (error) { toast(error.message, true); }
  }
}

function switchView(view) {
  state.view = view;
  $$("[data-view]").forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  $("#queue-view").hidden = view !== "queue";
  $("#compare-view").hidden = view !== "compare";
  if (view === "compare") loadCompareTasks(true);
}

$$("[data-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
$$("[data-status]").forEach((button) => button.addEventListener("click", () => {
  state.reviewStatus = button.dataset.status;
  $$("[data-status]").forEach((item) => item.classList.toggle("active", item === button));
  loadTasks({ preserveSelection: false });
}));
$("#priority-filter").addEventListener("change", (event) => { state.priority = event.target.value; loadTasks({ preserveSelection: false }); });
let searchTimer;
$("#search").addEventListener("input", (event) => {
  state.query = event.target.value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadTasks({ preserveSelection: false }), 250);
});
$("#task-list").addEventListener("click", (event) => {
  const card = event.target.closest("[data-task-id]");
  if (card) selectTask(card.dataset.taskId);
});
$("#load-more").addEventListener("click", () => loadTasks({ append: true }));
$("#refresh").addEventListener("click", async () => {
  await Promise.all([loadHealth(), loadTasks({ preserveSelection: true })]);
  if (state.view === "compare") await loadCompareTasks(true);
  toast("数据已刷新。 ");
});
$("#review-form").addEventListener("submit", saveReview);
$$("input[name=decision]").forEach((input) => input.addEventListener("change", () => {
  $("#stage-field").hidden = input.value !== "confirm" || !input.checked;
}));
$("#review-comment").addEventListener("input", (event) => { $("#comment-count").textContent = `${event.target.value.length} / 1800`; });
$("#next-task").addEventListener("click", nextPending);
$("#compare-before").addEventListener("change", (event) => changeCompare("before", event.target.value));
$("#compare-after").addEventListener("change", (event) => changeCompare("after", event.target.value));

reviewFormReset();
Promise.all([loadHealth(), loadTasks({ preserveSelection: false })]);
