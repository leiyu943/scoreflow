"""Image-only octave-clef recognition and conservative token rhythm repair.

The inference functions accept pixels, a frozen glyph model and predicted tokens.
They do not accept source MusicXML, references, sample IDs, MIDI or split labels.
"""
import copy
from collections import Counter, defaultdict
from fractions import Fraction
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
import numpy as np

from tab_tokens import detect_staffs


def read_gray(path):
    value = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if value is None:
        raise ValueError('Unreadable image')
    return value


class OctaveClefDetector:
    def __init__(self, model_dir):
        self.model_dir = Path(model_dir)
        self.config = json.loads((self.model_dir / 'detector.json').read_text(encoding='utf-8'))
        self.core = read_gray(self.model_dir / 'g_core.png')
        self.eight = read_gray(self.model_dir / 'eight.png')

    def scores(self, image_path):
        gray, ink, staffs = detect_staffs(image_path)
        if len(staffs) != 1 or staffs[0]['kind'] != 'staff':
            return {'status': 'unsupported', 'reason': 'requires exactly one five-line staff'}
        staff = staffs[0]
        space = staff['spacing']
        left = max(0, round(staff['left'] - space))
        right = min(gray.shape[1], round(staff['left'] + 15 * space))
        top = max(0, round(staff['lines'][0] - 4 * space))
        bottom = min(gray.shape[0], round(staff['lines'][-1] + 4 * space))
        crop = gray[top:bottom, left:right]
        ratio = self.config['normalized_staff_space'] / space
        crop = cv2.resize(crop, (round(crop.shape[1] * ratio), round(crop.shape[0] * ratio)), interpolation=cv2.INTER_CUBIC)
        best = None
        for scale in self.config['template_scales']:
            core = cv2.resize(self.core, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            if crop.shape[0] < core.shape[0] or crop.shape[1] < core.shape[1]:
                continue
            match = cv2.matchTemplate(crop, core, cv2.TM_CCOEFF_NORMED)
            _, score, _, point = cv2.minMaxLoc(match)
            if best is None or score > best[0]:
                best = score, point, scale
        if best is None:
            return {'status': 'unsupported', 'reason': 'image too small'}
        core_score, (x, y), scale = best
        dx, dy = self.config['eight_offset_from_core']
        ex, ey = round(x + dx * scale), round(y + dy * scale)
        eight = cv2.resize(self.eight, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        jitter = self.config['eight_search_jitter']
        x1, y1 = max(0, ex-jitter), max(0, ey-jitter)
        x2, y2 = min(crop.shape[1], ex+eight.shape[1]+jitter), min(crop.shape[0], ey+eight.shape[0]+jitter)
        search = crop[y1:y2, x1:x2]
        if search.shape[0] < eight.shape[0] or search.shape[1] < eight.shape[1]:
            return {'status': 'unsupported', 'reason': 'octave mark outside image'}
        _, score, _, mark = cv2.minMaxLoc(cv2.matchTemplate(search, eight, cv2.TM_CCOEFF_NORMED))
        return {'status': 'scored', 'core_score': float(core_score), 'eight_score': float(score),
                'template_scale': float(scale), 'staff_spacing': space,
                'clef_bbox_pixels': [round(left+x/ratio), round(top+y/ratio),
                    round(left+(x+self.core.shape[1]*scale)/ratio), round(top+(y+self.core.shape[0]*scale)/ratio)],
                'mark_bbox_pixels': [round(left+(x1+mark[0])/ratio), round(top+(y1+mark[1])/ratio),
                    round(left+(x1+mark[0]+eight.shape[1])/ratio), round(top+(y1+mark[1]+eight.shape[0])/ratio)]}

    def predict(self, image_path):
        result = self.scores(image_path)
        if result['status'] != 'scored':
            return dict(result, octave=None)
        if result['core_score'] < self.config['minimum_core_score']:
            return dict(result, octave=None, decision='abstain: unfamiliar clef appearance')
        if result['eight_score'] >= self.config['positive_threshold']:
            return dict(result, octave=-1, decision='visible lower-octave 8')
        if result['eight_score'] <= self.config['negative_threshold']:
            return dict(result, octave=0, decision='ordinary G clef')
        return dict(result, octave=None, decision='abstain: ambiguous octave mark')


def apply_octave_clef(root, detection):
    result = copy.deepcopy(root)
    target = detection.get('octave')
    if target not in (-1, 0):
        return result, {'applied': False, 'reason': 'detector abstained'}
    parts = result.findall('part')
    if len(parts) != 1 or any(int(s.text) > 1 for s in result.findall('.//staves')):
        return result, {'applied': False, 'reason': 'requires a single staff part'}
    clefs = result.findall('.//attributes/clef')
    if not clefs or any(c.findtext('sign') != 'G' or c.findtext('line') != '2' for c in clefs):
        return result, {'applied': False, 'reason': 'predicted clef is not consistently G2'}
    old = {int(c.findtext('clef-octave-change') or 0) for c in clefs}
    if len(old) != 1:
        return result, {'applied': False, 'reason': 'predicted octave clef changes within staff'}
    previous = old.pop()
    delta = target - previous
    if not delta:
        return result, {'applied': False, 'reason': 'already matches pixel decision', 'octave': target}
    for clef in clefs:
        for value in list(clef.findall('clef-octave-change')):
            clef.remove(value)
        if target:
            ET.SubElement(clef, 'clef-octave-change').text = str(target)
    count = 0
    for octave in result.findall('.//note/pitch/octave'):
        octave.text = str(int(octave.text) + delta)
        count += 1
    return result, {'applied': True, 'octave': target, 'pitch_octave_delta': delta, 'pitched_notes_updated': count}


def measure_end(groups):
    """Simulate the upstream token scheduler using rational whole-note time."""
    from homr.music_xml_generator import _advance_to_next_group
    clock, last_end, sounding = Fraction(0), Fraction(0), []
    for group in groups:
        timed = [s.get_duration().fraction for s in group.symbols if s.rhythm.startswith(('note_', 'rest_'))]
        if not timed:
            continue
        last_end = max(last_end, clock + max(timed))
        advance = _advance_to_next_group(group, clock, sounding)
        clock += advance
        sounding = [end for end in sounding if end > clock]
    return max(clock, last_end)


def repair_triplet_rests(tokens):
    """Repair overlong rests only when repeated predicted bars provide a check.

    No pitched token is changed. A repair must make the complete measure length
    EXACTLY equal to a majority of at least two other predicted measures.
    """
    from homr.music_xml_generator import TupletParser, group_into_chords, split_mixed_chords
    result = copy.deepcopy(tokens)
    groups = split_mixed_chords(group_into_chords(result))
    measures = TupletParser.split_into_measures(groups)
    lengths = [measure_end(m) for m in measures]
    nonempty = [v for v in lengths if v > 0]
    frequencies = Counter(nonempty)
    if not frequencies:
        return result, []
    target, count = frequencies.most_common(1)[0]
    if count < 2 or count * 2 <= len(nonempty):
        return result, []
    changes = []
    for number, (measure, length) in enumerate(zip(measures, lengths), 1):
        if length <= target:
            continue
        triplets = defaultdict(list)
        for group in measure:
            for symbol in group.symbols:
                if symbol.rhythm.startswith('note_'):
                    duration = symbol.get_duration()
                    if duration.actual_notes == 3 and duration.normal_notes == 2 and duration.dots == 0:
                        triplets[symbol.position].append(symbol)
        proposals = []
        for position, notes in triplets.items():
            duration_counts = Counter(n.rhythm for n in notes)
            rhythm, frequency = duration_counts.most_common(1)[0]
            if frequency < 6 or frequency * 4 < len(notes) * 3:
                continue
            unit = next(n.get_duration().fraction for n in notes if n.rhythm == rhythm)
            for group in measure:
                for symbol in group.symbols:
                    if symbol.position != position or not symbol.rhythm.startswith('rest_') or 'm' in symbol.rhythm or 'G' in symbol.rhythm:
                        continue
                    if symbol.get_duration().fraction > unit:
                        proposals.append((symbol, symbol.rhythm, 'rest_' + rhythm.split('_', 1)[1]))
        if not proposals:
            continue
        for symbol, old, new in proposals:
            symbol.rhythm, symbol._duration = new, None
        repaired_end = measure_end(measure)
        if repaired_end != target:
            for symbol, old, new in proposals:
                symbol.rhythm, symbol._duration = old, None
            continue
        changes.append({'predicted_measure': number, 'before_whole_notes': str(length),
            'after_whole_notes': str(repaired_end), 'supporting_predicted_bars': count,
            'rest_changes': [{'old': old, 'new': new, 'position': symbol.position} for symbol, old, new in proposals],
            'pitched_tokens_changed': 0})
    return result, changes
