"""Reference-free score events and exports. Times are rational quarter notes."""
from fractions import Fraction
from math import lcm
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

TUNING = {1:64, 2:59, 3:55, 4:50, 5:45, 6:40}


def guitar_playback_transposition(path):
    """Ordinary guitar G clef sounds an octave down; avoid double shifting G8."""
    root=ET.parse(path,parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))).getroot()
    parts=root.findall('part')
    if len(parts)!=1 or root.find('.//transpose') is not None:return {'applied':False,'reason':'existing transposition or multiple parts'}
    clefs=root.findall('.//clef')
    if not clefs or any(c.findtext('sign')!='G' or c.findtext('line')!='2' or int(c.findtext('clef-octave-change') or 0)!=0 for c in clefs):return {'applied':False,'reason':'octave/other clef already represented'}
    first=parts[0].find('measure')
    if first is None:return {'applied':False,'reason':'no measures'}
    a=first.find('attributes')
    if a is None:a=ET.Element('attributes');first.insert(0,a)
    tr=ET.SubElement(a,'transpose');ET.SubElement(tr,'diatonic').text='0';ET.SubElement(tr,'chromatic').text='0';ET.SubElement(tr,'octave-change').text='-1'
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    return {'applied':True,'semitones':-12,'source':'guitar application convention for ordinary G clef; no reference file'}


def override_xml_meter(path,meter):
    root=ET.parse(path,parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))).getroot()
    for part in root.findall('part'):
        measures=part.findall('measure')
        if not measures:continue
        first=measures[0].find('attributes')
        if first is None:first=ET.Element('attributes');measures[0].insert(0,first)
        for a in part.findall('.//attributes'):
            for t in list(a.findall('time')):a.remove(t)
        t=ET.SubElement(first,'time');ET.SubElement(t,'beats').text=str(meter[0]);ET.SubElement(t,'beat-type').text=str(meter[1])
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)


def xml_score(path,merge_ties=True):
    root = ET.parse(path, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))).getroot()
    for el in root.iter():
        if isinstance(el.tag, str): el.tag = el.tag.rsplit('}', 1)[-1]
    events, meters, positions = [], [], []
    bpm = 120
    for part in root.findall('part'):
        base, divisions, meter, transpose = Fraction(), 1, None, 0
        tied = {}
        for mi, measure in enumerate(part.findall('measure')):
            clock, previous, end = Fraction(), Fraction(), Fraction()
            for el in measure:
                if el.tag == 'attributes':
                    divisions = int(el.findtext('divisions') or divisions)
                    tr = el.find('transpose')
                    if tr is not None: transpose = int(tr.findtext('chromatic') or 0) + 12*int(tr.findtext('octave-change') or 0)
                    t = el.find('time')
                    if t is not None:
                        try: current = [int(t.findtext('beats')), int(t.findtext('beat-type'))]
                        except (TypeError, ValueError): current = None
                        if current and current != meter:
                            meter = current
                            if not any(m['start']==str(base) and m['meter']==meter for m in meters): meters.append({'start':str(base),'meter':meter})
                elif el.tag in {'backup','forward'}:
                    clock += Fraction(int(el.findtext('duration') or 0), divisions) * (-1 if el.tag=='backup' else 1)
                    end = max(end, clock)
                elif el.tag == 'direction':
                    sound = el.find('sound')
                    if sound is not None and sound.get('tempo'): bpm = float(sound.get('tempo'))
                elif el.tag == 'note':
                    if el.find('grace') is not None: continue
                    duration = Fraction(int(el.findtext('duration') or 0), divisions)
                    onset = previous if el.find('chord') is not None else clock
                    if el.find('chord') is None: previous, clock = onset, clock+duration
                    end = max(end, onset+duration)
                    pitch = el.find('pitch')
                    if pitch is None or duration <= 0: continue
                    value = 12*(int(pitch.findtext('octave'))+1)+{'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}[pitch.findtext('step')]+int(pitch.findtext('alter') or 0)+transpose
                    event={'pitch':value,'start':str(base+onset),'duration':str(duration),'velocity':80,'bar':mi+1,'part':part.get('id'),'staff':int(el.findtext('staff') or 1)}
                    coord = next((re.search(r'imgpos:\s*([\d.-]+),\s*([\d.-]+)', c.text or '') for c in el if c.tag is ET.Comment and 'imgpos:' in (c.text or '')),None)
                    if coord: event['image_xy']=[float(coord[1]),float(coord[2])]
                    ties={t.get('type') for t in el.findall('tie')}
                    key=(el.findtext('voice') or '1',event['staff'],value)
                    preceding=tied.get(key)
                    if merge_ties and preceding is not None and ties & {'stop','continue'} and Fraction(event['start'])==Fraction(preceding['start'])+Fraction(preceding['duration']):
                        preceding['duration']=str(Fraction(preceding['duration'])+duration)
                        if not ties & {'start','continue'}:tied.pop(key,None)
                    else:
                        events.append(event)
                        if ties & {'start','continue'}:tied[key]=event
                        else:tied.pop(key,None)
            base += end if end else Fraction(meter[0]*4,meter[1]) if meter else Fraction()
    events.sort(key=lambda e:(Fraction(e['start']),e['pitch']))
    return events, sorted(meters,key=lambda m:Fraction(m['start'])), bpm


def tab_events(bars):
    events, meters, base, previous = [], [], Fraction(), None
    for bar in bars:
        meter=bar.get('meter')
        if meter and meter!=previous:
            meters.append({'start':str(base),'meter':meter}); previous=meter
        for n in bar['notes']:
            if n.get('pitch') is not None:
                events.append(dict(n,start=str(base+Fraction(n['offset'])),bar=bar['index'],velocity=80))
        base += Fraction(bar['duration'])
    return sorted(events,key=lambda e:(Fraction(e['start']),e['pitch'])), meters


def vlq(value):
    value=int(value); result=[value&127]; value >>= 7
    while value: result.insert(0,(value&127)|128); value >>= 7
    return bytes(result)


def write_event_midi(path,events,meters=(),bpm=120,end_beat=None):
    ticks=960; rows=[]
    for m in meters:
        n,d=m['meter']
        if not 0<n<256 or d<=0 or d&(d-1): raise ValueError('Invalid MIDI meter')
        rows.append((round(Fraction(m['start'])*ticks),-2,bytes([255,88,4,n,d.bit_length()-1,24,8])))
    for n in events:
        pitch=int(n['pitch'])
        if not 0<=pitch<=127: raise ValueError('MIDI pitch outside 0..127')
        start=round(Fraction(n['start'])*ticks); end=round((Fraction(n['start'])+Fraction(n['duration']))*ticks)
        if start<0 or end<=start: raise ValueError('Invalid note time')
        rows.extend([(start,1,bytes([144,pitch,max(1,min(127,int(n.get('velocity',80))))])),(end,0,bytes([128,pitch,0]))])
    tempo=round(60000000/max(20,min(300,float(bpm))))
    data=bytearray(b'\x00\xff\x51\x03'+tempo.to_bytes(3,'big')+b'\x00\xc0\x18'); previous=0
    for tick,_,msg in sorted(rows): data.extend(vlq(tick-previous)+msg); previous=tick
    final_tick=max(previous,round(Fraction(end_beat)*ticks)) if end_beat is not None else previous
    data.extend(vlq(final_tick-previous)+b'\xff\x2f\x00')
    Path(path).write_bytes(b'MThd'+struct.pack('>IHHH',6,0,1,ticks)+b'MTrk'+struct.pack('>I',len(data))+data)


def tab_musicxml(path,bars):
    """Keep actual decoded timing, strings/frets and rests; no bar stretching."""
    root=ET.Element('score-partwise',version='4.0'); pl=ET.SubElement(root,'part-list')
    sp=ET.SubElement(pl,'score-part',id='P1'); ET.SubElement(sp,'part-name').text='Guitar TAB'
    part=ET.SubElement(root,'part',id='P1'); previous=None
    for bar in bars:
        m=ET.SubElement(part,'measure',number=str(bar['index']))
        denominators=[Fraction(n[k]).denominator for n in bar['notes'] for k in ('offset','duration')]+[Fraction(bar['duration']).denominator]
        div=lcm(960,*denominators); a=ET.SubElement(m,'attributes'); ET.SubElement(a,'divisions').text=str(div)
        if bar.get('meter') and bar['meter']!=previous:
            previous=bar['meter']; t=ET.SubElement(a,'time'); ET.SubElement(t,'beats').text=str(previous[0]); ET.SubElement(t,'beat-type').text=str(previous[1])
        if bar['index']==1:
            c=ET.SubElement(a,'clef'); ET.SubElement(c,'sign').text='TAB'; ET.SubElement(c,'line').text='5'
            details=ET.SubElement(a,'staff-details'); ET.SubElement(details,'staff-lines').text='6'
        cursor=Fraction();last_onset=None
        for n in sorted(bar['notes'],key=lambda n:(Fraction(n['offset']),n['string'])):
            onset=Fraction(n['offset']); duration=Fraction(n['duration'])
            chord=onset==last_onset
            if not chord and onset!=cursor:
                el=ET.SubElement(m,'forward' if onset>cursor else 'backup'); ET.SubElement(el,'duration').text=str(int(abs(onset-cursor)*div))
            el=ET.SubElement(m,'note')
            if chord:ET.SubElement(el,'chord')
            if n['pitch'] is None:
                unpitched=ET.SubElement(el,'unpitched');ET.SubElement(unpitched,'display-step').text='E';ET.SubElement(unpitched,'display-octave').text='4'
            else:
                pitch=ET.SubElement(el,'pitch'); pc=int(n['pitch'])%12
                step,alter=[('C',0),('C',1),('D',0),('D',1),('E',0),('F',0),('F',1),('G',0),('G',1),('A',0),('A',1),('B',0)][pc]
                ET.SubElement(pitch,'step').text=step
                if alter: ET.SubElement(pitch,'alter').text=str(alter)
                ET.SubElement(pitch,'octave').text=str(int(n['pitch'])//12-1)
            ET.SubElement(el,'duration').text=str(int(duration*div))
            notation=None
            for actual,normal in [(1,1),(3,2),(5,4),(6,4),(7,4),(9,8),(10,8),(11,8),(12,8)]:
                for den,name in {1:'whole',2:'half',4:'quarter',8:'eighth',16:'16th',32:'32nd',64:'64th'}.items():
                    for dots in range(3):
                        if Fraction(4,den)*sum((Fraction(1,2)**i for i in range(dots+1)),Fraction())*Fraction(normal,actual)==duration:
                            notation=(name,dots,actual,normal);break
                    if notation:break
                if notation:break
            if notation:
                name,dots,actual,normal=notation;ET.SubElement(el,'type').text=name
                for _ in range(dots):ET.SubElement(el,'dot')
                if actual!=1:
                    tm=ET.SubElement(el,'time-modification');ET.SubElement(tm,'actual-notes').text=str(actual);ET.SubElement(tm,'normal-notes').text=str(normal)
            if n['pitch'] is None:ET.SubElement(el,'notehead').text='x'
            tech=ET.SubElement(ET.SubElement(el,'notations'),'technical'); ET.SubElement(tech,'string').text=str(n['string'])
            if isinstance(n['fret'],int):ET.SubElement(tech,'fret').text=str(n['fret'])
            cursor=max(cursor,onset+duration) if chord else onset+duration;last_onset=onset
        if cursor<Fraction(bar['duration']):
            el=ET.SubElement(m,'forward'); ET.SubElement(el,'duration').text=str(int((Fraction(bar['duration'])-cursor)*div))
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
