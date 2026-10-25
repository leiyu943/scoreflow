"""Actual application gateway: detect layout, run guarded CUDA, export and audit."""
import argparse
from datetime import datetime
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from PIL import Image,ImageOps
from score_image_routing import detect_staffs,route_and_crop
from full_page_routing import prepare_page
from tab_tokens import token_bars
from score_pipeline_core import xml_score,tab_events,write_event_midi,tab_musicxml,override_xml_meter,guitar_playback_transposition

from runtime_paths import RUNTIME as B, gpu_python
CODE=Path(__file__).resolve().parent
GPU=gpu_python()

def progress(stage,message):
    print(json.dumps({'stage':stage,'message':message},ensure_ascii=False),flush=True)


def save(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def chunk_tab_systems(route,image,dest,maximum_bars=2):
    """Bound decoder length using visual geometry, never reference measures."""
    systems=[]
    with Image.open(image) as source:
        for system in route['systems']:
            segments=system['visual_segments']
            if len(segments)<=maximum_bars:
                systems.append(dict(system,chunk_index=1));continue
            for start in range(0,len(segments),maximum_bars):
                selected=segments[start:start+maximum_bars]
                box=[system['bbox'][0] if start==0 else max(0,selected[0]['left']-2),system['bbox'][1],min(source.width,selected[-1]['right']+3),system['bbox'][3]]
                crop=dest/f"tab_system_{system['index']}_chunk_{start//maximum_bars+1}.png"
                source.crop(box).save(crop)
                systems.append(dict(system,crop=str(crop),bbox=box,visual_segments=selected,chunk_index=start//maximum_bars+1))
    return systems


def run(command,out):
    env=os.environ.copy(); env.update(PYTHONIOENCODING='utf-8')
    result=subprocess.run([str(GPU),*map(str,command)],cwd=B,env=env,capture_output=True,timeout=400,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    out.write_bytes(result.stdout+b'\n'+result.stderr)
    if result.returncode: raise RuntimeError('GPU 识别失败，请查看 '+str(out)+'\n'+(result.stdout+result.stderr).decode('utf-8',errors='replace').replace('\x00','')[-1600:])
    return result


def recognize(image,dest,meter=None,checkpoint=None,mode='auto'):
    image=image.resolve(); dest=dest.resolve(); dest.mkdir(parents=True,exist_ok=False)
    registry=B/'model_registry.json';deployed=None
    if checkpoint is None and registry.is_file():
        deployed=json.loads(registry.read_text(encoding='utf-8'))
    work=dest/'input.png'
    with Image.open(image) as source:
        ImageOps.exif_transpose(source).convert('RGB').save(work)
    progress('layout','正在分析五线谱、六线谱与混合版式…')
    gray,ink,staffs=detect_staffs(work)
    if not staffs: raise ValueError('未可靠检测到五线谱或六线谱，请提供清晰完整的谱行。')
    has_tab=any(s['kind']=='tab' for s in staffs)
    has_staff=any(s['kind']=='staff' for s in staffs)
    mixed=has_tab and has_staff
    if mode=='staff' and not has_staff: raise ValueError('本页没有可靠的五线谱，请选择自动或六线谱模式。')
    if mode=='tab' and not has_tab: raise ValueError('本页没有可靠的六线谱，请选择自动或五线谱模式。')
    if deployed is not None and (mode=='tab' or (has_tab and not mixed and mode!='staff')):
        key='mixed_tab_checkpoint' if mixed and deployed.get('mixed_tab_checkpoint') else 'tab_checkpoint'
        checkpoint=B/Path(deployed[key]);digest=deployed['mixed_tab_sha256' if key=='mixed_tab_checkpoint' else 'tab_sha256']
        if not checkpoint.is_file():raise RuntimeError('尚未安装六线谱模型。请先运行安装识别环境.cmd，或按安装指引配置 Tabbox；五线谱可单独使用。')
        if not (B/'guitar-tab-omr/scripts/guitar_omr_eval.py').is_file():raise RuntimeError('缺少与六线谱模型匹配的架构脚本，请运行安装识别环境.cmd。')
        if not checkpoint.is_file() or hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=digest:raise RuntimeError('部署模型的校验和不符，停止识别。')
    flags=[]; geometry=[]; width=Image.open(work).width; scale=1920/width
    # A mixed page uses the validated staff-first policy: mask the TAB rows,
    # run the strongest five-line HOMR path on the remaining page, and keep
    # the six-line route deferred for its separate correction pass.  This
    # avoids sending six-line digits into HOMR as a false bass staff.
    if mode=='tab' or (has_tab and not mixed and mode!='staff'):
        progress('tab','正在运行六线谱识别；模型仍在优化中…')
        route=route_and_crop(work,dest); bars=[]
        flags.append({'type':'approximate_tab_geometry'})
        route['inference_chunks']=[]; previous_meter=None
        tab_systems=chunk_tab_systems(route,work,dest)
        batch_jobs=[]
        for system in tab_systems:
            sid='system_'+str(system['index'])+'_chunk_'+str(system['chunk_index'])
            hint=meter
            route['inference_chunks'].append({'system':system['index'],'chunk':system['chunk_index'],'crop':system['crop'],'visual_bars':len(system['visual_segments']),'meter_hint':hint,'meter_hint_source':'user' if meter else 'batch auto'})
            batch_jobs.append({'sid':sid,'input_image':system['crop'],'output_root':str(dest/'predictions'),'initial_meter':'/'.join(map(str,hint)) if hint else 'auto'})
        # Load Tabbox once for the whole page.  Starting one guarded CUDA
        # process per chunk was the dominant source of latency and is also
        # intentionally forbidden by gpu_guard's single-device lock.
        manifest=dest/'tabbox_batch_manifest.json'; save(manifest,batch_jobs)
        batch_checkpoint=checkpoint or (B/'tabbox_best.pt')
        run([CODE/'tabbox_batch_worker.py','--device','cuda','--batch-manifest',manifest,'--output-root',dest/'predictions','--checkpoint',batch_checkpoint],dest/'tabbox_batch.log')
        for system in tab_systems:
            sid='system_'+str(system['index'])+'_chunk_'+str(system['chunk_index'])
            payload=json.loads((dest/'predictions'/sid/'tabbox.json').read_text(encoding='utf-8'))
            if payload['truncated']: flags.append({'type':'decode_truncated','system':system['index']})
            try: decoded=token_bars(payload['tokens'])
            except ValueError as exc: raise ValueError('六线谱输出结构不完整，未生成可误用的结果：'+str(exc)) from exc
            if not decoded: raise ValueError('未识别到六线谱小节')
            segments=system['visual_segments']; matched=len(decoded)==len(segments)
            if not matched: flags.append({'type':'bar_count_mismatch','system':system['index'],'visual':len(segments),'decoded':len(decoded)})
            if system['staff_assisted_barlines_x']: flags.append({'type':'staff_pixel_barlines_used','system':system['index']})
            staff=next(s for s in route['staffs'] if s['kind']=='tab' and system['bbox'][1]<=s['lines'][0]<=system['bbox'][3])
            for local,bar in enumerate(decoded):
                bar['index']=len(bars)+1
                if meter: bar['meter']=list(meter)
                elif bar['meter'] is None and previous_meter:bar['meter']=list(previous_meter)
                if bar.get('meter'):previous_meter=bar['meter']
                if not bar.get('meter'): flags.append({'type':'meter_unconfirmed','bar':bar['index']})
                muted=sum(n.get('pitch') is None for n in bar['notes'])
                if muted:flags.append({'type':'muted_note_audio_unavailable','bar':bar['index'],'count':muted})
                if bar.get('meter') and Fraction(bar['duration'])!=Fraction(bar['meter'][0]*4,bar['meter'][1]): flags.append({'type':'bar_duration_mismatch','bar':bar['index']})
                # Explicitly approximate localization; never changes the decoded event timing.
                segment=segments[local] if matched else {'left':system['bbox'][0],'right':system['bbox'][2]}
                for n in sorted(bar['notes'],key=lambda n:(Fraction(n['offset']),n.get('pitch') or 0)):
                    if n.get('pitch') is None: continue
                    ratio=float(Fraction(n['offset'])/max(Fraction(bar['duration']),Fraction(1,960)))
                    x=segment['left']+(.08+.84*ratio)*(segment['right']-segment['left'])
                    geometry.append({'staff':system['index']-1,'x':x*scale,'y':staff['lines'][n['string']-1]*scale,'width':staff['spacing']*scale,'height':staff['spacing']*scale,'anchor':'center','approximate':True})
                bars.append(bar)
        events,meters=tab_events(bars); bpm=120
        xml=dest/'score.musicxml'; tab_musicxml(xml,bars); save(dest/'tab_events.json',bars)
        route['geometry_precision']='approximate interpolation inside detected bars; review before fine segmentation'
    else:
        if mixed:
            mixed_plan=prepare_page(work,dest/'mixed_inputs')
            staff_input=Path(mixed_plan['images']['staff_mask'])
            route=dict(mixed_plan)
            route.update({'detected_layout':'mixed_5_6','selected_engine':'homr_staff_mask',
                          'staff_model_invoked':True,'tab_model_invoked':False,
                          'reference_input':False,
                          'mixed_policy':'TAB masked; five-line HOMR is the primary mixed-page result'})
            flags.append({'type':'mixed_staff_mask_primary','input':str(staff_input)})
        else:
            staff_input=work
            route={'detected_layout':'five_only','selected_engine':'homr','staff_model_invoked':True,'staffs':staffs,'reference_input':False}
        progress('staff','正在运行优化后的五线谱识别与校正…')
        result=run([CODE/'run_homr_gpu.py',staff_input],dest/'homr.log')
        # The parent reports the unique guarded directory. Never select a stale prediction by glob/mtime.
        text=result.stdout.decode('utf-8',errors='replace')
        prefix='Guarded CUDA run; logs: '
        run_dir=Path(next(line[len(prefix):].strip() for line in text.splitlines() if line.startswith(prefix)))
        report=json.loads((run_dir/'homr_result.json').read_text(encoding='utf-8'))
        xml=dest/'score.musicxml'; shutil.copyfile(report['prediction'],xml)
        audit=json.loads((run_dir/'event_rules_audit.json').read_text(encoding='utf-8')); save(dest/'event_rules_audit.json',audit)
        flags.extend(audit.get('review_flags',[])); route['gpu_run']=str(run_dir)
        route['playback_transposition']=guitar_playback_transposition(xml)
        events,meters,bpm=xml_score(xml)
        for e in events:
            if 'image_xy' not in e: continue
            x,y=e['image_xy']; staff=min(enumerate(staffs),key=lambda t:abs(sum(t[1]['lines'])/len(t[1]['lines'])-y))
            geometry.append({'staff':staff[0],'x':x*scale,'y':y*scale,'width':staff[1]['spacing']*scale,'height':staff[1]['spacing']*scale,'anchor':'center','approximate':True})
        if meter:
            meters=[{'start':'0','meter':list(meter)}]
            override_xml_meter(xml,meter)
            flags.append({'type':'user_meter_override','meter':list(meter),'retimed_notes':False})
    if not events: raise ValueError('没有识别到可播放的音符')
    progress('export','正在保存 MIDI、MusicXML 与音符坐标…')
    midi=dest/'score.mid'; write_event_midi(midi,events,meters,bpm)
    geo=dest/'geometry_notes.json'; save(geo,geometry); save(dest/'routing.json',route)
    payload={'pipeline_version':1,'requested_mode':mode,'image':str(work),'source_image':str(image),'musicxml':str(xml),'midi':str(midi),'geometry':str(geo),'events':events,'bpm':bpm,'meters':meters,'folder':str(dest),'route':route,
        'corrections':{'metadata':{'meter':meters[0]['meter'] if meters else None,'bpm':bpm},'review_flags':flags,'reference_input':False},'input_sha256':hashlib.sha256(image.read_bytes()).hexdigest()}
    save(dest/'result.json',payload)
    save(dest/'corrections.json',payload['corrections'])
    return payload


