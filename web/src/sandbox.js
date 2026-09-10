// Spatial replay consumes kernel trips; no decorative traffic or inferred counts.
export function createSandbox({state,render,request,setNotice,runSimulation,escapeHtml:esc}) {
  let timer=null;
  const names={north_valley:'北谷村',south_valley:'南谷村',qingyuan_town:'清源镇',nursing_home:'青松养老院',county_hospital:'县人民医院',county_school:'第二中学',school_shelter:'北岸中学安置点',gym_shelter:'南部体育馆'};
  const supplemental=[{id:'county_hospital',x:121.407,y:31.302,name:'县人民医院'},{id:'county_school',x:121.444,y:31.308,name:'第二中学'}];
  const pct=v=>v==null?'—':`${(100*v).toFixed(1)}%`;
  function model() {
    const run=state.run;
    const config=run?.scenario_config||state.scenarioConfig;
    const spatial=state.spatialPackage;
    const places=[...spatial.places,...supplemental.filter(p=>!spatial.places.some(q=>q.id===p.id))];
    const shelters=(run?.transport?.shelters?.length?run.transport.shelters:spatial.shelters).map(s=>({...spatial.shelters.find(x=>x.id===s.id),...s}));
    const points=Object.fromEntries([...places,...shelters].map(p=>[p.id,p]));
    const routes=(run?.transport?.routes?.length?run.transport.routes:spatial.routes).map((r,i)=>{
      const origin=points[r.origin_id],dest=points[r.shelter_id];
      const coordinates=r.coordinates?.length?r.coordinates:(origin&&dest?[[origin.x,origin.y],[origin.x+(dest.x-origin.x)*.25,origin.y+.012],[dest.x-.01,dest.y+.008],[dest.x,dest.y]]:[]);
      return {...r,id:r.id||`route-${i}`,coordinates};
    });
    return {run,config,spatial,places,shelters,points,routes,minute:state.sandMinute??0,trips:run?.transport?.trips||[]};
  }
  const xy=([x,y])=>[60+(x-121.30)/.18*880,65+(31.33-y)/.14*485];
  const path=coords=>coords.map((p,i)=>`${i?'L':'M'}${xy(p).join(',')}`).join(' ');
  function depth(r,t) {
    const p=r.depth_profile||[];if(!p.length)return 0;
    if(t<=p[0][0])return p[0][1];
    for(let i=1;i<p.length;i++)if(t<=p[i][0])return p[i-1][1]+(p[i][1]-p[i-1][1])*(t-p[i-1][0])/(p[i][0]-p[i-1][0]);
    return p.at(-1)[1];
  }
  function status(r,m) {
    const close=m.config.bridge_closure_minute+(m.run?.policy_config?.bridge_extension_minutes||0);
    if((r.closed_minute!=null&&m.minute>=r.closed_minute)||(r.bridge_dependency?.length&&m.minute>=close))return '封闭';
    if(depth(r,m.minute)>=(r.max_depth_m??.30))return '积水超限';
    const busy=m.trips.filter(t=>(t.route_id===r.id||t.return_route_id===r.id)&&t.boarding_minute<=m.minute&&(t.release_minute==null||t.release_minute>m.minute)).length;
    if(busy>=(r.max_concurrent_vehicles??8))return '容量已满';
    return depth(r,m.minute)>.05?'积水减速':'可通行';
  }
  function position(coords,f) {
    const pts=coords.map(xy), lengths=pts.slice(1).map((p,i)=>Math.hypot(p[0]-pts[i][0],p[1]-pts[i][1]));
    let remaining=Math.max(0,Math.min(1,f))*lengths.reduce((a,b)=>a+b,0);
    for(let i=0;i<lengths.length;i++){
      if(remaining<=lengths[i]){const q=remaining/(lengths[i]||1);return [pts[i][0]+(pts[i+1][0]-pts[i][0])*q,pts[i][1]+(pts[i+1][1]-pts[i][1])*q];}remaining-=lengths[i];
    }
    return pts.at(-1)||[0,0];
  }
  function map(m) {
    const hidden=state.sandLayers||{};
    const selected=state.sandSelected;
    const contours=Array.from({length:18},(_,i)=>`<path d="M ${-60+i*12} ${40+i*13} C ${155+i*10} ${-130+i*15},${340+i*15} ${-60+i*13},${520+i*14} ${30+i*15} S ${850+i*9} ${145+i*8},1120 ${-80+i*20}"/>`).join('');
    const terrain=`<g class="sand-contours"><path class="hill" d="M0 0H1000V100Q750 235 560 180T0 205Z"/><path class="hill" d="M0 570Q200 350 365 435T690 590Z"/>${contours}</g>`;
    const roads=m.routes.filter(r=>r.coordinates.length).map(r=>{const s=status(r,m),bad=['封闭','积水超限'].includes(s);return `<g class="sand-road ${bad?'closed':s==='容量已满'?'busy':''} ${selected?.id===r.id?'selected':''}" data-map-route="${esc(r.id)}" role="button" tabindex="0" aria-label="${esc(names[r.origin_id]||r.origin_id)}至${esc(names[r.shelter_id]||r.shelter_id)}，${s}"><path class="road-bed" d="${path(r.coordinates)}"/><path class="road-line ${r.synthetic_detour?'detour':''}" d="${path(r.coordinates)}"/><path class="road-hit" d="${path(r.coordinates)}"/></g>`;}).join('');
    const rivers=m.spatial.rivers.map(r=>`<path class="sand-river-bank" d="${path(r.coordinates)}"/><path class="sand-river" d="${path(r.coordinates)}"/>`).join('');
    const flood=m.routes.filter(r=>r.coordinates.length&&depth(r,m.minute)>0).map(r=>`<path class="sand-depth" d="${path(r.coordinates)}" stroke-width="${12+Math.min(1,depth(r,m.minute))*60}" opacity="${Math.min(.65,.2+depth(r,m.minute))}"/>`).join('');
    const blocks=m.places.map(p=>{const [x,y]=xy([p.x,p.y]);return `<g transform="translate(${x-32},${y-18})">${Array.from({length:8},(_,i)=>{const bx=(i%4)*18,by=Math.floor(i/4)*23;return `<path d="M${bx} ${by}l11 -4v12l-11 4Z" fill="#637a86"/><path d="M${bx} ${by}l-5 -5 11 -4 5 5Z" fill="#96a7ab"/><path d="M${bx} ${by}l-5 -5v12l5 5Z" fill="#344f5e"/>`;}).join('')}</g>`;}).join('');
    const markers=[...m.places,...m.shelters].map(p=>{
      const [x,y]=xy([p.x,p.y]),shelter=m.shelters.some(s=>s.id===p.id);
      const total=m.run?.agents.filter(a=>a.location_id===p.id&&a.requires_transfer).length;
      const remaining=m.run?.agents.filter(a=>a.location_id===p.id&&a.requires_transfer&&(a.transit_minute==null||a.transit_minute>m.minute)).length;
      const label=names[p.id]||p.name;
      return `<g data-map-place="${esc(p.id)}" class="sand-place ${shelter?'shelter':''} ${selected?.id===p.id?'selected':''}" role="button" tabindex="0" aria-label="查看${esc(label)}" transform="translate(${x},${y})"><circle r="${shelter?10:7}"/><text class="marker-symbol" text-anchor="middle" y="4">${shelter?'+':''}</text><rect class="place-label" x="${shelter?-94:-65}" y="${shelter?18:-55}" width="${shelter?188:130}" height="${shelter?29:40}" rx="4"/><text text-anchor="middle" y="${shelter?37:-38}">${esc(label)}</text>${!shelter?`<text class="place-sub" text-anchor="middle" y="-23">${total==null?'合成聚落':`待转 ${remaining} / ${total}`}</text>`:''}</g>`;
    }).join('');
    const cars=m.trips.map((t,i)=>{
      const outbound=t.departure_minute<=m.minute&&m.minute<t.arrival_minute;
      const back=t.release_minute!=null&&t.return_start_minute<=m.minute&&m.minute<t.release_minute;
      if(!outbound&&!back)return '';
      const r=m.routes.find(r=>r.id===(outbound?t.route_id:t.return_route_id));if(!r?.coordinates.length)return '';
      const f=outbound?(m.minute-t.departure_minute)/(t.arrival_minute-t.departure_minute):1-(m.minute-t.return_start_minute)/(t.release_minute-t.return_start_minute);
      const [x,y]=position(r.coordinates,f);
      return `<g class="sand-car ${back?'returning':''}" data-map-trip="${i}" transform="translate(${x},${y})" role="button" tabindex="0" aria-label="车辆 ${t.vehicle+1} ${back?'返程':'载客'}"><rect x="-8" y="-5" width="16" height="10" rx="2"/><path d="M-3 -4V4"/></g>`;
    }).join('');
    return `<svg id="sandbox-map" viewBox="0 0 1000 620" role="img" aria-label="清源县合成路网沙盘，地点和车辆可选择"><defs><pattern id="sandgrid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#314654" stroke-width=".5"/></pattern></defs><rect width="1000" height="620" fill="#142c3a"/><rect width="1000" height="620" fill="url(#sandgrid)"/><g id="sand-world" transform="translate(${state.sandPanX||0},${state.sandPanY||0}) translate(500,310) scale(${state.sandZoom||1}) translate(-500,-310)">${hidden.terrain?'':terrain}<g>${rivers}</g>${hidden.flood?'':flood}${hidden.routes?'':roads}${hidden.terrain?'':blocks}${markers}${hidden.vehicles?'':cars}<text x="440" y="340" class="river-label" transform="rotate(5,440,340)">清 源 河</text></g><g class="sand-north" transform="translate(944 51)"><path d="M0 -15L-6 5 0 1 6 5Z"/><text y="23" text-anchor="middle">N</text></g><text x="22" y="597" class="sand-disclosure">SYNTHETIC · 路线积水过程示意 / 非实测淹没范围</text></svg>`;
  }
  function inspect(m) {
    const selected=state.sandSelected;
    if(selected?.type==='trip'){
      const t=m.trips[Number(selected.id)];if(!t)return '';
      return `<div class="sand-detail"><span class="sand-eyebrow">车辆轨迹</span><h3>转运车 ${t.vehicle+1}</h3><p>${esc(names[t.origin_id])} → ${esc(names[t.shelter_id])}</p><dl><dt>乘员</dt><dd>${t.passengers.length} 人</dd><dt>装载 / 出发</dt><dd>${t.boarding_minute} / ${t.departure_minute} 分</dd><dt>实际到达</dt><dd>${t.arrival_minute} 分</dd><dt>预计返回</dt><dd>${t.release_minute??'本轮无法返程'}</dd></dl><button data-sand-person="${esc(t.passengers[0])}">查看首位乘员的完整轨迹 →</button></div>`;
    }
    if(selected?.type==='route'){
      const r=m.routes.find(r=>r.id===selected.id);if(!r)return '';
      const points=r.depth_profile||[];
      return `<div class="sand-detail"><span class="sand-eyebrow">道路走廊</span><h3>${esc(names[r.origin_id]||r.origin_id)} → ${esc(names[r.shelter_id]||r.shelter_id)}</h3><span class="sand-tag">${status(r,m)}</span><dl><dt>当前积水</dt><dd>${depth(r,m.minute).toFixed(2)} m</dd><dt>通行情景阈值</dt><dd>${r.max_depth_m??.30} m</dd><dt>基础行程</dt><dd>${Number(r.travel_minutes).toFixed(1)} 分</dd><dt>同时占用上限</dt><dd>${r.max_concurrent_vehicles??8} 辆</dd></dl><svg class="sand-hydrograph" viewBox="0 0 250 85" aria-label="预设积水过程线"><path d="M15 5V68H240" stroke="#bdcbd1" fill="none"/><path d="${points.map(([t,d],i)=>`${i?'L':'M'}${15+t/Math.max(240,m.config.danger_arrival_minute+60)*220} ${68-Math.min(d,1)*60}`).join(' ')}" stroke="#338bad" stroke-width="2" fill="none"/><text x="15" y="82">0</text><text x="190" y="82">分钟 →</text></svg><p class="sand-muted">${r.synthetic_detour?'新增合成备用道路；需实地核验。':'过程线来自情景输入，阈值尚未本地校准。'}</p></div>`;
    }
    const id=selected?.id||'nursing_home',p=m.points[id];
    const shelter=m.shelters.find(s=>s.id===id);
    const targets=m.run?.agents.filter(a=>a.requires_transfer&&a.location_id===id)||[];
    const pending=targets.filter(a=>a.transit_minute==null||a.transit_minute>m.minute);
    const arrivals=m.trips.filter(t=>t.shelter_id===id&&t.arrival_minute<=m.minute).reduce((a,t)=>a+t.passengers.length,0);
    const reserved=m.trips.filter(t=>t.shelter_id===id&&t.boarding_minute<=m.minute).reduce((a,t)=>a+t.passengers.length,0);
    return `<div class="sand-detail"><span class="sand-eyebrow">${shelter?'安置设施':'重点区域'}</span><h3>${esc(names[id]||p?.name||id)}</h3><p class="sand-muted">${shelter?'到达、在途预留与剩余容量分别计数':'选择地图上的道路、车辆或地点查看详情'}</p><dl>${shelter?`<dt>实际到达</dt><dd>${arrivals} 人</dd><dt>已预留（含到达）</dt><dd>${reserved} / ${shelter.capacity}</dd><dt>全照护接收上限</dt><dd>${shelter.medical_slots??shelter.care_capacity??'—'}</dd>`:`<dt>应转 / 尚未出发</dt><dd>${m.run?`${targets.length} / ${pending.length}`:'待运行'}</dd><dt>已触达</dt><dd>${targets.filter(a=>a.contact_minute!=null&&a.contact_minute<=m.minute).length} 人</dd><dt>已完成安置</dt><dd>${targets.filter(a=>a.sheltered_minute!=null&&a.sheltered_minute<=m.minute).length} 人</dd>`}</dl>${!shelter?`<button data-sand-roster="${esc(id)}">打开该区域转移台账 →</button>`:''}</div>`;
  }
  function view() {
    const m=model(),run=m.run;
    const agents=run?.agents.filter(a=>a.requires_transfer)||[];
    const reached=agents.filter(a=>a.contact_minute!=null&&a.contact_minute<=m.minute).length;
    const arrived=agents.filter(a=>a.sheltered_minute!=null&&a.sheltered_minute<=m.minute).length;
    const transit=agents.filter(a=>a.transit_minute!=null&&a.transit_minute<=m.minute&&(a.sheltered_minute==null||a.sheltered_minute>m.minute)).length;
    const activeTrips=m.trips.filter(t=>t.boarding_minute<=m.minute&&(t.release_minute==null||t.release_minute>m.minute));
    const max=Math.max(240,Number(m.config.danger_arrival_minute)+60);
    const cfg=state.scenarioConfig;
    return `<div class="sand-view"><div class="sand-heading"><div><span class="sand-eyebrow">HONGCE / SCENARIO WORKSPACE</span><h2>清源县 · 洪涝转移沙盘</h2><p>观察灾害进程，检验组织响应与运输调度。</p></div><span class="sand-tag">${run?`${esc(run.run.policy_id)} · ${esc(run.run.code_version)}`:'合成场景 · 等待推演'}</span></div>
      <div class="sand-flow"><span class="active">01 配置情景</span><i>→</i><span class="${run?'active':''}">02 运行推演</span><i>→</i><span>03 回放与核对</span><button data-sand-review>查看政策实验 →</button></div>
      ${state.sandDirty?'<div class="sand-dirty" role="status">参数已变更。地图仍回放上次结果，请运行仿真应用新配置。</div>':''}
      <div class="sand-stats">${[['应转对象',run?agents.length:'—','人'],['已触达',run?reached:'—','人'],['转运途中',run?transit:'—','人'],['实际安置',run?arrived:'—','人'],['占用车辆',run?`${activeTrips.length} / ${run.resource_audit.vehicles}`:'—','辆']].map(([l,v,u])=>`<div><span>${l}</span><strong>${v}<small>${u}</small></strong></div>`).join('')}</div>
      <div class="sand-grid"><section class="sand-stage"><div class="sand-map-toolbar"><div>${[['terrain','地形与建筑'],['routes','道路'],['flood','路段积水'],['vehicles','车辆']].map(([k,v])=>`<button data-sand-layer="${k}" aria-pressed="${!state.sandLayers?.[k]}" class="${state.sandLayers?.[k]?'off':''}">${v}</button>`).join('')}</div><div><button data-sand-zoom="-" aria-label="缩小地图">−</button><button data-sand-zoom="+" aria-label="放大地图">+</button><button data-sand-zoom="reset">复位</button></div></div><div class="sand-map-wrap">${map(m)}<div class="sand-map-hint">点击要素查看详情 · 拖拽平移</div></div><div class="sand-legend"><span><i></i>可通行</span><span><i class="amber"></i>容量已满</span><span><i class="red"></i>封闭 / 积水超限</span><span><i class="car"></i>载客车辆</span><span><i class="return"></i>返程车辆</span></div>
      <div class="sand-playback"><button id="sand-play" ${!run?'disabled':''} aria-label="${state.sandPlaying?'暂停':'播放'}推演回放">${state.sandPlaying?'暂停':'播放'}</button><strong><span id="sand-clock">${String(Math.floor(m.minute/60)).padStart(2,'0')}:${String(m.minute%60).padStart(2,'0')}</span><small>第 ${m.minute} 分钟</small></strong><input id="sand-time" type="range" aria-label="沙盘回放分钟" min="0" max="${max}" value="${m.minute}" ${!run?'disabled':''}><select id="sand-speed" aria-label="回放速度">${[1,5,10].map(x=>`<option value="${x}" ${x===(state.sandSpeed||5)?'selected':''}>${x} 分 / 步</option>`).join('')}</select></div><div class="sand-milestones">${[['预警',m.config.warning_minute],['命令',m.config.evacuation_order_minute],['桥梁窗口',Number(m.config.bridge_closure_minute)+(run?.policy_config?.bridge_extension_minutes||0)],['危险到达',m.config.danger_arrival_minute]].map(([label,t])=>`<button data-sand-time="${t}" ${!run?'disabled':''}>${label} <b>${t}′</b></button>`).join('')}</div></section>
      <aside class="sand-inspector"><label class="sand-object-select">定位与检查<select id="sand-object"><option value="">选择地点或道路</option><optgroup label="地点">${[...m.places,...m.shelters].map(p=>`<option value="place:${esc(p.id)}" ${state.sandSelected?.id===p.id?'selected':''}>${esc(names[p.id]||p.name)}</option>`).join('')}</optgroup><optgroup label="道路">${m.routes.map(r=>`<option value="route:${esc(r.id)}" ${state.sandSelected?.id===r.id?'selected':''}>${esc(names[r.origin_id]||r.origin_id)} → ${esc(names[r.shelter_id]||r.shelter_id)}</option>`).join('')}</optgroup></select></label>${inspect(m)}<div class="sand-settings"><span class="sand-eyebrow">下一轮情景</span><label>压力情景<select id="sand-preset"><option value="">选择并调整参数</option><option value="normal">标准情景</option><option value="bridge">桥梁提前封闭</option><option value="flood">积水加剧</option><option value="capacity">道路容量受限</option><option value="comms">通信严重受损</option></select></label><div class="sand-input-grid">${[['road_capacity','走廊容量 / 辆',1,300,1,8],['loading_minutes','装载时间 / 分',0,30,1,5],['flood_peak_m','峰值积水 / m',0,5,.05,.45],['queue_aging_minutes','等待提权 / 分',5,180,5,45]].map(([k,l,min,max,step,def])=>`<label>${l}<input data-sand-config="${k}" type="number" min="${min}" max="${max}" step="${step}" value="${cfg[k]??def}"></label>`).join('')}</div><button class="primary" id="sand-run" ${state.busy?'disabled':''}>${state.busy?'正在计算…':'应用参数并推演'}</button><p class="sand-muted">参数为研究假设；详细情景与资源配置见情景编辑器。</p></div></aside></div>
      <div class="sand-bottom"><section><div class="sand-section-head"><h3>调度事件</h3><span>截至第 ${m.minute} 分钟</span></div>${run?`<div class="sand-event-list">${run.events.filter(e=>e.minute<=m.minute&&['dispatch','resource','organization','facility'].includes(e.kind)).slice(-5).reverse().map(e=>`<article><time>${e.minute}′</time><div><strong>${esc({'vehicle departed':'车辆出发','vehicle returned':'车辆返程完成','vehicle return blocked':'返程受阻','bridge_east closed':'桥梁窗口关闭','communications degraded':'通信受损','evacuation order issued':'下达转移命令','prepare_transfer':'机构准备转移','request_dispatch':'机构请求派车','confirmation workers assigned':'分配人工确认任务'}[e.message]||e.message)}</strong><small>${esc(e.payload.person||e.payload.actor||e.payload.reason||'')}${e.payload.vehicle!=null?` · 车辆 ${e.payload.vehicle+1}`:''}</small></div></article>`).join('')||'<p class="sand-muted">此时刻尚未发生调度事件。</p>'}</div>`:'<p class="sand-muted">运行后，车辆、人数和事件将同步回放。</p>'}</section><section><div class="sand-section-head"><h3>本轮结果与可信度</h3><span>完整时段</span></div><div class="sand-outcomes"><div><strong>${pct(run?.metrics.safe_before_danger_rate)}</strong><small>总体按时转移</small></div><div><strong>${pct(run?.metrics.vulnerable_safe_before_danger_rate)}</strong><small>脆弱群体</small></div><div><strong>${pct(run?.metrics.general_safe_before_danger_rate)}</strong><small>普通群体</small></div></div><p class="sand-muted">合成人口、预设积水过程线与走廊级运输模型。建筑体量为示意，结果尚未以实测洪水和演练数据校准。</p><a href="../docs/model-v3.md" target="_blank" id="sand-model-link">模型来源与验证边界</a></section></div><dialog id="sand-methods"><h2>模型依据与适用范围</h2><p>本轮采用合成人口与逐分钟事件模拟。车辆、照护人员、担架和安置名额受容量约束；积水过程线是预设输入，未经过实测洪水校准。</p><ul><li>道路关闭阈值与减速参数为研究假设，不能作为现实涉水通行依据。</li><li>路线容量在整条走廊层面统计，尚未解析交叉口、私家车与行人交通。</li><li>地图建筑和地形为示意；新增备用路径需要现实数据核验。</li><li>按时转移结果应同时检查普通与脆弱人群，且只适用于本轮输入。</li></ul><p>设计参考：<a href="https://sumo.dlr.de/docs/Simulation/Routing.html" target="_blank" rel="noopener">SUMO 路由</a> · <a href="https://www.hec.usace.army.mil/confluence/rasdocs/hgt/latest/tutorials/2d-unsteady-flow/2d-model-development-and-refinement" target="_blank" rel="noopener">HEC-RAS 校准流程</a></p><button id="sand-close-methods">返回沙盘</button></dialog></div>`;
  }
  function stop() {if(timer)clearInterval(timer);timer=null;state.sandPlaying=false;}
  function bind() {
    if(!document.getElementById('sandbox-map')){stop();return;}
    const on=(selector,fn)=>document.querySelectorAll(selector).forEach(el=>el.onclick=()=>fn(el));
    on('[data-map-place]',el=>{state.sandSelected={type:'place',id:el.dataset.mapPlace};render();});
    on('[data-map-route]',el=>{state.sandSelected={type:'route',id:el.dataset.mapRoute};render();});
    on('[data-map-trip]',el=>{state.sandSelected={type:'trip',id:el.dataset.mapTrip};render();});
    document.querySelectorAll('#sandbox-map [role="button"]').forEach(el=>el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click();}});
    on('[data-sand-layer]',el=>{state.sandLayers||={};state.sandLayers[el.dataset.sandLayer]=!state.sandLayers[el.dataset.sandLayer];render();});
    on('[data-sand-zoom]',el=>{if(el.dataset.sandZoom==='reset'){state.sandZoom=1;state.sandPanX=state.sandPanY=0;}else state.sandZoom=Math.max(.75,Math.min(2.5,(state.sandZoom||1)+(el.dataset.sandZoom==='+'?.25:-.25)));render();});
    document.getElementById('sand-object').onchange=e=>{const [type,...id]=e.target.value.split(':');if(!type)return;state.sandSelected={type,id:id.join(':')};render();};
    const svg=document.getElementById('sandbox-map');let drag=null,moved=false;
    svg.onpointerdown=e=>{if(e.target.closest('[role="button"]'))return;drag={x:e.clientX,y:e.clientY,px:state.sandPanX||0,py:state.sandPanY||0};moved=false;svg.setPointerCapture(e.pointerId);};
    svg.onpointermove=e=>{if(!drag)return;const scale=1000/svg.getBoundingClientRect().width;state.sandPanX=Math.max(-600,Math.min(600,drag.px+(e.clientX-drag.x)*scale));state.sandPanY=Math.max(-400,Math.min(400,drag.py+(e.clientY-drag.y)*scale));moved=true;document.getElementById('sand-world').setAttribute('transform',`translate(${state.sandPanX},${state.sandPanY}) translate(500,310) scale(${state.sandZoom||1}) translate(-500,-310)`);};
    svg.onpointerup=()=>{drag=null;if(moved)render();};svg.onpointercancel=()=>drag=null;
    const changeTime=t=>{stop();state.sandMinute=Number(t);render();};
    on('[data-sand-time]',el=>changeTime(el.dataset.sandTime));
    document.getElementById('sand-time').oninput=e=>{stop();document.getElementById('sand-clock').textContent=`${e.target.value}′`;};
    document.getElementById('sand-time').onchange=e=>changeTime(e.target.value);
    document.getElementById('sand-speed').onchange=e=>state.sandSpeed=Number(e.target.value);
    document.getElementById('sand-play').onclick=()=>{if(timer){stop();render();return;}state.sandPlaying=true;if((state.sandMinute||0)>=Number(document.getElementById('sand-time').max))state.sandMinute=0;timer=setInterval(()=>{const max=Number(document.getElementById('sand-time')?.max||240);state.sandMinute=Math.min(max,(state.sandMinute||0)+(state.sandSpeed||5));if(state.sandMinute>=max)stop();render();},800);render();};
    document.querySelectorAll('[data-sand-config]').forEach(el=>el.onchange=()=>{state.scenarioConfig[el.dataset.sandConfig]=Number(el.value);state.sandDirty=!!state.run;render();});
    document.getElementById('sand-preset').onchange=e=>{const presets={normal:{bridge_closure_minute:120,flood_peak_m:.45,road_capacity:8,communication_failure_rate:.3},bridge:{bridge_closure_minute:70},flood:{flood_peak_m:.8},capacity:{road_capacity:2},comms:{communication_failure_rate:.8}};Object.assign(state.scenarioConfig,presets[e.target.value]||{});state.sandDirty=!!state.run;render();setNotice('压力情景已写入配置；点击“应用参数并推演”重新计算。');};
    document.getElementById('sand-run').onclick=()=>{stop();runSimulation(document.getElementById('policy').value);};
    on('[data-sand-review]',()=>{state.active='政策对比';render();});
    on('[data-sand-roster]',el=>{state.personQuery=el.dataset.sandRoster;state.personPage=1;state.active='叫应确认台';render();});
    on('[data-sand-person]',async el=>{try{state.trace=await request(`/simulations/${state.run.run.id}/agents/${el.dataset.sandPerson}/trace`);state.active='个体与事件解释';render();}catch(e){setNotice(e.message);}});
    document.getElementById('sand-model-link').onclick=e=>{e.preventDefault();stop();document.getElementById('sand-methods').showModal();};
    document.getElementById('sand-close-methods').onclick=()=>document.getElementById('sand-methods').close();
  }
  return {view,bind,stop};
}
