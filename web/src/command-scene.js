import * as THREE from '../vendor/three.module.js';

// Continues the Three.js command-scene design in 75d76bb. Camera, lighting,
// terrain, water and routes remain separate; only kernel trips animate vehicles.
export function createCommandScene() {
  let renderer,scene,camera,root,host,frame,observer,model,select,geometryKey;
  let layers={},labels=[],vehicles=[],roads=[],cameraPose=null,drag=null,viewAspect=1;
  const names={north_valley:'北谷村',south_valley:'南谷村',qingyuan_town:'清源镇',nursing_home:'青松养老中心',county_hospital:'县人民医院',county_school:'第二中学',school_shelter:'北岸中学安置点',gym_shelter:'南部体育馆'};
  const project=([lon,lat])=>[(lon-121.39)/.18*82,(31.26-lat)/.14*58];
  const base=(x,z)=>2.5-x*.045-z*.018;
  const relief=(x,z)=>7.2*Math.exp(-((x+33)**2/170+(z+23)**2/120))+5.8*Math.exp(-((x-32)**2/180+(z+20)**2/135))+3.6*Math.exp(-((x+27)**2/210+(z-24)**2/160))+.45*Math.sin(x*.32)*Math.cos(z*.29);
  let riverSamples=[],pads=[],cameraTarget=new THREE.Vector3(0,1,0);
  const nearestRiver=(x,z)=>{let best={distance:Infinity,width:0,y:0};for(const p of riverSamples){const distance=Math.hypot(x-p.x,z-p.z);if(distance<best.distance)best={distance,width:p.width,y:p.y};}return best;};
  function naturalElevation(x,z){const r=nearestRiver(x,z),blend=Math.max(0,1-r.distance/(r.width+1.8));return base(x,z)+relief(x,z)*(1-blend)-blend*blend*1.6;}
  function elevationAt(x,z){let h=naturalElevation(x,z);for(const p of pads){const distance=Math.max(Math.abs(x-p.x)/3.1,Math.abs(z-p.z)/2.6),blend=Math.max(0,Math.min(1,(1.5-distance)*2));h=h*(1-blend)+p.y*blend;}return h;}
  function roadHeight(x,z){const r=nearestRiver(x,z),ground=Math.max(elevationAt(x,z),elevationAt(x-.5,z),elevationAt(x+.5,z),elevationAt(x,z-.5),elevationAt(x,z+.5))+.12;return r.distance<r.width+2.2?Math.max(ground,r.y+.4):ground;}
  const mat=(color,roughness=.8)=>new THREE.MeshStandardMaterial({color,roughness,metalness:.06});
  function box(group,x,y,z,w,h,d,material){const mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),material);mesh.position.set(x,y+h/2,z);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);return mesh;}
  function ribbon(points,width,height,material) {
    const vertices=[],indices=[];
    for(let i=0;i<points.length;i++){
      const a=points[Math.max(0,i-1)],b=points[Math.min(points.length-1,i+1)],p=points[i];
      const dx=b[0]-a[0],dz=b[1]-a[1],length=Math.hypot(dx,dz)||1;
      for(const side of [-1,1]){const x=p[0]-dz/length*width*.5*side,z=p[1]+dx/length*width*.5*side;vertices.push(x,height(x,z,p),z);}
      if(i<points.length-1){const k=i*2;indices.push(k,k+2,k+1,k+1,k+2,k+3);}
    }
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.setIndex(indices);geometry.computeVertexNormals();
    material.side=THREE.DoubleSide;const mesh=new THREE.Mesh(geometry,material);mesh.receiveShadow=true;return mesh;
  }
  function samplePolyline(coords,step=.3){
    const pts=coords.map(project),sample=[];
    for(let i=1;i<pts.length;i++){const a=pts[i-1],b=pts[i],n=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/step));for(let j=0;j<n;j++)sample.push([a[0]+(b[0]-a[0])*j/n,a[1]+(b[1]-a[1])*j/n]);}
    if(pts.length)sample.push(pts.at(-1));return sample;
  }
  function roadSide(points,width,side){
    const vertices=[],indices=[];
    points.forEach((p,i)=>{const a=points[Math.max(0,i-1)],b=points[Math.min(points.length-1,i+1)],len=Math.hypot(b[0]-a[0],b[1]-a[1])||1,x=p[0]-(b[1]-a[1])/len*width*.5*side,z=p[1]+(b[0]-a[0])/len*width*.5*side,h=roadHeight(x,z)-.035,r=nearestRiver(x,z),bottom=r.distance<r.width*.85?h-.14:elevationAt(x,z);vertices.push(x,h,z,x,bottom,z);if(i<points.length-1){const k=i*2;indices.push(k,k+1,k+2,k+1,k+3,k+2);}});
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.setIndex(indices);geometry.computeVertexNormals();const material=mat(0x4a5d63);material.side=THREE.DoubleSide;const mesh=new THREE.Mesh(geometry,material);mesh.receiveShadow=true;return mesh;
  }
  function building(group,x,z,w,d,h,kind,seed) {
    const y=elevationAt(x,z)+.08,wall=mat(kind==='home'?0xb6bab2:0xb9ced2),roof=mat(kind==='home'?0x546a77:0x648993);
    box(group,x,y,z,w,h,d,wall);
    if(kind==='home'){
      const shape=new THREE.Shape();shape.moveTo(-w/2,0);shape.lineTo(0,h*.38);shape.lineTo(w/2,0);shape.closePath();
      const g=new THREE.ExtrudeGeometry(shape,{depth:d,bevelEnabled:false});const m=new THREE.Mesh(g,roof);m.position.set(x,y+h,z-d/2);m.castShadow=true;group.add(m);
    }else{
      box(group,x,y+h,z,w+.08,.09,d+.08,roof);
      box(group,x+w*.2,y+h+.09,z,.18,.14,.24,mat(0x899b9e));
    }
    const glass=new THREE.MeshStandardMaterial({color:0x294e68,emissive:0x245774,emissiveIntensity:.28,roughness:.3});
    const floors=Math.max(1,Math.floor(h/.32)),windows=Math.max(1,Math.floor(w/.27));
    for(let f=0;f<floors;f++)for(let c=0;c<windows;c++)for(const side of [-1,1])box(group,x-w/2+w*(c+.5)/windows,y+.13+f*.29,z+side*(d/2+.012),.11,.12,.015,glass);
    for(let f=0;f<floors;f++)for(const side of [-1,1])box(group,x+side*(w/2+.012),y+.13+f*.29,z,.015,.12,.13,glass);
    box(group,x,y,z+d/2+.025,.16,.23,.03,mat(0x345361));
  }
  function district(p) {
    const group=new THREE.Group(),[x,z]=project([p.x,p.y]);
    const urban=p.id==='qingyuan_town',village=p.id.includes('valley');
    if(urban||village){
      for(let row=-2;row<=2;row++)for(let col=-3;col<=3;col++){
        if(row===0&&Math.abs(col)<2)continue;
        const bx=x+col*(urban?.85:1),bz=z+row*.96;
        if(nearestRiver(bx,bz).distance<1.4||roads.some(r=>r.points.some(q=>Math.hypot(q[0]-bx,q[1]-bz)<.65)))continue;
        building(group,bx,bz,urban?.60:.48,urban?.70:.56,urban?.8+(col+3)%3*.24:.38+(row+2)%2*.12,urban?'town':'home',row+col);
      }
      for(let row=-2;row<=2;row++)group.add(ribbon([[x-3.8,z+row*.96+.43],[x+3.8,z+row*.96+.43]],.15,(a,b)=>elevationAt(a,b)+.07,mat(0x55696f)));
    }else{
      const school=p.id.includes('school'),gym=p.id==='gym_shelter',hospital=p.id==='county_hospital';
      const ground=elevationAt(x,z);
      box(group,x,ground-.02,z,4.6,.1,3.6,mat(0x768c8b));
      if(gym){
        box(group,x,ground+.08,z,3.7,.85,2.3,mat(0xa9c3c7));
        const roof=new THREE.Mesh(new THREE.CylinderGeometry(1.22,1.22,3.8,24,1,false,0,Math.PI),mat(0x61919f,.42));roof.rotation.z=Math.PI/2;roof.rotation.y=Math.PI/2;roof.position.set(x,ground+.94,z);roof.castShadow=true;group.add(roof);
      }else{
        building(group,x-1.1,z-1.05,2,.8,hospital?1.8:.9,'institution');
        building(group,x-1.1,z+1.05,2,.8,hospital?1.3:.7,'institution');
        if(school){
          box(group,x+1.2,ground+.1,z,1.4,.035,2.75,mat(0xa47463));
          box(group,x+1.2,ground+.14,z,1.04,.035,2.26,mat(0x507d65));
          const loop=new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([[-.44,-.97],[.44,-.97],[.44,.97],[-.44,.97]].map(([a,b])=>new THREE.Vector3(x+1.2+a,ground+.19,z+b))),new THREE.LineBasicMaterial({color:0xc4d6c9}));group.add(loop);
        }else{
          box(group,x+1.4,ground+.12,z,.7,.04,2.6,mat(0x527b67));
          building(group,x-2,z,.7,1.3,.7,'institution');
          if(hospital){box(group,x-.9,ground+1.86,z-1.05,.15,.035,.52,mat(0xc77c65));box(group,x-.9,ground+1.87,z-1.05,.52,.035,.15,mat(0xc77c65));}
        }
      }
      // Campus access is a visual site connection, not a new simulated corridor.
      const gate=[x,z+2.2],candidates=roads.flatMap(r=>r.points).filter(q=>Math.abs(q[0]-x)>3.1||Math.abs(q[1]-z)>2.6);
      const connection=candidates.sort((a,b)=>Math.hypot(a[0]-gate[0],a[1]-gate[1])-Math.hypot(b[0]-gate[0],b[1]-gate[1]))[0];
      const access=[[x,z],gate];if(connection){for(let i=1,n=Math.ceil(Math.hypot(connection[0]-gate[0],connection[1]-gate[1])/.25);i<=n;i++)access.push([gate[0]+(connection[0]-gate[0])*i/n,gate[1]+(connection[1]-gate[1])*i/n]);}
      layers.routes.add(ribbon(access,.38,(a,b)=>roadHeight(a,b)+.025,mat(0x435968)));
      for(const side of [-1,1])box(group,x+side*.4,ground+.09,z+1.8,.14,.35,.14,mat(0x829ba5));
    }
    group.userData.placeId=p.id;layers.terrain.add(group);
    const marker=new THREE.Mesh(new THREE.RingGeometry(.25,.33,32),new THREE.MeshBasicMaterial({color:p.id.includes('shelter')?0x5ce2bf:0x66d5ff,side:THREE.DoubleSide}));marker.rotation.x=-Math.PI/2;marker.position.set(x,elevationAt(x,z)+.17,z);layers.markers.add(marker);
    labels.push({id:p.id,name:names[p.id]||p.name,anchor:new THREE.Vector3(x,elevationAt(x,z)+1.7,z)});
  }
  function build(m){
    scene=new THREE.Scene();scene.background=new THREE.Color(0x061321);scene.fog=new THREE.Fog(0x061321,125,240);
    camera=new THREE.PerspectiveCamera(38,1,.1,700);camera.position.set(22,68,79);camera.lookAt(0,1,0);
    root=new THREE.Group();root.rotation.y=-.2;scene.add(root);
    layers={};for(const id of ['terrain','water','flood','routes','markers','vehicles']){layers[id]=new THREE.Group();root.add(layers[id]);}
    const sunlight=new THREE.DirectionalLight(0xe1f2ff,1.8);sunlight.position.set(-30,70,25);sunlight.castShadow=true;sunlight.shadow.mapSize.set(2048,2048);Object.assign(sunlight.shadow.camera,{left:-60,right:60,top:45,bottom:-45,far:180});sunlight.shadow.bias=-.0004;scene.add(sunlight);scene.add(new THREE.HemisphereLight(0xb2c8dc,0x263a35,1.1));
    riverSamples=[];const riverLines=[];
    for(const river of m.spatial.rivers){
      const coords=river.coordinates.map(c=>{const [x,z]=project(c);return new THREE.Vector3(x,0,z);});
      const curve=new THREE.CatmullRomCurve3(coords,false,'centripetal');
      const samples=curve.getPoints(180).map(p=>[p.x,p.z]);const width=river.kind==='main_channel'?1.1:.65;
      riverSamples.push(...samples.map(([x,z])=>({x,z,width,y:base(x,z)-.9})));riverLines.push({samples,width});
    }
    // Prepared facility sites cut/fill the synthetic terrain; the same height is
    // used by terrain, foundations, buildings and entrance roads to prevent gaps.
    pads=[...m.places,...m.shelters].filter(p=>!p.id.includes('valley')&&p.id!=='qingyuan_town').map(p=>{const [x,z]=project([p.x,p.y]);return {x,z,y:naturalElevation(x,z)+.12};});
    // Original terrain mesh, refined with explicit river beds and solid sides.
    const geometry=new THREE.PlaneGeometry(90,64,180,128);geometry.rotateX(-Math.PI/2);const pos=geometry.attributes.position,colors=[],c=new THREE.Color();
    for(let i=0;i<pos.count;i++){const x=pos.getX(i),z=pos.getZ(i),h=elevationAt(x,z);pos.setY(i,h);const mix=Math.max(0,Math.min(1,(h-2)/8)),noise=Math.sin(x*127.1+z*311.7)*43758.5453,grain=(noise-Math.floor(noise))*.008,bank=nearestRiver(x,z).distance<1.35;c.setRGB((bank?.105:.035)+mix*.075+grain,(bank?.113:.083)+mix*.03+grain,(bank?.10:.084)+mix*.027+grain);colors.push(c.r,c.g,c.b);}
    geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));geometry.computeVertexNormals();const terrain=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({vertexColors:true,roughness:.96}));terrain.receiveShadow=true;layers.terrain.add(terrain);
    box(layers.terrain,0,-2.2,0,90,.7,64,mat(0x152f42));
    const edge=[];for(let x=-45;x<=45;x+=.5)edge.push([x,-32]);for(let z=-31.5;z<=32;z+=.5)edge.push([45,z]);for(let x=44.5;x>=-45;x-=.5)edge.push([x,32]);for(let z=31.5;z>=-32;z-=.5)edge.push([-45,z]);
    const sideVertices=[],sideIndices=[];edge.forEach(([x,z],i)=>{sideVertices.push(x,elevationAt(x,z),z,x,-1.5,z);if(i<edge.length-1){const k=i*2;sideIndices.push(k,k+1,k+2,k+1,k+3,k+2);}});const sideGeo=new THREE.BufferGeometry();sideGeo.setAttribute('position',new THREE.Float32BufferAttribute(sideVertices,3));sideGeo.setIndex(sideIndices);sideGeo.computeVertexNormals();const sideMat=mat(0x263d47);sideMat.side=THREE.DoubleSide;layers.terrain.add(new THREE.Mesh(sideGeo,sideMat));
    const boundary=new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([[-45,-32],[45,-32],[45,32],[-45,32]].map(([x,z])=>new THREE.Vector3(x,-1.47,z))),new THREE.LineBasicMaterial({color:0x3c8cad}));layers.terrain.add(boundary);
    const waterMat=new THREE.MeshStandardMaterial({color:0x245c76,metalness:.4,roughness:.2,emissive:0x104663,emissiveIntensity:.12});
    for(const {samples,width} of riverLines){
      for(const side of [-1,1]){const bank=samples.map((p,i)=>{const a=samples[Math.max(0,i-1)],b=samples[Math.min(samples.length-1,i+1)],len=Math.hypot(b[0]-a[0],b[1]-a[1])||1;return [p[0]-(b[1]-a[1])/len*width*.88*side,p[1]+(b[0]-a[0])/len*width*.88*side];});layers.water.add(ribbon(bank,.24,(x,z)=>elevationAt(x,z)+.018,mat(0x657473)));}
      layers.water.add(ribbon(samples,width*1.6,(x,z)=>base(x,z)-.88,waterMat));
      for(let i=4;i<samples.length-3;i+=7){const slice=samples.slice(i,i+3).map(([x,z])=>new THREE.Vector3(x,base(x,z)-.867,z));layers.water.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(slice),new THREE.LineBasicMaterial({color:0x8fbccb,transparent:true,opacity:.26})));}
    }
    roads=[];
    for(const r of m.routes){
      if(r.coordinates.length<2)continue;
      const pts=samplePolyline(r.coordinates),width=r.synthetic_detour?.48:.72;
      layers.routes.add(ribbon(pts,width+.22,(x,z)=>roadHeight(x,z)-.035,mat(0x687a7d)));
      for(const side of [-1,1])layers.routes.add(roadSide(pts,width+.22,side));
      const surface=mat(r.synthetic_detour?0x586d75:0x293d49);const mesh=ribbon(pts,width,roadHeight,surface);mesh.userData.routeId=r.id;layers.routes.add(mesh);roads.push({route:r,material:surface,points:pts});
      const stripeMat=new THREE.MeshBasicMaterial({color:0xd7cd92,side:THREE.DoubleSide});
      for(let i=0;i<pts.length-1;i+=5)layers.routes.add(ribbon(pts.slice(i,Math.min(i+3,pts.length)),.025,(x,z)=>roadHeight(x,z)+.018,stripeMat));
      // Deck edges and piers are only added where an actual route crosses water.
      let lastPier=-Infinity;
      for(let i=0;i<pts.length;i++){const [x,z]=pts[i],near=nearestRiver(x,z);if(near.distance<near.width*.75&&i-lastPier>5){lastPier=i;const h=roadHeight(x,z);box(layers.routes,x,elevationAt(x,z),z,.12,h-elevationAt(x,z),.15,mat(0x849da5));}}
      for(const sign of [-1,1]){const edgePts=pts.map((p,i)=>{const a=pts[Math.max(0,i-1)],b=pts[Math.min(pts.length-1,i+1)],len=Math.hypot(b[0]-a[0],b[1]-a[1])||1;return [p[0]-(b[1]-a[1])/len*width*.43*sign,p[1]+(b[0]-a[0])/len*width*.43*sign];});layers.routes.add(ribbon(edgePts,.025,(x,z)=>roadHeight(x,z)+.018,new THREE.MeshBasicMaterial({color:0xb5c6cb})));for(let i=1;i<edgePts.length-1;i++){const [x,z]=edgePts[i],near=nearestRiver(x,z);if(near.distance<near.width+.35){layers.routes.add(ribbon(edgePts.slice(i,i+2),.04,(x,z)=>roadHeight(x,z)+.22,mat(0xb2c5cc)));if(i%3===0)box(layers.routes,x,roadHeight(x,z),z,.045,.22,.045,mat(0x90abb8));}}}
      const wet=ribbon(pts,.65,(x,z)=>roadHeight(x,z)+.025,new THREE.MeshBasicMaterial({color:0x2498d6,transparent:true,opacity:.25,side:THREE.DoubleSide,depthWrite:false}));wet.userData.route=r;layers.flood.add(wet);
    }
    labels=[];for(const p of [...m.places,...m.shelters])district(p);
    const canopyMat=mat(0x2c504b),trunkMat=mat(0x526a65),positions=[];
    for(let x=-43;x<43;x+=1.2)for(let z=-30;z<30;z+=1.2){const noise=Math.sin(x*12.8+z*78.2)*43758.54,rand=noise-Math.floor(noise),noise2=Math.sin(z*8.4-x*9.2)*32768,xx=x+rand*.9,zz=z+(noise2-Math.floor(noise2))*.9,forest=Math.sin(xx*.17)*Math.cos(zz*.21)+relief(xx,zz)*.15;if(rand<.38||forest<.38||nearestRiver(xx,zz).distance<2||labels.some(p=>Math.hypot(p.anchor.x-xx,p.anchor.z-zz)<5))continue;if(roads.some(r=>r.points.some(p=>Math.hypot(p[0]-xx,p[1]-zz)<.85)))continue;positions.push([xx,zz,.55+rand*.8]);}
    const trees=new THREE.InstancedMesh(new THREE.SphereGeometry(.32,9,7),canopyMat,positions.length*3),trunks=new THREE.InstancedMesh(new THREE.CylinderGeometry(.045,.07,.65,6),trunkMat,positions.length);const dummy=new THREE.Object3D(),treeColor=new THREE.Color();
    positions.forEach(([x,z,h],i)=>{for(let j=0;j<3;j++){const angle=i*2.39+j*2.1;dummy.position.set(x+Math.cos(angle)*.15,elevationAt(x,z)+h*.48+.22+j*.13,z+Math.sin(angle)*.15);dummy.scale.set(h*.85,h*(.9+j*.08),h*.8);dummy.rotation.y=angle;dummy.updateMatrix();trees.setMatrixAt(i*3+j,dummy.matrix);treeColor.setHSL(.44+(i%5)*.006,.18+(i%3)*.025,.6+(i%7)*.02);trees.setColorAt(i*3+j,treeColor);}dummy.position.set(x,elevationAt(x,z)+.3,z);dummy.scale.set(1,1,1);dummy.updateMatrix();trunks.setMatrixAt(i,dummy.matrix);});trees.castShadow=true;layers.terrain.add(trees,trunks);
    vehicles=[];for(let v=0;v<(m.run?.resource_audit.vehicles||0);v++){const car=new THREE.Group(),body=mat(0xe5eced);car.userData.bodyMaterial=body;box(car,0,0,0,.5,.24,.24,body);box(car,.08,.24,0,.22,.1,.21,mat(0x317199));for(const x of [-.15,.16])for(const z of [-.14,.14]){const wheel=new THREE.Mesh(new THREE.CylinderGeometry(.065,.065,.04,8),mat(0x15212d));wheel.rotation.x=Math.PI/2;wheel.position.set(x,.045,z);car.add(wheel);}layers.vehicles.add(car);vehicles.push(car);}
    if(cameraPose){root.rotation.y=cameraPose.y;camera.position.copy(cameraPose.position);cameraTarget.copy(cameraPose.target);camera.lookAt(cameraTarget);}
  }
  function along(coords,f){const pts=coords.map(project),lengths=pts.slice(1).map((p,i)=>Math.hypot(p[0]-pts[i][0],p[1]-pts[i][1]));let left=Math.max(0,Math.min(1,f))*lengths.reduce((a,b)=>a+b,0);for(let i=0;i<lengths.length;i++){if(left<=lengths[i]){const q=left/(lengths[i]||1);return {x:pts[i][0]+(pts[i+1][0]-pts[i][0])*q,z:pts[i][1]+(pts[i+1][1]-pts[i][1])*q,angle:Math.atan2(-(pts[i+1][1]-pts[i][1]),pts[i+1][0]-pts[i][0])};}left-=lengths[i];}return {x:pts.at(-1)[0],z:pts.at(-1)[1],angle:0};}
  function update(m){
    model=m;const minute=m.minute;
    for(const car of vehicles)car.visible=false;
    vehicles.forEach((car,v)=>{
      const trips=m.trips.filter(t=>t.vehicle===v&&t.dispatch_minute<=minute),t=trips.at(-1),active=t&&minute<t.release_minute;
      const seg=active?t.segments?.find(s=>s.start_minute<=minute&&minute<s.end_minute):null;let p;
      if(seg){const r=m.routes.find(r=>r.id===seg.route_id),f=(minute-seg.start_minute)/(seg.end_minute-seg.start_minute);if(!r)return;p=along(r.coordinates,seg.reverse?1-f:f);if(seg.reverse)p.angle+=Math.PI;}
      else{const at=m.points[active?(minute<t.departure_minute?t.origin_id:t.shelter_id):(t?.shelter_id||m.run.transport.fleet_base_id)];if(!at)return;const [x,z]=project([at.x,at.y]);p={x:x+(v%5)*.48-1,z:z+2.3+Math.floor(v/5)*.35,angle:0};}
      car.visible=true;car.position.set(p.x,seg?roadHeight(p.x,p.z)+.04:elevationAt(p.x,p.z)+.12,p.z);car.rotation.y=p.angle;car.userData.tripIndex=t?m.trips.indexOf(t):null;
      car.userData.bodyMaterial.color.set(seg?.phase==='pickup'?0x6ab8e7:active?0xe2b776:0xe5eced);
    });
    for(const r of roads){const status=m.routeStatus(r.route);r.material.color.set(status==='封闭'||status==='积水超限'?0x934f43:status==='容量已满'?0x947548:r.route.synthetic_detour?0x586d75:0x293d49);}
    for(const wet of layers.flood.children)wet.visible=m.routeDepth(wet.userData.route)>0;
    for(const [key,g] of Object.entries(layers))g.visible=!m.hidden[key];
  }
  function positionLabels(){
    if(!host)return;const w=host.clientWidth,h=host.clientHeight,occupied=[];root.updateMatrixWorld();camera.updateMatrixWorld();
    const ordered=[...labels].sort((a,b)=>(b.id===model.selectedId)-(a.id===model.selectedId));
    for(const p of ordered){const screen=p.anchor.clone();root.localToWorld(screen);screen.project(camera);const el=p.element;if(!el)continue;let x=(screen.x*.5+.5)*w,y=(-screen.y*.5+.5)*h,placed=false;
      if(screen.z<1&&screen.z>-1&&x>10&&x<w-10&&y>30&&y<h-20){for(const dy of [-32,-59,5,32]){const rect={x:Math.max(6,Math.min(w-138,x-64)),y:y+dy,w:132,h:25};if(rect.y<10||rect.y>h-34||occupied.some(a=>rect.x<a.x+a.w+5&&rect.x+rect.w+5>a.x&&rect.y<a.y+a.h+4&&rect.y+rect.h+4>a.y))continue;el.style.transform=`translate(${rect.x}px,${rect.y}px)`;occupied.push(rect);placed=true;break;}}
      el.hidden=!placed||!!model.hidden.markers;
    }
  }
  function mount(container,m,onSelect){
    select=onSelect;const key=JSON.stringify([m.routes.map(r=>[r.id,r.coordinates]),m.places,m.shelters.map(s=>[s.id,s.x,s.y]),m.run?.resource_audit.vehicles]);
    if(!renderer){renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.95;
      renderer.domElement.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,moved:false};renderer.domElement.setPointerCapture(e.pointerId);});
      renderer.domElement.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.moved||=Math.abs(dx)+Math.abs(dy)>2;const offset=camera.position.clone().sub(cameraTarget);offset.applyAxisAngle(new THREE.Vector3(0,1,0),-dx*.005);offset.y=Math.max(4,Math.min(220,offset.y+dy*.2));camera.position.copy(cameraTarget).add(offset);camera.lookAt(cameraTarget);drag.x=e.clientX;drag.y=e.clientY;});
      renderer.domElement.addEventListener('pointerup',e=>{if(drag&&!drag.moved){const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);const hits=ray.intersectObjects([layers.vehicles,layers.routes,layers.terrain].filter(g=>g.visible),true);for(const hit of hits){let obj=hit.object;while(obj&&obj.userData.tripIndex==null&&!obj.userData.routeId&&!obj.userData.placeId)obj=obj.parent;if(obj){if(obj.userData.tripIndex!=null)select('trip',String(obj.userData.tripIndex));else if(obj.userData.routeId)select('route',obj.userData.routeId);else select('place',obj.userData.placeId);break;}}}drag=null;saveCamera();});
      renderer.domElement.addEventListener('pointercancel',()=>{drag=null;});
      renderer.domElement.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY>0?1.06:.94);},{passive:false});
    }
    if(key!==geometryKey){if(root)disposeScene();build(m);geometryKey=key;}
    host=container;host.replaceChildren(renderer.domElement);const overlay=document.createElement('div');overlay.className='command-labels';host.appendChild(overlay);
    for(const p of labels){const el=document.createElement('button');el.textContent=p.name;el.dataset.scenePlace=p.id;el.className='command-place-label';el.classList.toggle('selected',p.id===m.selectedId);el.onclick=()=>select('place',p.id);p.element=el;overlay.appendChild(el);}
    observer?.disconnect();observer=new ResizeObserver(()=>{if(!host?.isConnected)return;const w=host.clientWidth,h=host.clientHeight;renderer.setSize(w,h);viewAspect=w/h;camera.aspect=viewAspect;camera.updateProjectionMatrix();if(!cameraPose)reset();});observer.observe(host);
    update(m);if(!frame){const animate=()=>{if(host?.isConnected){scene.fog.near=Math.max(125,camera.position.length()*1.3);scene.fog.far=scene.fog.near+150;positionLabels();renderer.render(scene,camera);}frame=requestAnimationFrame(animate);};animate();}
  }
  function saveCamera(){if(camera)cameraPose={position:camera.position.clone(),target:cameraTarget.clone(),y:root.rotation.y};}
  function zoom(factor){if(!camera)return;camera.position.sub(cameraTarget).multiplyScalar(factor).clampLength(8,340).add(cameraTarget);camera.lookAt(cameraTarget);saveCamera();}
  function focus(id){const place=labels.find(p=>p.id===id);if(!place)return;root.updateMatrixWorld();cameraTarget.copy(place.anchor);root.localToWorld(cameraTarget);camera.position.copy(cameraTarget).add(new THREE.Vector3(5,9,12).multiplyScalar(Math.max(1,1.2/viewAspect)));camera.lookAt(cameraTarget);saveCamera();}
  function reset(){cameraPose=null;if(camera){cameraTarget.set(0,1,0);camera.position.set(22,68,79).multiplyScalar(Math.max(1,1.4/viewAspect));root.rotation.y=-.2;camera.lookAt(cameraTarget);}}
  function disposeScene(){root.traverse(o=>{o.geometry?.dispose();if(o.material){for(const material of Array.isArray(o.material)?o.material:[o.material])material.dispose();}});}
  function dispose(){observer?.disconnect();cancelAnimationFrame(frame);frame=null;if(root)disposeScene();renderer?.dispose();renderer=null;root=null;geometryKey=null;host=null;}
  return {mount,zoom,reset,focus,dispose};
}
