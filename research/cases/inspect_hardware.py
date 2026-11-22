import pathlib,re,json
for name in ['olimex-b1-pcb.kicad_pcb','rp2040-RPI-RP2040-MINIMAL_R3-S1.kicad_pcb']:
 p=pathlib.Path('research/cases/snapshots')/name;s=p.read_text();tokens=re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+',s);stack=[];root=None
 for t in tokens:
  if t=='(':
   x=[]
   if stack:stack[-1].append(x)
   else:root=x
   stack.append(x)
  elif t==')':stack.pop()
  else:stack[-1].append(t[1:-1] if t.startswith('"') else t)
 def children(n,k):return [i for i in n if isinstance(i,list) and i and i[0]==k]
 def first(n,k):return next(iter(children(n,k)),[])
 mods=children(root,'module')+children(root,'footprint');selected=[]
 for m in mods:
  texts=children(m,'fp_text');props=children(m,'property');ref=next((v[2] for v in texts if v[1]=='reference'),None) or next((v[2] for v in props if v[1]=='Reference'),None);val=next((v[2] for v in texts if v[1]=='value'),None) or next((v[2] for v in props if v[1]=='Value'),None)
  if 'ESP' in str(val) or 'RP2040' in str(val) or ref in ['C1','C2','C3','USB-UART1','LAN_CON1','U4','U2','J1','J2']:
   pads=[{'number':v[1],'type':v[2],'at':first(v,'at')[1:],'net':first(v,'net')[1:],'pinfunction':first(v,'pinfunction')[1:]} for v in children(m,'pad')]
   selected.append({'reference':ref,'value':val,'footprint':m[1],'at':first(m,'at')[1:],'layer':first(m,'layer')[1:],'pads':pads})
 result={'source':p.as_posix(),'file_version':first(root,'version')[1:],'generator_version':first(root,'generator_version')[1:],'copper_layers':[v[1] for v in first(root,'layers')[1:] if v[1].endswith('.Cu')],'thickness_mm':first(first(root,'general'),'thickness')[1:],'modules':len(mods),'segments':len(children(root,'segment')),'vias':len(children(root,'via')),'net_declarations':len(children(root,'net')),'selected_components':selected}
 out=pathlib.Path('research/cases/snapshots')/('hardware-extract-rp2040.json' if name.startswith('rp2040') else 'hardware-extract.json');out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(out,[(v['reference'],v['value'],len(v['pads'])) for v in selected]);print(result['copper_layers'],result['thickness_mm'],result['modules'],result['segments'],result['vias'])
