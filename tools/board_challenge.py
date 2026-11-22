#!/usr/bin/env python3
"""Extract visual PCB targets from licensed KiCad/EAGLE examples for local trials."""
from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
CASES=ROOT/"research"/"cases"/"snapshots"
OUT=ROOT/"local"/"board-challenges"/"analysis"


def _tokens(text):
    pattern=re.compile(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+)')
    for match in pattern.finditer(text):
        token=match.group(1)
        if token.startswith('"'):
            token=json.loads(token)
        yield token


def read_sexpr(path):
    stack=[];root=None
    with path.open("r",encoding="utf-8",errors="strict") as stream:
        text=stream.read()
    for token in _tokens(text):
        if token=="(":
            node=[]
            if stack:stack[-1].append(node)
            else:
                if root is not None:raise ValueError("multiple root expressions")
                root=node
            stack.append(node)
        elif token==")":
            if not stack:raise ValueError("unbalanced S-expression close")
            stack.pop()
        else:
            if not stack:raise ValueError("S-expression atom outside root")
            stack[-1].append(token)
    if stack or not root:raise ValueError("incomplete S-expression")
    return root


def children(node,key):
    return [item for item in node if isinstance(item,list) and item and item[0]==key]


def first(node,key):
    return next(iter(children(node,key)),None)


def _float(value):
    try:return float(value)
    except (TypeError,ValueError):return None


def parse_kicad(path):
    root=read_sexpr(path)
    layers=first(root,"layers") or []
    copper=[item[1] for item in layers[1:] if isinstance(item,list) and len(item)>2 and item[1].endswith(".Cu") and item[2]=="signal"]
    placements=[]
    for footprint in children(root,"footprint")+children(root,"module"):
        at=first(footprint,"at")
        if not at or len(at)<3:continue
        properties=children(footprint,"property")
        ref=next((item[2] for item in properties if len(item)>2 and item[1]=="Reference"),None)
        if ref is None:
            texts=children(footprint,"fp_text")
            ref=next((item[2] for item in texts if len(item)>2 and item[1]=="reference"),None)
        layer=first(footprint,"layer")
        placements.append({"reference":ref,"x":float(at[1]),"y":float(at[2]),"rotation":_float(at[3]) if len(at)>3 else 0,
                           "side":"bottom" if layer and (str(layer[1]).startswith("B.") or layer[1]=="bottom") else "top"})
    edges=[]
    for key in ("gr_line","gr_rect","gr_poly","gr_arc"):
        for item in children(root,key):
            layer=first(item,"layer")
            if not layer or layer[1]!="Edge.Cuts":continue
            for field in ("start","end","center","mid","xy"):
                for point in children(item,field):
                    if len(point)>=3:
                        x,y=_float(point[1]),_float(point[2])
                        if x is not None and y is not None:edges.append((x,y))
            pts=first(item,"pts")
            if pts:
                for point in children(pts,"xy"):
                    if len(point)>=3:edges.append((float(point[1]),float(point[2])))
            if key=="gr_rect":
                start,end=first(item,"start"),first(item,"end")
                if start and end:
                    x1,y1=float(start[1]),float(start[2]);x2,y2=float(end[1]),float(end[2])
                    edges.extend(((x1,y1),(x2,y2)))
    if not edges:raise ValueError(f"{path.name}: no board Edge.Cuts geometry found")
    xmin,xmax=min(x for x,y in edges),max(x for x,y in edges)
    ymin,ymax=min(y for x,y in edges),max(y for x,y in edges)
    segments=children(root,"segment")
    routes={}
    for segment in segments:
        layer=first(segment,"layer")
        name=layer[1] if layer and len(layer)>1 else "unknown"
        routes[name]=routes.get(name,0)+1
    via_count=len(children(root,"via"));zones=len(children(root,"zone"))
    return {"format":"KiCad","board_file":path.name,"board_width_mm":round(xmax-xmin,3),"board_height_mm":round(ymax-ymin,3),
        "aspect_ratio":round(max((xmax-xmin)/(ymax-ymin),(ymax-ymin)/(xmax-xmin)),3),"copper_layers":copper,
        "component_count":len(placements),"top_component_count":sum(p["side"]=="top" for p in placements),
        "bottom_component_count":sum(p["side"]=="bottom" for p in placements),"track_segment_count":len(segments),
        "track_segments_by_layer":routes,"via_count":via_count,"zone_count":zones,
        "outline_geometry_point_count":len(edges),"components":placements,"bounds_mm":[xmin,ymin,xmax,ymax]}


def parse_eagle(path):
    root=ET.parse(path).getroot();board=root.find("./drawing/board")
    if board is None:raise ValueError(f"{path.name}: board node is absent")
    edge_wires=[]
    for wire in board.findall("./plain/wire"):
        if wire.get("layer")=="20":edge_wires.append(wire)
    points=[]
    for wire in edge_wires:
        points.extend(((float(wire.get("x1")),float(wire.get("y1"))),(float(wire.get("x2")),float(wire.get("y2")))))
    if not points:raise ValueError(f"{path.name}: no EAGLE dimension-layer outline")
    xmin,xmax=min(x for x,y in points),max(x for x,y in points);ymin,ymax=min(y for x,y in points),max(y for x,y in points)
    elements=[]
    for element in board.findall("./elements/element"):
        rot=(element.get("rot") or "R0").lstrip("MR")
        elements.append({"reference":element.get("name"),"value":element.get("value"),"x":float(element.get("x")),
                         "y":float(element.get("y")),"rotation":float(rot or 0),"side":"bottom" if "M" in (element.get("rot") or "") else "top"})
    rules={item.get("name"):item.get("value") for item in board.findall("./designrules/param")}
    layer_setup=rules.get("layerSetup","")
    copper_layers=2 if layer_setup=="(1*16)" else max(2,layer_setup.count("*")+1) if layer_setup else None
    signal_counts={};vias=0;track_count=0
    for signal in board.findall("./signals/signal"):
        for wire in signal.findall("wire"):
            key=wire.get("layer","unknown");signal_counts[key]=signal_counts.get(key,0)+1;track_count+=1
        vias+=len(signal.findall("via"))
    return {"format":"EAGLE","board_file":path.name,"board_width_mm":round(xmax-xmin,3),
        "board_height_mm":round(ymax-ymin,3),"aspect_ratio":round(max((xmax-xmin)/(ymax-ymin),(ymax-ymin)/(xmax-xmin)),3),
        "copper_layer_count":copper_layers,"copper_layer_setup":layer_setup,"component_count":len(elements),
        "top_component_count":sum(p["side"]=="top" for p in elements),"bottom_component_count":sum(p["side"]=="bottom" for p in elements),
        "track_segment_count":track_count,"track_segments_by_layer":signal_counts,"via_count":vias,
        "outline_geometry_point_count":len(points),"components":elements,
        "bounds_mm":[round(xmin,3),round(ymin,3),round(xmax,3),round(ymax,3)]}


def spatial_profile(metrics):
    xmin,ymin,xmax,ymax=metrics["bounds_mm"];width=xmax-xmin;height=ymax-ymin
    counts=[[0 for _ in range(6)] for _ in range(6)]
    for item in metrics["components"]:
        col=min(5,max(0,int((item["x"]-xmin)/max(width,1e-9)*6)))
        row=min(5,max(0,int((item["y"]-ymin)/max(height,1e-9)*6)))
        counts[row][col]+=1
    total=metrics["component_count"]
    occupied=[{"row":r,"column":c,"component_count":counts[r][c],"share":round(counts[r][c]/max(total,1),4)}
              for r in range(6) for c in range(6) if counts[r][c]]
    metrics["placement_grid_6x6"]=counts;metrics["occupied_cells"]=occupied
    area=max(width*height,1e-9);metrics["component_density_per_cm2"]=round(total/area*100,2)
    metrics["track_segments_per_cm2"]=round(metrics["track_segment_count"]/area*100,2)
    metrics.pop("components",None);metrics.pop("bounds_mm",None)
    return metrics


def analyze(root=ROOT):
    cases={
        "rp2040-minimal":{"format":"KiCad","path":"local/board-challenges/sources/rp2040-minimal/package/RPI-RP2040-MINIMAL_R3-S1_public/RPI-RP2040-MINIMAL_R3-S1.kicad_pcb"},
        "feather-f405":{"format":"EAGLE","path":"local/board-challenges/sources/feather-f405/Adafruit_Feather_STM32F405_Express.brd"},
        "hackrf-one":{"format":"KiCad","path":"local/board-challenges/sources/hackrf-one/hackrf-one.kicad_pcb"}}
    result={}
    for key,item in cases.items():
        path=root/item["path"]
        if not path.is_file():raise FileNotFoundError(path)
        result[key]=spatial_profile(parse_kicad(path) if item["format"]=="KiCad" else parse_eagle(path))
        result[key]["source_path"]=item["path"]
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    result=analyze()
    path=OUT/"reference-effects.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(path.relative_to(ROOT).as_posix())
    print(json.dumps({k:{field:v for field,v in item.items() if field!="placement_grid_6x6"} for k,item in result.items()},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
