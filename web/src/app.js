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
  cases: [],
  selectedCase: null,
  caseScenario: null,
  scenarioConfig: {
    vulnerable_ratio: 0.32,
    timestep_minutes: 5,
    warning_minute: 45,
    evacuation_order_minute: 75,
    bridge_closure_minute: 120,
    danger_arrival_minute: 180,
    communication_failure_minute: 90,
    communication_failure_rate: 0.3,
    vehicles: 18,
    care_workers: 34,
    stretchers: 18,
    shelter_beds: 700,
    key_breakpoints: "",
    metric_candidates: ""
  },
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
    $("#health").textContent = `API ${health.status} · ${health.training_case_count || 0} cases`;
    await loadCases();
  } catch {
    $("#health").textContent = "API offline";
  }
  render();
}

async function loadCases(query = "") {
  const params = new URLSearchParams({ limit: "28" });
  if (query.trim()) params.set("q", query.trim());
  const data = await request(`/cases?${params.toString()}`);
  state.cases = data.cases || [];
  if (!state.selectedCase && state.cases.length) {
    await selectCase(state.cases[0].case_id, false);
  }
}

async function selectCase(caseId, rerender = true) {
  state.selectedCase = await request(`/cases/${encodeURIComponent(caseId)}`);
  state.caseScenario = await request(`/cases/${encodeURIComponent(caseId)}/scenario`);
  state.scenarioConfig.key_breakpoints = (state.selectedCase.intervention_points || []).join("、");
  state.scenarioConfig.metric_candidates = (state.selectedCase.metric_candidates || []).slice(0, 4).join("、");
  if (rerender) render();
}

async function runSimulation(policy) {
  setBusy(true, "正在运行多智能体仿真...");
  try {
    const seed = Number($("#seed").value);
    const population = Number($("#population").value);
    const caseId = state.selectedCase?.case_id;
    const scenario_overrides = buildScenarioOverrides();
    const validation = await request("/scenarios/validate", { method: "POST", body: JSON.stringify({ population, case_id: caseId, scenario_overrides }) });
    if (!validation.valid) throw new Error(validation.reason);
    const created = await request("/simulations/run", {
      method: "POST",
      body: JSON.stringify({ policy_id: policy, seed, population, case_id: caseId, scenario_overrides, output_dir: "outputs/api" })
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
  const run = $("#run");
  if (run) run.disabled = value;
  if (text) setNotice(text);
}

function setNotice(text) {
  $("#notice").textContent = text;
}

function render() {
  $("#page-title").textContent = state.active;
  const runControls = $("#run-controls");
  if (runControls) runControls.hidden = state.active !== "县域态势总览";
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
  const caseSearch = $("#case-search");
  if (caseSearch) {
    caseSearch.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter") return;
      setBusy(true, "正在检索训练案例...");
      try {
        await loadCases(caseSearch.value);
      } catch (error) {
        setNotice(error.message || "案例检索失败");
      } finally {
        setBusy(false);
        render();
      }
    });
  }
  document.querySelectorAll("[data-config-key]").forEach((input) => {
    const updateConfig = () => {
      const key = input.dataset.configKey;
      state.scenarioConfig[key] = input.type === "number" || input.type === "range" ? Number(input.value) : input.value;
      syncConfigMirror(key, input.value);
    };
    input.addEventListener("input", updateConfig);
    input.addEventListener("change", updateConfig);
  });
  document.querySelectorAll("[data-case-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      setBusy(true, "正在载入案例模板...");
      try {
        await selectCase(button.dataset.caseId, false);
        setNotice(`已选择 ${state.selectedCase.case_id}`);
      } catch (error) {
        setNotice(error.message || "案例载入失败");
      } finally {
        setBusy(false);
        render();
      }
    });
  });
  document.querySelectorAll("[data-run-policy]").forEach((button) => {
    button.addEventListener("click", () => runSimulation(button.dataset.runPolicy));
  });
}

function buildScenarioOverrides() {
  return {
    vulnerable_ratio: Number(state.scenarioConfig.vulnerable_ratio),
    timestep_minutes: Number(state.scenarioConfig.timestep_minutes),
    warning_minute: Number(state.scenarioConfig.warning_minute),
    evacuation_order_minute: Number(state.scenarioConfig.evacuation_order_minute),
    bridge_closure_minute: Number(state.scenarioConfig.bridge_closure_minute),
    danger_arrival_minute: Number(state.scenarioConfig.danger_arrival_minute),
    communication_failure_minute: Number(state.scenarioConfig.communication_failure_minute),
    communication_failure_rate: Number(state.scenarioConfig.communication_failure_rate),
    vehicles: Number(state.scenarioConfig.vehicles),
    care_workers: Number(state.scenarioConfig.care_workers),
    stretchers: Number(state.scenarioConfig.stretchers),
    shelter_beds: Number(state.scenarioConfig.shelter_beds)
  };
}

function syncConfigMirror(key, value) {
  const mirror = document.querySelector(`[data-config-value="${key}"]`);
  if (!mirror) return;
  if (key === "vulnerable_ratio" || key === "communication_failure_rate") {
    mirror.textContent = `${Math.round(Number(value) * 100)}%`;
  } else {
    mirror.textContent = value;
  }
}

function metric(label, value, tone = "good") {
  return `<div class="metric ${tone}"><span class="metric-icon">${label.slice(0, 1)}</span><label>${label}</label><strong>${value}</strong></div>`;
}

function row(label, value) {
  return `<div class="row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function overview() {
  const m = state.run?.metrics || {};
  const caseContext = state.run?.case_context || state.selectedCase;
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
        ${row("训练案例", caseContext?.case_id || "未选择")}
        ${row("策略", state.run?.run?.policy_id || "未运行")}
        ${row("Run ID", state.run?.run?.id || "-")}
        ${row("中位提前量", `${m.lead_time_minutes_median || 0} 分钟`)}
        ${row("群体公平缺口", num(m.group_safety_gap))}
      </div>
    </section>
  </div>`;
}

function editor() {
  const selected = state.selectedCase;
  const scenario = state.caseScenario;
  const cases = state.cases.length ? state.cases : [];
  const cfg = state.scenarioConfig;
  return `<div class="view"><section><h2>真实案例训练库</h2>
    <div class="case-tools">
      <label>检索案例<input id="case-search" value="" placeholder="养老、桥梁、工地、郑州..." /></label>
      <span>${cases.length} 个候选案例</span>
    </div>
    <div class="case-grid">
      <div class="case-list">
        ${cases.map((item) => `<button data-case-id="${escapeHtml(item.case_id)}" class="${selected?.case_id === item.case_id ? "selected" : ""}">
          <strong>${escapeHtml(item.case_id)}</strong>
          <span>${escapeHtml(item.case_name)}</span>
          <small>${escapeHtml(item.scenario_class)}</small>
        </button>`).join("")}
      </div>
      <div class="case-detail">
        <h2>${escapeHtml(selected?.case_name || "选择案例")}</h2>
        ${row("案例编号", selected?.case_id || "-")}
        ${row("情景类型", selected?.scenario_class || "-")}
        ${row("影响场所", (selected?.affected_setting || []).join("、") || "-")}
        ${row("真实伤亡/死失", selected?.observed_outcomes?.deaths_or_dead_missing || "未抽取")}
        ${row("直接经济损失", selected?.observed_outcomes?.direct_economic_loss || "未抽取")}
        <div class="tag-band">${(selected?.failure_modes || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
        <div class="tag-band policy-tags">${(scenario?.recommended_policies || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
      </div>
    </div>
    </section><div class="view two nested"><section><h2>政策方案</h2><div class="policy-list">
    ${policies.map(([id, name, short]) => `<div class="policy-option"><strong>${id} · ${name}</strong><span>${short}</span></div>`).join("")}
    </div></section><section><h2>合成县域设定</h2><div class="form-grid">
      <label>案例模板<input value="${escapeHtml(selected?.case_id || "未选择")}" readonly /></label>
      <label>训练来源<input value="应急管理部报告" readonly /></label>
      <label>脆弱人口比例<span class="live-value" data-config-value="vulnerable_ratio">${Math.round(Number(cfg.vulnerable_ratio) * 100)}%</span><input data-config-key="vulnerable_ratio" value="${escapeHtml(cfg.vulnerable_ratio)}" min="0.05" max="0.85" step="0.01" type="range" /></label>
      <label>关键断点<input data-config-key="key_breakpoints" value="${escapeHtml(cfg.key_breakpoints || "预警-响应联动触发阈值")}" /></label>
      <label>时间步长<select data-config-key="timestep_minutes">
        ${[5, 10, 15].map((value) => `<option value="${value}" ${Number(cfg.timestep_minutes) === value ? "selected" : ""}>${value} 分钟</option>`).join("")}
      </select></label>
      <label>指标候选<input data-config-key="metric_candidates" value="${escapeHtml(cfg.metric_candidates || "casualty_rate、property_loss_rate")}" /></label>
      <label>预警时刻<input data-config-key="warning_minute" value="${escapeHtml(cfg.warning_minute)}" min="0" max="220" step="5" type="number" /></label>
      <label>转移命令<input data-config-key="evacuation_order_minute" value="${escapeHtml(cfg.evacuation_order_minute)}" min="0" max="360" step="5" type="number" /></label>
      <label>危险到达<input data-config-key="danger_arrival_minute" value="${escapeHtml(cfg.danger_arrival_minute)}" min="60" max="360" step="5" type="number" /></label>
      <label>桥梁封闭<input data-config-key="bridge_closure_minute" value="${escapeHtml(cfg.bridge_closure_minute)}" min="0" max="360" step="5" type="number" /></label>
      <label>通信失败率<span class="live-value" data-config-value="communication_failure_rate">${Math.round(Number(cfg.communication_failure_rate) * 100)}%</span><input data-config-key="communication_failure_rate" value="${escapeHtml(cfg.communication_failure_rate)}" min="0" max="0.95" step="0.05" type="range" /></label>
      <label>转运车辆<input data-config-key="vehicles" value="${escapeHtml(cfg.vehicles)}" min="1" max="300" step="1" type="number" /></label>
      <label>照护人员<input data-config-key="care_workers" value="${escapeHtml(cfg.care_workers)}" min="1" max="300" step="1" type="number" /></label>
      <label>担架数量<input data-config-key="stretchers" value="${escapeHtml(cfg.stretchers)}" min="1" max="300" step="1" type="number" /></label>
      <label>避难床位<input data-config-key="shelter_beds" value="${escapeHtml(cfg.shelter_beds)}" min="50" max="5000" step="10" type="number" /></label>
    </div></section></div></div>`;
}

function timeline() {
  const events = (state.run?.events || []).slice(-12);
  const rows = events.length ? events : [{ minute: 0, kind: "ready", message: "请先在主页运行一次仿真，事件流会在这里显示。" }];
  return `<div class="view"><section><h2>事件流</h2><p class="section-note">每张卡片表示一次仿真事件：左上角是发生时间，标题是事件类型，正文是具体动作。这里展示的是最新一次运行的末尾事件。</p></section>
    <div class="timeline">${rows.map((event) => eventCard(event)).join("")}</div>
    <section class="metric-grid compact">
      ${metric("漏管关键动作", pct(state.run?.metrics?.missed_critical_action_rate), "warn")}
      ${metric("信任变化", num(state.run?.metrics?.trust_delta))}
      ${metric("群体缺口", num(state.run?.metrics?.group_safety_gap), "neutral")}
    </section></div>`;
}

function eventCard(event) {
  const kind = event.kind || event.event_type || "event";
  const message = event.message || event.description || "无说明";
  const payload = event.payload && Object.keys(event.payload).length
    ? `<small>${escapeHtml(JSON.stringify(event.payload))}</small>`
    : "";
  return `<div class="tick ${escapeHtml(kind)}"><b>${escapeHtml(event.minute)} 分钟</b><strong>${escapeHtml(eventKindLabel(kind))}</strong><span>${escapeHtml(eventMessageLabel(message))}</span>${payload}</div>`;
}

function eventKindLabel(kind) {
  return {
    ready: "等待运行",
    facility: "设施状态",
    warning: "预警发布",
    message: "信息触达",
    task: "转移任务",
    dispatch: "资源调度"
  }[kind] || kind;
}

function eventMessageLabel(message) {
  return {
    "communications degraded": "山地区域通信能力下降，部分对象可能无法及时收到预警。",
    "bridge_east closed": "东桥封闭，养老院和北谷村到避难点的路线受阻。",
    "official warning issued": "县级应急部门发布正式转移预警。",
    "warning converted to evacuation consideration": "居民或机构对象收到预警并进入转移决策。",
    "evacuation task created": "系统为对象生成转移任务，等待车辆、照护或路线资源。",
    "person sheltered": "对象已被转运并完成安置。"
  }[message] || message;
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
    <section><h2>事件记录</h2>${events.map((item) => eventCard(item)).join("") || "<p>运行后显示事件记录。</p>"}</section></div>`;
}

function review() {
  const m = state.run?.metrics || {};
  const selected = state.run?.case_context || state.selectedCase;
  const uplift = metricMean("S5", "safe_before_danger_rate") !== undefined && metricMean("S0", "safe_before_danger_rate") !== undefined
    ? pct(Math.max(0, metricMean("S5", "safe_before_danger_rate") - metricMean("S0", "safe_before_danger_rate")))
    : "待实验";
  return `<div class="view two"><section><h2>策略建议</h2>
    <p>当前训练案例：${escapeHtml(selected?.case_name || "未选择")}。</p>
    <p>当前 ${escapeHtml(state.run?.run?.policy_id || "-")} 安全转移率为 ${pct(m.safe_before_danger_rate)}，脆弱群体风险为 ${pct(m.vulnerable_harm_risk)}。</p>
    <p>批量实验中 S5 相比 S0 的安全转移率均值提升：${uplift}。</p>
    <p>优先动作：${escapeHtml(state.scenarioConfig.key_breakpoints || (selected?.intervention_points || ["提前预警", "脆弱户逐户确认", "车辆与照护资源联动调度", "桥路断点预案同步更新"]).join("、"))}。</p>
    </section><section><h2>交付状态</h2>
    ${row("数据标签", "FACT / SYNTHETIC / SIMULATED")}
    ${row("外部模型密钥", "不需要")}
    ${row("核心内核", "规则智能体 + 多层网络 + 资源调度")}
    ${row("输出", "JSON 指标、事件、个体轨迹、实验比较")}
    </section></div>`;
}

init();
