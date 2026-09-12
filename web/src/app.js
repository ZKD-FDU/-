import { createSandbox } from "./sandbox.js";
import { createWorkbench } from "./workbench.js";
const urlParams = new URLSearchParams(window.location.search);
const API_BASE = urlParams.get("api") || window.HONGCE_API_BASE || "http://127.0.0.1:8000";
const SPATIAL_PACKAGE_PATH = "data/spatial/qingyuan";

const policies = [
  ["S0", "基线单向通知", "短信/广播为主"],
  ["S1", "设施优先加固", "桥路与避难点"],
  ["S2", "数字预警前移", "更早触达"],
  ["S3", "网格叫应确认", "逐户闭环"],
  ["S4", "社区互助优先", "包保/邻里/备用通信"],
  ["S5", "韧性综合方案", "前移+叫应+调拨"]
];

const tabs = ["县域态势总览", "情景编辑器", "参数校准", "实时推演", "叫应确认台", "政策对比", "策略参数搜索", "个体与事件解释", "复盘与建议"];
const mapModes = [
  ["hydrology", "水文预报"],
  ["warning", "预警设置"],
  ["simulation", "模拟预演"],
  ["plan", "预案生成"]
];

const fallbackSpatialMap = {
  package_id: "frontend-fallback-qingyuan",
  label: "SYNTHETIC_SPATIAL",
  method: {
    route_engine: "frontend_fallback",
    risk_overlay: "embedded coordinates",
    hydrology: "main river and tributary exported as upstream-to-downstream polylines"
  },
  places: [
    { id: "north_valley", name: "北谷村", type: "village", population: 220, vulnerable_population: 90, risk_score: 0.18, elevation_m: 52, river_distance_m: 1200, evacuation_role: "watch_pretransfer", x: 121.318, y: 31.318 },
    { id: "qingyuan_town", name: "清源镇", type: "town", population: 530, vulnerable_population: 110, risk_score: 0.22, elevation_m: 36, river_distance_m: 760, evacuation_role: "command_support_partial", x: 121.388, y: 31.276 },
    { id: "south_valley", name: "南谷村", type: "village", population: 180, vulnerable_population: 70, risk_score: 0.72, elevation_m: 23, river_distance_m: 180, evacuation_role: "priority_transfer", x: 121.392, y: 31.206 },
    { id: "nursing_home", name: "青松养老照料中心", type: "care", population: 69, vulnerable_population: 55, risk_score: 0.88, elevation_m: 18, river_distance_m: 90, evacuation_role: "mandatory_priority_transfer", x: 121.352, y: 31.248 }
  ],
  shelters: [
    { id: "school_shelter", name: "第二中学避难点（北岸高地）", capacity: 620, care_capacity: 80, x: 121.458, y: 31.284 },
    { id: "gym_shelter", name: "县体育馆安置点（南部高地）", capacity: 180, care_capacity: 28, x: 121.432, y: 31.226 }
  ],
  rivers: [
    { id: "main_river", name: "清源河主槽", kind: "main_channel", flow_direction: "W-E", risk_score: 0.82, coordinates: [[121.3, 31.255], [121.335, 31.256], [121.37, 31.255], [121.405, 31.253], [121.44, 31.251], [121.474, 31.248]] },
    { id: "south_tributary", name: "南支沟", kind: "tributary_culvert", flow_direction: "S-N", risk_score: 0.68, coordinates: [[121.386, 31.199], [121.397, 31.207], [121.409, 31.218], [121.421, 31.229], [121.432, 31.226], [121.405, 31.253]] }
  ],
  bridges: [
    { id: "bridge_east", name: "东桥", risk_score: 0.8, bridge_type: "main_river_bridge", x: 121.382, y: 31.255 },
    { id: "bridge_south", name: "南涵洞", risk_score: 0.68, bridge_type: "tributary_culvert", x: 121.409, y: 31.218 }
  ],
  risk_zones: [
    { id: "floodplain_01", name: "主河道漫溢区", risk_score: 0.82, geometry: { type: "Polygon", coordinates: [[[121.3, 31.271], [121.335, 31.269], [121.372, 31.267], [121.409, 31.265], [121.444, 31.263], [121.474, 31.259], [121.474, 31.236], [121.438, 31.238], [121.402, 31.24], [121.366, 31.242], [121.331, 31.244], [121.3, 31.248], [121.3, 31.271]]] } },
    { id: "tributary_ponding_01", name: "南支沟倒灌积水区", risk_score: 0.68, geometry: { type: "Polygon", coordinates: [[[121.382, 31.199], [121.398, 31.205], [121.414, 31.216], [121.432, 31.226], [121.437, 31.236], [121.421, 31.232], [121.405, 31.22], [121.389, 31.211], [121.382, 31.199]]] } }
  ],
  routes: [
    { id: "route-north_valley-school_shelter", origin_id: "north_valley", shelter_id: "school_shelter", travel_minutes: 33.3, risk_score: 0, bridge_exposure_score: 0, bridge_dependency: [], crosses_high_risk: false, coordinates: [[121.318, 31.318], [121.36, 31.312], [121.406, 31.298], [121.458, 31.284]] },
    { id: "route-qingyuan_town-school_shelter", origin_id: "qingyuan_town", shelter_id: "school_shelter", travel_minutes: 16.2, risk_score: 0, bridge_exposure_score: 0, bridge_dependency: [], crosses_high_risk: false, coordinates: [[121.388, 31.276], [121.421, 31.282], [121.458, 31.284]] },
    { id: "route-south_valley-gym_shelter", origin_id: "south_valley", shelter_id: "gym_shelter", travel_minutes: 10.7, risk_score: 0.68, bridge_exposure_score: 0.68, bridge_dependency: ["bridge_south"], crosses_high_risk: true, coordinates: [[121.392, 31.206], [121.409, 31.218], [121.421, 31.223], [121.432, 31.226]] },
    { id: "route-nursing_home-school_shelter", origin_id: "nursing_home", shelter_id: "school_shelter", travel_minutes: 26.2, risk_score: 0.82, bridge_exposure_score: 0.8, bridge_dependency: ["bridge_east"], crosses_high_risk: true, coordinates: [[121.352, 31.248], [121.382, 31.255], [121.421, 31.274], [121.458, 31.284]] }
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
  mapMode: "simulation",
  navCollapsed: readStoredFlag("hongce.navCollapsed", false),
  layers: { terrain: true, water: true, flood: true, routes: true, shelter: true },
  hudCollapsed: { left: false, right: false },
  hudHidden: false,
  savedRuns: {},
  experimentRuns: 3,
  experimentKind: "baseline",
  busy: false
};

const layerItems = [
  ["terrain", "三维地形"],
  ["water", "河道水位"],
  ["flood", "风险淹没"],
  ["routes", "转移路线"],
  ["shelter", "避难承载"]
];

const $ = (selector) => document.querySelector(selector);
const content = $("#content");

function readStoredFlag(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : raw === "1";
  } catch {
    return fallback;
  }
}

function writeStoredFlag(key, value) {
  try {
    window.localStorage.setItem(key, value ? "1" : "0");
  } catch {
    /* localStorage 不可用时忽略，只影响记忆功能 */
  }
}

function pct(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  return `${Math.round(Number(value || 0) * 1000) / 10}%`;
}

function num(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
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
  const data = await response.json();
  if (data.error || data.status === "failed") throw new Error(data.error || "请求失败");
  return data;
}

async function init() {
  $("#tabs").innerHTML = tabs.map((tab) => `<button data-tab="${tab}" data-short="${escapeHtml(tab.slice(0, 1))}" title="${escapeHtml(tab)}" class="${tab === state.active ? "active" : ""}">${tab}</button>`).join("");
  $("#policy").innerHTML = policies.map(([id, name]) => `<option value="${id}" ${id === "S5" ? "selected" : ""}>${id} · ${name}</option>`).join("");
  $("#tabs").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.active = button.dataset.tab;
    render();
  });
  $("#run").addEventListener("click", () => runSimulation($("#policy").value));
  applyNavCollapsed();
  $("#nav-toggle").addEventListener("click", () => {
    state.navCollapsed = !state.navCollapsed;
    writeStoredFlag("hongce.navCollapsed", state.navCollapsed);
    applyNavCollapsed();
    // 侧栏宽度变化后画布尺寸失效，等过渡结束再按新宽度重建地图。
    window.setTimeout(render, 240);
  });
  try {
    const health = await request("/health");
    $("#health").textContent = `API ${health.status} · ${health.training_case_count || 0} cases`;
    try {
      await loadSpatialPackage();
    } catch (error) {
      state.spatialContext = null;
      state.spatialPackage = fallbackSpatialMap;
      setNotice("空间包暂用内置 QGIS 演示图层；启动新版 API 后会自动读取 data/spatial/qingyuan。");
    }
    await loadCases();
    await loadParameters();
    if (urlParams.has('review')) {
      const bundle = await request('/validation/latest');
      state.validationBundle = bundle;
      state.validationStored = true;
      state.experiment = bundle.baseline;
      state.active = '政策对比';
      setNotice(`本轮成果 · ${bundle.run_count} 次可复现实验 · 每方案 ${bundle.seeds.length} 个种子`);
    }
  } catch {
    $("#health").textContent = "API offline";
  }
  render();
  if(urlParams.has('sandbox')) await runSimulation($('#policy').value);
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
  sandbox.stop();
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
    state.savedRuns[policy] = state.run;
    state.sandDirty = false;
    state.sandMinute = state.run.scenario_config.evacuation_order_minute + 30;
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
        experiment: state.experimentKind === "abc" ? "abc" : state.experimentKind === "sensitivity" ? "transport_sensitivity" : "s0_s3_s5",
        seeds: Array.from({length: state.experimentRuns || 3}, (_, i) => Number($("#seed").value) + i),
        scenario_overrides: buildScenarioOverrides(),
        spatial_package_path: state.spatialContext ? SPATIAL_PACKAGE_PATH : undefined,
        case_id: state.selectedCase?.case_id,
        population,
        output_dir: "outputs/api_experiments"
      })
    });
    state.experiment = response.comparison;
    state.validationStored = false;
    state.experimentInput = JSON.stringify(buildScenarioOverrides());
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
  setBusy(true, "正在比较候选动作 策略推荐...");
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
  document.querySelectorAll("#sand-run, #sand-preset, #sand-dispatch, #sand-depot, [data-sand-config], #seed, #population, #policy, #run-experiment, #run-optimization, #run-bandit, #experiment-kind, #experiment-runs, [data-run-policy]").forEach(el => el.disabled = value);
  document.getElementById("notice").classList.toggle("is-busy", value);
  if (text) setNotice(text);
}

function setNotice(text) {
  $("#notice").textContent = text;
}

function applyNavCollapsed() {
  const shell = document.querySelector(".shell");
  const toggle = $("#nav-toggle");
  if (shell) shell.classList.toggle("nav-collapsed", state.navCollapsed);
  if (toggle) {
    toggle.setAttribute("aria-expanded", String(!state.navCollapsed));
    const label = state.navCollapsed ? "展开侧边栏" : "折叠侧边栏";
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
  }
}

function render() {
  $("#page-title").textContent = state.active;
  const runControls = $("#run-controls");
  if (runControls) runControls.hidden = false;
  document.querySelectorAll("#tabs button").forEach((button) => button.classList.toggle("active", button.dataset.tab === state.active));
  const route = {
    "县域态势总览": sandbox.view,
    "情景编辑器": editor,
    "参数校准": calibrationWorkbench,
    "实时推演": sandbox.view,
    "叫应确认台": callDesk,
    "政策对比": comparison,
    "策略参数搜索": decisionLab,
    "个体与事件解释": explanation,
    "复盘与建议": review
  };
  content.innerHTML = route[state.active]();
  workbench.bind();
  sandbox.bind();
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
      state.sandDirty = !!state.run;
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
    transport_mode: "network",
    dispatch_model: "positioned_fleet",
    dispatch_mode: state.scenarioConfig.dispatch_mode || 'policy_priority',
    fleet_base_id: state.scenarioConfig.fleet_base_id || 'school_shelter',
    road_capacity: Number(state.scenarioConfig.road_capacity ?? 8),
    loading_minutes: Number(state.scenarioConfig.loading_minutes ?? 5),
    flood_peak_m: Number(state.scenarioConfig.flood_peak_m ?? .45),
    queue_aging_minutes: Number(state.scenarioConfig.queue_aging_minutes ?? 45),
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
      <label>证据来源<input value="应急管理部报告" readonly /></label>
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
      <label>转运车辆<input data-config-key="vehicles" value="${escapeHtml(cfg.vehicles)}" min="0" max="300" step="1" type="number" /></label>
      <label>照护人员<input data-config-key="care_workers" value="${escapeHtml(cfg.care_workers)}" min="0" max="300" step="1" type="number" /></label>
      <label>担架数量<input data-config-key="stretchers" value="${escapeHtml(cfg.stretchers)}" min="0" max="300" step="1" type="number" /></label>
      <label>避难床位<input data-config-key="shelter_beds" value="${escapeHtml(cfg.shelter_beds)}" min="0" max="5000" step="10" type="number" /></label>
    </div></section>`;
}

function editorCases() {
  const selected = state.selectedCase;
  const scenario = state.caseScenario;
  const cases = state.cases.length ? state.cases : [];
  return `<section><h2>灾害治理证据库</h2>
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

function timeline() { return workbench.timeline(); }

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

function callDesk() { return workbench.callDesk(); }

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

function comparison() { return workbench.comparison(); }

function decisionLab() {
  const mdp = state.mdp;
  const best = state.optimization?.best;
  const recommended = state.bandit?.recommended;
  return `<div class="view">
    <div class="toolbar">
      <button id="load-mdp">查看 MDP/POMDP 定义</button>
      <button class="primary" id="run-optimization">运行参数优化</button>
      <button id="run-bandit">比较候选动作</button>
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
        <h2>候选动作比较</h2>
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
    ${row("暴露风险指数", num(m.vulnerable_harm_risk))}
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
    ${row("暴露风险指数", num(m.vulnerable_harm_risk))}
    ${row("排队分钟", num(m.resource_queue_minutes_mean))}
    ${Object.keys(recommended.constraints || {}).length ? `<p class="warning-text">约束惩罚：${escapeHtml(JSON.stringify(recommended.constraints))}</p>` : "<p class=\"ok-text\">推荐动作满足当前硬约束。</p>"}
  </div>`;
}

function explanation() { return workbench.explanation(); }

function review() { return workbench.review(); }

const sandbox = createSandbox({state,render,request,setNotice,runSimulation,escapeHtml});
const workbench = createWorkbench({state, request, render, setNotice, escapeHtml, pct, num});

init();
