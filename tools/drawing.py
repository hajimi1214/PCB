"""Preview and apply finite edits only in a registered local native project copy.

No cloud project creation, raw JS input, production-file overwrite or router is
exposed. Evidence is private to local/drawing. Ambiguous attempts are not retried.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path, PureWindowsPath
import re
import shutil
import uuid
import zipfile
from manufacturing import ManufacturingError, validate_manufacturing_exports


class DrawingError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise DrawingError("Expected a locally generated copy/plan ID.")
    return value


def number(value):
    if type(value) not in {int, float} or not math.isfinite(value) or abs(value) > 1000000:
        raise DrawingError("All geometry must use finite mil values in +/-1000000.")
    return value


def validate_operations(operations, constraints, snapshot):
    if not isinstance(operations, list) or not 1 <= len(operations) <= 20:
        raise DrawingError("Prepare 1..20 operations per plan.")
    required = {"units", "source", "region", "min_trace_width", "min_hole", "min_annular_ring"}
    if not isinstance(constraints, dict) or set(constraints) != required or constraints["units"] != "mil":
        raise DrawingError("Supply explicit mil geometry limits and a source; no factory defaults are assumed.")
    if not isinstance(constraints["source"], str) or not constraints["source"].strip() or len(constraints["source"]) > 500:
        raise DrawingError("Constraint provenance is required (datasheet/factory/project reference).")
    region = constraints["region"]
    if not isinstance(region, list) or len(region) != 4:
        raise DrawingError("region must be [min_x,min_y,max_x,max_y] in mil.")
    xmin,ymin,xmax,ymax = map(number, region)
    if xmin >= xmax or ymin >= ymax:
        raise DrawingError("Invalid drawing region.")
    for k in ("min_trace_width", "min_hole", "min_annular_ring"):
        if number(constraints[k]) <= 0:
            raise DrawingError("Minimum geometry limits must be positive.")
    def inside(x,y,r=0):
        number(x);number(y)
        if not xmin+r <= x <= xmax-r or not ymin+r <= y <= ymax-r:
            raise DrawingError("Requested geometry exceeds the declared drawing region.")
    nets = snapshot["nets"]
    layers = {l["id"]:l for l in snapshot["layers"]}
    components = {c["id"]:c for c in snapshot["components"]}
    moved, unique = set(), set()
    schemas = {"move":{"kind","component_id","x","y"},
               "place":{"kind","component_id","x","y","rotation"},
               "footprint":{"kind","library_uuid","footprint_uuid","designator","x","y","rotation","expected_pad_numbers","visual_only"},
               "line":{"kind","net","layer","x1","y1","x2","y2","width"},
               "via":{"kind","net","x","y","hole","diameter"},
               "outline":{"kind","points","width"},
               "replace_outline":{"kind","primitive_id","points","width"}}
    for op in operations:
        if not isinstance(op, dict) or op.get("kind") not in schemas or set(op) != schemas[op["kind"]]:
            raise DrawingError("Only strict move/line/via operation objects are supported.")
        key = json.dumps(op,sort_keys=True,allow_nan=False)
        if key in unique:raise DrawingError("Duplicate operation in plan.")
        unique.add(key)
        if op["kind"]=="footprint":
            if (op["visual_only"] is not True or not re.fullmatch(r"[0-9a-f]{16,64}",op["library_uuid"]) or
                    not re.fullmatch(r"[0-9a-f]{16,64}",op["footprint_uuid"]) or
                    not isinstance(op["designator"],str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*",op["designator"]) or
                    not isinstance(op["expected_pad_numbers"],list) or len(op["expected_pad_numbers"])>300 or
                    any(not isinstance(pad,str) or not pad for pad in op["expected_pad_numbers"])):
                raise DrawingError("Visual-only footprint placement requires exact library identity, unique designator, and pad evidence.")
            if any(component.get("designator")==op["designator"] for component in snapshot["components"]):
                raise DrawingError("Footprint designator already exists on this PCB.")
            if op["designator"] in {item.get("designator") for item in operations if item is not op and item.get("kind")=="footprint"}:
                raise DrawingError("Visual-only footprint plan contains a duplicate designator.")
            if type(op["x"]) not in {int,float} or type(op["y"]) not in {int,float} or not 0<=op["rotation"]<360:
                raise DrawingError("Invalid visual-only footprint pose.")
            inside(op["x"],op["y"])
        elif op["kind"] in {"move","place"}:
            if not isinstance(op["component_id"], str):raise DrawingError("Component ID must be a string.")
            c = components.get(op["component_id"])
            if not c or c["locked"] is not False or c["id"] in moved:raise DrawingError("Unknown, locked or duplicate component.")
            layer = layers.get(c["layer"], {})
            component_side=layer.get("type") in {"TOP","BOTTOM"} or (c["layer"] in {1,2} and layer.get("type")=="SIGNAL")
            if not component_side or layer.get("locked") is not False or layer.get("layerStatus")==0:
                raise DrawingError("Component placement requires an enabled top/bottom copper layer.")
            inside(op["x"],op["y"])
            angle_delta=0
            if op["kind"]=="place":
                angle=number(op["rotation"])
                if not 0<=angle<360:raise DrawingError("Placement rotation must be in 0..359.999 degrees.")
                angle_delta=math.radians(angle-number(c["rotation"]))
            for p in c["pads"]:
                dx=p["x"]-c["x"];dy=p["y"]-c["y"]
                x=c["x"]+dx*math.cos(angle_delta)-dy*math.sin(angle_delta)
                y=c["y"]+dx*math.sin(angle_delta)+dy*math.cos(angle_delta)
                inside(x+op["x"]-c["x"],y+op["y"]-c["y"])
            moved.add(c["id"])
        else:
            if op["kind"] in {"outline","replace_outline"}:
                points=op["points"]
                if (not isinstance(points,list) or not 5<=len(points)<=64 or
                        any(not isinstance(point,list) or len(point)!=2 for point in points)):
                    raise DrawingError("Board outline must be a closed 4..63 segment polygon.")
                clean=[]
                for x,y in points:
                    number(x);number(y);inside(x,y);clean.append((x,y))
                if clean[0]!=clean[-1] or any(clean[i]==clean[i+1] for i in range(len(clean)-1)):
                    raise DrawingError("Board outline must close explicitly and contain no zero-length segment.")
                area=sum(clean[i][0]*clean[i+1][1]-clean[i+1][0]*clean[i][1] for i in range(len(clean)-1))
                if abs(area)<1e-6:raise DrawingError("Board outline area must be nonzero.")
                if len(set(clean[:-1]))<4:raise DrawingError("Board outline requires at least four distinct vertices.")
                for i in range(len(clean)-1):
                    for j in range(i+1,len(clean)-1):
                        if j in {i,i+1} or (i==0 and j==len(clean)-2):continue
                        a,b=clean[i],clean[i+1];c,d=clean[j],clean[j+1]
                        orient=lambda p,q,r:(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
                        on=lambda p,q,r: min(p[0],q[0])-1e-8<=r[0]<=max(p[0],q[0])+1e-8 and min(p[1],q[1])-1e-8<=r[1]<=max(p[1],q[1])+1e-8
                        o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
                        if (o1*o2<0 and o3*o4<0 or
                                abs(o1)<1e-8 and on(a,b,c) or abs(o2)<1e-8 and on(a,b,d) or
                                abs(o3)<1e-8 and on(c,d,a) or abs(o4)<1e-8 and on(c,d,b)):
                            raise DrawingError("Board outline self-intersects.")
                outline_layer=snapshot.get("outline_layer")
                outlines=snapshot.get("outline_primitive_ids")
                expected_outline_ids = [] if op["kind"]=="outline" else [op["primitive_id"]]
                if (not isinstance(outline_layer,dict) or outline_layer.get("id")!=11 or outline_layer.get("locked") is not False or
                        outline_layer.get("layerStatus")==0 or outlines is None or outlines!=expected_outline_ids):
                    raise DrawingError("Board outline identity does not match the exact create/replace baseline.")
                width=number(op["width"])
                if not 0.1<=width<=10:raise DrawingError("Board-outline stroke width must be between 0.1 and 10 mil.")
                continue
            if not isinstance(op["net"], str) or not op["net"] or op["net"] not in nets:
                raise DrawingError("Use a literal existing PCB net; never invent a net during routing.")
            if op["kind"] == "line":
                if type(op["layer"]) is not int:raise DrawingError("Layer must be an integer ID.")
                l = layers.get(op["layer"], {})
                if l.get("type") != "SIGNAL" or l.get("layerStatus") not in (1,2) or l.get("locked") is not False:
                    raise DrawingError("Lines require an enabled, unlocked signal copper layer.")
                w = number(op["width"])
                if w < constraints["min_trace_width"]:raise DrawingError("Trace is below declared width limit.")
                inside(op["x1"],op["y1"],w/2);inside(op["x2"],op["y2"],w/2)
                if op["x1"]==op["x2"] and op["y1"]==op["y2"]:raise DrawingError("Zero length line.")
            else:
                h,d = number(op["hole"]),number(op["diameter"])
                if h < constraints["min_hole"] or (d-h)/2 < constraints["min_annular_ring"]:
                    raise DrawingError("Via violates declared drill or annular ring limit.")
                inside(op["x"],op["y"],d/2)
    return operations


class DrawingService:
    def __init__(self, root, client=None):
        self.root = Path(root).resolve()
        self.base = self.safe(self.root / "local" / "drawing")
        if client is None:
            spec = importlib.util.spec_from_file_location("pcb_drawing_transport", self.root/"tools"/"eda_client.py")
            module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            client = module.EdaClient(timeout=25,allow_drawing=True,allow_drc_run=True,action_dir=self.root/"tools"/"eda_actions")
        self.client = client

    def safe(self, path):
        path = Path(path)
        if not path.is_absolute():path = self.root/path
        if not path.is_relative_to(self.root):raise DrawingError("Path must stay in the PCB repository.")
        for node in [path, *path.parents]:
            if node == self.root:break
            if node.is_symlink() or getattr(node,"is_junction",lambda:False)():raise DrawingError("Links/junctions are not allowed.")
        if not path.resolve().is_relative_to(self.root):raise DrawingError("Path escapes repository.")
        return path

    def write(self,path,obj):
        path=self.safe(path);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("x",encoding="utf-8") as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)

    def rewrite(self,path,obj):
        path=self.safe(path)
        if not path.is_file():raise DrawingError("The local evidence record to update is absent.")
        temporary=self.safe(path.with_name(path.name+f".{uuid.uuid4().hex}.next"))
        with temporary.open("x",encoding="utf-8") as stream:json.dump(obj,stream,ensure_ascii=False,indent=2,allow_nan=False)
        temporary.replace(path)

    def load(self,path):
        path=self.safe(path)
        if path.stat().st_size>2000000:raise DrawingError("Evidence exceeds bounded size.")
        return json.loads(path.read_text(encoding="utf-8"))

    def copy_project(self, relative_path):
        if not isinstance(relative_path,str) or PureWindowsPath(relative_path).drive or Path(relative_path).is_absolute() or ".." in relative_path.replace("\\","/").split("/"):
            raise DrawingError("Native project path must be repository-relative.")
        src=self.safe(self.root/relative_path)
        if src.suffix.lower()==".epro2":
            return {"status":"needs_native_project","reason":"epro2 is an import archive. Export a local .eprj2 or .eprj3 project from EDA first; this tool never renames archives or creates a cloud project."}
        if not src.is_file() or src.suffix.lower() not in {".eprj2",".eprj3"}:
            raise DrawingError("Select a native .eprj2 file or .eprj3 index file.")
        folder = src.parent if src.suffix.lower()==".eprj3" else None
        if folder == self.root or (folder and self.base.is_relative_to(folder)):
            raise DrawingError("Folder projects must have a dedicated directory inside this repository.")
        if folder and len(list(folder.glob("*.eprj3"))) != 1:
            raise DrawingError("Select a dedicated directory with exactly one native project index.")
        if not folder and any(Path(str(src)+suffix).exists() for suffix in ("-wal","-shm","-journal")):
            raise DrawingError("Native database has active journal files; save and close it before copying.")
        paths=[]
        pending=[folder] if folder else []
        if not folder:paths=[src]
        while pending:
            current=self.safe(pending.pop())
            for item in sorted(current.iterdir()):
                self.safe(item)
                if item.is_dir():pending.append(item)
                else:paths.append(item)
                if len(paths)+len(pending)>5000:raise DrawingError("Native project tree exceeds copy limit.")
        files=[];total=0
        for p in paths:
            self.safe(p)
            if p.is_file():
                total+=p.stat().st_size;files.append(p)
                if len(files)>5000 or total>80*1024*1024:raise DrawingError("Native project exceeds copy limit.")
        cid=uuid.uuid4().hex;dest=self.safe(self.base/"copies"/cid)
        original={}
        for p in files:
            rel=p.relative_to(folder) if folder else Path(p.name)
            before=p.read_bytes();original[rel.as_posix()]=digest(before)
            target=self.safe(dest/rel);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as f:f.write(before)
            if digest(p.read_bytes())!=original[rel.as_posix()]:raise DrawingError("Original changed during copy; copied snapshot not opened.")
        for p in files:
            rel=p.relative_to(folder) if folder else Path(p.name)
            if digest(p.read_bytes())!=original[rel.as_posix()]:raise DrawingError("Original changed during snapshot; copied project not opened.")
        if not folder and any(Path(str(src)+suffix).exists() for suffix in ("-wal","-shm","-journal")):
            raise DrawingError("Native database journal appeared while copying; copied project not opened.")
        entry=dest/src.name
        record={"copy_id":cid,"path":str(entry),"original_hashes":original,"original_path":relative_path}
        result=self.client._run_cli(["open","--path",str(entry),"--headless","true"],"open_working_copy")
        value=result.get("value")
        if result.get("status")!="ok" or not isinstance(value,dict) or not value.get("sessionId"):
            self.write(self.base/"copies"/f"{cid}.failed.json",record)
            return {"status":"unavailable","copy_id":cid,"copy_path":entry.relative_to(self.root).as_posix(),"reason":"Native copy created, but EDA session opening was not confirmed. No automatic retry."}
        record["session_id"]=value["sessionId"]
        self.write(self.base/"copies"/f"{cid}.json",record)
        self.bound(record)
        project=self.invoke(record,"focus_working_copy",{})
        record["project_uuid"]=project["project_uuid"]
        self.write(self.base/"copies"/f"{cid}.identity.json",{"project_uuid":record["project_uuid"]})
        return {"status":"copy_opened","copy_id":cid,"session_id":record["session_id"],"path":entry.relative_to(self.root).as_posix(),"original_unchanged":True}

    def import_reference_project(self,session_id,source_path,project_slug,file_type):
        if not isinstance(session_id,str) or not session_id:raise DrawingError("An explicit CLI session is required.")
        if not isinstance(project_slug,str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,47}",project_slug):
            raise DrawingError("Reference project slug must be a short lowercase name.")
        source=self.safe(self.root/source_path)
        source_root=self.safe(self.root/"local"/"board-challenges"/"sources")
        reference_root=self.safe(self.base/"references")
        valid_suffixes={"KiCad":{".zip"},"EAGLE":{".brd",".zip"}}
        if not source.is_relative_to(source_root) or source.suffix.lower() not in valid_suffixes.get(file_type,set()) or not source.is_file():
            raise DrawingError("Import a staged KiCad ZIP or an EAGLE BRD/ZIP from local/board-challenges/sources.")
        if type(source.stat().st_size) is not int or not 0<source.stat().st_size<=100*1024*1024:
            raise DrawingError("Reference ZIP is empty or exceeds the 100 MiB import limit.")
        if file_type not in {"KiCad","EAGLE"}:
            raise DrawingError("Only KiCad and EAGLE project packages are supported for reference import.")
        sessions=self.client.list_sessions().get("sessions",[])
        live=[item for item in sessions if item.get("session_id")==session_id and item.get("backend")=="cli" and item.get("status")=="alive"]
        if len(live)!=1:raise DrawingError("Reference import requires one exact live native CLI session.")
        session_check=self.client.invoke_script("inspect_project",session_id,{},backend="cli")
        session_value=session_check.get("value")
        blank=(isinstance(session_value,dict) and session_value.get("status")=="unavailable" and
               session_value.get("reason")=="No current project is selected in EDA.")
        if not blank:
            raise DrawingError("Reference import must use a blank EDA project session.")
        reference_root.mkdir(parents=True,exist_ok=True)
        for project_record_path in reference_root.glob("*.json"):
            if not project_record_path.is_file():continue
            previous=self.load(project_record_path)
            if previous.get("project_slug")==project_slug and previous.get("workspace_kind")=="imported_reference_project":
                raise DrawingError("This reference project slug already has an imported project registration.")
        for previous_attempt in reference_root.glob("*.attempt.json"):
            attempt_record=self.load(previous_attempt)
            if attempt_record.get("project_slug")!=project_slug:continue
            previous_result=self.safe(reference_root/previous_attempt.name.replace(".attempt.json",".result.json"))
            if not previous_result.is_file():raise DrawingError("A prior import has no result receipt; project creation may have succeeded.")
            receipt=self.load(previous_result)
            if receipt.get("source_project_may_exist") is not False:
                raise DrawingError("A prior import may have created a cloud project; do not retry it automatically.")
            lookup=self.client.invoke_script("inspect_project_by_slug",session_id,{"project_slug":project_slug},backend="cli")
            observed=lookup.get("value")
            if not isinstance(observed,dict) or observed.get("ok") is not True or observed.get("absence_confirmed") is not True:
                raise DrawingError("Could not verify absence of the prior project; do not retry import.")
            receipt["retry_gate_lookup"]={"project_slug":project_slug,"exact_match_count":observed.get("exact_match_count"),
                                          "absence_confirmed":True}
            temporary=previous_result.with_suffix(".next.json")
            temporary.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
            temporary.replace(previous_result)
        cid=uuid.uuid4().hex
        attempt=self.safe(reference_root/f"{cid}.attempt.json")
        friendly_name=f"PCB visual reference - {project_slug}"
        imported=None
        try:
            self.write(attempt,{"status":"started","project_slug":project_slug,"source_path":source.relative_to(self.root).as_posix(),
                                "source_sha256":digest(source.read_bytes()),"file_type":file_type,
                                "destination":"new_user_project","public_source":True})
            result=self.client.invoke_script("import_reference_project",session_id,{
                "source_path":str(source),"project_slug":project_slug,"project_friendly_name":friendly_name,
                "file_type":file_type,"destination":"new_user_project"},backend="cli")
            imported=result.get("value")
            if not isinstance(imported,dict) or imported.get("ok") is not True:
                reason=imported.get("reason") if isinstance(imported,dict) else result.get("reason") or result.get("status")
                raise DrawingError("EDA reference import failed: "+str(reason))
            boards=imported.get("boards")
            if not isinstance(boards,list) or len(boards)!=1:
                raise DrawingError("Imported reference must contain exactly one Board for this visual test.")
            board=boards[0]
            if any(not isinstance(board.get(key),str) or not board[key] for key in ("board_name","pcb_uuid","schematic_uuid")):
                raise DrawingError("Imported reference Board identity is incomplete.")
            record={"copy_id":cid,"workspace_kind":"imported_reference_project","status":"reference_project_imported",
                "project_slug":project_slug,"session_id":session_id,"project_uuid":imported.get("project_uuid"),
                "source_path":source.relative_to(self.root).as_posix(),"source_sha256":digest(source.read_bytes()),
                "file_type":file_type,"source_board_name":board["board_name"],"source_pcb_uuid":board["pcb_uuid"],
                "source_schematic_uuid":board["schematic_uuid"],"pcb_uuid":None,"schematic_uuid":board["schematic_uuid"],
                "project_friendly_name":imported.get("friendly_name"),"destination":"new_user_project",
                "layout_ready_for_placement":False,"source_files_are_public":True}
            if not isinstance(record["project_uuid"],str) or not record["project_uuid"]:
                raise DrawingError("EDA did not return the new user project UUID.")
            self.write(self.safe(reference_root/f"{cid}.json"),record)
            self.write(self.safe(reference_root/f"{cid}.result.json"),record)
            return {key:value for key,value in record.items() if key!="session_id"}
        except Exception as exc:
            receipt={"status":"recovery_required","project_slug":project_slug,"source_path":source.relative_to(self.root).as_posix(),
                "error_type":type(exc).__name__,"reason":str(exc)[:400],
                "destination":"new_user_project","source_project_may_exist":isinstance(imported,dict) and bool(imported.get("project_uuid")),
                "files_present":[]}
            result_path=self.safe(reference_root/f"{cid}.result.json")
            if not result_path.exists():self.write(result_path,receipt)
            if isinstance(exc,DrawingError):raise
            raise DrawingError("Reference import outcome is uncertain; inspect its local result record before retrying.") from exc

    def create_board_from_schematic(self,copy_id,source_board_name,source_pcb_uuid,schematic_uuid):
        cid=identity(copy_id);record=self._copy_record(cid)
        if record.get("workspace_kind")=="gui_test_copy":
            raise DrawingError("Fresh-layout creation is restricted to a managed local native-project copy.")
        if any(not isinstance(value,str) or not value for value in (source_board_name,source_pcb_uuid,schematic_uuid)):
            raise DrawingError("Select one exact source Board, PCB UUID, and schematic UUID.")
        project_uuid=record.get("project_uuid")
        if not project_uuid:
            identity_path=self.safe(self.base/"copies"/f"{cid}.identity.json")
            if not identity_path.is_file():raise DrawingError("Working-copy project identity is not recorded.")
            project_uuid=self.load(identity_path).get("project_uuid")
        if not isinstance(project_uuid,str) or not project_uuid:
            raise DrawingError("Working-copy project identity is invalid.")
        if record.get("workspace_kind")=="imported_reference_project" and (
                record.get("source_board_name")!=source_board_name or
                record.get("source_pcb_uuid")!=source_pcb_uuid or
                record.get("source_schematic_uuid")!=schematic_uuid):
            raise DrawingError("Source Board identity differs from the imported reference project registration.")
        creation_id=uuid.uuid4().hex;root=self.safe(self.base/"board-creations");root.mkdir(parents=True,exist_ok=True)
        attempt=self.safe(root/f"{creation_id}.attempt.json")
        self.write(attempt,{"creation_id":creation_id,"copy_id":cid,"project_uuid":project_uuid,
            "source_board_name":source_board_name,"source_pcb_uuid":source_pcb_uuid,"schematic_uuid":schematic_uuid})
        try:
            value=self.invoke(record,"create_board_from_schematic",{
                "expected_project_uuid":project_uuid,"source_board_name":source_board_name,
                "source_pcb_uuid":source_pcb_uuid,"schematic_uuid":schematic_uuid})
            result={**value,"creation_id":creation_id,"copy_id":cid,"source_board_name":source_board_name,
                "source_pcb_uuid":source_pcb_uuid,"project_uuid":project_uuid}
            if value.get("ok") is True and record.get("workspace_kind")=="imported_reference_project":
                record["layout_board_name"]=value.get("board_name")
                record["pcb_uuid"]=value.get("pcb_uuid")
                record["layout_schematic_uuid"]=value.get("schematic_uuid")
                record["layout_ready_for_placement"]=value.get("layout_ready_for_placement") is True
                record["source_board_still_present"]=value.get("source_board_still_present") is True
                self.rewrite(self.base/"references"/f"{cid}.json",record)
            self.write(self.safe(root/f"{creation_id}.result.json"),result)
            if value.get("ok") is not True:
                raise DrawingError("Fresh PCB creation did not fully import schematic components: "+str(value.get("reason")))
            return result
        except Exception as exc:
            result_path=self.safe(root/f"{creation_id}.result.json")
            if not result_path.exists():
                self.write(result_path,{"status":"recovery_required","creation_id":creation_id,"copy_id":cid,
                    "project_uuid":project_uuid,"source_board_name":source_board_name,"source_pcb_uuid":source_pcb_uuid,
                    "schematic_uuid":schematic_uuid,"error_type":type(exc).__name__,"reason":str(exc)[:400]})
            if isinstance(exc,DrawingError):raise
            raise DrawingError("New Board creation outcome is uncertain; inspect its result record before retrying.") from exc

    def initialize_layout_board(self,copy_id,source_board_name,source_pcb_uuid,source_schematic_uuid,
                                layout_board_name,layout_pcb_uuid,layout_schematic_uuid):
        cid=identity(copy_id);record=self._copy_record(cid)
        if record.get("workspace_kind")!="imported_reference_project":
            raise DrawingError("Fresh schematic import is restricted to a registered open-source reference project.")
        if (record.get("source_board_name")!=source_board_name or record.get("source_pcb_uuid")!=source_pcb_uuid or
                record.get("source_schematic_uuid")!=source_schematic_uuid or
                not isinstance(layout_pcb_uuid,str) or layout_pcb_uuid==source_pcb_uuid or
                not isinstance(layout_schematic_uuid,str)):
            raise DrawingError("Layout Board identities do not match the registered source and PCB copy.")
        project_uuid=record.get("project_uuid")
        result=self.invoke(record,"initialize_layout_board",{
            "expected_project_uuid":project_uuid,"source_board_name":source_board_name,"source_pcb_uuid":source_pcb_uuid,
            "source_schematic_uuid":source_schematic_uuid,"layout_board_name":layout_board_name,
            "layout_pcb_uuid":layout_pcb_uuid,"layout_schematic_uuid":layout_schematic_uuid})
        if result.get("ok") is not True:
            raise DrawingError("Fresh Board initialization did not pass: "+str(result.get("reason")))
        if (result.get("source_board_still_present") is not True or result.get("layout_copied") is not False or
                result.get("layout_ready_for_placement") is not True):
            raise DrawingError("Fresh Board verification did not prove independent placement geometry.")
        record.update({"pcb_uuid":layout_pcb_uuid,"layout_board_name":layout_board_name,
            "layout_schematic_uuid":layout_schematic_uuid,"layout_ready_for_placement":True,
            "source_board_association_intact":result.get("source_board_association_intact") is True,
            "fresh_board_metrics":{key:result.get(key) for key in ("component_count","net_count","existing_track_count","existing_via_count","existing_outline_count")}})
        self.rewrite(self.base/"references"/f"{cid}.json",record)
        return {"copy_id":cid,**result}

    def associate_reference_layout_board(self,copy_id,source_board_name,source_pcb_uuid,source_schematic_uuid,
                                         layout_pcb_uuid,layout_schematic_uuid):
        cid=identity(copy_id);record=self._copy_record(cid)
        if record.get("workspace_kind")!="imported_reference_project":
            raise DrawingError("Orphan-board recovery is restricted to a registered open-source reference project.")
        if (record.get("source_board_name")!=source_board_name or record.get("source_pcb_uuid")!=source_pcb_uuid or
                record.get("source_schematic_uuid")!=source_schematic_uuid or layout_pcb_uuid==source_pcb_uuid or
                not isinstance(layout_schematic_uuid,str) or not layout_schematic_uuid):
            raise DrawingError("Orphan PCB/schematic identities do not match the registered reference.")
        result=self.invoke(record,"associate_reference_layout_board",{
            "expected_project_uuid":record["project_uuid"],"source_board_name":source_board_name,
            "source_pcb_uuid":source_pcb_uuid,"source_schematic_uuid":source_schematic_uuid,
            "layout_pcb_uuid":layout_pcb_uuid,"layout_schematic_uuid":layout_schematic_uuid})
        if result.get("ok") is not True or result.get("layout_ready_for_placement") is not True:
            raise DrawingError("Orphan PCB could not be safely associated and initialized from the schematic: "+str(result.get("reason")))
        record.update({"pcb_uuid":layout_pcb_uuid,"layout_board_name":result.get("layout_board_name"),
            "layout_schematic_uuid":layout_schematic_uuid,"layout_ready_for_placement":True,
            "source_board_still_present":result.get("source_board_still_present") is True,
            "source_board_association_intact":result.get("source_board_association_intact") is True,
            "fresh_board_metrics":{key:result.get(key) for key in ("component_count","net_count","existing_track_count","existing_via_count","existing_outline_count")}})
        self.rewrite(self.base/"references"/f"{cid}.json",record)
        return {"copy_id":cid,**result}

    def register_visual_layout_target(self,copy_id,source_board_name,source_pcb_uuid,layout_board_name,layout_pcb_uuid):
        cid=identity(copy_id);record=self._copy_record(cid)
        if record.get("workspace_kind")!="imported_reference_project":
            raise DrawingError("Visual target registration requires an imported public reference project.")
        if (record.get("source_board_name")!=source_board_name or record.get("source_pcb_uuid")!=source_pcb_uuid or
                layout_pcb_uuid==source_pcb_uuid):
            raise DrawingError("Visual target identifiers do not match the registered reference project.")
        value=self.invoke(record,"register_visual_layout_target",{
            "expected_project_uuid":record["project_uuid"],"source_board_name":source_board_name,
            "source_pcb_uuid":source_pcb_uuid,"layout_board_name":layout_board_name,"layout_pcb_uuid":layout_pcb_uuid})
        if (value.get("ok") is not True or value.get("component_count")!=0 or value.get("track_count")!=0 or
                value.get("via_count")!=0 or value.get("outline_count")!=0):
            raise DrawingError("Target PCB is not a verified blank visual layout surface.")
        record.update({"pcb_uuid":layout_pcb_uuid,"layout_board_name":layout_board_name,
            "layout_schematic_uuid":value.get("layout_schematic_uuid"),"layout_ready_for_placement":True,
            "layout_mode":"visual-only-footprints","schematic_linked_devices":False,
            "source_board_still_present":True,"source_board_association_intact":value.get("source_board_schematic_uuid")==record.get("source_schematic_uuid")})
        self.rewrite(self.base/"references"/f"{cid}.json",record)
        return {"copy_id":cid,**value}

    def create_gui_pcb_copy(self,session_id,expected_project_uuid,source_pcb_uuid):
        sessions=self.client.list_sessions()
        live=[s for s in sessions.get("sessions",[]) if s.get("session_id")==session_id and s.get("backend")=="cli" and s.get("origin")=="user" and s.get("status")=="alive"]
        if len(live)!=1:raise DrawingError("A single live user GUI session is required for the test PCB copy.")
        cid=uuid.uuid4().hex
        result=self.client.invoke_script("create_gui_pcb_copy",session_id,
            {"expected_project_uuid":expected_project_uuid,"source_pcb_uuid":source_pcb_uuid},backend="cli")
        value=result.get("value",{})
        if not isinstance(value,dict) or value.get("ok") is not True or value.get("project_uuid")!=expected_project_uuid or value.get("source_pcb_uuid")!=source_pcb_uuid:
            raise DrawingError("EDA did not confirm the new test PCB copy; inspect the live project tree before retrying.")
        record={"copy_id":cid,"workspace_kind":"gui_test_copy","session_id":session_id,
                "project_uuid":expected_project_uuid,"source_pcb_uuid":source_pcb_uuid,
                "pcb_uuid":value["copy_pcb_uuid"],"pcb_name":value.get("copy_pcb_name"),
                "source_board_name":value["source_board_name"],"source_schematic_uuid":value["source_schematic_uuid"],
                "copy_board_name":value["copy_board_name"],"schematic_uuid":value["copy_schematic_uuid"],
                "parent_board_name":value.get("parent_board_name"),"status":"active","cleanup_required":True}
        self.write(self.base/"gui-copies"/f"{cid}.json",record)
        return {"status":"test_copy_created","copy_id":cid,"source_pcb_uuid":source_pcb_uuid,
                "copy_pcb_uuid":record["pcb_uuid"],"copy_pcb_name":record["pcb_name"],"cleanup_required":True}

    def _copy_record(self,copy_id):
        cid=identity(copy_id)
        for path in (self.base/"copies"/f"{cid}.json",self.base/"gui-copies"/f"{cid}.json",
                     self.base/"references"/f"{cid}.json"):
            if path.is_file():
                record=self.load(path)
                if record.get("copy_id")!=cid:raise DrawingError("Registered copy identity mismatch.")
                return record
        raise DrawingError("No managed working copy has this ID.")

    def cleanup_gui_pcb_copy(self,copy_id):
        cid=identity(copy_id);record=self._copy_record(cid)
        if record.get("workspace_kind")!="gui_test_copy":raise DrawingError("This copy was not created as a GUI PCB test clone.")
        receipt=self.base/"gui-copies"/f"{cid}.cleanup.json"
        if receipt.exists():return self.load(receipt)
        for path in (self.base/"routes").glob("*.json"):
            plan=self.load(path)
            if plan.get("copy_id")==cid and path.name.endswith(".json"):
                job=self.base/"routes"/f"{plan.get('plan_id')}.job.json"
                if job.exists() and self.load(job).get("state") in {"queued","running"}:
                    raise DrawingError("A route job is still active on the test PCB copy.")
        self.bound(record)
        result=self.client.invoke_script("delete_gui_pcb_copy",record["session_id"],{
            "expected_project_uuid":record["project_uuid"],"source_pcb_uuid":record["source_pcb_uuid"],
            "source_schematic_uuid":record["source_schematic_uuid"],"copy_board_name":record["copy_board_name"],
            "copy_pcb_uuid":record["pcb_uuid"],"copy_schematic_uuid":record["schematic_uuid"]},backend="cli")
        value=result.get("value",{})
        if (not isinstance(value,dict) or value.get("ok") is not True or value.get("cleanup_verified") is not True or
                value.get("source_pcb_still_present") is not True or value.get("source_schematic_still_present") is not True):
            raise DrawingError("EDA could not verify cleanup of the registered test PCB copy.")
        receipt_value={"status":"cleanup_verified","copy_id":cid,"result":value}
        self.write(receipt,receipt_value)
        return receipt_value

    def bound(self, record):
        if record.get("workspace_kind")=="imported_reference_project":
            sessions=self.client.list_sessions().get("sessions",[])
            live=[item for item in sessions if item.get("session_id")==record.get("session_id") and
                  item.get("backend")=="cli" and item.get("status")=="alive"]
            if len(live)!=1:raise DrawingError("The imported reference project EDA session is not available.")
            result=self.client.invoke_script("focus_working_copy",record["session_id"],{},backend="cli")
            value=result.get("value")
            if not isinstance(value,dict) or value.get("ok") is not True or value.get("project_uuid")!=record.get("project_uuid"):
                raise DrawingError("The active project differs from the registered imported reference project.")
            return
        if record.get("workspace_kind")=="gui_test_copy":
            result=self.client.list_sessions();rows=result.get("sessions")
            live=[x for x in rows or [] if x.get("session_id")==record.get("session_id") and x.get("backend")=="cli" and x.get("origin")=="user" and x.get("status")=="alive"]
            if len(live)!=1:raise DrawingError("The registered live GUI session is not available.")
            if not re.fullmatch(r"[0-9a-f]{16,64}",record.get("pcb_uuid","")) or record.get("pcb_uuid")==record.get("source_pcb_uuid"):
                raise DrawingError("The GUI test-copy identity is invalid.")
            return
        expected=self.safe(Path(record["path"]))
        if not expected.is_relative_to(self.base/"copies"/record["copy_id"]):raise DrawingError("Unregistered copy path.")
        result=self.client._run_cli(["session","list"],"verify_copy_session")
        rows=result.get("value")
        if result.get("status")!="ok" or not isinstance(rows,list):raise DrawingError("Cannot verify copy session.")
        matches=[x for x in rows if x.get("sessionId")==record["session_id"] and x.get("status")=="alive" and x.get("origin")=="cli" and isinstance(x.get("path"),str) and Path(x["path"]).resolve()==expected.resolve()]
        if len(matches)!=1:raise DrawingError("Session does not match the live registered native copy.")

    def invoke(self,record,action,args):
        self.bound(record)
        result=self.client.invoke_script(action,record["session_id"],args,backend="cli")
        value=result.get("value")
        if not isinstance(value,dict) or value.get("ok") is not True:
            raise DrawingError("Fixed EDA action did not succeed: "+str(value.get("reason") if isinstance(value,dict) else result.get("status")))
        return value

    def project_identity(self,record):
        value=self.invoke(record,"focus_working_copy",{})
        if record.get("workspace_kind")=="gui_test_copy" and value.get("project_uuid")!=record.get("project_uuid"):
            raise DrawingError("Live session has switched away from the registered project.")
        return value

    def prepare(self,copy_id,pcb_uuid,operations,constraints):
        cid=identity(copy_id)
        if not isinstance(pcb_uuid,str) or not 1<=len(pcb_uuid)<=256:raise DrawingError("Explicit PCB UUID required.")
        record=self._copy_record(cid)
        if record.get("workspace_kind")=="imported_reference_project" and (
                record.get("layout_ready_for_placement") is not True or record.get("pcb_uuid")!=pcb_uuid):
            raise DrawingError("Imported-reference visual prototypes must use the specifically registered blank target PCB UUID.")
        project={"project_uuid":record.get("project_uuid")}
        if not project["project_uuid"]:project=self.load(self.base/"copies"/f"{cid}.identity.json")
        env=self.invoke(record,"inspect_environment",{})
        capabilities=env.get("capabilities",{})
        needed={"sys_FileManager.getDocumentSource","pcb_Document.beginCommandGroup","pcb_Document.commitCommandGroup",
                "pcb_Document.rollbackCommandGroup"}
        for op in operations if isinstance(operations,list) else []:
            if isinstance(op,dict) and op.get("kind")=="move":needed.update({"pcb_PrimitiveComponent.modify","pcb_PrimitiveComponent.get"})
            if isinstance(op,dict) and op.get("kind")=="place":needed.update({"pcb_PrimitiveComponent.modify","pcb_PrimitiveComponent.get","sys_Math.rotate"})
            if isinstance(op,dict) and op.get("kind")=="footprint":needed.update({"lib_Footprint.get","pcb_PrimitiveComponent.create","pcb_PrimitiveComponent.modify","pcb_PrimitiveComponent.get"})
            if isinstance(op,dict) and op.get("kind")=="line":needed.update({"pcb_PrimitiveLine.create","pcb_PrimitiveLine.get"})
            if isinstance(op,dict) and op.get("kind")=="via":needed.update({"pcb_PrimitiveVia.create","pcb_PrimitiveVia.get"})
            if isinstance(op,dict) and op.get("kind")=="outline":needed.update({"pcb_MathPolygon.createPolygon","pcb_PrimitivePolyline.create","pcb_PrimitivePolyline.get","pcb_PrimitivePolyline.getAll"})
            if isinstance(op,dict) and op.get("kind")=="replace_outline":needed.update({"pcb_MathPolygon.createPolygon","pcb_PrimitivePolyline.modify","pcb_PrimitivePolyline.get","pcb_PrimitivePolyline.getAll"})
        absent=sorted(method for method in needed if capabilities.get(method) is not True)
        if absent:raise DrawingError("This EDA version lacks required drawing APIs: "+", ".join(absent))
        args={"pcb_uuid":pcb_uuid,"expected_project_uuid":project["project_uuid"]}
        self.invoke(record,"focus_working_copy",args)
        snapshot=self.invoke(record,"drawing_state",args)
        if digest(snapshot["source"].encode())!=snapshot["source_sha256"]:raise DrawingError("Snapshot digest mismatch.")
        validate_operations(operations,constraints,snapshot)
        pid=uuid.uuid4().hex
        plan={"plan_id":pid,"copy_id":cid,"target":args,"operations":operations,"constraints":constraints,"baseline":snapshot}
        self.write(self.base/"plans"/f"{pid}.json",plan)
        raw=json.dumps(plan,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()
        self.write(self.base/"plans"/f"{pid}.sha256.json",{"sha256":digest(raw)})
        return {"status":"prepared","plan_id":pid,"copy_id":cid,"baseline_sha256":snapshot["source_sha256"],
                "operations":operations,"constraints":constraints,"backup":f"local/drawing/plans/{pid}.json",
                "checks":["existing net IDs","unlocked signal layers","finite mil geometry","declared limits","duplicate operations"],
                "not_checked":["actual board outline/keepouts","clearances/obstacles","impedance/current","DRC","schematic equivalence"],
                "design_writes":False}

    def apply(self,plan_id):
        pid=identity(plan_id);plan=self.load(self.base/"plans"/f"{pid}.json")
        integrity=self.load(self.base/"plans"/f"{pid}.sha256.json")
        if digest(json.dumps(plan,ensure_ascii=False,sort_keys=True,allow_nan=False).encode())!=integrity["sha256"]:
            raise DrawingError("Saved plan changed; prepare a new plan.")
        receipt=self.base/"plans"/f"{pid}.result.json"
        if receipt.exists():return self.load(receipt)
        record=self._copy_record(plan['copy_id'])
        self.bound(record)
        validate_operations(plan["operations"],plan["constraints"],plan["baseline"])
        # Exclusive attempt file survives crashes/timeouts. Replays never issue another write.
        attempt=self.safe(self.base/"plans"/f"{pid}.attempt.json")
        if attempt.exists():return {"status":"recovery_required","plan_id":pid,"reason":"A previous write attempt has an unknown outcome; inspect the copy and baseline before making a new plan."}
        self.write(attempt,{"plan_id":pid,"copy_id":plan["copy_id"]})
        args={**plan["target"],"expected_source_sha256":plan["baseline"]["source_sha256"],"plan_id":pid,"operations":plan["operations"]}
        result=self.client.invoke_script("apply_drawing_batch",record["session_id"],args,backend="cli")
        value=result.get("value")
        if not isinstance(value,dict):value={"ok":False,"status":"recovery_required","reason":"No complete result; do not retry automatically."}
        if value.get("ok") is True:
            post=value.get("source")
            if not isinstance(post,str) or digest(post.encode())!=value.get("source_sha256"):
                value={"ok":False,"status":"recovery_required","reason":"Post-write snapshot did not validate."}
            else:
                self.write(self.base/"plans"/f"{pid}.after.json",{"source":post,"sha256":value["source_sha256"]})
                value={k:v for k,v in value.items() if k!="source"}
        final={**value,"plan_id":pid,"copy_id":plan["copy_id"],"baseline_backup":f"local/drawing/plans/{pid}.json"}
        self.write(receipt,final)
        return final

    def export(self,plan_id):
        pid=identity(plan_id)
        plan=self.load(self.base/"plans"/f"{pid}.json")
        result=self.load(self.base/"plans"/f"{pid}.result.json")
        if result.get("ok") is not True or not re.fullmatch(r"[0-9a-f]{64}",result.get("source_sha256","")):
            raise DrawingError("Only a verified applied plan can be exported.")
        record=self._copy_record(plan['copy_id'])
        path=self.safe(self.base/"exports"/f"{pid}-{uuid.uuid4().hex}.epro2")
        path.parent.mkdir(parents=True,exist_ok=True)
        observed=self.invoke(record,"export_drawing_copy",{**plan["target"],"expected_source_sha256":result["source_sha256"],"artifact_path":str(path)})
        if not path.is_file() or not 0<path.stat().st_size<=80*1024*1024:raise DrawingError("Export not present on disk within size limit.")
        if digest(path.read_bytes())!=observed.get("archive_sha256") or path.stat().st_size!=observed.get("bytes"):
            raise DrawingError("Disk export differs from native export digest.")
        with zipfile.ZipFile(path) as archive:
            entries=archive.infolist()
            if len(entries)>10000 or sum(i.file_size for i in entries)>200*1024*1024 or any(i.flag_bits&1 for i in entries):
                raise DrawingError("Export is encrypted or exceeds archive inspection limits.")
            if archive.testzip() is not None:raise DrawingError("Export failed ZIP CRC check.")
            if not any(i.filename.endswith('.epru') for i in entries):raise DrawingError("Export has no native project stream.")
        evidence={"status":"exported","plan_id":pid,"path":path.relative_to(self.root).as_posix(),
                  "sha256":observed["archive_sha256"],"bytes":observed["bytes"],"zip_crc_verified":True,
                  "native_reopen_verified":False,"drc_required":True}
        self.write(path.with_suffix('.evidence.json'),evidence)
        return evidence

    def preview_routing(self,copy_id,pcb_uuid,routing_nets,layers):
        cid=identity(copy_id)
        if not isinstance(pcb_uuid,str) or not 1<=len(pcb_uuid)<=256:raise DrawingError("Explicit PCB UUID required.")
        if not isinstance(routing_nets,list) or not 1<=len(routing_nets)<=64 or any(not isinstance(n,str) or not n for n in routing_nets):
            raise DrawingError("Select 1..64 literal existing network names.")
        if len(set(routing_nets))!=len(routing_nets):raise DrawingError("Routing network list contains duplicates.")
        if not isinstance(layers,list) or not 1<=len(layers)<=8 or any(type(v) is not int for v in layers):
            raise DrawingError("Select 1..8 signal layer IDs.")
        if len(set(layers))!=len(layers):raise DrawingError("Routing layer list contains duplicates.")
        record=self._copy_record(cid)
        project={"project_uuid":record.get("project_uuid")}
        if not project["project_uuid"]:project=self.load(self.base/"copies"/f"{cid}.identity.json")
        env=self.invoke(record,"inspect_environment",{})
        capabilities=env.get("capabilities",{})
        required={"pcb_Document.startAutoRouting","pcb_Document.getAutoJobStatus","pcb_Document.cancelAutoJob",
                  "pcb_Document.getAutoJobLog","pcb_Document.getRatlines"}
        absent=sorted(method for method in required if capabilities.get(method) is not True)
        if absent:raise DrawingError("This EDA version lacks native router job APIs: "+", ".join(absent))
        target={"pcb_uuid":pcb_uuid,"expected_project_uuid":project["project_uuid"]}
        self.invoke(record,"focus_working_copy",target)
        snap=self.invoke(record,"drawing_state",target)
        names=set(snap.get("nets",[]));layer_map={l["id"]:l for l in snap.get("layers",[])}
        if any(n not in names for n in routing_nets):raise DrawingError("Routing preview references an absent net.")
        for layer in layers:
            item=layer_map.get(layer,{})
            if item.get("type")!="SIGNAL" or item.get("layerStatus") not in (1,2) or item.get("locked") is not False:
                raise DrawingError("Routing preview includes a disabled, locked or non-SIGNAL layer.")
        pid=uuid.uuid4().hex
        plan={"plan_id":pid,"copy_id":cid,"target":target,"routing_nets":routing_nets,"layers":layers,
              "baseline_source_sha256":snap["source_sha256"],"baseline_source":snap["source"],"rules_snapshot":snap["layers"],
              "strategy":{"engine":"JLCEDA native startAutoRouting","corner":"45deg","existing":"keep","optimization":"completion"},
              "status":"previewed"}
        self.write(self.base/"routes"/f"{pid}.json",plan)
        raw=json.dumps(plan,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()
        self.write(self.base/"routes"/f"{pid}.sha256.json",{"sha256":digest(raw)})
        return {"status":"previewed","route_plan_id":pid,"copy_id":cid,"pcb_uuid":pcb_uuid,
                "routing_nets":routing_nets,"layers":layers,"baseline_sha256":snap["source_sha256"],
                "strategy":plan["strategy"],"writes_started":False,
                "not_checked":["obstacle avoidance in the native engine","routing constraints beyond saved EDA rules","DRC","schematic equivalence","impedance/SI/PI"]}

    def _routing_plan(self,plan_id):
        pid=identity(plan_id);path=self.base/"routes"/f"{pid}.json";plan=self.load(path)
        checksum=self.load(self.base/"routes"/f"{pid}.sha256.json")
        raw=json.dumps(plan,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()
        if checksum.get("sha256")!=digest(raw):raise DrawingError("Saved routing preview changed; prepare it again.")
        record=self._copy_record(plan['copy_id'])
        return pid,plan,record

    def start_routing(self,plan_id):
        pid,plan,record=self._routing_plan(plan_id);job_file=self.base/"routes"/f"{pid}.job.json"
        if job_file.exists():return self.load(job_file)
        attempt=self.safe(self.base/"routes"/f"{pid}.attempt.json")
        if attempt.exists():return {"status":"recovery_required","route_plan_id":pid,"reason":"Previous start outcome is unknown. Do not retry this route plan."}
        self.bound(record)
        current=self.invoke(record,"drawing_state",plan["target"])
        if current.get("source_sha256")!=plan["baseline_source_sha256"]:
            raise DrawingError("PCB changed since routing preview; prepare a new route plan.")
        self.write(attempt,{"route_plan_id":pid,"copy_id":plan["copy_id"]})
        args={**plan["target"],"expected_source_sha256":plan["baseline_source_sha256"],
              "routing_nets":plan["routing_nets"],"layers":plan["layers"]}
        try:result=self.client.invoke_script("start_auto_route",record["session_id"],args,backend="cli")
        except Exception:
            return {"status":"recovery_required","route_plan_id":pid,"reason":"No complete start response. Inspect the copy and session before proceeding."}
        value=result.get("value")
        if not isinstance(value,dict) or value.get("ok") is not True or not isinstance(value.get("job_id"),str):
            state={"status":"recovery_required","route_plan_id":pid,"reason":"Router start result is ambiguous. Do not retry automatically."}
        else:
            state={"status":"started","route_plan_id":pid,"copy_id":plan["copy_id"],"job_id":value["job_id"],
                   "pcb_uuid":plan["target"]["pcb_uuid"],"project_uuid":plan["target"]["expected_project_uuid"],
                   "baseline_source_sha256":plan["baseline_source_sha256"],"state":"queued"}
        self.write(job_file,state)
        return state

    def route_status(self,plan_id):
        pid,plan,record=self._routing_plan(plan_id);path=self.base/"routes"/f"{pid}.job.json";job=self.load(path)
        if not isinstance(job.get("job_id"),str):return {"status":"recovery_required","route_plan_id":pid,"reason":"No verified native job ID."}
        result=self.invoke(record,"auto_route_status",{**plan["target"],"expected_source_sha256":plan["baseline_source_sha256"],"job_id":job["job_id"]})
        state=result.get("state")
        if state not in {"queued","running","completed","canceled","failed"}:
            raise DrawingError("Native routing job state is unsupported.")
        updated={**job,"state":state,"progress_percent":result.get("progress_percent"),
                 "partial":result.get("partial"),"error":result.get("error"),
                 "source_sha256":result.get("source_sha256"),"source_changed":result.get("source_changed"),
                 "unrouted_ratlines":result.get("unrouted_ratlines"),"router_progress":result.get("router_progress"),
                 "requires_drc":True}
        tmp=self.safe(self.base/"routes"/f"{pid}.job.next.json");tmp.write_text(json.dumps(updated,ensure_ascii=False,indent=2),encoding="utf-8")
        tmp.replace(path)
        return {**updated,"completion_is_design_pass":False,"native_drc_completed":False}

    def cancel_routing(self,plan_id):
        pid,plan,record=self._routing_plan(plan_id);job=self.load(self.base/"routes"/f"{pid}.job.json")
        if job.get("state") not in {"queued","running"} or not isinstance(job.get("job_id"),str):
            raise DrawingError("Only a recorded queued/running job can be canceled.")
        value=self.invoke(record,"cancel_auto_route",{**plan["target"],"job_id":job["job_id"]})
        if value.get("cancel_requested") is not True:raise DrawingError("Native engine did not accept the cancellation request.")
        result={"status":"cancel_requested","route_plan_id":pid,"job_id":job["job_id"],"terminal_state_verified":False}
        self.write(self.base/"routes"/f"{pid}.cancel.json",result)
        return result

    def export_route(self,plan_id):
        pid,plan,record=self._routing_plan(plan_id);job=self.load(self.base/"routes"/f"{pid}.job.json")
        if job.get("state")!="completed" or job.get("partial") is True or not re.fullmatch(r"[0-9a-f]{64}",job.get("source_sha256","")):
            raise DrawingError("Only a completed router job with verified post-route source can be exported.")
        # Route-generated geometry is a native EDA result. Reuse the archive check with the router's source digest.
        path=self.safe(self.base/"exports"/f"route-{pid}-{uuid.uuid4().hex}.epro2");path.parent.mkdir(parents=True,exist_ok=True)
        args={**plan["target"],"expected_source_sha256":job["source_sha256"],"artifact_path":str(path)}
        observed=self.invoke(record,"export_drawing_copy",args)
        if (not path.is_file() or not 0<path.stat().st_size<=80*1024*1024 or
                path.stat().st_size!=observed.get("bytes") or digest(path.read_bytes())!=observed.get("archive_sha256")):
            raise DrawingError("Router archive export failed its disk hash check.")
        with zipfile.ZipFile(path) as archive:
            entries=archive.infolist()
            if len(entries)>10000 or sum(i.file_size for i in entries)>200*1024*1024 or any(i.flag_bits&1 for i in entries) or archive.testzip():
                raise DrawingError("Router archive is encrypted or failed bounded ZIP validation.")
            if not any(i.filename.endswith(".epru") for i in entries):raise DrawingError("Router archive lacks its native project stream.")
        receipt={"status":"exported","route_plan_id":pid,"path":path.relative_to(self.root).as_posix(),
                 "sha256":observed["archive_sha256"],"bytes":observed["bytes"],"native_reopen_verified":False,
                 "unrouted_ratlines":job.get("unrouted_ratlines"),"drc_required":True}
        self.write(path.with_suffix(".evidence.json"),receipt)
        return receipt

    def export_manufacturing(self,copy_id,pcb_uuid):
        cid=identity(copy_id);record=self._copy_record(cid)
        registered_pcb=record.get("pcb_uuid");project_uuid=record.get("project_uuid")
        if registered_pcb and registered_pcb!=pcb_uuid:
            raise DrawingError("Requested PCB UUID differs from the registered copy identity.")
        if not isinstance(pcb_uuid,str) or not pcb_uuid or pcb_uuid==record.get("source_pcb_uuid"):
            raise DrawingError("Manufacturing export requires a registered non-source PCB copy.")
        if not project_uuid:
            identity_path=self.safe(self.base/"copies"/f"{cid}.identity.json")
            if not identity_path.is_file():raise DrawingError("Working-copy project identity is not recorded.")
            project_uuid=self.load(identity_path).get("project_uuid")
        if not isinstance(project_uuid,str) or not project_uuid:
            raise DrawingError("Working-copy project identity is invalid.")
        target={"pcb_uuid":pcb_uuid,"expected_project_uuid":project_uuid}
        self.invoke(record,"open_project_pcb",target)
        before=self.invoke(record,"drawing_state",target)
        source_sha=before.get("semantic_source_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}",source_sha or ""):
            raise DrawingError("The target PCB source digest could not be verified.")
        raw_source_sha=before.get("source_sha256")
        drc=self.invoke(record,"inspect_drc",{**target,"expected_document_uuid":pcb_uuid,"run":True})
        ratlines=self.invoke(record,"inspect_ratlines",{**target,"expected_document_uuid":pcb_uuid})
        after=self.invoke(record,"drawing_state",target)
        if after.get("semantic_source_sha256")!=source_sha:
            raise DrawingError("The PCB changed while DRC and unrouted connections were checked.")
        layers=after.get("layers")
        copper_count=sum(1 for layer in layers if isinstance(layer,dict) and layer.get("type") in {"TOP","BOTTOM","SIGNAL","PLANE"}
                         and layer.get("layerStatus")!=0) if isinstance(layers,list) else 0
        export_root=self.safe(self.base/"exports")
        export_root.mkdir(parents=True,exist_ok=True)
        preflight={
            "copy_id":cid,"pcb_uuid":pcb_uuid,"project_uuid":project_uuid,"source_sha256":source_sha,
            "source_hash_basis":"canonical JSON record values with object-key order normalized",
            "raw_source_sha256_before_drc":raw_source_sha,"raw_source_sha256_after_drc":after.get("source_sha256"),
            "drc":{key:drc.get(key) for key in ("fresh_result","native_check_passed","state","total_count","failed_items","checked_at")},
            "unrouted_ratlines":ratlines.get("unrouted_total"),"enabled_copper_layers":copper_count,
        }
        drc_passed=drc.get("fresh_result") is True and drc.get("native_check_passed") is True
        routes_complete=ratlines.get("unrouted_total")==0 and ratlines.get("routing_complete") is True
        if not drc_passed or not routes_complete:
            blocked={"status":"blocked","copy_id":cid,"preflight":preflight,
                     "manufacturing_files_exported":False,"reason":"A fresh zero-violation DRC and zero ratlines are required."}
            return blocked
        if copper_count!=4:
            raise DrawingError("The manufacturing export gate requires a four-copper-layer PCB.")
        prefix=f"pcb-{cid}-{source_sha[:16]}-"
        for previous in export_root.glob(prefix+"*"):
            previous=self.safe(previous)
            previous_manifest=previous/"manifest.json"
            if previous_manifest.is_file():
                manifest=self.load(previous_manifest)
                if manifest.get("source_sha256")!=source_sha:continue
                try:validate_manufacturing_exports(previous,copper_count)
                except ManufacturingError as exc:raise DrawingError("Existing manufacturing export no longer validates.") from exc
                for item in manifest.get("files",[]):
                    path=self.safe(previous/item["name"])
                    if not path.is_file() or path.stat().st_size!=item.get("bytes") or digest(path.read_bytes())!=item.get("sha256"):
                        raise DrawingError("Existing manufacturing file differs from its recorded digest.")
                return manifest
            if (previous/"attempt.json").is_file():
                result_path=previous/"result.json"
                if not result_path.is_file():
                    raise DrawingError("A prior manufacturing export has an unknown outcome; inspect its attempt directory.")
                prior=self.load(result_path)
                present=prior.get("files_present")
                allowed={"attempt.json","preflight.json","result.json"}
                actual={path.name for path in previous.iterdir()}
                if (prior.get("status")!="recovery_required" or not isinstance(present,list) or
                        set(present)!=allowed or actual!=allowed):
                    raise DrawingError("A prior manufacturing attempt may have written output; inspect its recorded files before continuing.")
        directory=self.safe(export_root/f"{prefix}{uuid.uuid4().hex[:16]}")
        directory.mkdir()
        self.write(directory/"preflight.json",preflight)
        manifest_path=directory/"manifest.json"
        attempt_path=directory/"attempt.json"
        self.write(attempt_path,{"status":"started","copy_id":cid,"pcb_uuid":pcb_uuid,"source_sha256":source_sha})
        args={**target,"expected_source_sha256":source_sha,"artifact_directory":str(directory)}
        try:
            self.bound(record)
            response=self.client.invoke_script("export_manufacturing",record["session_id"],args,backend="cli")
            observed=response.get("value")
            if not isinstance(observed,dict) or observed.get("ok") is not True:
                reason=observed.get("reason") if isinstance(observed,dict) else response.get("status")
                raise DrawingError("EDA manufacturing export did not complete: "+str(reason))
            if observed.get("source_sha256")!=source_sha or observed.get("pcb_uuid")!=pcb_uuid or observed.get("project_uuid")!=project_uuid:
                raise DrawingError("EDA manufacturing export identity or source digest changed.")
            expected={"gerber":"Gerber.zip","bom":"BOM.xlsx","pick_and_place":"PickAndPlace.tsv"}
            rows=observed.get("files")
            if not isinstance(rows,list) or len(rows)!=len(expected):raise DrawingError("EDA returned an incomplete manufacturing file list.")
            observed_by_kind={row.get("kind"):row for row in rows if isinstance(row,dict)}
            if set(observed_by_kind)!=set(expected):raise DrawingError("EDA returned an unexpected manufacturing file set.")
            files=[]
            for kind,name in expected.items():
                row=observed_by_kind[kind];path=self.safe(directory/name)
                if row.get("name")!=name or not re.fullmatch(r"[0-9a-f]{64}",row.get("sha256","")):
                    raise DrawingError("EDA manufacturing file metadata is malformed.")
                if path.is_symlink() or not path.is_file() or path.stat().st_size!=row.get("bytes") or digest(path.read_bytes())!=row["sha256"]:
                    raise DrawingError("EDA manufacturing file failed disk size/SHA-256 verification.")
                files.append({"kind":kind,"name":name,"bytes":row["bytes"],"sha256":row["sha256"]})
            try:validation=validate_manufacturing_exports(directory,copper_count)
            except ManufacturingError as exc:raise DrawingError("Manufacturing outputs failed structural validation: "+str(exc)) from exc
            final=self.invoke(record,"drawing_state",target)
            if final.get("semantic_source_sha256")!=source_sha:
                raise DrawingError("PCB changed during manufacturing export; discard these files.")
            manifest={"status":"manufacturing_files_exported","copy_id":cid,"pcb_uuid":pcb_uuid,
                "project_uuid":project_uuid,"source_sha256":source_sha,"preflight":preflight,"files":files,
                "source_hash_basis":"canonical JSON record values with object-key order normalized",
                "raw_source_sha256_before_drc":raw_source_sha,"raw_source_sha256_after_export":final.get("source_sha256"),
                "source_serialization_changed":raw_source_sha!=final.get("source_sha256"),
                "file_validation":validation,"gerber_profile":observed.get("gerber_profile"),
                "manufacturing_acceptance":False,"native_reopen_verified":False,
                "independent_cam_review_required":True,"functional_board_tested":False}
            self.write(manifest_path,manifest)
            return manifest
        except Exception as exc:
            result_path=directory/"result.json"
            if not result_path.exists():
                self.write(result_path,{"status":"recovery_required","copy_id":cid,"pcb_uuid":pcb_uuid,
                    "source_sha256":source_sha,"error_type":type(exc).__name__,"reason":str(exc)[:500],
                    "files_present":[path.name for path in directory.iterdir() if path.is_file()]})
            if isinstance(exc,DrawingError):raise
            raise DrawingError("Manufacturing export outcome is uncertain; inspect its result.json before retrying.") from exc
