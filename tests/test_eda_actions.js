// Run the fixed action bodies in isolated AsyncFunction mocks. No live EDA calls.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ACTION_DIR = path.resolve(__dirname, "../tools/eda_actions");
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const NOW = 1_800_000_000_000;
class FixedDate extends Date { static now() { return NOW; } }

async function runAction(name, eda, args = {}, ClockDate = FixedDate) {
  const source = fs.readFileSync(path.join(ACTION_DIR, `${name}.js`), "utf8");
  if (name === "export_connectivity" && !args.artifact_path) args = {...args, artifact_path:"D:/PCB/local/eda-snapshots/test.netlist"};
  return new AsyncFunction("eda", "__CLI__", "Date", source)(eda, {args}, ClockDate);
}

const TARGET = Object.freeze({
  pcb_uuid: "pcb-target",
  expected_document_uuid: "pcb-target",
  expected_project_uuid: "project-target"
});

function pad(id, number = "1", net = "GND") {
  return {
    getState_PrimitiveId: () => id,
    getState_PadNumber: () => number,
    getState_Net: () => net,
    getState_X: () => 10,
    getState_Y: () => 20,
    getState_Layer: () => 1
  };
}

function component(id, pads) {
  return {
    getState_PrimitiveId: () => id,
    getState_Designator: () => "U1",
    getState_Footprint: () => ({uuid: "footprint-1"}),
    getState_X: () => 10,
    getState_Y: () => 20,
    getState_Layer: () => 1,
    getState_Rotation: () => 90,
    getAllPins: async () => pads
  };
}

function makeApi(options = {}) {
  const calls = {document: 0, project: 0, boards: 0, netlist: 0, netlistSave: 0, savedFiles:{}, components: 0, layers: 0, ratlines:0, freshDrc: 0, cachedDrc: 0};
  const state = {
    focus: {uuid: TARGET.pcb_uuid, parentProjectUuid: TARGET.expected_project_uuid, documentType: 3},
    boards: [{name: "Test Board", parentProjectUuid: TARGET.expected_project_uuid,
      pcb: {uuid: TARGET.pcb_uuid, name: "PCB"},
      schematic: {uuid: "sch-target", name: "SCH", page: [{uuid: "sch-page-1", name: "P1"}]}}],
    project: {uuid: TARGET.expected_project_uuid, friendlyName: "Test Project"},
    documentSource:JSON.stringify({type:"DOCHEAD",ticket:1,id:"0123456789abcdef"})+"||"+JSON.stringify({uuid:TARGET.pcb_uuid,docType:"PCB",updateTime:1,client:"test",version:"test"})+"|\n"+JSON.stringify({type:"NET",ticket:2,id:"fedcba9876543210"})+"||{}|",
    components: [component("component-1", [pad("physical-a", "1"), pad("physical-b", "1"), pad("physical-c", "2", "VCC")])],
    ratlines:[],
    drc: {state: "passed", totalCount: 0, failedItems: 0, violations: [], checkedAt: NOW + 1},
    drift: () => { state.focus = {...state.focus, uuid: "unrelated-document"}; }
  };
  const api = {
    sys_Environment: {
      getEditorCurrentVersion: () => "4.1.100",
      isClient: () => true,
      isJLCEDAProEdition: () => true
    },
    dmt_SelectControl: {getCurrentDocumentInfo: async () => { calls.document++; return {...state.focus}; }},
    dmt_Project: {getCurrentProjectInfo: async () => { calls.project++; return {...state.project}; }},
    dmt_Board: {getAllBoardsInfo: async () => { calls.boards++; return state.boards; }},
    dmt_Schematic: {getAllSchematicsInfo:async()=>[{uuid:"sch-target",name:"SCH",parentProjectUuid:TARGET.expected_project_uuid,page:[{uuid:"sch-page-1",name:"P1"}]}]},
    dmt_Pcb: {getAllPcbsInfo:async()=>[{uuid:TARGET.pcb_uuid,name:"PCB",parentProjectUuid:TARGET.expected_project_uuid,parentBoardName:"Test Board"}]},
    dmt_EditorControl: {openDocument:async id=>{calls.opened=id;return 'tab-pcb';},activateDocument:async id=>id==='tab-pcb',waitForDocumentReady:async id=>id==='tab-pcb'},
    sys_FileManager:{getDocumentSource:async()=>state.documentSource},
    sys_FileSystem:{saveFileToFileSystem:async(path,file)=>{calls.netlistSave++;calls.savedFiles[path]=new Uint8Array(await file.arrayBuffer());return true;}},
    pcb_ManufactureData: {getNetlistFile: async () => {
      calls.netlist++;
      return {name:"pcb.net",size:2,arrayBuffer:async()=>new TextEncoder().encode("{}").buffer};
    }},
    sch_ManufactureData: {getNetlistFile: async () => {
      calls.netlist++;
      return {name:"sch.net",size:2,arrayBuffer:async()=>new TextEncoder().encode("{}").buffer};
    }},
    pcb_PrimitiveComponent: {getAll: async () => { calls.components++; return state.components; }},
    pcb_Layer: {getAllLayers: async () => { calls.layers++; return [{id: 1, type: "TOP"}]; }},
    pcb_Document:{getRatlines:async({cursor,limit})=>{calls.ratlines++;const start=cursor?Number(cursor):0;const items=state.ratlines.slice(start,start+limit);const next=start+items.length;return {items,hasMore:next<state.ratlines.length,...(next<state.ratlines.length?{nextCursor:String(next)}:{})};}},
    pcb_Drc: {
      checkDetailed: async () => { calls.freshDrc++; return state.drc; },
      getDrcResult: async () => { calls.cachedDrc++; return state.drc; }
    }
  };
  Object.assign(state, options.state || {});
  return {api, calls, state};
}

function noCanvasReads(calls) {
  assert.equal(calls.netlist, 0);
  assert.equal(calls.components, 0);
  assert.equal(calls.layers, 0);
  assert.equal(calls.freshDrc, 0);
  assert.equal(calls.cachedDrc, 0);
}

test("inspect_environment reports observed capability without inventing a board pass", async () => {
  const {api} = makeApi();
  const result = await runAction("inspect_environment", api, TARGET);
  assert.equal(result.ok, true);
  assert.equal(result.version, "4.1.100");
  assert.equal(result.current_document.uuid, TARGET.pcb_uuid);
  assert.equal(result.capabilities["pcb_Drc.checkDetailed"], true);
  assert.equal(result.native_check_passed, undefined);
});

test("a mismatched focused target prevents canvas API reads", async () => {
  for (const action of ["inspect_project", "export_connectivity", "inspect_drc"]) {
    const {api, calls, state} = makeApi();
    state.drift();
    const result = await runAction(action, api, TARGET);
    assert.equal(result.ok, false, action);
    assert.equal(result.status, "target_mismatch", action);
    noCanvasReads(calls);
  }
});

test("a mismatched project prevents connectivity canvas reads", async () => {
  const {api, calls, state} = makeApi();
  state.focus.parentProjectUuid = "other-project";
  const result = await runAction("export_connectivity", api, TARGET);
  assert.equal(result.status, "target_mismatch");
  noCanvasReads(calls);
});

test("a nonmatching associated PCB is rejected before any canvas access", async () => {
  const {api, calls, state} = makeApi();
  state.boards[0].pcb.uuid = "other-pcb";
  const result = await runAction("export_connectivity", api, TARGET);
  assert.equal(result.status, "target_mismatch");
  noCanvasReads(calls);
});

test("project inspection discards data if focus changes after an asynchronous tree read", async () => {
  const {api, calls, state} = makeApi();
  api.dmt_Board.getAllBoardsInfo = async () => { calls.boards++; state.drift(); return state.boards; };
  const result = await runAction("inspect_project", api, TARGET);
  assert.equal(result.ok, false);
  assert.equal(result.status, "target_mismatch");
  noCanvasReads(calls);
});

test("project tree remains inspectable from project home with no focused canvas", async () => {
  const {api,state}=makeApi();state.focus=undefined;
  const result=await runAction("inspect_project",api,{});
  assert.equal(result.ok,true);
  assert.equal(result.current_document,null);
  assert.equal(result.project.uuid,TARGET.expected_project_uuid);
  assert.equal(result.boards[0].pcb.uuid,TARGET.pcb_uuid);
  assert.equal(result.pcbs[0].uuid,TARGET.pcb_uuid);
});

test("opening a project PCB checks project association before changing focus",async()=>{
  const {api,calls}=makeApi();
  const result=await runAction("open_project_pcb",api,{pcb_uuid:TARGET.pcb_uuid,expected_project_uuid:TARGET.expected_project_uuid});
  assert.equal(result.ok,true);assert.equal(result.read_only,true);assert.equal(calls.opened,TARGET.pcb_uuid);
  const {api:wrong,calls:wrongCalls,state}=makeApi();state.boards[0].pcb.uuid="other-pcb";
  const denied=await runAction("open_project_pcb",wrong,{pcb_uuid:TARGET.pcb_uuid,expected_project_uuid:TARGET.expected_project_uuid});
  assert.equal(denied.status,"target_mismatch");assert.equal(wrongCalls.opened,undefined);
});

test("ratline inspection pages the whole focused PCB and groups nets",async()=>{
  const {api,calls,state}=makeApi();state.ratlines=Array.from({length:205},(_,i)=>({primitiveId:"r"+i,net:i%2?"GND":"VCC",startId:"a",endId:"b",length:10}));
  const result=await runAction("inspect_ratlines",api,TARGET);
  assert.equal(result.ok,true);assert.equal(result.unrouted_total,205);assert.equal(result.page_count,2);assert.equal(calls.ratlines,2);
  assert.deepEqual(result.nets.map(n=>n.count),[102,103]);assert.equal(result.nets.every(n=>n.samples.length===3),true);
});

test("ratline inspection stops on focus drift between pages",async()=>{
  const {api,calls,state}=makeApi();state.ratlines=Array.from({length:205},(_,i)=>({primitiveId:"r"+i,net:"GND",startId:"a",endId:"b",length:10}));
  api.pcb_Document.getRatlines=async({cursor,limit})=>{calls.ratlines++;const start=cursor?Number(cursor):0;const items=state.ratlines.slice(start,start+limit);state.drift();return {items,hasMore:start+items.length<state.ratlines.length,nextCursor:String(start+items.length)};};
  const result=await runAction("inspect_ratlines",api,TARGET);
  assert.equal(result.status,"target_mismatch");assert.equal(calls.ratlines,1);
});

test("connectivity export rejects focus drift while waiting for Board identity", async () => {
  const {api, calls, state} = makeApi();
  api.dmt_Board.getAllBoardsInfo = async () => { calls.boards++; state.drift(); return state.boards; };
  const result = await runAction("export_connectivity", api, TARGET);
  assert.equal(result.status, "target_mismatch");
  noCanvasReads(calls);
});

test("connectivity export discards netlist if focus changes during asynchronous file buffer read", async () => {
  const {api, calls, state} = makeApi();
  api.pcb_ManufactureData.getNetlistFile = async () => {
    calls.netlist++;
    return {size: 2, arrayBuffer: async () => { state.drift(); return new TextEncoder().encode("{}").buffer; }};
  };
  const result = await runAction("export_connectivity", api, TARGET);
  assert.equal(result.ok, false);
  assert.equal(result.status, "target_mismatch");
  assert.equal(calls.components, 0);
  assert.equal(calls.layers, 0);
});

test("native netlist bytes are saved locally and only digest metadata is returned",async()=>{
  const {api,calls}=makeApi();
  const result=await runAction("export_connectivity",api,TARGET);
  assert.equal(result.ok,true);assert.equal(calls.netlistSave,1);
  assert.equal(result.native_netlist.bytes,2);assert.match(result.native_netlist.sha256,/^[0-9a-f]{64}$/);
  assert.deepEqual(Array.from(calls.savedFiles[result.native_netlist.artifact_path]),[123,125]);
  assert.equal(Object.hasOwn(result.native_netlist,"text"),false);
});

test("large native netlist is streamed as a local File without returning its text",async()=>{
  const {api,calls}=makeApi();const bytes=new Uint8Array(400*1024);bytes.fill(65);
  api.pcb_ManufactureData.getNetlistFile=async()=>({name:"large.net",size:bytes.length,arrayBuffer:async()=>bytes.buffer});
  const result=await runAction("export_connectivity",api,TARGET);
  assert.equal(result.ok,true);assert.equal(result.native_netlist.bytes,bytes.length);
  assert.equal(calls.netlistSave,1);assert.equal(Object.hasOwn(result.native_netlist,"text"),false);
  assert.equal(calls.savedFiles[result.native_netlist.artifact_path].length,bytes.length);
});

test("connectivity export discards the result when asynchronous physical-pad reads change focus", async () => {
  const {api, calls, state} = makeApi();
  state.components[0].getAllPins = async () => { state.drift(); return [pad("a", "1")]; };
  const result = await runAction("export_connectivity", api, TARGET);
  assert.equal(result.ok, false);
  assert.equal(result.status, "target_mismatch");
  assert.equal(calls.layers, 0, "Do not query a different canvas after the pad read changed focus.");
});

test("an empty component read that changes focus must not fall through to another canvas's layer API", async () => {
  const {api, calls, state} = makeApi();
  api.pcb_PrimitiveComponent.getAll = async () => { calls.components++; state.drift(); return []; };
  const result = await runAction("export_connectivity", api, TARGET);
  assert.equal(result.status, "target_mismatch");
  assert.equal(calls.layers, 0);
});

test("explicit zero pagination limit is rejected rather than converted into a default", async () => {
  const {api} = makeApi();
  const result = await runAction("export_connectivity", api, {...TARGET, limit: 0});
  assert.equal(result.ok, false);
  assert.equal(result.status, "rejected");
});

test("physical pad identities remain distinct when logical pad numbers repeat", async () => {
  const {api} = makeApi();
  const result = await runAction("export_connectivity", api, TARGET);
  assert.equal(result.ok, true);
  assert.equal(result.pads.length, 3);
  assert.deepEqual(result.pads.map(p => p.pad_number), ["1", "1", "2"]);
  assert.equal(new Set(result.pads.map(p => p.primitive_id)).size, 3);
  assert.equal(result.components[0].physical_pad_count, 3);
  assert.equal(result.pagination.selected_physical_pads, 3);
  assert.equal(result.layer_count_total,1);
  assert.deepEqual(result.layers,[{id:1,name:undefined,type:"TOP",layer_status:undefined,locked:undefined}]);
});

test("physical-pad pagination preserves every repeated-number physical object", async () => {
  const {api, state} = makeApi();
  const pads = Array.from({length: 105}, (_, i) => pad(`physical-${String(i).padStart(3, "0")}`, "57"));
  state.components = [component("component-1", pads)];
  const first = await runAction("export_connectivity", api, {...TARGET, pad_offset: 0});
  const last = await runAction("export_connectivity", api, {...TARGET, pad_offset: first.pagination.next_pad_offset});
  assert.equal(first.pads.length, 100);
  assert.equal(first.pagination.selected_physical_pads, 105);
  assert.equal(first.pagination.next_pad_offset, 100);
  assert.equal(last.pads.length, 5);
  assert.equal(last.pagination.next_pad_offset, null);
  const joined = [...first.pads, ...last.pads];
  assert.equal(new Set(joined.map(p => p.primitive_id)).size, 105);
  assert.equal(joined.every(p => p.pad_number === "57"), true);
});

test("cached DRC cannot pass even if its timestamp and state appear successful", async () => {
  const {api, calls} = makeApi();
  const result = await runAction("inspect_drc", api, {...TARGET, run: false});
  assert.equal(result.ok, true);
  assert.equal(result.run_requested, false);
  assert.equal(result.fresh_result, false);
  assert.equal(result.native_check_passed, false);
  assert.equal(calls.freshDrc, 0);
  assert.equal(calls.cachedDrc, 1);
});

test("a fresh complete native passed DRC can pass only its narrow native gate", async () => {
  const {api, calls} = makeApi();
  class AdvancingDate extends Date {
    static reads = 0;
    static now() { return NOW + Math.min(this.reads++, 1); }
  }
  const result = await runAction("inspect_drc", api, {...TARGET, run: true}, AdvancingDate);
  assert.equal(result.ok, true);
  assert.equal(result.fresh_result, true);
  assert.equal(result.native_check_passed, true);
  assert.equal(calls.freshDrc, 1);
  assert.equal(calls.cachedDrc, 0);
  assert.match(result.limitation, /not a schematic equivalence/);
});

for (const [label, override] of [
  ["failed items", {failedItems: 1}],
  ["incomplete state", {state: "incomplete"}],
  ["checking state", {state: "checking"}],
  ["not checked state", {state: "notChecked"}],
  ["failed state", {state: "failed"}],
  ["reported violations", {totalCount: 1, violations: [{rule: "clearance"}]}],
  ["same-millisecond equality", {checkedAt: NOW}],
  ["stale timestamp", {checkedAt: NOW - 1}],
  ["seconds timestamp", {checkedAt: Math.floor(NOW / 1000)}],
  ["far future timestamp", {checkedAt: NOW + 1001}],
  ["absent timestamp", {checkedAt: undefined}],
  ["unknown result schema", {totalCount: -1}]
]) {
  test(`DRC never passes ${label}`, async () => {
    const {api, state} = makeApi();
    Object.assign(state.drc, override);
    const result = await runAction("inspect_drc", api, {...TARGET, run: true});
    assert.equal(result.native_check_passed, false);
  });
}

test("a thrown native DRC is incomplete and cannot pass", async () => {
  const {api} = makeApi();
  api.pcb_Drc.checkDetailed = async () => { throw new Error("INCOMPLETE_RESULT"); };
  const result = await runAction("inspect_drc", api, {...TARGET, run: true});
  assert.equal(result.ok, false);
  assert.equal(result.status, "incomplete");
  assert.equal(result.native_check_passed, false);
});

test("focus drift after asynchronous DRC discards an otherwise passing result", async () => {
  const {api, state} = makeApi();
  api.pcb_Drc.checkDetailed = async () => { state.drift(); return state.drc; };
  const result = await runAction("inspect_drc", api, {...TARGET, run: true});
  assert.equal(result.ok, false);
  assert.equal(result.status, "target_mismatch");
  assert.equal(result.native_check_passed, false);
});

test("DRC cannot substitute cached results for an unavailable native detailed check", async () => {
  const {api, calls} = makeApi();
  delete api.pcb_Drc.checkDetailed;
  const result = await runAction("inspect_drc", api, {...TARGET, run: true});
  assert.equal(result.status, "unsupported");
  assert.equal(result.native_check_passed, false);
  assert.equal(calls.cachedDrc, 0);
});
