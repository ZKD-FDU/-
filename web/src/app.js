const API_BASE = window.HONGCE_API_BASE || "http://127.0.0.1:8000";

const policies = [
  ["S0", "基线单向通知", "短信/广播为主"],
  ["S1", "设施优先加固", "桥路与避难点"],
  ["S2", "数字预警前移", "更早触达"],
  ["S3", "网格叫应确认", "逐户闭环"],
  ["S4", "资源集中调拨", "车辆/床位扩容"],
  ["S5", "韧性综合方案", "前移+叫应+调拨"]
];

const tabs = ["县域态势总览", "情景编辑器", "实时推演", "叫应确认台", "政策对比", "个体与事件解释", "复盘与建议"];

const state = {
  active: tabs[0],
  run: null,
  experiment: null,
  trace: null,
  busy: false
};

const $ = (selector) => document.querySelector(selector);
const content = $("#content");

function pct(value) {
  return `${Math.round(Number(value || 0) * 1000) / 10}%`;
}

function num(value) {
  return Number(value || 0).toFixed(2);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "content-type": "application/json", ...(options.headers || {}) },
    ...options
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function init() {
  $("#tabs").innerHTML = tabs.map((tab) => `<button data-tab="${tab}" class="${tab === state.active ? "active" : ""}">${tab}</button>`).join("");
  $("#policy").innerHTML = policies.map(([id, name]) => `<option value="${id}" ${id === "S5" ? "selected" : ""}>${id} · ${name}</option>`).join("");
  $("#tabs").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.active = button.dataset.tab;
    render();
  });
  $("#run").addEventListener("click", () => runSimulation($("#policy").value));
  try {
    const health = await request("/health");
    $("#health").textContent = `API ${health.status}`;
  } catch {
    $("#health").textContent = "API offline";
  }
  render();
}

async function runSimulation(policy) {
  setBusy(true, "正在运行多智能体仿真...");
  try {
    const seed = Number($("#seed").value);
    const population = Number($("#population").value);
    const validation = await request("/scenarios/validate", { method: "POST", body: JSON.stringify({ population }) });
    if (!validation.valid) throw new Error(validation.reason);
    const created = await request("/simulations/run", {
      method: "POST",
      body: JSON.stringify({ policy_id: policy, seed, population, output_dir: "outputs/api" })
    });
    state.run = await request(`/simulations/${created.run_id}`);
    const first = state.run.agents.find((agent) => agent.is_vulnerable) || state.run.agents[0];
    state.trace = first ? await request(`/simulations/${created.run_id}/agents/${first.id}/trace`) : null;
    setNotice(`已生成 ${created.run_id}`);
  } catch (error) {
    setNotice(error.message || "运行失败");
  } finally {
    setBusy(false);
    render();
  }
}

async function runExperiment() {
  setBusy(true, "正在执行 A/B/C 批量政策实验...");
  try {
    const population = Number($("#population").value);
    const response = await request("/experiments/run", {
      method: "POST",
      body: JSON.stringify({
        experiment: "abc",
        seeds: [202608060, 202608061, 202608062],
        population,
        output_dir: "outputs/api_experiments"
      })
    });
    state.experiment = response.comparison;
    setNotice(`实验完成：${response.experiment_id}`);
  } catch (error) {
    setNotice(error.message || "实验失败");
  } finally {
    setBusy(false);
    render();
  }
}

function setBusy(value, text) {
  state.busy = value;
  $("#run").disabled = value;
  if (text) setNotice(text);
}

function setNotice(text) {
  $("#notice").textContent = text;
}

function render() {
  $("#page-title").textContent = state.active;
  document.querySelectorAll("#tabs button").forEach((button) => button.classList.toggle("active", button.dataset.tab === state.active));
  const route = {
    "县域态势总览": overview,
    "情景编辑器": editor,
    "实时推演": timeline,
    "叫应确认台": callDesk,
    "政策对比": comparison,
    "个体与事件解释": explanation,
    "复盘与建议": review
  };
  content.innerHTML = route[state.active]();
  const experimentButton = $("#run-experiment");
  if (experimentButton) experimentButton.addEventListener("click", runExperiment);
  document.querySelectorAll("[data-run-policy]").forEach((button) => {
    button.addEventListener("click", () => runSimulation(button.dataset.runPolicy));
  });
}

function metric(label, value, tone = "good") {
  return `<div class="metric ${tone}"><span class="metric-icon">${label.slice(0, 1)}</span><label>${label}</label><strong>${value}</strong></div>`;
}

function row(label, value) {
  return `<div class="row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function overview() {
  const m = state.run?.metrics || {};
  return `<div class="view">
    <section class="metric-grid">
      ${metric("安全转移率", pct(m.safe_before_danger_rate))}
      ${metric("脆弱群体风险", pct(m.vulnerable_harm_risk), "warn")}
      ${metric("闭环响应", pct(m.response_closure_rate))}
      ${metric("平均排队分钟", num(m.resource_queue_minutes_mean), "neutral")}
    </section>
    <section class="map-band">
      <div class="county-map">
        <span class="node valley">北谷村</span><span class="node town">清源镇</span>
        <span class="node shelter">学校避难点</span><span class="node care">养老院</span>
        <span class="waterline"></span><span class="roadline"></span>
      </div>
      <div class="side-table">
        <h2>最新运行</h2>
        ${row("策略", state.run?.run?.policy_id || "未运行")}
        ${row("Run ID", state.run?.run?.id || "-")}
        ${row("中位提前量", `${m.lead_time_minutes_median || 0} 分钟`)}
        ${row("群体公平缺口", num(m.group_safety_gap))}
      </div>
    </section>
  </div>`;
}

function editor() {
  return `<div class="view two"><section><h2>政策方案</h2><div class="policy-list">
    ${policies.map(([id, name, short]) => `<button data-run-policy="${id}"><strong>${id} · ${name}</strong><span>${short}</span></button>`).join("")}
    </div></section><section><h2>合成县域设定</h2><div class="form-grid">
      <label>脆弱人口比例<input value="约 32%" readonly /></label>
      <label>避难点<input value="学校/卫生院/镇政府" readonly /></label>
      <label>关键断点<input value="东桥、山顶通信站、养老院" readonly /></label>
      <label>时间步长<input value="5 分钟" readonly /></label>
    </div></section></div>`;
}

function timeline() {
  const events = (state.run?.events || []).slice(-12);
  const rows = events.length ? events : [{ minute: 0, event_type: "ready", description: "点击运行生成事件流" }];
  return `<div class="view"><div class="timeline">${rows.map((event) => `<div class="tick"><b>${escapeHtml(event.minute)}'</b><strong>${escapeHtml(event.event_type)}</strong><span>${escapeHtml(event.description)}</span></div>`).join("")}</div>
    <section class="metric-grid compact">
      ${metric("漏管关键动作", pct(state.run?.metrics?.missed_critical_action_rate), "warn")}
      ${metric("信任变化", num(state.run?.metrics?.trust_delta))}
      ${metric("群体缺口", num(state.run?.metrics?.group_safety_gap), "neutral")}
    </section></div>`;
}

function callDesk() {
  const agents = (state.run?.agents || []).filter((agent) => agent.is_vulnerable).slice(0, 12);
  return `<div class="view"><section><table><thead><tr><th>对象</th><th>位置</th><th>状态</th><th>风险</th><th>原因</th></tr></thead><tbody>
    ${agents.map((agent) => `<tr><td>${escapeHtml(agent.id)}</td><td>${escapeHtml(agent.location_id)}</td><td><span class="status ${String(agent.status).includes("blocked") ? "blocked" : String(agent.status).includes("sheltered") ? "done" : ""}">${escapeHtml(agent.status)}</span></td><td>${num(agent.harm_risk)}</td><td>${escapeHtml(agent.reason)}</td></tr>`).join("")}
    </tbody></table></section></div>`;
}

function metricMean(policy, metricName) {
  const entry = state.experiment?.experiments?.C_chain_breaks?.summary?.[policy]?.[metricName] || state.experiment?.summary?.[policy]?.[metricName];
  return entry && typeof entry === "object" ? Number(entry.mean) : undefined;
}

function comparison() {
  const notes = state.experiment?.experiments ? Object.values(state.experiment.experiments).flatMap((item) => item.interpretation) : [];
  return `<div class="view"><div class="toolbar"><button class="primary" id="run-experiment">运行 A/B/C 实验</button></div>
    <section class="comparison">${policies.map(([id, name]) => `<div class="policy-card"><strong>${id}</strong><span>${name}</span><b>${pct(metricMean(id, "safe_before_danger_rate"))}</b><small>安全转移率均值</small></div>`).join("")}</section>
    <section class="notes">${notes.length ? notes.map((note) => `<p>${escapeHtml(note)}</p>`).join("") : "<p>运行批量实验后显示策略差异、区间和断点解释。</p>"}</section></div>`;
}

function explanation() {
  const traces = Array.isArray(state.trace?.traces) ? state.trace.traces : [];
  const events = (state.run?.events || []).slice(-12);
  return `<div class="view two"><section><h2>个体决策轨迹</h2>${traces.map((item) => `<div class="trace"><strong>${escapeHtml(item.minute)} 分钟 · ${escapeHtml(item.action)}</strong><p>${escapeHtml(item.reason)}</p></div>`).join("") || "<p>运行后显示首个脆弱个体轨迹。</p>"}</section>
    <section><h2>事件记录</h2>${events.map((item) => `<div class="event"><strong>${escapeHtml(item.minute)} 分钟 · ${escapeHtml(item.event_type)}</strong><span>${escapeHtml(item.description)}</span></div>`).join("") || "<p>运行后显示事件记录。</p>"}</section></div>`;
}

function review() {
  const m = state.run?.metrics || {};
  const uplift = metricMean("S5", "safe_before_danger_rate") !== undefined && metricMean("S0", "safe_before_danger_rate") !== undefined
    ? pct(Math.max(0, metricMean("S5", "safe_before_danger_rate") - metricMean("S0", "safe_before_danger_rate")))
    : "待实验";
  return `<div class="view two"><section><h2>策略建议</h2>
    <p>当前 ${escapeHtml(state.run?.run?.policy_id || "-")} 安全转移率为 ${pct(m.safe_before_danger_rate)}，脆弱群体风险为 ${pct(m.vulnerable_harm_risk)}。</p>
    <p>批量实验中 S5 相比 S0 的安全转移率均值提升：${uplift}。</p>
    <p>优先动作：提前预警、脆弱户逐户确认、车辆与照护资源联动调度、桥路断点预案同步更新。</p>
    </section><section><h2>交付状态</h2>
    ${row("数据标签", "SYNTHETIC / SIMULATED")}
    ${row("外部模型密钥", "不需要")}
    ${row("核心内核", "规则智能体 + 多层网络 + 资源调度")}
    ${row("输出", "JSON 指标、事件、个体轨迹、实验比较")}
    </section></div>`;
}

init();
