"""Small bounded if/else rules; no model inference, fitting or reference input.

Input: predicted symbols, optional cached image-clef decision.
Output: corrected MusicXML and a list of applied rules. O(number of symbols).
"""
from collections import Counter
import copy
from fractions import Fraction
import xml.etree.ElementTree as ET

from teacher_image_refinement import apply_octave_clef,repair_triplet_rests
from teacher_timing_candidate import exporter


RULES={
    'octave_clef':'图片确认低八度谱号时修正八度',
    'repeat_empty_bar':'反复起点前没有音符时不生成空小节',
    'duplicate_chord_tone':'同起点同声部完全重复音符去重',
    'triplet_rest':'有多数小节支持时修正过长的三连音休止符',
    'meter_consistency':'至少两个小节支持且没有矛盾候选时修正拍号分子',
    'short_interior_bar':'小节长度证据一致时补齐中间短小节的时间',
}


def deduplicate_chords(tokens):
    result=[]
    seen=set()
    in_chord=False
    removed=0
    for symbol in copy.deepcopy(tokens):
        if symbol.rhythm=='chord':
            in_chord=True
            continue
        if not in_chord:
            seen=set()
        key=(symbol.rhythm,symbol.pitch,symbol.lift,symbol.position,symbol.articulation,symbol.slur)
        exact_duplicate=in_chord and symbol.rhythm.startswith('note_') and key in seen
        if exact_duplicate:
            removed+=1
            in_chord=False
            continue
        if in_chord and result:
            result.append(type(symbol)('chord'))
        result.append(symbol)
        seen.add(key)
        in_chord=False
    return result,removed


def measure_rows(root):
    rows=[]
    for part in root.findall('part'):
        divisions=Fraction(1)
        for measure in part.findall('measure'):
            cursor=last=end=Fraction(0)
            notes=0
            for child in measure:
                if child.tag=='attributes':
                    divisions=Fraction(child.findtext('divisions') or divisions)
                duration=Fraction(child.findtext('duration') or 0)/divisions
                if child.tag=='backup':cursor-=duration
                elif child.tag=='forward':cursor+=duration;end=max(end,cursor)
                elif child.tag=='note':
                    notes+=1
                    chord=child.find('chord') is not None
                    onset=last if chord else cursor
                    if not chord:last=onset;cursor+=duration
                    end=max(end,cursor,onset+duration)
            rows.append({'part':part,'element':measure,'length':end,'cursor':cursor,
                         'divisions':divisions,'notes':notes})
    return rows


def meter_and_short_bar_rules(root):
    """No global time stretching. Existing note onsets/durations are preserved.

    Only add a forward at an interior bar's end. Pickups, final bars, repeat or
    ending boundaries, explicit meter changes and conflicting lengths are kept.
    """
    changes=[]
    flags=[]
    if len(root.findall('part'))!=1:
        return changes,['multiple_parts_require_review']
    times=root.findall('.//attributes/time')
    signatures={(t.findtext('beats'),t.findtext('beat-type')) for t in times}
    if len(signatures)!=1:
        return changes,['missing_or_changing_meter']
    beats,beat_type=next(iter(signatures))
    if not beats or not beat_type or not beats.isdigit() or not beat_type.isdigit():
        return changes,['unsupported_meter']
    denominator=int(beat_type)
    if denominator<=0 or int(beats)<=0:
        return changes,['unsupported_meter']
    rows=[r for r in measure_rows(root) if r['length']>0]
    if len(rows)<3:
        return changes,['insufficient_bar_evidence']
    candidates=Counter(r['length'] for r in rows if (r['length']*denominator/4).denominator==1
        and 1<=r['length']*denominator/4<=12)
    supported=[length for length,count in candidates.items() if count>=2]
    if len(supported)!=1:
        return changes,['conflicting_or_insufficient_bar_lengths']
    target=supported[0]
    support=candidates[target]
    # An isolated short opening bar is a possible pickup and is not evidence
    # against a meter agreed by the following bars.
    comparable=rows[1:] if rows[0]['length']<target else rows
    allowed_gap=Fraction(1) if support>=3 else Fraction(1,2)
    if any(abs(r['length']-target)>allowed_gap for r in comparable):
        return changes,['large_bar_length_disagreement']
    expected=Fraction(int(beats)*4,denominator)
    if expected!=target:
        new_beats=int(target*denominator/4)
        for time in times:time.find('beats').text=str(new_beats)
        changes.append({'rule':'meter_consistency','before':beats+'/'+beat_type,
                        'after':str(new_beats)+'/'+beat_type,'supporting_bars':support})
    for index,row in enumerate(rows):
        gap=target-row['length']
        if gap<=0:
            continue
        if index==0 or index==len(rows)-1:
            flags.append('opening_or_final_short_bar:'+str(index+1))
            continue
        measure=row['element']
        before=rows[index-1]['element']
        after=rows[index+1]['element']
        if any(m.findall('.//repeat') or m.findall('.//ending') for m in (before,measure,after)):
            flags.append('short_bar_near_repeat_or_ending:'+str(index+1))
            continue
        # A whole beat missing can be a real, unrecognized meter change.
        # Never fill it using duration consensus alone, even with three votes.
        if gap>min(allowed_gap,Fraction(1,2)) or measure.get('implicit')=='yes':
            flags.append('ambiguous_short_bar:'+str(index+1))
            continue
        forward=(target-row['cursor'])*row['divisions']
        if forward<=0 or forward.denominator!=1:
            flags.append('short_bar_not_exactly_encodable:'+str(index+1))
            continue
        ET.SubElement(ET.SubElement(measure,'forward'),'duration').text=str(int(forward))
        changes.append({'rule':'short_interior_bar','measure':measure.get('number'),
            'old_quarters':str(row['length']),'new_quarters':str(target),
            'added_quarters':str(gap),'supporting_bars':support,'note_durations_changed':0})
    return changes,flags


def correct_events(staffs,arguments,clef_decision=None,title=''):
    """All decisions depend only on predictions and optional image evidence."""
    changes=[]
    cleaned=[]
    for staff in staffs:
        tokens,count=deduplicate_chords(staff)
        if count:
            changes.append({'rule':'duplicate_chord_tone','removed':count})
        tokens,details=repair_triplet_rests(tokens)
        if details:
            changes.extend(dict(detail,rule='triplet_rest') for detail in details)
        cleaned.append(tokens)
    # Count the known artifact from tokens without generating a second XML.
    removed=0
    for staff in cleaned:
        has_timed_event=False
        for symbol in staff:
            if symbol.rhythm.startswith(('note_','rest_')) or symbol.rhythm=='measureRest':
                has_timed_event=True
            elif symbol.rhythm=='repeatStart':
                if not has_timed_event:removed+=1
                has_timed_event=False
            elif 'barline' in symbol.rhythm or symbol.rhythm.startswith('repeatEnd'):
                has_timed_event=False
    result=exporter().generate_xml(arguments,cleaned,title)
    if removed:
        changes.append({'rule':'repeat_empty_bar','removed':removed})
    if clef_decision is not None:
        result,detail=apply_octave_clef(result,clef_decision)
        if detail['applied']:
            changes.append(dict(detail,rule='octave_clef'))
    details,flags=meter_and_short_bar_rules(result)
    changes.extend(details)
    unknown=sum(s.rhythm.startswith('note_') and s.pitch in ('.','_') for staff in staffs for s in staff)
    if unknown:flags.append('note_without_pitch:'+str(unknown))
    return result,{'changes':changes,'review_flags':sorted(set(flags)),
        'rules_version':'simple_event_rules_v2','reference_input':False}
