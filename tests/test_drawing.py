import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from drawing import DrawingService,DrawingError,validate_operations,digest
from eda_client import EdaClient,EdaClientError

LIMITS={'units':'mil','source':'test fixture constraints only','region':[0,0,1000,1000],
        'min_trace_width':6,'min_hole':12,'min_annular_ring':6}
MOVE={'kind':'move','component_id':'c1','x':200,'y':300}
LINE={'kind':'line','net':'GND','layer':15,'x1':100,'y1':100,'x2':200,'y2':100,'width':6}
VIA={'kind':'via','net':'GND','x':200,'y':100,'hole':12,'diameter':24}

def snapshot():
    return {'ok':True,'source':'fixture PCB source','source_sha256':digest(b'fixture PCB source'),
            'semantic_source_sha256':digest(b'fixture semantic PCB source'),
            'components':[{'id':'c1','x':100,'y':100,'layer':1,'rotation':0,'locked':False,
                           'pads':[{'id':'pad1','x':95,'y':100},{'id':'pad2','x':105,'y':100}]}],
            'nets':['GND'],'layers':[{'id':1,'type':'SIGNAL','layerStatus':1,'locked':False},
                                     {'id':15,'type':'SIGNAL','layerStatus':1,'locked':False}],
            'outline_layer':{'id':11,'type':'OTHER','layerStatus':1,'locked':False},
            'outline_primitive_ids':[]}

def manufacturing_state():
    value=snapshot()
    value['layers'].extend([
        {'id':2,'type':'SIGNAL','layerStatus':1,'locked':False},
        {'id':3,'type':'SIGNAL','layerStatus':1,'locked':False},
    ])
    return value

def write_manufacturing_fixtures(directory):
    directory.mkdir(parents=True,exist_ok=True)
    gerber=directory/'Gerber.zip'
    with zipfile.ZipFile(gerber,'w') as archive:
        for name in ('Top.GTL','Bottom.GBL','Inner1.G1','Inner2.G2'):
            archive.writestr(name,'%TF.FileFunction,Copper,L1,Top*%\nM02*\n')
        archive.writestr('Outline.GKO','%TF.FileFunction,Profile*%\nM02*\n')
        archive.writestr('Drill.PTH.DRL','M48\nM30\n')
    bom=directory/'BOM.xlsx'
    with zipfile.ZipFile(bom,'w') as archive:
        archive.writestr('[Content_Types].xml','<Types/>')
        archive.writestr('xl/workbook.xml','<workbook/>')
        archive.writestr('xl/worksheets/sheet1.xml','<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Designator</t></is></c><c r="B1" t="inlineStr"><is><t>Quantity</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>U1</t></is></c><c r="B2"><v>1</v></c></row></sheetData></worksheet>')
    pnp=directory/'PickAndPlace.tsv'
    pnp.write_bytes(b'\xff\xfe'+ 'Reference\tX\tY\tRotation\tLayer\nU1\t1.0\t2.0\t0\tTop\n'.encode('utf-16le'))
    return {'gerber':gerber,'bom':bom,'pick_and_place':pnp}

class DrawingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.client=Mock();self.service=DrawingService(self.root,self.client)
        self.opened=None
        def cli(args,_operation):
            if args[0]=='open':
                self.opened=args[args.index('--path')+1]
                return {'status':'ok','value':{'sessionId':'session','path':self.opened}}
            return {'status':'ok','value':[{'sessionId':'session','path':self.opened,'origin':'cli','status':'alive'}]}
        self.client._run_cli.side_effect=cli
        def invoke(action,_sid,args,**_):
            if action=='inspect_environment':v={'ok':True,'capabilities':{
                'pcb_Document.startAutoRouting':True,'pcb_Document.getAutoJobStatus':True,'pcb_Document.cancelAutoJob':True,
                'pcb_Document.getAutoJobLog':True,'pcb_Document.getRatlines':True,'sys_FileManager.getDocumentSource':True,
                'pcb_Document.beginCommandGroup':True,'pcb_Document.commitCommandGroup':True,'pcb_Document.rollbackCommandGroup':True,
                'pcb_PrimitiveComponent.modify':True,'pcb_PrimitiveComponent.get':True,
                'pcb_PrimitiveLine.create':True,'pcb_PrimitiveLine.get':True,'pcb_PrimitiveVia.create':True,'pcb_PrimitiveVia.get':True}}
            elif action=='focus_working_copy':v={'ok':True,'project_uuid':'project'}
            elif action=='drawing_state':v=snapshot()
            else:v={'ok':True,'status':'completed','source':'after','source_sha256':digest(b'after'),'drc_required':True}
            return {'status':'observed','value':v}
        self.client.invoke_script.side_effect=invoke

    def prepare(self):
        p=self.root/'raw'/'source.eprj2';p.parent.mkdir(exist_ok=True);p.write_bytes(b'fixture-native-file')
        copied=self.service.copy_project('raw/source.eprj2')
        return self.service.prepare(copied['copy_id'],'pcb',[MOVE,LINE,VIA],LIMITS)

    def test_native_copy_preview_apply_and_replay(self):
        plan=self.prepare();before=(self.root/'raw/source.eprj2').read_bytes()
        self.assertEqual(plan['status'],'prepared');self.assertFalse(plan['design_writes'])
        result=self.service.apply(plan['plan_id']);self.assertEqual(result['status'],'completed');self.assertNotIn('source',result)
        count=self.client.invoke_script.call_count
        self.assertEqual(self.service.apply(plan['plan_id']),result);self.assertEqual(self.client.invoke_script.call_count,count)
        self.assertEqual((self.root/'raw/source.eprj2').read_bytes(),before)

    def test_archive_is_not_renamed_or_opened_as_native(self):
        (self.root/'source.epro2').write_bytes(b'archive')
        self.assertEqual(self.service.copy_project('source.epro2')['status'],'needs_native_project')
        self.client._run_cli.assert_not_called()

    def test_eprj3_clones_supporting_directory(self):
        p=self.root/'raw'/'native';(p/'pcb').mkdir(parents=True)
        (p/'main.eprj3').write_text('{}');(p/'pcb'/'board.epcb2').write_text('board')
        r=self.service.copy_project('raw/native/main.eprj3')
        self.assertEqual((self.root/r['path']).parent.joinpath('pcb/board.epcb2').read_text(),'board')

    def test_path_escape_is_rejected(self):
        for p in ('../other.eprj2','C:\\other.eprj2','raw/../../other.eprj2'):
            with self.assertRaises(DrawingError):self.service.copy_project(p)
        self.client._run_cli.assert_not_called()

    def test_plan_amendment_rejected(self):
        plan=self.prepare();p=self.root/'local/drawing/plans'/f"{plan['plan_id']}.json"
        d=json.loads(p.read_text());d['operations'][0]['x']=201;p.write_text(json.dumps(d))
        with self.assertRaises(DrawingError):self.service.apply(plan['plan_id'])

    def test_closed_or_foreign_session_cannot_write(self):
        plan=self.prepare();self.client._run_cli.return_value={'status':'ok','value':[]};self.client._run_cli.side_effect=None
        with self.assertRaises(DrawingError):self.service.apply(plan['plan_id'])

    def test_crash_attempt_is_never_replayed(self):
        plan=self.prepare();self.client.invoke_script.side_effect=TimeoutError('fixture')
        with self.assertRaises(TimeoutError):self.service.apply(plan['plan_id'])
        count=self.client.invoke_script.call_count
        self.assertEqual(self.service.apply(plan['plan_id'])['status'],'recovery_required')
        self.assertEqual(self.client.invoke_script.call_count,count)

    def test_constraints_require_real_inputs_and_reject_invalid_geometry(self):
        cases=[([{**MOVE,'x':True}],LIMITS),([{**LINE,'net':'imaginary'}],LIMITS),([{**LINE,'width':1}],LIMITS),
               ([{**VIA,'diameter':14}],LIMITS),([{**MOVE,'x':1001}],LIMITS),([MOVE,MOVE],LIMITS),([MOVE],{**LIMITS,'source':''}),
               ([{**LINE,'x2':float('inf')}],LIMITS),([{**MOVE,'layer':2}],LIMITS)]
        for ops,limits in cases:
            with self.subTest(ops=ops),self.assertRaises((DrawingError,ValueError)):
                validate_operations(ops,limits,snapshot())

    def test_fresh_layout_geometry_accepts_rotation_and_closed_outline(self):
        operations=[{'kind':'place','component_id':'c1','x':200,'y':300,'rotation':90},
                    {'kind':'outline','points':[[100,100],[500,100],[500,700],[100,700],[100,100]],'width':2}]
        self.assertEqual(validate_operations(operations,LIMITS,snapshot()),operations)

    def test_outline_replacement_requires_the_exact_existing_primitive(self):
        operation={'kind':'replace_outline','primitive_id':'outline-1',
                   'points':[[100,100],[500,100],[500,700],[100,700],[100,100]],'width':2}
        baseline=snapshot();baseline['outline_primitive_ids']=['outline-1']
        self.assertEqual(validate_operations([operation],LIMITS,baseline),[operation])
        baseline['outline_primitive_ids']=['outline-2']
        with self.assertRaises(DrawingError):validate_operations([operation],LIMITS,baseline)

    def test_visual_only_footprint_instance_requires_exact_library_and_pad_identity(self):
        footprint={'kind':'footprint','library_uuid':'a'*32,'footprint_uuid':'b'*16,'designator':'U1','x':200,'y':300,
                   'rotation':90,'expected_pad_numbers':['1','2','2'],'visual_only':True}
        self.assertEqual(validate_operations([footprint],LIMITS,snapshot()),[footprint])
        for invalid in ({**footprint,'visual_only':False},{**footprint,'designator':'../../R1'},
                        {**footprint,'expected_pad_numbers':[],'footprint_uuid':'broken'}):
            with self.subTest(invalid=invalid),self.assertRaises(DrawingError):validate_operations([invalid],LIMITS,snapshot())

    def test_fresh_layout_geometry_rejects_existing_outline_and_self_intersection(self):
        crossing={'kind':'outline','points':[[100,100],[500,700],[100,700],[500,100],[100,100]],'width':2}
        with self.assertRaises(DrawingError):validate_operations([crossing],LIMITS,snapshot())
        existing=snapshot();existing['outline_primitive_ids']=['outline-1']
        with self.assertRaises(DrawingError):validate_operations([{'kind':'outline','points':[[100,100],[500,100],[500,700],[100,700],[100,100]],'width':2}],LIMITS,existing)

    def test_native_export_checks_bytes_and_zip_crc(self):
        plan=self.prepare();self.service.apply(plan['plan_id'])
        def exporter(action,sid,args,**_):
            self.assertEqual(action,'export_drawing_copy')
            with zipfile.ZipFile(args['artifact_path'],'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('fixture.epru','fixture-native-project-stream')
            raw=Path(args['artifact_path']).read_bytes()
            return {'value':{'ok':True,'archive_sha256':digest(raw),'bytes':len(raw)}}
        self.client.invoke_script.side_effect=exporter
        r=self.service.export(plan['plan_id'])
        self.assertEqual(r['status'],'exported');self.assertTrue(r['zip_crc_verified']);self.assertFalse(r['native_reopen_verified'])
        self.assertTrue((self.root/r['path']).is_file())

    def test_native_export_rejects_wrong_disk_digest(self):
        plan=self.prepare();self.service.apply(plan['plan_id'])
        def exporter(action,sid,args,**_):
            Path(args['artifact_path']).write_bytes(b'not an archive')
            return {'value':{'ok':True,'archive_sha256':'0'*64,'bytes':14}}
        self.client.invoke_script.side_effect=exporter
        with self.assertRaises(DrawingError):self.service.export(plan['plan_id'])

    def test_manufacturing_export_runs_fresh_drc_and_reuses_verified_files(self):
        plan=self.prepare();record=self.service._copy_record(plan['copy_id']);calls=[]
        def invoke(action,sid,args,**_):
            calls.append((action,args))
            if action=='drawing_state':value=manufacturing_state()
            elif action=='inspect_drc':value={'ok':True,'fresh_result':True,'native_check_passed':True,
                'state':'passed','total_count':0,'failed_items':0,'checked_at':12345}
            elif action=='inspect_ratlines':value={'ok':True,'routing_complete':True,'unrouted_total':0}
            elif action=='export_manufacturing':
                paths=write_manufacturing_fixtures(Path(args['artifact_directory']))
                value={'ok':True,'pcb_uuid':args['pcb_uuid'],'project_uuid':args['expected_project_uuid'],
                    'source_sha256':args['expected_source_sha256'],'gerber_profile':'JLCEDA one-click defaults',
                    'files':[{'kind':kind,'name':path.name,'bytes':path.stat().st_size,'sha256':digest(path.read_bytes())}
                             for kind,path in paths.items()]}
            else:value={'ok':True,'status':'observed'}
            return {'status':'observed','value':value}
        self.client.invoke_script.side_effect=invoke
        first=self.service.export_manufacturing(plan['copy_id'],'pcb')
        self.assertEqual(first['status'],'manufacturing_files_exported')
        self.assertTrue(first['file_validation']['gerber']['zip_crc_verified'])
        self.assertFalse(first['manufacturing_acceptance'])
        self.assertTrue(any(action=='inspect_drc' and args['run'] is True for action,args in calls))
        export_count=sum(action=='export_manufacturing' for action,_ in calls)
        second=self.service.export_manufacturing(plan['copy_id'],'pcb')
        self.assertEqual(second,first)
        self.assertEqual(sum(action=='export_manufacturing' for action,_ in calls),export_count)

    def test_manufacturing_export_blocks_without_fresh_zero_violation_drc(self):
        plan=self.prepare();calls=[]
        def invoke(action,sid,args,**_):
            calls.append(action)
            if action=='drawing_state':value=manufacturing_state()
            elif action=='inspect_drc':value={'ok':True,'fresh_result':False,'native_check_passed':False,
                'state':'notChecked','total_count':0,'failed_items':0,'checked_at':None}
            elif action=='inspect_ratlines':value={'ok':True,'routing_complete':True,'unrouted_total':0}
            else:value={'ok':True}
            return {'status':'observed','value':value}
        self.client.invoke_script.side_effect=invoke
        result=self.service.export_manufacturing(plan['copy_id'],'pcb')
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(result['manufacturing_files_exported'])
        self.assertNotIn('export_manufacturing',calls)

    def test_manufacturing_export_retries_only_recorded_failure_without_any_outputs(self):
        plan=self.prepare();calls=[];states=[snapshot(),manufacturing_state()]
        def invoke(action,sid,args,**_):
            calls.append(action)
            if action=='drawing_state':value=states[min(sum(x=='drawing_state' for x in calls)-1,len(states)-1)]
            elif action=='inspect_drc':value={'ok':True,'fresh_result':True,'native_check_passed':True,
                'state':'passed','total_count':0,'failed_items':0,'checked_at':12345}
            elif action=='inspect_ratlines':value={'ok':True,'routing_complete':True,'unrouted_total':0}
            elif action=='export_manufacturing':
                paths=write_manufacturing_fixtures(Path(args['artifact_directory']))
                value={'ok':True,'pcb_uuid':'pcb','project_uuid':'project','source_sha256':args['expected_source_sha256'],
                    'files':[{'kind':kind,'name':path.name,'bytes':path.stat().st_size,'sha256':digest(path.read_bytes())}
                             for kind,path in paths.items()]}
            else:value={'ok':True}
            return {'status':'observed','value':value}
        self.client.invoke_script.side_effect=invoke
        root=self.root/'local/drawing/exports';root.mkdir(parents=True,exist_ok=True)
        directory=root/('pcb-'+plan['copy_id']+'-'+snapshot()['semantic_source_sha256'][:16]+'-'+'a'*16)
        directory.mkdir()
        for name,data in {'attempt.json':{'status':'started'},'preflight.json':{},
                          'result.json':{'status':'recovery_required','files_present':['attempt.json','preflight.json','result.json']}}.items():
            (directory/name).write_text(json.dumps(data),encoding='utf-8')
        result=self.service.export_manufacturing(plan['copy_id'],'pcb')
        self.assertEqual(result['status'],'manufacturing_files_exported')
        self.assertEqual(sum(action=='export_manufacturing' for action in calls),1)

    def test_manufacturing_export_refuses_retry_when_prior_output_might_exist(self):
        plan=self.prepare();calls=[]
        def invoke(action,sid,args,**_):
            calls.append(action)
            if action=='drawing_state':value=manufacturing_state()
            elif action=='inspect_drc':value={'ok':True,'fresh_result':True,'native_check_passed':True,
                'state':'passed','total_count':0,'failed_items':0,'checked_at':12345}
            elif action=='inspect_ratlines':value={'ok':True,'routing_complete':True,'unrouted_total':0}
            else:value={'ok':False,'reason':'must not be called'}
            return {'status':'observed','value':value}
        self.client.invoke_script.side_effect=invoke
        root=self.root/'local/drawing/exports';root.mkdir(parents=True,exist_ok=True)
        directory=root/('pcb-'+plan['copy_id']+'-'+snapshot()['semantic_source_sha256'][:16]+'-'+'a'*16)
        directory.mkdir()
        for name,data in {'attempt.json':{'status':'started'},'preflight.json':{},
                          'result.json':{'status':'recovery_required','files_present':['attempt.json','preflight.json','result.json','Gerber.zip']},
                          'Gerber.zip':b'partial'}.items():
            path=directory/name
            if isinstance(data,bytes):path.write_bytes(data)
            else:path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(DrawingError):self.service.export_manufacturing(plan['copy_id'],'pcb')
        self.assertNotIn('export_manufacturing',calls)

    def test_database_journal_prevents_inconsistent_copy(self):
        (self.root/'board.eprj2').write_bytes(b'db');(self.root/'board.eprj2-wal').write_bytes(b'active')
        with self.assertRaises(DrawingError):self.service.copy_project('board.eprj2')
        self.client._run_cli.assert_not_called()

    def test_transport_requires_explicit_drawing_mode_and_fixed_common_source(self):
        action_dir=Path(__file__).resolve().parents[1]/'tools/eda_actions'
        readonly=EdaClient(action_dir=action_dir)
        with self.assertRaises(EdaClientError):readonly._action_script('drawing_state',{'pcb_uuid':'p','expected_project_uuid':'j'})
        writer=EdaClient(action_dir=action_dir,allow_drawing=True)
        code,args,sha=writer._action_script('drawing_state',{'pcb_uuid':'p','expected_project_uuid':'j'})
        self.assertIn('const capture = async',code);self.assertIn('await capture()',code);self.assertEqual(len(sha),64)
        open_code,_,_=writer._action_script('open_project_pcb',{'pcb_uuid':'p','expected_project_uuid':'j'})
        self.assertIn('const a=__CLI__.args',open_code)
        self.assertNotIn('const capture = async',open_code)
        with self.assertRaises(EdaClientError):writer.invoke_script('drawing_state','s',args,backend='bridge')

    def test_drawing_parameters_cannot_supply_raw_code(self):
        writer=EdaClient(action_dir=Path(__file__).resolve().parents[1]/'tools/eda_actions',allow_drawing=True)
        with self.assertRaises(EdaClientError):writer._action_script('apply_drawing_batch',{'code':'write-anything'})

    def test_native_route_preview_start_poll_cancel_and_export(self):
        p=self.root/'raw'/'source.eprj2';p.parent.mkdir(exist_ok=True);p.write_bytes(b'fixture-native-file')
        copied=self.service.copy_project('raw/source.eprj2')
        plan=self.service.preview_routing(copied['copy_id'],'pcb',['GND'],[15])
        self.assertEqual(plan['status'],'previewed')
        def invoke(action,_sid,args,**_):
            if action=='focus_working_copy':value={'ok':True,'project_uuid':'project'}
            elif action=='drawing_state':value=snapshot()
            elif action=='start_auto_route':value={'ok':True,'status':'started','job_id':'job'}
            elif action=='auto_route_status':value={'ok':True,'status':'observed','job_id':'job','state':'running','progress_percent':5,'partial':False}
            else:value={'ok':True,'status':'observed','cancel_requested':True}
            return {'status':'observed','value':value}
        self.client.invoke_script.side_effect=invoke
        started=self.service.start_routing(plan['route_plan_id']);self.assertEqual(started['status'],'started')
        polled=self.service.route_status(plan['route_plan_id']);self.assertEqual(polled['state'],'running')
        canceled=self.service.cancel_routing(plan['route_plan_id']);self.assertEqual(canceled['status'],'cancel_requested')

    def test_native_route_start_unknown_outcome_is_never_replayed(self):
        p=self.root/'native.eprj2';p.write_bytes(b'fixture');copy=self.service.copy_project('native.eprj2')
        plan=self.service.preview_routing(copy['copy_id'],'pcb',['GND'],[15])
        self.client.invoke_script.side_effect=lambda action,*args,**kwargs: {'status':'unavailable','value':None} if action=='start_auto_route' else ({'status':'observed','value':{'ok':True,'project_uuid':'project'}} if action=='focus_working_copy' else {'status':'observed','value':snapshot()})
        result=self.service.start_routing(plan['route_plan_id']);self.assertEqual(result['status'],'recovery_required')
        calls=self.client.invoke_script.call_count
        self.assertEqual(self.service.start_routing(plan['route_plan_id'])['status'],'recovery_required')
        self.assertEqual(self.client.invoke_script.call_count,calls)

    def test_route_preview_rejects_old_eda_before_saving_a_plan(self):
        p=self.root/'old.eprj2';p.write_bytes(b'fixture');copy=self.service.copy_project('old.eprj2')
        self.client.invoke_script.side_effect=lambda action,*args,**kwargs: {'status':'observed','value':{'ok':True,'capabilities':{}}} if action=='inspect_environment' else {'status':'observed','value':{'ok':True,'project_uuid':'project'}}
        with self.assertRaises(DrawingError):self.service.preview_routing(copy['copy_id'],'pcb',['GND'],[15])
        self.assertEqual(list((self.root/'local/drawing/routes').glob('*.json')),[])

    def test_route_export_requires_completed_nonpartial_job(self):
        p=self.root/'native.eprj2';p.write_bytes(b'fixture');copy=self.service.copy_project('native.eprj2')
        plan=self.service.preview_routing(copy['copy_id'],'pcb',['GND'],[15])
        route_dir=self.root/'local/drawing/routes';job=route_dir/f"{plan['route_plan_id']}.job.json"
        job.write_text(json.dumps({'state':'running','job_id':'job'}))
        with self.assertRaises(DrawingError):self.service.export_route(plan['route_plan_id'])
        job.write_text(json.dumps({'state':'completed','partial':True,'job_id':'job','source_sha256':digest(b'after')}))
        with self.assertRaises(DrawingError):self.service.export_route(plan['route_plan_id'])

    def test_route_export_retains_unrouted_count_as_nonpassing_evidence(self):
        p=self.root/'native.eprj2';p.write_bytes(b'fixture');copy=self.service.copy_project('native.eprj2')
        plan=self.service.preview_routing(copy['copy_id'],'pcb',['GND'],[15])
        job_file=self.root/'local/drawing/routes'/f"{plan['route_plan_id']}.job.json"
        job_file.write_text(json.dumps({'state':'completed','partial':False,'job_id':'job','source_sha256':digest(b'after'),
                                        'unrouted_ratlines':{'total':3,'pages':1}}))
        def exporter(action,sid,args,**_):
            self.assertEqual(action,'export_drawing_copy')
            with zipfile.ZipFile(args['artifact_path'],'w') as z:z.writestr('fixture.epru','project')
            raw=Path(args['artifact_path']).read_bytes()
            return {'value':{'ok':True,'archive_sha256':digest(raw),'bytes':len(raw)}}
        self.client.invoke_script.side_effect=exporter
        result=self.service.export_route(plan['route_plan_id'])
        self.assertEqual(result['unrouted_ratlines']['total'],3)
        self.assertFalse(result['native_reopen_verified'])

    def test_gui_test_copy_is_registered_and_uses_only_exact_created_identity(self):
        self.client.list_sessions.return_value={'status':'ok','sessions':[{'session_id':'gui-session','backend':'cli','origin':'user','status':'alive'}]}
        source_id='1'*32;copy_id='2'*32
        self.client.invoke_script.side_effect=None
        self.client.invoke_script.return_value={'status':'observed','value':{'ok':True,'status':'observed','project_uuid':'3'*32,
            'source_pcb_uuid':source_id,'copy_pcb_uuid':copy_id,'copy_pcb_name':'PCB copy',
            'source_board_name':'source board','source_schematic_uuid':'4'*32,'copy_board_name':'source board copy','copy_schematic_uuid':'5'*32}}
        result=self.service.create_gui_pcb_copy('gui-session','3'*32,source_id)
        record=self.service._copy_record(result['copy_id'])
        self.assertEqual(result['status'],'test_copy_created')
        self.assertEqual(record['workspace_kind'],'gui_test_copy')
        self.assertNotEqual(record['pcb_uuid'],record['source_pcb_uuid'])
        self.assertEqual(self.client.invoke_script.call_args.args[0],'create_gui_pcb_copy')

    def test_gui_test_copy_cleanup_requires_terminal_route_job_and_verifies_deletion(self):
        cid='a'*32;route_id='b'*32
        record={'copy_id':cid,'workspace_kind':'gui_test_copy','session_id':'gui-session','project_uuid':'3'*32,
                'source_pcb_uuid':'1'*32,'source_schematic_uuid':'4'*32,'copy_board_name':'source board copy',
                'pcb_uuid':'2'*32,'schematic_uuid':'5'*32,'status':'active'}
        path=self.root/'local/drawing/gui-copies';path.mkdir(parents=True);(path/f'{cid}.json').write_text(json.dumps(record))
        routes=self.root/'local/drawing/routes';routes.mkdir(parents=True)
        (routes/f'{route_id}.json').write_text(json.dumps({'plan_id':route_id,'copy_id':cid}))
        (routes/f'{route_id}.job.json').write_text(json.dumps({'state':'running','job_id':'job'}))
        self.client.list_sessions.return_value={'status':'ok','sessions':[{'session_id':'gui-session','backend':'cli','origin':'user','status':'alive'}]}
        with self.assertRaises(DrawingError):self.service.cleanup_gui_pcb_copy(cid)
        (routes/f'{route_id}.job.json').write_text(json.dumps({'state':'completed','job_id':'job'}))
        self.client.invoke_script.side_effect=None
        self.client.invoke_script.return_value={'status':'observed','value':{'ok':True,'cleanup_verified':True,
            'source_pcb_still_present':True,'source_schematic_still_present':True}}
        result=self.service.cleanup_gui_pcb_copy(cid)
        self.assertEqual(result['status'],'cleanup_verified')
        self.assertEqual(self.client.invoke_script.call_args.args[0],'delete_gui_pcb_copy')

if __name__=='__main__':unittest.main()
