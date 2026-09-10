// Evidence-focused views share the same scenario and run objects as the map.
export function createWorkbench(ctx) {
  const { state, request, render, setNotice, escapeHtml: esc, pct, num } = ctx;
  const names = { unregistered:'未登记',uncontacted:'未联系',contact_failed:'联系失败',contacted:'已联系',
    misunderstood:'待解释',distrusted:'待建立信任',refused:'暂缓转移',confirmed:'同意转移',authorization_wait:'待授权 / 准备',
    waiting_transfer:'待转运',resource_blocked:'等待资源',route_blocked:'路线受阻',in_transit:'转运中',
    sheltered:'已安置',unsuitable_shelter:'床位不足' };
  const places = {nursing_home:'青松养老院',county_hospital:'县人民医院',county_school:'第二中学',north_valley:'北谷村',south_valley:'南谷村',qingyuan_town:'清源镇'};
  const option = (value,label,current) => `<option value="${esc(value)}" ${String(value)===String(current)?'selected':''}>${esc(label)}</option>`;
  const empty = (title,body) => `<section class="lab-empty"><span class="lab-kicker">洪策 · 政策实验室</span><h2>${title}</h2><p>${body}</p><button class="primary" data-go="县域态势总览">进入态势总览</button></section>`;
  const minutes = value => value == null ? '—' : `${value} 分钟`;
  const gap = value => value == null ? '—' : `${value>0?'+':''}${(value*100).toFixed(1)} pp`;
  const stamp = () => `<div class="lab-stamp"><span class="lab-dot"></span>合成人口 · 条件性仿真<span>${esc(state.run?.run?.code_version || 'v2')}</span></div>`;
  function selectedExperiment() {
    if (!state.experiment?.experiments) return state.experiment;
    return state.experiment.experiments[state.experimentTab || 'A_money_allocation'];
  }
  function comparison() {
    const exp = selectedExperiment();
    const rows = Object.entries(exp?.summary || {});
    const variants = Object.fromEntries((exp?.variants || []).map(v=>[v.id,v]));
    const number = state.experimentRuns || 3;
    return `<div class="view lab-view"><section class="lab-heading"><div><span class="lab-kicker">POLICY LAB</span><h2>同一情景，看清每项措施的作用</h2><p>使用当前情景配置，比较按时转移、群体差距和资源投入。</p></div>${stamp()}</section>
      <section class="lab-controls"><label>实验设计<select id="experiment-kind">${option('baseline','S0 / S3 / S5 政策对照',state.experimentKind || 'baseline')}${option('abc','A / B / C 机制实验',state.experimentKind || 'baseline')}${option('sensitivity','运输假设敏感性',state.experimentKind || 'baseline')}</select></label>
      <label>每方案重复次数<select id="experiment-runs">${option(3,'3 次 · 快速演示',number)}${option(50,'50 次 · 验证实验',number)}</select></label>
      <button class="primary" id="run-experiment" ${state.busy?'disabled':''}>${state.busy?'实验运行中…':'运行当前情景实验'}</button><button id="load-validation">查看本轮验证成果</button><button id="export-evidence" ${!exp?'disabled':''}>导出实验数据</button></section>
      ${state.validationStored?'<p class="lab-footnote">当前展示已完成的本轮验证成果；下方记录的是该实验的实际配置。点击“运行当前情景实验”可使用编辑器中的新配置重新计算。</p>':''}
      ${exp ? `<div class="lab-meta"><span>样本 / 方案 <strong>${exp.seeds?.length || 0}</strong></span><span>人口 <strong>${exp.population}</strong></span><span>预警 <strong>${minutes(exp.scenario_config?.warning_minute)}</strong></span><span>车辆 <strong>${exp.scenario_config?.vehicles}</strong></span><span>内核 <strong>${esc(exp.code_version)}</strong></span><span>场景版本 <code>${esc(exp.scenario_config_hash)}</code></span></div>`:''}
      ${state.experiment?.experiments?`<div class="lab-tabs">${[['A_money_allocation','A · 同预算'],['B_trigger_timing','B · 预警与授权'],['C_chain_breaks','C · 单机制消融']].map(([key,label])=>`<button data-experiment-tab="${key}" class="${(state.experimentTab||'A_money_allocation')===key?'active':''}">${label}</button>`).join('')}</div>`:''}
      ${rows.some(([,m])=>m.general_safe_before_danger_rate?.mean===0)?'<p class="lab-guardrail">部分方案中普通应转人群按时转移率为 0。总体提升不能掩盖资源分配问题，请勿据此直接形成无条件政策推荐。</p>':''}
      ${rows.length?`<section class="lab-chart"><div class="lab-section-title"><h3>${esc(exp.title || '政策对照结果')}</h3><span>${(exp.seeds?.length||0)>=50?'验证实验':'快速演示 · 尚不足 50 个种子'}</span></div>
      ${rows.map(([id,m])=>`<div class="lab-bar-row"><div><strong>${esc(variants[id]?.name || id)}</strong><small>${esc(id)}</small></div><div class="lab-bar-track"><i style="width:${Math.max(0,Math.min(100,m.safe_before_danger_rate.mean*100))}%"></i></div><b>${pct(m.safe_before_danger_rate.mean)}</b></div>`).join('')}
      <p class="lab-footnote">条形表示应转人群按时安全转移率。以下 CI95 是均值置信区间；P05–P95 表示模拟结果分布。</p></section>
      <section class="lab-table-wrap"><table class="lab-table"><thead><tr><th>方案</th><th>脆弱群体按时转移</th><th>普通群体按时转移</th><th>均值 CI95</th><th>安全人数 / 应转人数</th><th>群体差距</th><th>预算单位</th><th>相对基线变化</th></tr></thead><tbody>${rows.map(([id,m])=>{
        const v=m.vulnerable_safe_before_danger_rate;const delta=exp.paired_differences?.[id]?.safe_before_danger_rate;
        return `<tr><td><strong>${esc(variants[id]?.name || id)}</strong><small>${esc((variants[id]?.changed_fields || []).join(' · '))}</small></td><td>${pct(v?.mean)}</td><td>${pct(m.general_safe_before_danger_rate?.mean)}</td><td>${v?.ci95_low==null?'样本不足':`${pct(v.ci95_low)} – ${pct(v.ci95_high)}`}</td><td>${num(m.safe_count?.mean)} / ${num(m.target_count?.mean)}</td><td>${gap(m.group_safety_gap?.mean)}</td><td>${num(m.policy_cost?.mean)}</td><td class="${(delta?.mean||0)<0?'lab-negative':'lab-positive'}">${gap(delta?.mean)}</td></tr>`;
      }).join('')}</tbody></table></section><p class="lab-footnote">预算为可审计的合成单位，不代表实际采购价格。总体改善不等于每个群体都受益；负向变化完整保留。</p>`:empty('准备一次可复现的政策对照','先调整情景，再运行实验。结果会保留场景、种子、政策措施和分组分母。')}
      </div>`;
  }
  function callDesk() {
    if (!state.run) return empty('让每个重点对象都可追踪','运行仿真后，可按对象编号、地点和状态查找完整名册。');
    const all = state.run.agents.filter(a=>a.requires_transfer);
    const q=(state.personQuery||'').toLowerCase();
    const filtered=all.filter(a=>(!state.personStatus || a.status===state.personStatus) && `${a.id} ${a.location_id} ${places[a.location_id]||a.location_id}`.toLowerCase().includes(q));
    const pages=Math.max(1,Math.ceil(filtered.length/20));const page=Math.min(state.personPage||1,pages);
    const rows=filtered.slice((page-1)*20,page*20);
    return `<div class="view lab-view"><section class="lab-heading"><div><span class="lab-kicker">RESPONSE LOOP</span><h2>重点对象确认与转移台账</h2><p>从名册到安置，查看每个人的阻塞原因和责任主体。</p></div>${stamp()}</section>
      <div class="lab-stats"><div><small>应转对象</small><strong>${all.length}</strong></div><div><small>人工确认</small><strong>${all.filter(a=>a.acknowledged_minute!=null).length}</strong></div><div><small>已安置</small><strong>${all.filter(a=>a.status==='sheltered').length}</strong></div><div><small>尚未安置</small><strong>${all.filter(a=>a.status!=='sheltered').length}</strong></div></div>
      <section class="lab-controls"><label>搜索对象<input id="person-query" placeholder="编号或地点，例如 p00001 / 养老院" value="${esc(state.personQuery||'')}"></label><label>当前状态<select id="person-status">${option('','全部状态',state.personStatus||'')}${Object.entries(names).map(([k,v])=>option(k,v,state.personStatus||'')).join('')}</select></label><button id="filter-people">筛选</button><span>共 ${filtered.length} 人</span></section>
      <section class="lab-table-wrap"><table class="lab-table"><thead><tr><th>对象 / 地点</th><th>状态</th><th>人工确认</th><th>出发 → 安置</th><th>等待</th><th>当前原因</th><th></th></tr></thead><tbody>${rows.map(a=>`<tr><td><strong>${esc(a.id)} · ${a.age} 岁</strong><small>${esc(places[a.location_id]||a.location_id)}</small></td><td><span class="lab-badge ${a.status==='sheltered'?'done':'pending'}">${names[a.status]||esc(a.status)}</span></td><td>${minutes(a.acknowledged_minute)}</td><td>${minutes(a.transit_minute)} → ${minutes(a.sheltered_minute)}</td><td>${minutes(a.resource_wait_minutes)}</td><td>${esc(a.reason)}</td><td><button data-person="${esc(a.id)}">查看轨迹 →</button></td></tr>`).join('')||'<tr><td colspan="7">没有匹配的对象，请调整筛选条件。</td></tr>'}</tbody></table></section>
      <div class="lab-pagination"><button data-person-page="${page-1}" ${page<=1?'disabled':''}>上一页</button><span>${page} / ${pages}</span><button data-person-page="${page+1}" ${page>=pages?'disabled':''}>下一页</button></div></div>`;
  }
  function timeline() {
    if (!state.run) return empty('回放真实的仿真事件','每个事件均来自内核运行；车辆到达前不会计入安置人数。');
    const max=Math.max(240,...state.run.events.map(e=>e.minute));const t=state.replayMinute ?? 90;
    const events=state.run.events.filter(e=>e.minute<=t).slice(-30).reverse();
    const departed=state.run.agents.filter(a=>a.transit_minute!=null&&a.transit_minute<=t);
    const arrived=departed.filter(a=>a.sheltered_minute!=null&&a.sheltered_minute<=t);
    return `<div class="view lab-view"><section class="lab-heading"><div><span class="lab-kicker">EVENT REPLAY</span><h2>第 ${t} 分钟 · 转移过程回放</h2><p>滑动时间轴，查看已发生的确认、组织和运输事件。</p></div>${stamp()}</section><section class="lab-replay"><input aria-label="回放分钟" id="replay-minute" type="range" min="0" max="${max}" step="1" value="${t}"><div><span>0 分钟</span><strong>${t} 分钟</strong><span>${max} 分钟</span></div></section>
      <div class="lab-stats"><div><small>已出发</small><strong>${departed.length}</strong></div><div><small>转运途中</small><strong>${departed.length-arrived.length}</strong></div><div><small>已实际到达</small><strong>${arrived.length}</strong></div></div>
      <section class="lab-events">${events.map(eventCard).join('')||'<p>当前时刻尚无事件。</p>'}</section></div>`;
  }
  function eventCard(e) {
    const titles={'warning received':'收到预警','vehicle departed':'车辆出发','person sheltered':'到达安置点','vehicle returned':'车辆返程完成',
      'evacuation task created':'生成转移任务','evacuation order issued':'下达转移命令','official warning issued':'发布预警',
      'bridge_east closed':'桥梁封闭','communications degraded':'通信失效','prepare_transfer':'机构准备转移',
      'wait_authorization':'机构等待授权','request_dispatch':'机构请求派车','confirmation workers assigned':'分配人工确认任务',
      'unregistered person discovered':'发现名册漏登对象','message delivery failed':'关系消息送达失败'};
    const p=e.payload||{};
    return `<article class="lab-event"><time>${e.minute}<small>分钟</small></time><div><strong>${esc(titles[e.message]||e.message)}</strong><p>${esc(p.person||p.actor||p.source||'')}${p.reason?' · '+esc(p.reason):''}${p.people?' · '+esc(p.people.join('、')):''}</p></div><span>${esc(p.channel||p.layer||e.kind)}</span></article>`;
  }
  function explanation() {
    const a=state.trace?.agent;
    if (!state.run) return empty('追溯每个人的行动依据','先运行仿真，或从确认台点击一个对象。');
    const timelineFields=[['contact_minute','收到信息'],['acknowledged_minute','人工确认'],['confirmed_minute','同意转移'],['transit_minute','车辆出发'],['sheltered_minute','实际安置']];
    const saved=Object.values(state.savedRuns||{}).filter(r=>r.scenario_hash===state.run.scenario_hash);
    return `<div class="view lab-view"><section class="lab-heading"><div><span class="lab-kicker">INDIVIDUAL TRACE</span><h2>${esc(a?.id||'选择对象')} · ${esc(places[a?.location_id]||'个体决策与行动')}</h2><p>可见信息、行为因素与运输事件使用同一份运行记录。</p></div>${stamp()}</section>
      <section class="lab-controls"><label>对象编号<input id="trace-person-id" value="${esc(a?.id||'')}" placeholder="输入完整对象编号"></label><button id="load-person-trace">查看对象</button><span>${esc(a?.reason||'')}</span></section>
      ${a?`<section class="lab-person-stages">${timelineFields.map(([key,label])=>`<div class="${a[key]!=null?'complete':''}"><small>${label}</small><strong>${minutes(a[key])}</strong></div>`).join('')}</section>
      <div class="lab-meta"><span>责任主体 <code>${esc(a.responsible_actor_id)}</code></span><span>路线 <code>${esc(a.route_id||'待分配')}</code></span><span>暴露风险指数 <strong>${num(a.harm_risk)}</strong></span></div>
      ${saved.length>1?`<section class="lab-table-wrap"><h3>同一对象 · 已运行政策对照</h3><table class="lab-table"><thead><tr><th>政策</th><th>同意转移</th><th>车辆出发</th><th>实际安置</th></tr></thead><tbody>${saved.map(r=>{const p=r.agents.find(p=>p.id===a.id);return `<tr><td>${r.run.policy_id}</td><td>${minutes(p?.confirmed_minute)}</td><td>${minutes(p?.transit_minute)}</td><td>${minutes(p?.sheltered_minute)}</td></tr>`;}).join('')}</tbody></table></section>`:''}
      <section class="lab-decisions">${(state.trace?.traces||[]).map(t=>`<article><div><span>${t.minute} 分钟</span><strong>${esc(t.reason||t.action)}</strong></div><p>${Object.entries(t.factors||{}).map(([k,v])=>`${esc(k)} ${num(v)}`).join(' · ')}</p></article>`).join('')||'<p>该对象尚未形成行为决策；请查看信息触达事件。</p>'}</section><section class="lab-events">${(state.trace?.events||[]).map(eventCard).join('')}</section>`:'<p>未找到对象，请核对编号。</p>'}</div>`;
  }
  function review() {
    if (!state.run) return empty('把实验转化为可核对的政策备忘','运行仿真后导出版本、输入、指标与残余风险。');
    const m=state.run.metrics;
    return `<div class="view lab-view"><section class="lab-heading"><div><span class="lab-kicker">DECISION MEMO</span><h2>本轮推演的结果与残余风险</h2><p>建议需结合资源预算与适用条件，由人复核。</p></div><button class="primary" id="export-memo">导出政策备忘</button></section>
      <div class="lab-stats"><div><small>按时转移率</small><strong>${pct(m.safe_before_danger_rate)}</strong></div><div><small>脆弱群体按时转移率</small><strong>${pct(m.vulnerable_safe_before_danger_rate)}</strong></div><div><small>平均资源等待</small><strong>${num(m.resource_queue_minutes_mean)} <small>分钟</small></strong></div></div>
      <section><h3>重点复核事项</h3><p>本轮 ${m.target_count} 名应转对象中，${m.safe_count} 人在危险到达前安置。尚有 ${m.target_count-m.safe_count} 人未按时完成。</p><p>优先在确认台检查等待授权、未触达、资源等待和路线受阻对象；结合对照实验判断应改进的机制。</p><p>暴露风险为合成指数。信任变化尚未校准，暂不报告。案例参数仍需人工核验，结果仅为当前模型假设下的后果。</p></section>${stamp()}</div>`;
  }
  function download(filename,data,type='application/json') {
    const a=document.createElement('a');const url=URL.createObjectURL(new Blob([type==='application/json'?JSON.stringify(data,null,2):data],{type}));
    a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function loadPerson(id) {
    try { state.trace=await request(`/simulations/${state.run.run.id}/agents/${encodeURIComponent(id)}/trace`);state.active='个体与事件解释';render(); }
    catch(e){setNotice(e.message);}
  }
  function bind() {
    document.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>{state.active=b.dataset.go;render();});
    document.querySelectorAll('[data-person]').forEach(b=>b.onclick=()=>loadPerson(b.dataset.person));
    document.querySelectorAll('[data-person-page]').forEach(b=>b.onclick=()=>{state.personPage=Number(b.dataset.personPage);render();});
    document.querySelectorAll('[data-experiment-tab]').forEach(b=>b.onclick=()=>{state.experimentTab=b.dataset.experimentTab;render();});
    const el=id=>document.getElementById(id);
    if(el('experiment-kind')) el('experiment-kind').onchange=e=>{state.experimentKind=e.target.value;if(state.validationStored&&state.validationBundle){state.experiment=state.experimentKind==='abc'?state.validationBundle.mechanisms:state.experimentKind==='sensitivity'?state.validationBundle.sensitivity:state.validationBundle.baseline;render();}};
    if(el('experiment-runs')) el('experiment-runs').onchange=e=>state.experimentRuns=Number(e.target.value);
    if(el('load-validation')) el('load-validation').onclick=async()=>{try {const bundle=await request('/validation/latest');state.validationBundle=bundle;state.validationStored=true;state.experiment=state.experimentKind==='abc'?bundle.mechanisms:state.experimentKind==='sensitivity'?bundle.sensitivity:bundle.baseline;render();setNotice(`已加载本轮验证成果 · 每方案 ${bundle.seeds.length} 个种子 · 总计 ${bundle.run_count} 次运行`);}catch(e){setNotice(e.message);}};
    const filter=()=>{state.personQuery=el('person-query').value;state.personStatus=el('person-status').value;state.personPage=1;render();};
    if(el('filter-people')) el('filter-people').onclick=filter;
    if(el('person-query')) el('person-query').onkeydown=e=>{if(e.key==='Enter')filter();};
    if(el('person-status')) el('person-status').onchange=filter;
    if(el('replay-minute')) el('replay-minute').onchange=e=>{state.replayMinute=Number(e.target.value);render();};
    if(el('load-person-trace')) el('load-person-trace').onclick=()=>loadPerson(el('trace-person-id').value.trim());
    if(el('export-evidence')) el('export-evidence').onclick=()=>download('hongce-experiments.json',state.experiment);
    if(el('export-memo')) el('export-memo').onclick=()=>download('洪策政策备忘.md',`# 洪策政策备忘\n\n运行 ${state.run.run.id}\n\n场景 ${state.run.scenario_hash}\n\n政策 ${state.run.run.policy_id}\n\n${state.run.metrics.safe_count} / ${state.run.metrics.target_count} 名应转对象按时安全安置。\n\n## 指标与配置\n\n\`\`\`json\n${JSON.stringify({metrics:state.run.metrics,scenario:state.run.scenario_config,policy:state.run.policy_config,resources:state.run.resource_audit},null,2)}\n\`\`\`\n\n## 适用条件\n\n合成人口与合成灾害假设下的政策压力测试。暴露风险为指数，非伤亡概率。参数待人工校准。逐项复核未按时转移者的授权、联系、路线与资源阻塞；本备忘不自动形成现实指挥指令。\n`,'text/markdown;charset=utf-8');
  }
  return {comparison,callDesk,timeline,explanation,review,bind};
}
