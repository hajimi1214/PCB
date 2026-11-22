const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createHash} = require('node:crypto');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const DIR = path.resolve(__dirname,'../tools/eda_actions');
const target = {pcb_uuid:'pcb',expected_project_uuid:'project'};
const sha = s => createHash('sha256').update(s).digest('hex');

async function run(name,api,args={}) {
  return new AsyncFunction('eda','__CLI__',fs.readFileSync(path.join(DIR,'drawing_common.js'),'utf8')+'\n'+
    fs.readFileSync(path.join(DIR,name+'.js'),'utf8'))(api,{args:{...target,...args}});
}
async function runStandalone(name,api,args={}) {
  return new AsyncFunction('eda','__CLI__',fs.readFileSync(path.join(DIR,name+'.js'),'utf8'))(api,{args});
}
function fixture() {
  const f = {calls:[],footprintLookups:[],focus:{uuid:'pcb',documentType:3,parentProjectUuid:'project'}};
  f.jobStatus={jobId:'job-1',state:'running',progress:40,partial:false};f.ratlines=[];
  f.board={nets:['GND','VCC'],layers:[{id:1,type:'SIGNAL',layerStatus:1,locked:false},{id:15,type:'SIGNAL',layerStatus:1,locked:false},{id:11,type:'OTHER',layerStatus:1,locked:false}],
      components:[{id:'c1',designator:'U1',x:100,y:100,rotation:90,layer:1,locked:false,device:{libraryUuid:'device-library',uuid:'device'},footprint:{libraryUuid:'footprint-library',uuid:'existing-footprint'},
      device:{libraryUuid:'fixture-device-library',uuid:'fixture-device',name:'Fixture Device'},
      footprint:{libraryUuid:'fixture-footprint-library',uuid:'fixture-footprint',name:'Fixture Footprint'},
      pads:[{id:'p1',number:'1',net:'GND',x:95,y:100,layer:1},{id:'p2',number:'1',net:'GND',x:105,y:100,layer:1}]}],lines:[],vias:[],outlines:[]};
  const primitive=o=>{
    if (!o) return undefined;
    const map={PrimitiveId:'id',Designator:'designator',Component:'device',Footprint:'footprint',X:'x',Y:'y',Rotation:'rotation',Layer:'layer',PrimitiveLock:'locked',PadNumber:'number',Net:'net',StartX:'x1',StartY:'y1',EndX:'x2',EndY:'y2',LineWidth:'width',HoleDiameter:'hole',Diameter:'diameter',ViaType:'viaType',Polygon:'polygon'};
    const r={};for (const [getter,key] of Object.entries(map))r['getState_'+getter]=()=>o[key];
    if(o.pads)r.getAllPins=async()=>o.pads.map(primitive);
    return r;
  };
  f.source=()=>JSON.stringify({type:"DOCHEAD",ticket:0,id:"0123456789abcdef"})+"||"+
    JSON.stringify({uuid:"pcb",docType:"PCB"})+"|\n"+
    JSON.stringify({type:"DATA",ticket:1,id:"fedcba9876543210"})+"||"+JSON.stringify(f.board)+"|";
  f.api={
    dmt_SelectControl:{getCurrentDocumentInfo:async()=>f.focus},
    sys_FileManager:{getDocumentSource:async()=>f.source()},
    pcb_Layer:{getAllLayers:async()=>structuredClone(f.board.layers)},
    pcb_Net:{getAllNetsName:async()=>[...f.board.nets]},
    pcb_PrimitiveComponent:{
      getAll:async()=>f.board.components.map(primitive),
      get:async id=>primitive(f.board.components.find(c=>c.id===id)),
      create:async(footprint,layer,x,y,rotation)=>{const o={id:'component'+f.board.components.length,designator:'',x,y,rotation,layer,locked:false,device:undefined,footprint:{libraryUuid:footprint.libraryUuid,uuid:footprint.uuid,name:footprint.name},pads:(footprint.pad_numbers||[]).map((number,index)=>({id:'visualpad'+index,number,net:null,x:x+index,y,layer}))};f.calls.push('footprint');f.board.components.push(o);return primitive(o);},
      modify:async(id,pos)=>{
        f.calls.push('move');const c=f.board.components.find(c=>c.id===id),oldX=c.x,oldY=c.y,oldRotation=c.rotation;
        const rad=((pos.rotation??oldRotation)-oldRotation)*Math.PI/180;
        for(const p of c.pads){const x=p.x-oldX,y=p.y-oldY;p.x=oldX+x*Math.cos(rad)-y*Math.sin(rad)+pos.x-oldX;p.y=oldY+x*Math.sin(rad)+y*Math.cos(rad)+pos.y-oldY;}
        Object.assign(c,pos);return primitive(c);
      }
    },
    lib_Footprint:{get:async(uuid,libraryUuid)=>{f.calls.push('resolve-footprint');f.footprintLookups.push({uuid,libraryUuid});return {uuid,libraryUuid:libraryUuid??'a'.repeat(32),name:'fixture-footprint',pad_numbers:['1','2']};}},
    pcb_PrimitiveLine:{
      create:async(net,layer,x1,y1,x2,y2,width)=>{
        f.calls.push('line');const o={id:'line'+f.board.lines.length,net,layer,x1,y1,x2,y2,width};f.board.lines.push(o);return primitive(o);
      },get:async id=>primitive(f.board.lines.find(l=>l.id===id))
    },
    pcb_PrimitiveVia:{
      create:async(net,x,y,hole,diameter,viaType)=>{
        f.calls.push('via');const o={id:'via'+f.board.vias.length,net,x,y,hole,diameter,viaType};f.board.vias.push(o);return primitive(o);
      },get:async id=>primitive(f.board.vias.find(v=>v.id===id))
    },
    pcb_PrimitivePolyline:{
      create:async(net,layer,polygon,width)=>{f.calls.push('outline');const o={id:'outline'+f.board.outlines.length,net,layer,polygon,width};f.board.outlines.push(o);return primitive(o);},
      modify:async(id,props)=>{f.calls.push('outline-modify');const o=f.board.outlines.find(o=>o.id===id);if(!o)return undefined;Object.assign(o,props);return primitive(o);},
      get:async id=>primitive(f.board.outlines.find(o=>o.id===id)),
      getAll:async(net,layer)=>f.board.outlines.filter(o=>layer===undefined||o.layer===layer).map(primitive)
    },
    pcb_MathPolygon:{createPolygon:source=>({getSource:()=>source})},
    sys_Math:{rotate:(points,angle,cx,cy)=>{const rad=angle*Math.PI/180;return points.map(p=>({x:cx+(p.x-cx)*Math.cos(rad)-(p.y-cy)*Math.sin(rad),y:cy+(p.x-cx)*Math.sin(rad)+(p.y-cy)*Math.cos(rad)}));}},
    pcb_Document:{
      beginCommandGroup:async()=>{f.calls.push('begin');f.backup=structuredClone(f.board);return {groupId:'g1'};},
      commitCommandGroup:async()=>{f.calls.push('commit');return true;},
      rollbackCommandGroup:async()=>{f.calls.push('rollback');f.board=structuredClone(f.backup);return true;},
      startAutoRouting:async(props)=>{f.calls.push('route-start');f.routeProps=props;return {jobId:'job-1'};},
      getAutoJobStatus:async id=>({ ...f.jobStatus,jobId:id }),
      getAutoJobLog:async()=>({logs:[],progress:{progress:0.4,routabitity:0.8}}),
      getRatlines:async({cursor,limit})=>{const start=cursor?Number(cursor):0,items=f.ratlines.slice(start,start+limit),next=start+items.length;return {items,hasMore:next<f.ratlines.length,...(next<f.ratlines.length?{nextCursor:String(next)}:{})};},
      cancelAutoJob:async()=>true
    }
  };
  f.apply=ops=>run('apply_drawing_batch',f.api,{operations:ops,plan_id:'a'.repeat(32),expected_source_sha256:sha(f.source())});
  return f;
}
const move={kind:'move',component_id:'c1',x:200,y:300};
const line={kind:'line',net:'GND',layer:15,x1:10,y1:20,x2:40,y2:20,width:6};
const via={kind:'via',net:'GND',x:40,y:20,hole:12,diameter:24};
const place={kind:'place',component_id:'c1',x:200,y:300,rotation:0};
const outline={kind:'outline',points:[[0,0],[400,0],[400,600],[0,600],[0,0]],width:2};
const replacementOutline={kind:'replace_outline',primitive_id:'outline0',points:[[0,0],[400,0],[400,600],[0,600],[0,0]],width:2};

test('snapshot source digest and physical pads retain duplicate numbers',async()=>{
  const f=fixture(),r=await run('drawing_state',f.api);
  assert.equal(r.ok,true);assert.equal(r.source_sha256,sha(r.source));assert.equal(r.components[0].pads.length,2);assert.deepEqual(f.calls,[]);
});
test('reference importer targets a named new account project and reports source Boards',async()=>{
  const calls=[];let current=null;
  const api={
    sys_Environment:{isClient:()=>true,isJLCEDAProEdition:()=>true,getUserInfo:()=>({uuid:'user'})},
    dmt_Team:{getAllTeamsInfo:async()=>[{name:'个人',uuid:'personal-team'}]},
    dmt_Project:{getCurrentProjectInfo:async()=>current,openProject:async id=>{calls.push(['open',id]);current={uuid:id};return true;},waitForReady:async()=>true},
    dmt_Board:{getAllBoardsInfo:async()=>[{name:'source',parentProjectUuid:'new-project',pcb:{uuid:'source-pcb',name:'PCB'},schematic:{uuid:'source-sch',name:'SCH'}}]},
    sys_FileSystem:{readFileFromFileSystem:async path=>new File(['zip'],path.split('\\').pop())},
    sys_FileManager:{importProjectByProjectFile:async(file,type,props,destination)=>{calls.push(['import',type,props,destination]);return {uuid:'new-project',friendlyName:'Reference'};}}
  };
  const result=await runStandalone('import_reference_project',api,{source_path:'D:\\refs\\case.zip',file_type:'KiCad',project_slug:'rp2040-minimal',project_friendly_name:'RP2040 reference',destination:'new_user_project'});
  assert.equal(result.ok,true,JSON.stringify(result));assert.equal(result.destination,'new_user_project');assert.equal(result.cloud_upload,true);
  assert.deepEqual(result.boards,[{board_name:'source',pcb_uuid:'source-pcb',pcb_name:'PCB',schematic_uuid:'source-sch',schematic_name:'SCH'}]);
  assert.deepEqual(calls.map(item=>item[0]),['import','open']);
  assert.equal(calls[0][3].operation,'New Project');assert.equal(calls[0][3].newProjectName,'rp2040-minimal');
  assert.equal(calls[0][3].newProjectOwnerTeamUuid,'personal-team');
  assert.equal(calls[0][2].associateFootprint,true);
});
test('new Board action imports schematic components without cloning source geometry',async()=>{
  const calls=[],project={uuid:'project'},source={name:'reference',parentProjectUuid:'project',pcb:{uuid:'source-pcb',name:'source'},schematic:{uuid:'source-sch',name:'schematic'}};
  let board=null,focus=null;
  const component={getState_PrimitiveId:()=> 'c1'};
  const api={
    dmt_Project:{getCurrentProjectInfo:async()=>project,waitForReady:async()=>true},
    dmt_Board:{getAllBoardsInfo:async()=>board?[source,board]:[source],createBoard:async(schematic,pcb)=>{calls.push(['createBoard',schematic,pcb]);board={name:'layout',parentProjectUuid:'project',pcb:{uuid:pcb,name:'fresh'},schematic:{uuid:schematic,name:'schematic'}};return 'layout';}},
    dmt_Pcb:{createPcb:async()=>{calls.push(['createPcb']);return 'fresh-pcb';}},
    dmt_Schematic:{copySchematic:async sourceSchematic=>{calls.push(['copySchematic',sourceSchematic]);return 'layout-sch';},getAllSchematicsInfo:async()=>[{uuid:'source-sch',parentProjectUuid:'project'}]},
    dmt_EditorControl:{openDocument:async id=>{calls.push(['open',id]);focus=id;return 'tab';},activateDocument:async()=>true,waitForDocumentReady:async()=>true},
    dmt_SelectControl:{getCurrentDocumentInfo:async()=>({uuid:focus,parentProjectUuid:'project',documentType:3})},
    pcb_Document:{importChanges:async (...args)=>{calls.push(['importChanges',...args]);return true;}},
    pcb_PrimitiveComponent:{getAll:async()=>[component]},
    pcb_PrimitiveLine:{getAll:async()=>[]},pcb_PrimitiveVia:{getAll:async()=>[]},
    pcb_PrimitivePolyline:{getAll:async(net,layer)=>layer===11?[]:[]},pcb_Net:{getAllNetsName:async()=>['GND']}
  };
  const result=await runStandalone('create_board_from_schematic',api,{expected_project_uuid:'project',source_board_name:'reference',source_pcb_uuid:'source-pcb',schematic_uuid:'source-sch'});
  assert.equal(result.ok,true,JSON.stringify(result));assert.equal(result.pcb_uuid,'fresh-pcb');
  assert.equal(result.layout_copied,false);assert.equal(result.layout_ready_for_placement,true);assert.equal(result.source_board_still_present,true);
  assert.deepEqual(calls.map(item=>item[0]),['copySchematic','createPcb','createBoard','open','importChanges']);
  assert.deepEqual(calls[4],['importChanges','layout-sch']);
});
test('finite batch moves pads rigidly, draws inner-layer net trace and through via',async()=>{
  const f=fixture(),r=await f.apply([move,line,via]);
  assert.equal(r.ok,true);assert.equal(r.status,'completed');assert.equal(r.operation_count,3);
  assert.equal(r.drc_required,true);assert.equal(r.saved_to_native_project,false);
  assert.deepEqual(f.board.components[0].pads.map(p=>[p.id,p.x,p.y,p.net]),[['p1',195,300,'GND'],['p2',205,300,'GND']]);
  assert.equal(f.board.vias[0].viaType,0);assert.equal(r.source_sha256,sha(f.source()));
  assert.deepEqual(f.calls,['begin','move','line','via','commit']);
});
test('fresh-layout plan rotates schematic-derived components and adds an empty-layer outline',async()=>{
  const f=fixture(),r=await f.apply([place,outline]);
  assert.equal(r.ok,true,JSON.stringify(r));assert.equal(r.operation_count,2);
  assert.equal(f.board.components[0].rotation,0);
  assert.deepEqual(f.board.components[0].pads.map(p=>[Math.round(p.x),Math.round(p.y)]),[[200,305],[200,295]]);
  assert.equal(f.board.outlines.length,1);assert.equal(f.board.outlines[0].layer,11);
  assert.equal(f.board.outlines[0].polygon.getSource().length,11);
  assert.deepEqual(f.calls,['begin','move','outline','commit']);
});
test('closed outline readback accepts EDA-normalized reversed traversal',async()=>{
  const f=fixture(),create=f.api.pcb_PrimitivePolyline.create;
  f.api.pcb_PrimitivePolyline.create=async(...args)=>{
    const obj=await create(...args),source=args[2].getSource();
    const points=[[source[0],source[1]]];
    for(let index=3;index<source.length;index+=2)points.push([source[index],source[index+1]]);
    points.pop();
    const reversed=[points[0],...points.slice(1).reverse(),points[0]];
    f.board.outlines[0].polygon={getSource:()=>[reversed[0][0],reversed[0][1],'L',...reversed.slice(1).flat()]};
    return obj;
  };
  const r=await f.apply([outline]);
  assert.equal(r.ok,true,JSON.stringify(r));assert.equal(f.board.outlines.length,1);
  assert.equal(r.drc_required,true);
});
test('outline replacement changes geometry but preserves the exact primitive identity',async()=>{
  const f=fixture(),oldSource=[20,20,'L',80,20,80,80,20,80,20,20];
  f.board.outlines.push({id:'outline0',net:'',layer:11,width:2,polygon:oldSource});
  const r=await f.apply([replacementOutline]);
  assert.equal(r.ok,true,JSON.stringify(r));assert.equal(f.board.outlines.length,1);
  assert.deepEqual(f.board.outlines[0].polygon.getSource(),[0,0,'L',400,0,400,600,0,600,0,0]);
  assert.deepEqual(f.calls,['begin','outline-modify','commit']);
});
test('visual-only footprint batch resolves the exact library item and verifies physical pad numbers',async()=>{
  const f=fixture();f.board.components=[];
  const operation={kind:'footprint',library_uuid:'a'.repeat(32),footprint_uuid:'b'.repeat(16),designator:'U1',
    x:200,y:300,rotation:90,expected_pad_numbers:['1','2'],visual_only:true};
  const r=await f.apply([operation]);
  assert.equal(r.ok,true,JSON.stringify(r));assert.equal(r.visual_only_component_count,1);assert.equal(r.visual_only_no_device_or_net_binding,true);
  assert.equal(f.board.components[0].designator,'U1');assert.equal(f.board.components[0].device,undefined);
  assert.deepEqual(f.board.components[0].pads.map(pad=>pad.number),['1','2']);
  assert.ok(f.calls.indexOf('resolve-footprint') < f.calls.indexOf('begin'));
  assert.deepEqual(f.footprintLookups,[{uuid:'b'.repeat(16),libraryUuid:'a'.repeat(32)}]);
  assert.deepEqual(f.calls,['resolve-footprint','begin','footprint','move','commit']);
});
test('footprint lookup failure is diagnosed before opening a write group',async()=>{
  const f=fixture();f.board.components=[];
  f.api.lib_Footprint.get=async()=>{f.calls.push('resolve-footprint');throw {name:'Error',code:'LIBRARY_MISSING',message:{detail:'not found',token:'private'}};};
  const operation={kind:'footprint',library_uuid:'a'.repeat(32),footprint_uuid:'b'.repeat(16),designator:'U1',
    x:200,y:300,rotation:90,expected_pad_numbers:['1','2'],visual_only:true};
  const r=await f.apply([operation]);
  assert.equal(r.ok,false);assert.equal(r.stage,'resolve-footprint-U1');assert.equal(r.rollback,'not_needed');
  assert.match(r.reason,/LIBRARY_MISSING/);assert.match(r.reason,/detail/);assert.doesNotMatch(r.reason,/private/);
  assert.deepEqual(f.calls,['resolve-footprint']);
});
test('stale baseline prevents any geometry writes',async()=>{
  const f=fixture(),old=sha(f.source());f.board.components[0].x++;
  const r=await run('apply_drawing_batch',f.api,{operations:[move],plan_id:'a'.repeat(32),expected_source_sha256:old});
  assert.equal(r.ok,false);assert.deepEqual(f.calls,[]);
});
test('identity mismatch never touches the other document',async()=>{
  const f=fixture();f.focus.uuid='other';let read=false;
  f.api.sys_FileManager.getDocumentSource=async()=>{read=true;return f.source();};
  const r=await f.apply([move]);assert.equal(r.ok,false);assert.equal(read,false);assert.deepEqual(f.calls,[]);
});
for (const [label,change,ops] of [
  ['locked component',f=>f.board.components[0].locked=true,[move]],
  ['negative plane routing',f=>f.board.layers[1].type='PLANE',[line]],
  ['unused signal layer',f=>f.board.layers[1].layerStatus=0,[line]],
  ['unknown net',()=>{},[{...line,net:'UNDECLARED'}]],
  ['zero segment',()=>{},[{...line,x2:10,y2:20}]],
  ['nonfinite coordinate',()=>{},[{...move,x:NaN}]],
  ['duplicate moves',()=>{},[move,move]],
  ['outline over existing board outline',f=>{f.board.outlines.push({id:'old-outline',layer:11});},[outline]],
  ['outline self-intersection',()=>{},[{...outline,points:[[0,0],[400,600],[0,600],[400,0],[0,0]]}]],
  ['blind/unknown operation',()=>{},[{kind:'blind-via'}]],
])test(`preflight refuses ${label} before command group`,async()=>{
  const f=fixture();change(f);const r=await f.apply(ops);assert.equal(r.ok,false);assert.deepEqual(f.calls,[]);
});
test('mid-batch failure rolls back and verifies baseline source',async()=>{
  const f=fixture(),original=f.source();f.api.pcb_PrimitiveVia.create=async()=>{throw Error('fixture failure');};
  const r=await f.apply([move,via]);assert.equal(r.ok,false);assert.equal(r.rollback,'source_verified');assert.equal(f.source(),original);assert(!f.calls.includes('commit'));
});
test('physical net corruption in modify rejects and rolls back',async()=>{
  const f=fixture(),modify=f.api.pcb_PrimitiveComponent.modify;
  f.api.pcb_PrimitiveComponent.modify=async(...args)=>{const o=await modify(...args);f.board.components[0].pads[1].net='VCC';return o;};
  const r=await f.apply([move]);assert.equal(r.ok,false);assert.equal(r.rollback,'source_verified');
});
test('automatic line splitting cannot masquerade as exact readback',async()=>{
  const f=fixture(),create=f.api.pcb_PrimitiveLine.create;
  f.api.pcb_PrimitiveLine.create=async(...args)=>{const o=await create(...args);f.board.lines[0].x2--;return o;};
  const r=await f.apply([line]);assert.equal(r.ok,false);assert.equal(r.rollback,'source_verified');
});
test('focus drift after writing never rolls back the new focused board',async()=>{
  const f=fixture(),modify=f.api.pcb_PrimitiveComponent.modify;
  f.api.pcb_PrimitiveComponent.modify=async(...args)=>{const o=await modify(...args);f.focus.uuid='other';return o;};
  const r=await f.apply([move]);assert.equal(r.ok,false);assert.equal(r.recovery_required,true);assert.equal(r.rollback,'unverified');assert(!f.calls.includes('rollback'));
});
test('false rollback reports recovery required',async()=>{
  const f=fixture();f.api.pcb_PrimitiveVia.create=async()=>undefined;f.api.pcb_Document.rollbackCommandGroup=async()=>false;
  const r=await f.apply([move,via]);assert.equal(r.ok,false);assert.equal(r.recovery_required,true);
});
test('commit failure does not return completed',async()=>{
  const f=fixture();f.api.pcb_Document.commitCommandGroup=async()=>false;
  const r=await f.apply([move]);assert.equal(r.ok,false);assert.equal(r.rollback,'source_verified');
});
test('native export hashes bytes and saves only the bound unchanged document',async()=>{
  const f=fixture();let saved=0;
  f.api.sys_FileManager.getProjectFile=async()=>new File(['fixture archive'],'native.epro2');
  f.api.sys_FileSystem={saveFileToFileSystem:async(p,file)=>{saved++;assert.equal(p,'managed-output.epro2');assert.equal(await file.text(),'fixture archive');return true;}};
  const r=await run('export_drawing_copy',f.api,{expected_source_sha256:sha(f.source()),artifact_path:'managed-output.epro2'});
  assert.equal(r.ok,true);assert.equal(r.archive_sha256,sha('fixture archive'));assert.equal(saved,1);assert.equal(r.native_reopen_verified,false);
});
test('export aborts if source changes while native archive is generated',async()=>{
  const f=fixture();let saved=0;
  f.api.sys_FileManager.getProjectFile=async()=>{f.board.components[0].x++;return new File(['fixture'],'native.epro2');};
  f.api.sys_FileSystem={saveFileToFileSystem:async()=>{saved++;return true;}};
  const r=await run('export_drawing_copy',f.api,{expected_source_sha256:sha(f.source()),artifact_path:'managed-output.epro2'});
  assert.equal(r.ok,false);assert.equal(saved,0);
});
test('manufacturing export writes exact Gerber, BOM and metric pick-and-place files',async()=>{
  const f=fixture(),saved=new Map(),baseline=await run('drawing_state',f.api),sourceHash=baseline.semantic_source_sha256;
  const originalSource=f.source;
  f.api.pcb_ManufactureData={
    getGerberFile:async name=>{f.calls.push(['gerber',name]);const ordered=JSON.stringify(f.board);
      const reordered=JSON.stringify(Object.fromEntries(Object.entries(f.board).reverse()));
      f.source=()=>originalSource().replace(ordered,reordered);return new File(['gerber'],name+'.zip');},
    getBomFile:async(name,type)=>{f.calls.push(['bom',name,type]);return new File(['bom'],name+'.xlsx');},
    getPickAndPlaceFile:async(name,type,unit)=>{f.calls.push(['pnp',name,type,unit]);return new File(['pnp'],name+'.txt');}
  };
  f.api.sys_FileSystem={saveFileToFileSystem:async(path,file)=>{saved.set(path,new Uint8Array(await file.arrayBuffer()));return true;}};
  const directory=`C:\\pcb\\pcb-${'a'.repeat(32)}-${sourceHash.slice(0,16)}-${'b'.repeat(16)}`;
  const r=await run('export_manufacturing',f.api,{expected_source_sha256:sourceHash,artifact_directory:directory});
  assert.equal(r.ok,true,JSON.stringify(r));assert.equal(r.manufacturing_acceptance,false);assert.equal(r.files.length,3);
  assert.deepEqual([...saved.keys()],['C:\\pcb\\pcb-'+ 'a'.repeat(32)+'-'+sourceHash.slice(0,16)+'-'+'b'.repeat(16)+'\\Gerber.zip',
    'C:\\pcb\\pcb-'+'a'.repeat(32)+'-'+sourceHash.slice(0,16)+'-'+'b'.repeat(16)+'\\BOM.xlsx',
    'C:\\pcb\\pcb-'+'a'.repeat(32)+'-'+sourceHash.slice(0,16)+'-'+'b'.repeat(16)+'\\PickAndPlace.tsv']);
  assert.deepEqual(f.calls.map(call=>call[0]),['gerber','bom','pnp']);
  assert.deepEqual(f.calls[2].slice(2),['csv','mm']);
});
test('manufacturing export stops after a mid-export source change',async()=>{
  const f=fixture(),saved=[];let bomCalls=0;const baseline=await run('drawing_state',f.api),sourceHash=baseline.semantic_source_sha256;
  f.api.pcb_ManufactureData={
    getGerberFile:async name=>new File(['gerber'],name+'.zip'),
    getBomFile:async name=>{bomCalls++;f.board.components[0].x++;return new File(['bom'],name+'.xlsx');},
    getPickAndPlaceFile:async name=>new File(['pnp'],name+'.txt')
  };
  f.api.sys_FileSystem={saveFileToFileSystem:async path=>{saved.push(path);return true;}};
  const directory=`C:\\pcb\\pcb-${'a'.repeat(32)}-${sourceHash.slice(0,16)}-${'b'.repeat(16)}`;
  const r=await run('export_manufacturing',f.api,{expected_source_sha256:sourceHash,artifact_directory:directory});
  assert.equal(r.ok,false);assert.equal(r.status,'partial');assert.equal(bomCalls,1);assert.equal(saved.length,1);
  assert.equal(r.files[0].name,'Gerber.zip');
});
test('native router is explicit, preserves tracks and selects only enabled signal layers',async()=>{
  const f=fixture(),r=await run('start_auto_route',f.api,{routing_nets:['GND','VCC'],layers:[1,15],expected_source_sha256:sha(f.source())});
  assert.equal(r.ok,true,JSON.stringify(r));assert.equal(r.status,'started');assert.deepEqual(f.routeProps,{RoutingNets:['GND','VCC'],layers:[1,15],ignoreNets:[],cornerStyle:0,existingPrimitiveMode:'keep',optimization:1});
});
test('router rejects PLANE layers, unknown nets and stale source before starting',async()=>{
  const f=fixture();f.board.layers[1].type='PLANE';
  const plane=await run('start_auto_route',f.api,{routing_nets:['GND'],layers:[15],expected_source_sha256:sha(f.source())});
  assert.equal(plane.ok,false);assert(!f.calls.includes('route-start'));
  f.board.layers[1].type='SIGNAL';
  const unknown=await run('start_auto_route',f.api,{routing_nets:['unknown'],layers:[15],expected_source_sha256:sha(f.source())});
  assert.equal(unknown.ok,false);assert(!f.calls.includes('route-start'));
  const stale=await run('start_auto_route',f.api,{routing_nets:['GND'],layers:[15],expected_source_sha256:'0'.repeat(64)});
  assert.equal(stale.ok,false);assert(!f.calls.includes('route-start'));
});
test('router status reports terminal source digest and paginates all ratlines',async()=>{
  const f=fixture();f.jobStatus={jobId:'job-1',state:'completed',progress:100,partial:false};
  f.ratlines=Array.from({length:205},(_,i)=>({id:String(i)}));
  const r=await run('auto_route_status',f.api,{job_id:'job-1',expected_source_sha256:sha(f.source())});
  assert.equal(r.ok,true);assert.equal(r.unrouted_ratlines.total,205);assert.equal(r.unrouted_ratlines.pages,2);
  assert.equal(r.source_changed,false);assert.equal(r.requires_drc,true);
});
test('router status never calls ratline API while the engine is active',async()=>{
  const f=fixture();let pages=0;f.api.pcb_Document.getRatlines=async()=>{pages++;return {items:[],hasMore:false};};
  const r=await run('auto_route_status',f.api,{job_id:'job-1',expected_source_sha256:sha(f.source())});
  assert.equal(r.state,'running');assert.equal(r.unrouted_ratlines,null);assert.equal(pages,0);
});
test('router cancellation only requests cancellation of an active target job',async()=>{
  const f=fixture(),r=await run('cancel_auto_route',f.api,{job_id:'job-1'});
  assert.equal(r.cancel_requested,true);assert.match(r.limitation,/not a terminal state/);
  f.jobStatus.state='completed';const denied=await run('cancel_auto_route',f.api,{job_id:'job-1'});assert.equal(denied.ok,false);
});
