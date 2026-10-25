"""Join recognized pages in reading order, preserving rests and cross-page ties.

No model/GUI dependencies. A manifest contains ordered {result,id,name} pages.
"""
import argparse
import copy
from fractions import Fraction
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from score_pipeline_core import xml_score, write_event_midi

def read_xml(path):
    root = ET.parse(path, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))).getroot()
    for el in root.iter():
        if isinstance(el.tag, str): el.tag = el.tag.rsplit('}', 1)[-1]
    return root

def part_duration(part, inherited_meter=None):
    """Count actual measure extents, including silent endings and multiple voices."""
    total, divisions, meter = Fraction(), 1, inherited_meter
    for measure in part.findall('measure'):
        clock = previous = end = Fraction()
        for el in measure:
            if el.tag == 'attributes':
                divisions = int(el.findtext('divisions') or divisions)
                t = el.find('time')
                if t is not None:
                    try: meter = (int(t.findtext('beats')), int(t.findtext('beat-type')))
                    except (TypeError, ValueError): pass
            elif el.tag in {'backup', 'forward'}:
                clock += Fraction(int(el.findtext('duration') or 0), divisions) * (-1 if el.tag == 'backup' else 1)
                end = max(end, clock)
            elif el.tag == 'note' and el.find('grace') is None:
                duration = Fraction(int(el.findtext('duration') or 0), divisions)
                onset = previous if el.find('chord') is not None else clock
                if el.find('chord') is None: previous, clock = onset, clock + duration
                end = max(end, onset + duration)
        total += end if end else Fraction(meter[0] * 4, meter[1]) if meter else Fraction()
    return total

def add_padding(part, amount):
    if amount <= 0: return
    # A separate silent measure keeps a shorter part aligned to the next page.
    measure = ET.SubElement(part, 'measure', number='padding', implicit='yes')
    attributes = ET.SubElement(measure, 'attributes')
    ET.SubElement(attributes, 'divisions').text = str(amount.denominator)
    forward = ET.SubElement(measure, 'forward')
    ET.SubElement(forward, 'duration').text = str(amount.numerator)

def assemble(manifest, output):
    config = json.loads(Path(manifest).read_text(encoding='utf-8'))
    entries = config.get('pages') or []
    if not entries: raise ValueError('没有可合并的谱页')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    pages, shifted, meters, flags, offset = [], [], [], [], Fraction()
    joined = None; compatible = True; base_parts = []
    for index, entry in enumerate(entries):
        raw_path = Path(entry['result']).resolve()
        raw = json.loads(raw_path.read_text(encoding='utf-8'))
        if not raw.get('events'): raise ValueError(f'第 {index+1} 页没有可播放音符，未跳过此页')
        root = read_xml(raw['musicxml'])
        parts = root.findall('part')
        if not parts: raise ValueError(f'第 {index+1} 页缺少可合并的谱面声部')
        durations = [part_duration(p, (raw.get('meters') or [{}])[0].get('meter')) for p in parts]
        note_end = max(Fraction(e['start']) + Fraction(e['duration']) for e in raw['events'])
        extent = max([note_end, *durations])
        if extent <= 0: raise ValueError(f'第 {index+1} 页时长无效')
        page = { 'id':entry.get('id',str(index)), 'name':entry.get('name',f'第 {index+1} 页'),
                 'index':index, 'start':str(offset), 'duration':str(extent), 'end':str(offset+extent),
                 'result':str(raw_path), 'image':raw['image'], 'source_image':raw.get('source_image',raw['image']),
                 'geometry':raw.get('geometry'), 'events':raw['events'], 'meters':raw.get('meters',[]),
                 'route':raw.get('route',{}), 'corrections':raw.get('corrections',{}) }
        pages.append(page)
        for e in raw['events']:
            shifted.append(dict(e, start=str(offset+Fraction(e['start'])), page=index, page_id=page['id']))
        for m in raw.get('meters',[]):
            item = dict(m, start=str(offset+Fraction(m['start'])))
            if not meters or meters[-1]['meter'] != item['meter']: meters.append(item)
        for f in raw.get('corrections',{}).get('review_flags',[]):
            flags.append(dict(f,page=index+1) if isinstance(f,dict) else {'type':str(f),'page':index+1})
        if joined is None:
            joined = copy.deepcopy(root); base_parts = joined.findall('part')
            for p in base_parts:
                for m in list(p.findall('measure')): p.remove(m)
        if len(parts) != len(base_parts): compatible = False
        if compatible:
            for pi, part in enumerate(parts):
                for mi, measure in enumerate(part.findall('measure')):
                    m = copy.deepcopy(measure)
                    if mi == 0:
                        # Each recognizer output is a standalone score. Reset
                        # page-local defaults so an inherited guitar transpose
                        # or a TAB's six staff lines cannot alter the next page.
                        attr=m.find('attributes')
                        if attr is None: attr=ET.Element('attributes');m.insert(0,attr)
                        if attr.find('divisions') is None: ET.SubElement(attr,'divisions').text='1'
                        if attr.find('transpose') is None:
                            tr=ET.SubElement(attr,'transpose');ET.SubElement(tr,'chromatic').text='0'
                        if attr.find('staff-details') is None:
                            details=ET.SubElement(attr,'staff-details');ET.SubElement(details,'staff-lines').text='6' if attr.findtext('clef/sign')=='TAB' else '5'
                    if index and mi == 0:
                        mark = m.find('print')
                        if mark is None: mark = ET.Element('print'); m.insert(0,mark)
                        mark.set('new-page','yes')
                    base_parts[pi].append(m)
                add_padding(base_parts[pi],extent-durations[pi])
        offset += extent
    bpm = float(config.get('bpm') or json.loads(Path(entries[0]['result']).read_text(encoding='utf-8')).get('bpm') or 120)
    events = shifted
    xml_path = output/'score.musicxml'
    if compatible:
        # The existing player has a single global BPM. Keep MusicXML and MIDI
        # consistent rather than injecting each page's default tempo again.
        for direction in joined.findall('.//direction'):
            for sound in direction.findall('sound'): sound.attrib.pop('tempo',None)
            for dtype in direction.findall('direction-type'):
                for metronome in dtype.findall('metronome'): dtype.remove(metronome)
        for part in base_parts:
            for i, measure in enumerate(part.findall('measure'),1): measure.set('number',str(i))
        first = base_parts[0].find('measure')
        direction = ET.Element('direction'); ET.SubElement(direction,'sound',tempo=str(bpm)); first.insert(0,direction)
        ET.ElementTree(joined).write(xml_path,encoding='utf-8',xml_declaration=True)
        merged_events,_,_ = xml_score(xml_path)
        # Preserve TAB fingering/velocity. Parsing the joined XML also joins
        # ties which start on one page and continue onto the next.
        origins = {(Fraction(e['start']),int(e['pitch']),e.get('part')):e for e in shifted}
        loose = {(Fraction(e['start']),int(e['pitch'])):e for e in shifted}
        for e in merged_events:
            source = origins.get((Fraction(e['start']),e['pitch'],e.get('part'))) or loose.get((Fraction(e['start']),e['pitch']))
            if source:
                for k in ['string','fret','velocity','page','page_id']:
                    if k in source: e[k]=source[k]
        # A merged export must agree with the individual page notes, allowing
        # only the removal of continued tied attacks.
        if not merged_events: raise ValueError('合并谱面没有生成音符')
        events = merged_events
    else:
        flags.append({'type':'multipart_page_structure_changed','message':'页间声部数量不同，已合并 MIDI；请使用各页 MusicXML。'})
    events.sort(key=lambda e:(Fraction(e['start']),int(e['pitch'])))
    midi_path = output/'score.mid'; write_event_midi(midi_path,events,meters,bpm,end_beat=offset)
    result = {'pipeline_version':2,'document_version':1,'title':config.get('title','完整曲目'),
              'pages':pages,'events':events,'bpm':bpm,'meters':meters,'duration':str(offset),
              'midi':str(midi_path.resolve()),'musicxml':str(xml_path.resolve()) if compatible else '',
              'folder':str(output.resolve()),'image':pages[0]['image'],'geometry':pages[0]['geometry'],
              'source_image':pages[0]['source_image'],'route':{'detected_layout':'multi_page' if len(pages)>1 else pages[0]['route'].get('detected_layout','unknown'),'page_count':len(pages)},
              'corrections':{'review_flags':flags,'reference_input':False,'page_join':'actual XML extent including rests; no bar rounding','tempo_policy':'first-page global BPM'}}
    temp=output/'result.tmp'; temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); temp.replace(output/'result.json')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('manifest',type=Path); p.add_argument('--output',required=True,type=Path)
    a=p.parse_args(); assemble(a.manifest,a.output)
