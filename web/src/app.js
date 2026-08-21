const urlParams = new URLSearchParams(window.location.search);
const API_BASE = urlParams.get("api") || window.HONGCE_API_BASE || "http://127.0.0.1:8000";
const SPATIAL_PACKAGE_PATH = "data/spatial/qingyuan";

const policies = [
  ["S0", "基线单向通知", "短信/广播为主"],
  ["S1", "设施优先加固", "桥路与避难点"],
  ["S2", "数字预警前移", "更早触达"],
  ["S3", "网格叫应确认", "逐户闭环"],
  ["S4", "资源集中调拨", "车辆/床位扩容"],
  ["S5", "韧性综合方案", "前移+叫应+调拨"]
];

const tabs = ["县域态势总览", "情景编辑器", "参数校准", "实时推演", "叫应确认台", "政策对比", "策略优化与RL", "个体与事件解释", "复盘与建议"];

const fallbackSpatialMap = {
  package_id: "frontend-fallback-qingyuan",
  label: "SYNTHETIC_SPATIAL",
  method: {
    route_engine: "frontend_fallback",
    risk_overlay: "embedded coordinates"
  },
  places: [
    { id: "north_valley", name: "北谷村", type: "village", population: 220, vulnerable_population: 90, risk_score: 0.82, x: 121.318, y: 31.305 },
    { id: "qingyuan_town", name: "清源镇", type: "town", population: 530, vulnerable_population: 110, risk_score: 0.82, x: 121.392, y: 31.258 },
    { id: "south_valley", name: "南谷村", type: "village", population: 180, vulnerable_population: 70, risk_score: 0.82, x: 121.428, y: 31.205 },
    { id: "nursing_home", name: "青松养老照料中心", type: "care", population: 69, vulnerable_population: 55, risk_score: 0.82, x: 121.346, y: 31.282 }
  ],
  shelters: [
    { id: "school_shelter", name: "第二中学避难点", capacity: 620, x: 121.46, y: 31.248 },
    { id: "gym_shelter", name: "县体育馆避难点", capacity: 180, x: 121.405, y: 31.225 }
  ],
  bridges: [
    { id: "bridge_east", name: "东桥", risk_score: 0.8, x: 121.372, y: 31.272 },
    { id: "bridge_south", name: "南涵洞", risk_score: 0.45, x: 121.416, y: 31.214 }
  ],
  risk_zones: [
    { id: "floodplain_01", name: "河湾漫溢区", risk_score: 0.82, geometry: { type: "Polygon", coordinates: [[[121.3, 31.32], [121.47, 31.29], [121.45, 31.22], [121.33, 31.2], [121.3, 31.32]]] } }
  ],
  routes: [
    { id: "route-north_valley-gym_shelter", origin_id: "north_valley", shelter_id: "gym_shelter", travel_minutes: 29.1, risk_score: 0.82, bridge_exposure_score: 0.8, crosses_high_risk: true },
    { id: "route-qingyuan_town-gym_shelter", origin_id: "qingyuan_town", shelter_id: "gym_shelter", travel_minutes: 9.3, risk_score: 0.82, bridge_exposure_score: 0, crosses_high_risk: true },
    { id: "route-south_valley-gym_shelter", origin_id: "south_valley", shelter_id: "gym_shelter", travel_minutes: 7.5, risk_score: 0.82, bridge_exposure_score: 0.45, crosses_high_risk: true },
    { id: "route-nursing_home-gym_shelter", origin_id: "nursing_home", shelter_id: "gym_shelter", travel_minutes: 20.3, risk_score: 0.82, bridge_exposure_score: 0.8, crosses_high_risk: true }
  ],
  coverage: { coverage_minutes: 60, covered_place_count: 4, uncovered_place_count: 0, coverage_rate: 1, total_shelter_capacity: 800 }
};

const state = {
  active: tabs[0],
  run: null,
  experiment: null,
  mdp: null,
  optimization: null,
  bandit: null,
  parameterLibrary: null,
  selectedCaseParameters: null,
  parameterScenario: null,
  trace: null,
  cases: [],
  selectedCase: null,
  caseScenario: null,
  spatialPackage: fallbackSpatialMap,
  spatialContext: null,
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
  editorSub: "params",
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
    try {
      await loadSpatialPackage();
    } catch (error) {
      state.spatialContext = null;
      state.spatialPackage = fallbackSpatialMap;
      setNotice(`空间包暂用离线 fallback：${error.message || "API 未提供空间包"}`);
    }
    await loadCases();
    await loadParameters();
  } catch {
    $("#health").textContent = "API offline";
  }
  render();
}

async function loadSpatialPackage() {
  const params = new URLSearchParams({ path: SPATIAL_PACKAGE_PATH });
  const data = await request(`/spatial/package?${params.toString()}`);
  if (data.error) throw new Error(data.error);
  state.spatialContext = data;
  state.spatialPackage = data.package || fallbackSpatialMap;
  if (data.scenario_overrides) {
    Object.assign(state.scenarioConfig, data.scenario_overrides);
  }
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
  try {
    state.selectedCaseParameters = await request(`/parameters/cases/${encodeURIComponent(caseId)}`);
  } catch {
    state.selectedCaseParameters = null;
  }
  state.scenarioConfig.key_breakpoints = (state.selectedCase.intervention_points || []).join("、");
  state.scenarioConfig.metric_candidates = (state.selectedCase.metric_candidates || []).slice(0, 4).join("、");
  if (rerender) render();
}

async function loadParameters() {
  state.parameterLibrary = await request("/parameters");
  if (state.selectedCase?.case_id) {
    state.selectedCaseParameters = await request(`/parameters/cases/${encodeURIComponent(state.selectedCase.case_id)}`);
  }
}

async function deriveParameterScenario() {
  setBusy(true, "正在从案例参数库推导情景参数...");
  try {
    const caseId = state.selectedCase?.case_id || "";
    state.parameterScenario = await request("/parameters/derive-scenario", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId })
    });
    const suggestion = state.parameterScenario.scenario_config_suggestion || {};
    for (const key of ["warning_minute", "evacuation_order_minute", "communication_failure_rate"]) {
      if (suggestion[key] !== undefined) state.scenarioConfig[key] = suggestion[key];
    }
    setNotice(`已从 ${caseId || "全案例"} 参数库推导情景配置。`);
  } catch (error) {
    setNotice(error.message || "参数推导失败");
  } finally {
    setBusy(false);
    render();
  }
}

async function runSimulation(policy) {
  setBusy(true, "正在运行多智能体仿真...");
  try {
    const seed = Number($("#seed").value);
    const population = Number($("#population").value);
    const caseId = state.selectedCase?.case_id;
    const scenario_overrides = buildScenarioOverrides();
    const spatial_package_path = SPATIAL_PACKAGE_PATH;
    const validation = await request("/scenarios/validate", { method: "POST", body: JSON.stringify({ population, case_id: caseId, scenario_overrides, spatial_package_path }) });
    if (!validation.valid) throw new Error(validation.reason);
    const created = await request("/simulations/run", {
      method: "POST",
      body: JSON.stringify({ policy_id: policy, seed, population, case_id: caseId, scenario_overrides, spatial_package_path, output_dir: "outputs/api" })
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

async function loadMdpContract() {
  if (state.mdp) return state.mdp;
  state.mdp = await request("/decision/mdp");
  return state.mdp;
}

async function runPolicyOptimization() {
  setBusy(true, "正在运行可解释政策参数优化...");
  try {
    state.mdp = await loadMdpContract();
    state.optimization = await request("/decision/optimize", {
      method: "POST",
      body: JSON.stringify({
        method: "grid",
        max_candidates: 18,
        seeds: [202608060, 202608061, 202608062],
        population: Number($("#population").value),
        spatial_package_path: SPATIAL_PACKAGE_PATH,
        scenario_overrides: buildScenarioOverrides()
      })
    });
    setNotice("策略优化完成：候选组合均来自实际仿真运行。");
  } catch (error) {
    setNotice(error.message || "策略优化失败");
  } finally {
    setBusy(false);
    render();
  }
}

async function runBanditRecommendation() {
  setBusy(true, "正在运行 Contextual Bandit 策略推荐...");
  try {
    state.bandit = await request("/decision/bandit", {
      method: "POST",
      body: JSON.stringify({
        seeds: [202608060, 202608061],
        population: Number($("#population").value),
        spatial_package_path: SPATIAL_PACKAGE_PATH,
        scenario_overrides: buildScenarioOverrides(),
        current_risk_level: "high"
      })
    });
    setNotice(`Bandit 推荐：${state.bandit.recommended.action}`);
  } catch (error) {
    setNotice(error.message || "Bandit 推荐失败");
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
    "参数校准": calibrationWorkbench,
    "实时推演": timeline,
    "叫应确认台": callDesk,
    "政策对比": comparison,
    "策略优化与RL": decisionLab,
    "个体与事件解释": explanation,
    "复盘与建议": review
  };
  content.innerHTML = route[state.active]();
  const experimentButton = $("#run-experiment");
  if (experimentButton) experimentButton.addEventListener("click", runExperiment);
  const mdpButton = $("#load-mdp");
  if (mdpButton) {
    mdpButton.addEventListener("click", async () => {
      setBusy(true, "正在读取 MDP/POMDP 合约...");
      try {
        await loadMdpContract();
        setNotice("MDP/POMDP 合约已加载。");
      } catch (error) {
        setNotice(error.message || "MDP 合约加载失败");
      } finally {
        setBusy(false);
        render();
      }
    });
  }
  const optimizeButton = $("#run-optimization");
  if (optimizeButton) optimizeButton.addEventListener("click", runPolicyOptimization);
  const banditButton = $("#run-bandit");
  if (banditButton) banditButton.addEventListener("click", runBanditRecommendation);
  const reloadParametersButton = $("#reload-parameters");
  if (reloadParametersButton) {
    reloadParametersButton.addEventListener("click", async () => {
      setBusy(true, "正在读取案例参数库...");
      try {
        await loadParameters();
        setNotice("案例参数库已加载。");
      } catch (error) {
        setNotice(error.message || "参数库加载失败");
      } finally {
        setBusy(false);
        render();
      }
    });
  }
  const deriveParametersButton = $("#derive-parameter-scenario");
  if (deriveParametersButton) deriveParametersButton.addEventListener("click", deriveParameterScenario);
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
  document.querySelectorAll("[data-editor-sub]").forEach((button) => {
    button.addEventListener("click", () => {
      state.editorSub = button.dataset.editorSub;
      render();
    });
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

function calibrationWorkbench() {
  const library = state.parameterLibrary;
  const quality = library?.quality || {};
  const caseRecord = state.selectedCaseParameters?.case;
  const estimates = caseRecord?.parameter_estimates || [];
  const aggregate = library?.aggregates?.ALL_CASES?.parameters || [];
  const missing = quality.missing_review_item_counts || {};
  return `<div class="view">
    <section>
      <div class="section-actions">
        <div>
          <h2>案例参数库</h2>
          <p class="section-note">这里把应急管理部案例转成可校准参数范围。每个参数都保留来源标签、置信度和复核状态，供仿真、策略优化和专家校准共用。</p>
        </div>
        <div class="toolbar-buttons">
          <button id="reload-parameters" class="secondary">读取参数库</button>
          <button id="derive-parameter-scenario">用当前案例推导情景</button>
        </div>
      </div>
      <div class="metric-grid compact">
        ${metric("案例数", quality.case_count || 0, "neutral")}
        ${metric("参数估计", quality.parameter_estimate_count || 0, "neutral")}
        ${metric("平均置信度", pct(quality.mean_confidence || 0), quality.mean_confidence >= 0.55 ? "good" : "warn")}
        ${metric("需复核转移数", missing.transfer_or_evacuation_count || 0, "warn")}
      </div>
    </section>
    <section class="calibration-grid-view">
      <div class="decision-card">
        <h2>当前案例参数</h2>
        ${caseRecord ? `
          ${row("案例", `${caseRecord.case_id} · ${caseRecord.case_name}`)}
          ${row("情景类型", caseRecord.scenario_class)}
          ${row("平均置信度", pct(caseRecord.calibration_readiness?.mean_confidence || 0))}
          ${row("下一步复核", caseRecord.calibration_readiness?.next_review_action || "-")}
          <div class="parameter-table">
            ${estimates.slice(0, 12).map((item) => parameterRow(item)).join("")}
          </div>
        ` : `<p class="section-note">请先在“情景编辑器”选择案例。</p>`}
      </div>
      <div class="decision-card">
        <h2>全案例聚合范围</h2>
        <div class="parameter-table">
          ${aggregate.slice(0, 14).map((item) => parameterRow(item, true)).join("")}
        </div>
      </div>
    </section>
    <section class="calibration-grid">
      ${sourceCard("CASE_DERIVED", library?.source_labels?.CASE_DERIVED, "来自报告")}
      ${sourceCard("QGIS_DERIVED", library?.source_labels?.QGIS_DERIVED, "来自空间")}
      ${sourceCard("EXPERT_PRIOR", library?.source_labels?.EXPERT_PRIOR, "专家先验")}
      ${sourceCard("SYNTHETIC_ASSUMPTION", library?.source_labels?.SYNTHETIC_ASSUMPTION, "临时假设")}
    </section>
    ${state.parameterScenario ? `<section><h2>参数推导情景</h2><div class="decision-result">
      ${Object.entries(state.parameterScenario.scenario_config_suggestion || {}).map(([key, value]) => row(key, value)).join("")}
    </div></section>` : ""}
  </div>`;
}

function parameterRow(item, aggregate = false) {
  const confidence = item.confidence ?? item.mean_confidence ?? 0;
  return `<div class="parameter-row">
    <div>
      <strong>${escapeHtml(parameterLabel(item.name))}</strong>
      <span>${escapeHtml(item.name)}</span>
    </div>
    <b>${escapeHtml(item.value_min)} - ${escapeHtml(item.value_max)} ${escapeHtml(item.unit || "")}</b>
    <em class="${confidence >= 0.55 ? "ok-text" : "warning-text"}">${pct(confidence)}</em>
    <small>${escapeHtml(aggregate ? item.dominant_source_label : item.source_label)}</small>
  </div>`;
}

function parameterLabel(name) {
  return {
    warning_lead_minutes: "预警提前量",
    evacuation_order_delay_minutes: "转移命令延迟",
    response_activation_delay_minutes: "响应启动延迟",
    communication_failure_rate: "通信失败率",
    grassroots_call_strength: "网格叫应强度",
    vulnerable_priority_weight: "脆弱优先权重",
    bridge_closure_threshold: "桥梁封闭阈值",
    route_failure_probability: "路线失效概率",
    shelter_capacity_pressure: "避难容量压力",
    public_trust_delta_prior: "信任变化先验",
    casualty_rate_anchor: "伤亡锚点",
    property_loss_rate_anchor: "财产损失锚点"
  }[name] || name;
}

function sourceCard(label, description, title) {
  return `<div class="calibration-card">
    <strong>${escapeHtml(title)}</strong>
    <span>${escapeHtml(label)}</span>
    <p>${escapeHtml(description || "-")}</p>
  </div>`;
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
  const spatial = state.run?.spatial_context || state.spatialContext;
  const spatialSummary = spatial?.summary || spatialPackageSummary(state.spatialPackage);
  return `<div class="view">
    <section class="metric-grid">
      ${metric("安全转移率", pct(m.safe_before_danger_rate))}
      ${metric("脆弱群体风险", pct(m.vulnerable_harm_risk), "warn")}
      ${metric("闭环响应", pct(m.response_closure_rate))}
      ${metric("平均排队分钟", num(m.resource_queue_minutes_mean), "neutral")}
    </section>
    <section class="map-band">
      ${terrainMap(m)}
      <div class="side-table">
        <h2>最新运行</h2>
        ${row("训练案例", caseContext?.case_id || "未选择")}
        ${row("策略", state.run?.run?.policy_id || "未运行")}
        ${row("Run ID", state.run?.run?.id || "-")}
        ${row("中位提前量", `${m.lead_time_minutes_median || 0} 分钟`)}
        ${row("群体公平缺口", num(m.group_safety_gap))}
        ${row("空间包", spatial?.package_id || "离线 fallback")}
        ${row("覆盖率/床位", `${pct(spatialSummary.coverage_rate)} / ${spatialSummary.total_shelter_capacity || state.spatialPackage?.coverage?.total_shelter_capacity || 0}`)}
        ${row("路线均值/高风险占比", `${spatialSummary.mean_route_minutes || 0} 分钟 / ${pct(spatialSummary.high_risk_route_share)}`)}
      </div>
    </section>
  </div>`;
}

function spatialPackageSummary(spatialPackage) {
  const spatial = normalizedSpatialMapFrom(spatialPackage || fallbackSpatialMap);
  const routes = spatial.routes || [];
  const routeMinutes = routes.map((route) => Number(route.travel_minutes || 0)).filter(Number.isFinite);
  const highRiskRoutes = routes.filter((route) => route.crosses_high_risk || Number(route.bridge_exposure_score || 0) >= 0.65);
  return {
    coverage_rate: Number(spatial.coverage?.coverage_rate || 0),
    total_shelter_capacity: Number(spatial.coverage?.total_shelter_capacity || spatial.shelters.reduce((sum, shelter) => sum + Number(shelter.capacity || 0), 0)),
    mean_route_minutes: routeMinutes.length ? Math.round((routeMinutes.reduce((sum, value) => sum + value, 0) / routeMinutes.length) * 100) / 100 : 0,
    high_risk_route_share: routes.length ? highRiskRoutes.length / routes.length : 0
  };
}

function terrainMap(metrics = {}) {
  const spatial = normalizedSpatialMap();
  const live = liveSpatialState(spatial);
  const bounds = mapBounds(spatial);
  const project = ([lon, lat]) => {
    const width = 1000;
    const height = 620;
    const pad = 70;
    const x = pad + ((lon - bounds.minLon) / (bounds.maxLon - bounds.minLon)) * (width - pad * 2);
    const y = height - pad - ((lat - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * (height - pad * 2);
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
  };
  const path = (coords) => coords.map((coord, index) => `${index ? "L" : "M"}${project(coord).join(" ")}`).join(" ");
  const closedPath = (coords) => `${path(coords)} Z`;
  const roadPaths = spatial.routes.map((route) => {
    const routeLive = live.routes[route.id] || {};
    const classes = ["map-road"];
    if (route.crosses_high_risk || route.bridge_exposure_score >= 0.65) classes.push("risk-route");
    if (routeLive.status === "closed") classes.push("closed");
    if (routeLive.status === "active") classes.push("active");
    const label = `${route.name || route.id} · ${route.travel_minutes || 0} 分钟 · ${routeLive.label}`;
    return `<path class="${classes.join(" ")}" d="${path(route.coordinates)}"><title>${escapeHtml(label)}</title></path>`;
  }).join("");
  const riskZones = spatial.risk_zones.map((zone) => `<path class="risk-zone risk-${riskLevel(zone.risk_score)}" d="${closedPath(zone.polygon)}"><title>${escapeHtml(zone.name)} · 风险 ${Math.round(Number(zone.risk_score || 0) * 100)}%</title></path>`).join("");
  const contours = terrainContours();
  const villages = spatial.places.map((place) => {
    const [x, y] = project([place.x, place.y]);
    const vulnerable = Math.round((place.vulnerable_population / place.population) * 100);
    const placeLive = live.places[place.id] || { sheltered: 0, total: 0, blocked: 0, moving: 0, progress: 0 };
    const progress = Math.round(placeLive.progress * 100);
    const ring = Math.max(0, Math.min(100, progress));
    const markerType = place.type || (place.id.includes("town") ? "town" : place.id.includes("nursing") ? "care" : "village");
    return `<g class="map-point ${markerType} risk-${riskLevel(place.risk_score)}" transform="translate(${x} ${y})">
      <circle class="progress-ring" r="15" pathLength="100" stroke-dasharray="${ring} ${100 - ring}"></circle>
      <circle r="${markerType === "town" ? 10 : markerType === "care" ? 9 : 8}"></circle>
      <text x="14" y="-10">${escapeHtml(place.name)}</text>
      <text class="map-subtext" x="14" y="8">已转 ${placeLive.sheltered}/${placeLive.total || place.population} · 脆弱 ${vulnerable}%</text>
      ${placeLive.blocked ? `<text class="map-alert" x="14" y="25">受阻 ${placeLive.blocked}</text>` : ""}
    </g>`;
  }).join("");
  const shelters = spatial.shelters.map((shelter) => {
    const [x, y] = project([shelter.x, shelter.y]);
    const capacityShare = Math.round((live.shelteredTotal / Math.max(1, shelter.capacity || 1)) * 100);
    return `<g class="map-point shelter" transform="translate(${x} ${y})">
      <rect x="-9" y="-9" width="18" height="18" rx="3"></rect>
      <text x="15" y="-8">${escapeHtml(shelter.name)}</text>
      <text class="map-subtext" x="15" y="10">容量 ${shelter.capacity} · 总安置 ${live.shelteredTotal} · ${capacityShare}%</text>
    </g>`;
  }).join("");
  const bridges = spatial.bridges.map((bridge) => {
    const [x, y] = project([bridge.x, bridge.y]);
    const closed = live.bridgeClosed && bridge.risk_score >= 0.65;
    return `<g class="map-bridge ${bridge.risk_score > 0.7 ? "high" : ""} ${closed ? "closed" : ""}" transform="translate(${x} ${y})">
      <path d="M-12 0 L12 0 M-8 -5 L-8 5 M0 -5 L0 5 M8 -5 L8 5"></path>
      <text x="14" y="-6">${escapeHtml(bridge.name)}${closed ? " 封闭" : ""}</text>
    </g>`;
  }).join("");
  const safeRate = Math.round(Number(metrics.safe_before_danger_rate || 0) * 1000) / 10;
  const queue = Number(metrics.resource_queue_minutes_mean || 0).toFixed(1);
  const source = state.spatialContext?.package_id || spatial.package_id || "fallback";
  const method = spatial.method?.route_engine || "unknown";
  return `<div class="terrain-panel">
    <div class="terrain-toolbar">
      <div><strong>QGIS 实时空间态势图</strong><span>空间包 ${escapeHtml(source)} · ${escapeHtml(method)} · EPSG:4326</span></div>
      <div class="map-badges"><span>t=${live.minute}′</span><span class="${live.commsDegraded ? "bad" : "good"}">通信${live.commsDegraded ? "受损" : "正常"}</span><span class="${live.bridgeClosed ? "bad" : "good"}">桥涵${live.bridgeClosed ? "封闭" : "可通行"}</span><span>安全转移 ${safeRate}%</span></div>
    </div>
    <svg class="terrain-map" viewBox="0 0 1000 620" role="img" aria-label="洪策 QGIS 地形态势图">
      <defs>
        <linearGradient id="terrainBase" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#d9e8d2" />
          <stop offset="38%" stop-color="#b8d1b0" />
          <stop offset="68%" stop-color="#d9c58f" />
          <stop offset="100%" stop-color="#8f846c" />
        </linearGradient>
        <radialGradient id="ridgeLight" cx="30%" cy="22%" r="65%">
          <stop offset="0%" stop-color="rgba(255,255,255,0.62)" />
          <stop offset="60%" stop-color="rgba(255,255,255,0.08)" />
          <stop offset="100%" stop-color="rgba(50,54,44,0.22)" />
        </radialGradient>
        <filter id="terrainShadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#31413c" flood-opacity="0.22" />
        </filter>
      </defs>
      <rect class="terrain-bg" x="0" y="0" width="1000" height="620"></rect>
      <path class="terrain-hillshade hill-a" d="M20 500 C150 390 205 225 360 210 C520 194 600 100 780 68 C900 48 980 90 1010 130 L1010 620 L20 620 Z"></path>
      <path class="terrain-hillshade hill-b" d="M-40 210 C120 260 238 120 405 142 C548 160 660 260 806 235 C918 216 965 168 1035 198 L1035 -20 L-40 -20 Z"></path>
      <path class="river" d="M-20 136 C122 173 200 239 326 250 C458 262 565 342 690 372 C812 403 902 480 1025 510"></path>
      ${contours}
      ${riskZones}
      ${roadPaths}
      ${bridges}
      ${villages}
      ${shelters}
      <g class="north-arrow" transform="translate(925 74)">
        <path d="M0 -34 L13 16 L0 8 L-13 16 Z"></path>
        <text y="42">N</text>
      </g>
    </svg>
    <div class="live-strip">
      <div><strong>${live.shelteredTotal}</strong><span>已安置对象</span></div>
      <div><strong>${live.blockedTotal}</strong><span>受阻/资源不足</span></div>
      <div><strong>${live.movingTotal}</strong><span>正在转移</span></div>
      <div><strong>${live.dangerEta}′</strong><span>距危险到达</span></div>
    </div>
    <div class="terrain-footer">
      <span><i class="legend risk"></i>高风险漫溢区</span>
      <span><i class="legend road"></i>可通行路线</span>
      <span><i class="legend closed"></i>封闭/高风险路线</span>
      <span><i class="legend bridge"></i>桥梁/涵洞断点</span>
      <span><i class="legend shelter"></i>避难点</span>
      <span>资源排队 ${queue} 分钟</span>
    </div>
  </div>`;
}

function normalizedSpatialMap() {
  return normalizedSpatialMapFrom(state.spatialPackage || fallbackSpatialMap);
}

function normalizedSpatialMapFrom(source) {
  const fallbackRiskById = Object.fromEntries((fallbackSpatialMap.risk_zones || []).map((zone) => [zone.id, zone]));
  const fallbackRouteById = Object.fromEntries((fallbackSpatialMap.routes || []).map((route) => [route.id, route]));
  const places = (source.places || fallbackSpatialMap.places).map((place) => ({
    type: place.type || (place.id?.includes("town") ? "town" : place.id?.includes("nursing") ? "care" : "village"),
    ...place
  }));
  const shelters = source.shelters || fallbackSpatialMap.shelters;
  const placeById = Object.fromEntries(places.map((place) => [place.id, place]));
  const shelterById = Object.fromEntries(shelters.map((shelter) => [shelter.id, shelter]));
  const risk_zones = (source.risk_zones || fallbackSpatialMap.risk_zones).map((zone) => {
    const fallback = fallbackRiskById[zone.id] || {};
    const geometry = zone.geometry || fallback.geometry;
    const polygon = zone.polygon || geometry?.coordinates?.[0] || fallback.polygon || [];
    return { ...fallback, ...zone, polygon };
  }).filter((zone) => zone.polygon?.length);
  const routes = (source.routes || fallbackSpatialMap.routes).map((route) => {
    const fallback = fallbackRouteById[route.id] || {};
    const origin = placeById[route.origin_id] || placeById[fallback.origin_id];
    const shelter = shelterById[route.shelter_id] || shelterById[fallback.shelter_id];
    const coordinates = route.coordinates || fallback.coordinates || (origin && shelter ? [[origin.x, origin.y], [shelter.x, shelter.y]] : []);
    return { ...fallback, ...route, coordinates, name: route.name || `${origin?.name || route.origin_id}-${shelter?.name || route.shelter_id}` };
  }).filter((route) => route.coordinates?.length >= 2);
  return { ...fallbackSpatialMap, ...source, places, shelters, risk_zones, routes };
}

function liveSpatialState(spatial) {
  const agents = state.run?.agents || [];
  const events = state.run?.events || [];
  const scenario = state.run?.scenario_config || state.scenarioConfig;
  const minute = Math.max(0, ...events.map((event) => Number(event.minute || 0)));
  const dangerMinute = Number(scenario.danger_arrival_minute || 0);
  const bridgeMinute = Number(scenario.bridge_closure_minute || 0);
  const commMinute = Number(scenario.communication_failure_minute || 0);
  const bridgeClosed = events.some((event) => String(event.message || "").includes("bridge_east closed")) || (bridgeMinute > 0 && minute >= bridgeMinute);
  const commsDegraded = events.some((event) => String(event.message || "").includes("communications degraded")) || (commMinute > 0 && minute >= commMinute);
  const places = Object.fromEntries(spatial.places.map((place) => [place.id, { total: 0, sheltered: 0, blocked: 0, moving: 0, progress: 0 }]));
  for (const agent of agents) {
    const bucket = places[agent.location_id];
    if (!bucket) continue;
    bucket.total += 1;
    const status = String(agent.status || "");
    if (status.includes("sheltered")) bucket.sheltered += 1;
    else if (status.includes("blocked") || status.includes("unreachable") || status.includes("waiting")) bucket.blocked += 1;
    else if (status.includes("evac") || status.includes("transfer") || status.includes("confirmed")) bucket.moving += 1;
  }
  for (const place of spatial.places) {
    const bucket = places[place.id];
    if (!bucket.total) bucket.total = Number(place.population || 0);
    bucket.progress = bucket.total ? bucket.sheltered / bucket.total : 0;
  }
  const routes = Object.fromEntries(spatial.routes.map((route) => {
    const closed = bridgeClosed && (route.bridge_exposure_score >= 0.65 || route.crosses_high_risk);
    const active = minute >= Number(scenario.evacuation_order_minute || 0) && !closed;
    const label = closed ? "封闭/绕行" : active ? "转移中" : "待命";
    return [route.id, { status: closed ? "closed" : active ? "active" : "standby", label }];
  }));
  const shelteredTotal = agents.filter((agent) => String(agent.status || "").includes("sheltered")).length;
  const blockedTotal = agents.filter((agent) => String(agent.status || "").includes("blocked") || String(agent.reason || "").includes("资源")).length;
  const movingTotal = Math.max(0, agents.filter((agent) => String(agent.status || "").includes("evac") || String(agent.status || "").includes("confirmed")).length);
  return {
    minute,
    dangerEta: dangerMinute ? Math.max(0, dangerMinute - minute) : 0,
    bridgeClosed,
    commsDegraded,
    places,
    routes,
    shelteredTotal,
    blockedTotal,
    movingTotal
  };
}

function riskLevel(score) {
  const value = Number(score || 0);
  if (value >= 0.75) return "high";
  if (value >= 0.45) return "medium";
  return "low";
}

function mapBounds(spatial) {
  const coords = [
    ...spatial.places.map((item) => [item.x, item.y]),
    ...spatial.shelters.map((item) => [item.x, item.y]),
    ...spatial.bridges.map((item) => [item.x, item.y]),
    ...spatial.risk_zones.flatMap((item) => item.polygon),
    ...spatial.routes.flatMap((item) => item.coordinates)
  ];
  const lons = coords.map(([lon]) => lon);
  const lats = coords.map(([, lat]) => lat);
  return {
    minLon: Math.min(...lons) - 0.015,
    maxLon: Math.max(...lons) + 0.015,
    minLat: Math.min(...lats) - 0.015,
    maxLat: Math.max(...lats) + 0.015
  };
}

function terrainContours() {
  const lines = [
    "M18 492 C156 430 194 340 318 332 C488 320 588 234 744 212 C870 194 942 226 1012 282",
    "M30 430 C160 378 228 292 346 294 C482 296 560 208 720 168 C842 136 930 152 1018 210",
    "M-10 368 C118 330 220 252 342 260 C486 268 590 186 744 134 C856 96 940 104 1022 158",
    "M12 306 C132 290 220 210 360 218 C520 228 628 154 760 100 C850 62 934 62 1020 112",
    "M65 548 C190 502 310 432 462 438 C606 444 716 394 848 350 C922 326 980 328 1028 360",
    "M110 588 C235 548 338 496 474 500 C640 506 740 456 890 420"
  ];
  return lines.map((d, index) => `<path class="contour contour-${index % 3}" d="${d}"></path>`).join("");
}

function editor() {
  const sub = state.editorSub || "params";
  return `<div class="view">
    <div class="subtabs">
      <button data-editor-sub="params" class="${sub === "params" ? "active" : ""}">县域模拟参数设定</button>
      <button data-editor-sub="cases" class="${sub === "cases" ? "active" : ""}">经典案例模拟（${state.cases.length || 28} 个案例）</button>
    </div>
    ${sub === "params" ? editorParams() : editorCases()}
  </div>`;
}

function editorParams() {
  const selected = state.selectedCase;
  const cfg = state.scenarioConfig;
  return `<section><h2>合成县域设定</h2><div class="form-grid">
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
    </div></section>`;
}

function editorCases() {
  const selected = state.selectedCase;
  const scenario = state.caseScenario;
  const cases = state.cases.length ? state.cases : [];
  return `<section><h2>真实案例训练库</h2>
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
        ${row("致灾触发", (selected?.hazard_trigger || []).join("、") || "-")}
        ${row("影响场所", (selected?.affected_setting || []).join("、") || "-")}
        ${row("行动者链", (selected?.actor_chain || []).join(" → ") || "-")}
        ${row("自下而上信号", (selected?.bottom_up_signals || []).join("、") || "-")}
        ${row("干预点", (selected?.intervention_points || []).join("、") || "-")}
        ${row("状态机", (scenario?.state_machine || []).join(" → ") || "-")}
        ${row("指标候选", (selected?.metric_candidates || []).join("、") || "-")}
        ${row("真实伤亡/死失", selected?.observed_outcomes?.deaths_or_dead_missing || "未抽取")}
        ${row("直接经济损失", selected?.observed_outcomes?.direct_economic_loss || "未抽取")}
        <div class="tag-band">${(selected?.failure_modes || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
        <div class="tag-band policy-tags">${(scenario?.recommended_policies || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
      </div>
    </div>
    </section>`;
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
  if (state.experiment?.experiments) {
    const values = Object.values(state.experiment.experiments)
      .map((experiment) => experiment.summary?.[policy]?.[metricName]?.mean)
      .filter((value) => Number.isFinite(Number(value)))
      .map(Number);
    if (values.length) return values.reduce((sum, value) => sum + value, 0) / values.length;
  }
  const entry = state.experiment?.summary?.[policy]?.[metricName];
  return entry && typeof entry === "object" ? Number(entry.mean) : undefined;
}

function comparison() {
  const notes = state.experiment?.experiments ? Object.values(state.experiment.experiments).flatMap((item) => item.interpretation) : [];
  return `<div class="view"><div class="toolbar"><button class="primary" id="run-experiment">运行 A/B/C 实验</button></div>
    <section class="comparison">${policies.map(([id, name]) => `<div class="policy-card"><strong>${id}</strong><span>${name}</span><b>${pct(metricMean(id, "safe_before_danger_rate"))}</b><small>${state.experiment?.experiments ? "A/B/C 综合安全转移率" : "安全转移率均值"}</small></div>`).join("")}</section>
    <section class="notes">${notes.length ? notes.map((note) => `<p>${escapeHtml(note)}</p>`).join("") : "<p>运行批量实验后显示策略差异、区间和断点解释。</p>"}</section></div>`;
}

function decisionLab() {
  const mdp = state.mdp;
  const best = state.optimization?.best;
  const recommended = state.bandit?.recommended;
  return `<div class="view">
    <div class="toolbar">
      <button id="load-mdp">查看 MDP/POMDP 定义</button>
      <button class="primary" id="run-optimization">运行参数优化</button>
      <button id="run-bandit">运行 Contextual Bandit</button>
    </div>
    <section class="decision-grid">
      <div class="decision-card">
        <h2>MDP/POMDP 结构</h2>
        ${mdp ? `
          ${row("观测模型", mdp.observation_model)}
          ${row("Transition", mdp.transition_source)}
          <div class="tag-band">${mdp.state_variables.slice(0, 10).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
          <div class="tag-band policy-tags">${mdp.action_variables.slice(0, 8).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
        ` : "<p>先加载合约，系统会显示状态、动作、奖励、约束和校准来源。</p>"}
      </div>
      <div class="decision-card">
        <h2>奖励与约束</h2>
        ${mdp ? `
          <div class="reward-list">${Object.entries(mdp.reward_terms).map(([key, value]) => `<span>${escapeHtml(key)} <b>${num(value)}</b></span>`).join("")}</div>
          <div class="constraint-list">${Object.entries(mdp.constraints).map(([key, value]) => `<span>${escapeHtml(key)} <b>${num(value)}</b></span>`).join("")}</div>
        ` : "<p>奖励函数同时惩罚伤亡风险、排队、群体公平缺口和漏管动作。</p>"}
      </div>
    </section>
    <section class="decision-grid">
      <div class="decision-card">
        <h2>最优政策参数组合</h2>
        ${best ? optimizationSummary(best) : "<p>运行参数优化后，这里会显示可解释的最优组合。每个候选组合都会调用仿真内核实际运行。</p>"}
      </div>
      <div class="decision-card">
        <h2>高级 RL 推荐</h2>
        ${recommended ? banditSummary(recommended) : "<p>Contextual Bandit 会比较“提前预警、加车、养老院优先、备用通信、桥涵绕行”等动作臂。</p>"}
      </div>
    </section>
    <section>
      <h2>校准与验证路线</h2>
      <div class="calibration-grid">
        ${["应急管理部案例校准参数范围", "QGIS 空间包校准路程/覆盖/风险区", "专家校准致灾因子", "S0-S5 与优化/RL 对比", "消融：去掉网格叫应", "消融：去掉脆弱优先", "消融：去掉 QGIS 空间约束", "不确定性：雨强/通信/车辆/响应率"].map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
    </section>
  </div>`;
}

function optimizationSummary(best) {
  const c = best.candidate;
  const m = best.metrics_mean;
  return `<div class="decision-result">
    ${row("综合奖励", best.aggregate_reward)}
    ${row("安全转移率", pct(m.safe_before_danger_rate))}
    ${row("脆弱风险", pct(m.vulnerable_harm_risk))}
    ${row("群体公平缺口", num(m.group_safety_gap))}
    ${row("排队分钟", num(m.resource_queue_minutes_mean))}
    <div class="tag-band policy-tags">
      <span>预警提前 ${escapeHtml(c.warning_lead_minutes)} 分钟</span>
      <span>命令提前 ${escapeHtml(c.order_lead_minutes)} 分钟</span>
      <span>车辆 x${escapeHtml(c.vehicle_multiplier)}</span>
      <span>脆弱优先 ${escapeHtml(c.vulnerable_priority_weight)}</span>
      <span>通信补救 ${escapeHtml(c.communication_repair_strength)}</span>
    </div>
    ${Object.keys(best.violations || {}).length ? `<p class="warning-text">仍有约束违背：${escapeHtml(JSON.stringify(best.violations))}</p>` : "<p class=\"ok-text\">硬约束未触发惩罚。</p>"}
  </div>`;
}

function banditSummary(recommended) {
  const m = recommended.metrics_mean;
  return `<div class="decision-result">
    ${row("推荐动作", recommended.action)}
    ${row("期望奖励", recommended.expected_reward)}
    ${row("安全转移率", pct(m.safe_before_danger_rate))}
    ${row("脆弱风险", pct(m.vulnerable_harm_risk))}
    ${row("排队分钟", num(m.resource_queue_minutes_mean))}
    ${Object.keys(recommended.constraints || {}).length ? `<p class="warning-text">约束惩罚：${escapeHtml(JSON.stringify(recommended.constraints))}</p>` : "<p class=\"ok-text\">推荐动作满足当前硬约束。</p>"}
  </div>`;
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
