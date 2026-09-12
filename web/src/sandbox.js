import {createCommandScene} from './command-scene.js';
// Spatial replay consumes kernel trips; no decorative traffic or inferred counts.
export function createSandbox({state,render,request,setNotice,runSimulation,escapeHtml:esc}) {
  let timer=null;
  const scene=createCommandScene();
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
    const busy=m.run?.transport?.road_reservations
      ? (m.run.transport.road_reservations[r.id]||[]).filter(s=>s.start_minute<=m.minute&&m.minute<s.end_minute).length
      : m.trips.filter(t=>(t.route_id===r.id||t.return_route_id===r.id)&&(t.dispatch_minute??t.boarding_minute)<=m.minute&&(t.release_minute==null||t.release_minute>m.minute)).length;
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
  function inspect(m) {
    const selected=state.sandSelected;
    if(selected?.type==='trip'){
      const t=m.trips[Number(selected.id)];if(!t)return '';
      return `<div class="sand-detail"><span class="sand-eyebrow">车辆轨迹</span><h3>转运车 ${t.vehicle+1}</h3><p>${esc(names[t.origin_id])} → ${esc(names[t.shelter_id])}</p><dl><dt>派车位置</dt><dd>${esc(names[t.vehicle_origin_id]||t.vehicle_origin_id||'旧模型未跟踪')}</dd><dt>派车时刻</dt><dd>${t.dispatch_minute??t.boarding_minute} 分</dd><dt>乘员</dt><dd>${t.passengers.length} 人</dd><dt>装载 / 出发</dt><dd>${t.boarding_minute} / ${t.departure_minute} 分</dd><dt>实际到达</dt><dd>${t.arrival_minute} 分</dd><dt>卸载后可再调度</dt><dd>${t.release_minute??'本轮无法返程'} 分</dd></dl><p class="sand-muted">${esc(t.dispatch_reason||'按政策顺序调度')}</p><ol class="sand-itinerary">${(t.segments||[]).map(seg=>`<li><b>${seg.start_minute}–${seg.end_minute}′ · ${seg.phase==='pickup'?'空驶':'载客'}</b><span>${esc(names[seg.from_id]||seg.from_id)} → ${esc(names[seg.to_id]||seg.to_id)}</span></li>`).join('')}</ol><button data-sand-person="${esc(t.passengers[0])}">查看首位乘员的完整轨迹 →</button></div>`;
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
    const reserved=m.trips.filter(t=>t.shelter_id===id&&(t.dispatch_minute??t.boarding_minute)<=m.minute).reduce((a,t)=>a+t.passengers.length,0);
    return `<div class="sand-detail"><span class="sand-eyebrow">${shelter?'安置设施':'重点区域'}</span><h3>${esc(names[id]||p?.name||id)}</h3><p class="sand-muted">${shelter?'到达、在途预留与剩余容量分别计数':'选择地图上的道路、车辆或地点查看详情'}</p><dl>${shelter?`<dt>实际到达</dt><dd>${arrivals} 人</dd><dt>已预留（含到达）</dt><dd>${reserved} / ${shelter.capacity}</dd><dt>全照护接收上限</dt><dd>${shelter.medical_slots??shelter.care_capacity??'—'}</dd>`:`<dt>应转 / 尚未出发</dt><dd>${m.run?`${targets.length} / ${pending.length}`:'待运行'}</dd><dt>已触达</dt><dd>${targets.filter(a=>a.contact_minute!=null&&a.contact_minute<=m.minute).length} 人</dd><dt>已完成安置</dt><dd>${targets.filter(a=>a.sheltered_minute!=null&&a.sheltered_minute<=m.minute).length} 人</dd>`}</dl><button data-sand-focus="${esc(id)}">放大查看街区与设施</button>${!shelter?`<button data-sand-roster="${esc(id)}">打开该区域转移台账 →</button>`:''}</div>`;
  }
  function coverage(m) {
    if(!m.run)return '';
    const targets=m.run.agents.filter(a=>a.requires_transfer),limit=Math.max(240,Number(m.config.danger_arrival_minute)+60);
    const groups=[{label:'脆弱群体',v:true,color:'#397f95'},{label:'普通群体',v:false,color:'#ae8055'}];
    return `<div class="sand-coverage"><svg viewBox="0 0 420 106" role="img" aria-label="各应转群体累计安置比例，随时间回放"><path d="M26 8V82H402M26 45H402M26 8H402" fill="none" stroke="#e0e7eb"/><text x="0" y="12">100%</text><text x="10" y="84">0</text>${groups.map(g=>{const people=targets.filter(a=>a.is_vulnerable===g.v);if(!people.length)return '';const times=people.filter(a=>a.sheltered_minute!=null&&a.sheltered_minute<=m.minute).map(a=>a.sheltered_minute).sort((a,b)=>a-b);let line='M26 82';times.forEach((t,i)=>line+=`H${26+t/limit*376}V${82-(i+1)/people.length*74}`);line+=`H${26+m.minute/limit*376}`;return `<path d="${line}" fill="none" stroke="${g.color}" stroke-width="2"/>`;}).join('')}<path d="M${26+m.minute/limit*376} 8V82" stroke="#839ba7" stroke-dasharray="3 3"/><text x="26" y="101">0′</text><text x="330" y="101">${limit}′ · 仿真时间</text></svg><div>${groups.map(g=>`<span><i style="background:${g.color}"></i>${g.label}</span>`).join('')}<span>累计安置 / 各组应转人数</span></div></div>`;
  }
  function view() {
    const m=model(),run=m.run,agents=run?.agents.filter(a=>a.requires_transfer)||[],cfg=state.scenarioConfig;
    const at=m.minute,max=Math.max(240,Number(m.config.danger_arrival_minute)+60);
    const arrived=agents.filter(a=>a.sheltered_minute!=null&&a.sheltered_minute<=at).length;
    const moving=agents.filter(a=>a.transit_minute!=null&&a.transit_minute<=at&&(a.sheltered_minute==null||a.sheltered_minute>at)).length;
    const busy=m.trips.filter(t=>(t.dispatch_minute??t.boarding_minute)<=at&&at<t.release_minute).length;
    const modes=[['hydrology','水文预报'],['warning','预警设置'],['simulation','模拟预演'],['plan','预案生成']];
    const mode=state.mapMode||'simulation';
    return `<div class="view command-workspace">
      <section class="metric-grid">${[['总体按时转移',pct(run?.metrics.safe_before_danger_rate)],['脆弱群体按时转移',pct(run?.metrics.vulnerable_safe_before_danger_rate)],['普通群体按时转移',pct(run?.metrics.general_safe_before_danger_rate)],['应转对象',run?agents.length:'—']].map(([label,value])=>`<div class="metric"><span class="metric-icon">${label[0]}</span><label>${label}</label><strong>${value}</strong></div>`).join('')}</section>
      ${state.sandDirty?'<div class="command-dirty" role="status">参数已修改。三维沙盘仍显示上次结果，运行推演后应用新配置。</div>':''}
      <section class="map-band command-band restored-command-band">
        <div class="terrain-panel command-terrain-panel three-ready" id="terrain-panel">
          <div class="terrain-toolbar"><div class="command-title-block"><strong>清源县极端洪涝人员转移联合指挥舱</strong><span>县防汛抗旱指挥部 · 合成情景 · 三维事件回放</span></div><div class="map-badges"><span>第 ${at} 分钟</span><span class="${at>=m.config.communication_failure_minute?'bad':'good'}">通信${at>=m.config.communication_failure_minute?'受损':'正常'}</span><button class="hud-toggle" id="command-focus">${state.commandFocus?'显示数据面板':'专注三维沙盘'}</button></div></div>
          <div class="forecast-tabs command-mode-tabs">${modes.map(([key,label])=>`<button data-command-mode="${key}" class="${mode===key?'active':''}">${label}</button>`).join('')}</div>
          <div class="command-layer-controls">${[['terrain','三维地形 / 建筑'],['water','河道水面'],['flood','路段积水'],['routes','转移道路'],['markers','设施标签'],['vehicles','调度车辆']].map(([key,label])=>`<button data-sand-layer="${key}" aria-pressed="${!state.sandLayers?.[key]}" class="${state.sandLayers?.[key]?'off':''}"><i></i>${label}</button>`).join('')}<div class="command-camera-tools"><button data-camera="in" aria-label="放大三维场景">＋</button><button data-camera="out" aria-label="缩小三维场景">－</button><button data-camera="reset">复位视角</button></div></div>
          <div class="command-map-frame"><div id="scenario-3d-map" class="scenario-3d-map" aria-label="清源县三维合成洪涝转移沙盘"></div><div class="command-scene-hint">拖动旋转 · 滚轮缩放 · 点击设施或车辆</div><div class="command-source-note">合成地形及建筑 · 道路与车辆对应仿真记录 · 非实测淹没范围</div><div id="scene-error" role="status"></div></div>
          <div class="live-strip"><div><strong>${arrived}</strong><span>此刻已安置</span></div><div><strong>${moving}</strong><span>此刻载客途中</span></div><div><strong>${busy} / ${run?.resource_audit.vehicles??'—'}</strong><span>任务占用 / 总车辆</span></div><div><strong>${Math.max(0,m.config.danger_arrival_minute-at)}′</strong><span>距危险到达</span></div></div>
          <div class="command-replay"><button id="sand-play" ${!run?'disabled':''}>${state.sandPlaying?'暂停':'播放'}</button><strong id="sand-clock">${String(Math.floor(at/60)).padStart(2,'0')}:${String(at%60).padStart(2,'0')}</strong><input id="sand-time" aria-label="沙盘回放分钟" type="range" min="0" max="${max}" value="${at}" ${!run?'disabled':''}><select id="sand-speed" aria-label="回放速度">${[1,5,10].map(v=>`<option value="${v}" ${v===(state.sandSpeed||1)?'selected':''}>${v} 分 / 步</option>`).join('')}</select></div>
          <div class="command-milestones">${[['预警',m.config.warning_minute],['命令',m.config.evacuation_order_minute],['危险到达',m.config.danger_arrival_minute]].map(([label,t])=>`<button data-sand-time="${t}" ${!run?'disabled':''}>${label} ${t}′</button>`).join('')}<span>车辆：蓝 / 空驶 · 橙 / 载客与装卸 · 白 / 待命</span><span>道路：灰 / 通行 · 黄 / 容量满 · 红 / 封闭或积水超限</span></div>
        </div>
        <aside class="side-table command-details"><h2>${modes.find(([k])=>k===mode)?.[1]||'对象详情'}</h2><label>定位与检查<select id="sand-object"><optgroup label="地点">${[...m.places,...m.shelters].map(p=>`<option value="place:${esc(p.id)}" ${state.sandSelected?.id===p.id?'selected':''}>${esc(names[p.id]||p.name)}</option>`).join('')}</optgroup><optgroup label="道路">${m.routes.map(r=>`<option value="route:${esc(r.id)}" ${state.sandSelected?.id===r.id?'selected':''}>${esc(names[r.origin_id]||r.origin_id)} → ${esc(names[r.shelter_id]||r.shelter_id)}</option>`).join('')}</optgroup><optgroup label="车辆任务">${m.trips.map((t,i)=>`<option value="trip:${i}" ${state.sandSelected?.type==='trip'&&Number(state.sandSelected.id)===i?'selected':''}>车辆 ${t.vehicle+1} · ${t.dispatch_minute??t.boarding_minute}′ 派车</option>`).join('')}</optgroup></select></label>${inspect(m)}
          <div class="command-settings"><h3>下一轮参数</h3><label>压力情景<select id="sand-preset"><option value="">选择压力条件</option><option value="normal">标准情景</option><option value="bridge">桥梁提前封闭</option><option value="flood">积水加剧</option><option value="capacity">道路容量受限</option><option value="comms">通信受损</option></select></label><label>派车顺序<select id="sand-dispatch"><option value="policy_priority" ${cfg.dispatch_mode!=='balanced_coverage'?'selected':''}>按政策优先顺序</option><option value="balanced_coverage" ${cfg.dispatch_mode==='balanced_coverage'?'selected':''}>已知人群覆盖均衡</option></select></label><label>初始集结点<select id="sand-depot">${m.shelters.map(sh=>`<option value="${esc(sh.id)}" ${(cfg.fleet_base_id||'school_shelter')===sh.id?'selected':''}>${esc(names[sh.id]||sh.name)}</option>`).join('')}</select></label><div class="command-input-grid">${[['road_capacity','道路容量 / 辆',1,300,1,8],['loading_minutes','装载 / 分',0,30,1,5],['flood_peak_m','积水峰值 / m',0,5,.05,.45],['queue_aging_minutes','等待提权 / 分',5,180,5,45]].map(([k,l,min,max,step,def])=>`<label>${l}<input data-sand-config="${k}" type="number" min="${min}" max="${max}" step="${step}" value="${cfg[k]??def}"></label>`).join('')}</div><button class="primary" id="sand-run" ${state.busy?'disabled':''}>${state.busy?'正在推演…':'应用参数并推演'}</button></div></aside>
      </section>
      <section class="command-evidence"><div><h2>分组安置进程</h2>${coverage(m)}<p class="sand-muted">按各组应转人数为分母，仅在实际到达后累计。合成人口与预设灾害过程尚未以实测数据校准。</p></div><div><h2>结果复核</h2><p>运行版本：${esc(run?.run.code_version||'等待运行')}</p><p>此刻 ${arrived} 人已到达；完整时段的按时转移结果见上方仪表盘。</p><button data-sand-review>查看同种子政策对照 →</button><button id="sand-model-link">模型依据与适用范围</button></div></section>
      <dialog id="sand-methods"><h2>模型依据与适用范围</h2><p>保留原指挥舱三维风格。地形、建筑、河床为合成空间示意；道路状态和车辆分段行程来自仿真内核。车辆从驻地空驶接人，卸载后在目的地等待下次任务。</p><p>道路通行使用预设水深和情景阈值，未求解水动力或校准真实灾情。建筑不是实测地物，不能用画面判断现实安全。详细计算规则见项目 docs/model-v4.md。</p><button id="sand-close-methods">返回沙盘</button></dialog>
    </div>`;
  }
  function stop(){if(timer)clearInterval(timer);timer=null;state.sandPlaying=false;}
  function bind(){
    const host=document.getElementById('scenario-3d-map');if(!host){stop();scene.dispose();return;}
    document.querySelector('.command-workspace').classList.toggle('command-focused',!!state.commandFocus);
    const m=model();m.hidden=state.sandLayers||{};m.selectedId=state.sandSelected?.id;m.routeStatus=r=>status(r,m);m.routeDepth=r=>depth(r,m.minute);
    const choose=(type,id)=>{stop();state.sandSelected={type,id};render();};
    try{scene.mount(host,m,choose);}catch(error){document.getElementById('scene-error').textContent='三维场景加载失败：'+error.message;}
    const on=(q,f)=>document.querySelectorAll(q).forEach(el=>el.onclick=()=>f(el));
    on('[data-camera]',el=>el.dataset.camera==='reset'?scene.reset():scene.zoom(el.dataset.camera==='in'?.9:1.1));
    on('[data-sand-layer]',el=>{state.sandLayers||={};state.sandLayers[el.dataset.sandLayer]=!state.sandLayers[el.dataset.sandLayer];render();});
    on('[data-command-mode]',el=>{stop();state.mapMode=el.dataset.commandMode;if(state.mapMode==='plan'){state.active='复盘与建议';render();return;}if(state.mapMode==='hydrology'){const route=m.routes.find(r=>r.depth_profile?.length);if(route)state.sandSelected={type:'route',id:route.id};state.commandFocus=false;}if(state.mapMode==='warning')state.commandFocus=false;render();if(state.mapMode==='warning')document.querySelector('.command-settings').scrollIntoView({block:'center',behavior:'smooth'});});
    document.getElementById('command-focus').onclick=()=>{state.commandFocus=!state.commandFocus;render();};
    document.getElementById('sand-object').onchange=e=>{const [type,...id]=e.target.value.split(':');choose(type,id.join(':'));};
    const time=t=>{stop();state.sandMinute=Number(t);render();};on('[data-sand-time]',el=>time(el.dataset.sandTime));
    document.getElementById('sand-time').oninput=e=>{stop();document.getElementById('sand-clock').textContent=e.target.value+'′';};document.getElementById('sand-time').onchange=e=>time(e.target.value);
    document.getElementById('sand-speed').onchange=e=>state.sandSpeed=Number(e.target.value);
    document.getElementById('sand-play').onclick=()=>{if(timer){stop();render();return;}state.sandPlaying=true;if(state.sandMinute>=Number(document.getElementById('sand-time').max))state.sandMinute=0;timer=setInterval(()=>{state.sandMinute=Math.min(Number(document.getElementById('sand-time').max),(state.sandMinute||0)+(state.sandSpeed||1));if(state.sandMinute>=Number(document.getElementById('sand-time').max))stop();render();},600);render();};
    document.querySelectorAll('[data-sand-config]').forEach(el=>el.onchange=()=>{stop();state.scenarioConfig[el.dataset.sandConfig]=Number(el.value);state.sandDirty=!!state.run;render();});
    for(const [id,key] of [['sand-dispatch','dispatch_mode'],['sand-depot','fleet_base_id']])document.getElementById(id).onchange=e=>{stop();state.scenarioConfig[key]=e.target.value;state.sandDirty=!!state.run;render();};
    document.getElementById('sand-preset').onchange=e=>{const presets={normal:{bridge_closure_minute:120,flood_peak_m:.45,road_capacity:8,communication_failure_rate:.3},bridge:{bridge_closure_minute:70},flood:{flood_peak_m:.8},capacity:{road_capacity:2},comms:{communication_failure_rate:.8}};stop();Object.assign(state.scenarioConfig,presets[e.target.value]||{});state.sandDirty=!!state.run;render();};
    document.getElementById('sand-run').onclick=()=>{stop();runSimulation(document.getElementById('policy').value);};
    on('[data-sand-roster]',el=>{state.personQuery=el.dataset.sandRoster;state.personPage=1;state.active='叫应确认台';render();});
    on('[data-sand-focus]',el=>{scene.focus(el.dataset.sandFocus);host.scrollIntoView({block:'center',behavior:'smooth'});});
    on('[data-sand-person]',async el=>{try{state.trace=await request(`/simulations/${state.run.run.id}/agents/${el.dataset.sandPerson}/trace`);state.active='个体与事件解释';render();}catch(e){setNotice(e.message);}});
    on('[data-sand-review]',()=>{state.active='政策对比';render();});
    document.getElementById('sand-model-link').onclick=()=>{stop();document.getElementById('sand-methods').showModal();};document.getElementById('sand-close-methods').onclick=()=>document.getElementById('sand-methods').close();
  }
  return {view,bind,stop};
}
