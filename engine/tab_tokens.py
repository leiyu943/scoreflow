"""Extracted inference-only TAB parsing and pixel staff detection."""
from fractions import Fraction
import re
from pathlib import Path
import cv2
import numpy as np
TUNING = {1:64,2:59,3:55,4:50,5:45,6:40}

def clusters(values, gap):
    groups = []
    for value in values:
        value = int(value)
        if not groups or value - groups[-1][-1] > gap:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [int(round(sum(g) / len(g))) for g in groups]

def detect_staffs(image_path):
    """Detect five/six parallel lines from raster pixels only."""
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError('Cannot read image ' + str(image_path))
    ink = cv2.threshold(image, 205, 255, cv2.THRESH_BINARY_INV)[1]
    width = image.shape[1]
    # Short line fragments still count when fret digits interrupt a string;
    # do not bridge noteheads/beams into additional fictitious staff lines.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(16, min(40, width // 35)), 1))
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    span_horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                                     cv2.getStructuringElement(cv2.MORPH_RECT, (max(24, width // 20), 1)))
    centers = clusters(np.where((horizontal > 0).sum(axis=1) > width * .25)[0], 3)
    staffs, used = [], set()
    for index in range(len(centers)):
        if index in used:
            continue
        for count in (6, 5):
            lines = centers[index:index + count]
            if len(lines) != count:
                continue
            gaps = np.diff(lines)
            spacing = float(np.median(gaps))
            if spacing < 4 or np.max(np.abs(gaps - spacing)) > max(2, spacing * .20):
                continue
            # A five-line subset of a six-line staff must never become a staff.
            if index + count < len(centers) and abs(centers[index + count] - lines[-1] - spacing) < max(2, spacing * .2):
                continue
            coverage = (span_horizontal[lines] > 0).sum(axis=0)
            # Fret digits erase short horizontal pieces near the right edge.
            # Requiring almost every string clips valid end-of-system notes.
            xs = np.where(coverage >= 3)[0]
            if not len(xs):
                continue
            staffs.append({'kind': 'tab' if count == 6 else 'staff', 'lines': lines,
                           'spacing': spacing, 'left': int(xs[0]), 'right': int(xs[-1])})
            used.update(range(index, index + count))
            break
    return image, ink, staffs

def token_bars(tokens):
    """Decode exact beat fractions; never stretch notes to fill a visual bar."""
    bars, current, beat = [], None, None
    meter = None
    def commit():
        nonlocal beat
        if beat is None or current is None:
            return
        duration = Fraction(4, beat['denominator']) * sum((Fraction(1, 2)**i for i in range(beat['dots'] + 1)), Fraction()) * beat['tuplet']
        for string, fret in beat['notes']:
            current['notes'].append({'offset': str(current['_position']), 'duration': str(duration),
                                     'string': string, 'fret': fret,
                                     'pitch': TUNING[string] + fret if isinstance(fret, int) else None})
        current['_position'] += duration
        beat = None
    for token in tokens:
        if token.startswith('TS_'):
            values = token.split('_')[1:]
            if len(values) == 2:
                meter = [int(v) for v in values]
                if current is not None:
                    current['meter'] = meter
        elif token == 'BAR':
            if current is not None:
                raise ValueError('Nested BAR token')
            current = {'index': len(bars) + 1, 'meter': meter, 'notes': [], '_position': Fraction()}
        elif token == 'BEAT':
            commit()
        elif token.startswith('DUR_'):
            beat = {'denominator': int(token[4:]), 'dots': 0, 'tuplet': Fraction(1), 'notes': []}
        elif token.startswith('DOTS_') and beat is not None:
            beat['dots'] = int(token[5:])
        elif token.startswith('TUPLET_') and beat is not None:
            actual, normal = map(int, token.split('_')[1:])
            beat['tuplet'] = Fraction(normal, actual)
        elif re.fullmatch(r'N_S[1-6]_F(?:\d+|X)', token) and beat is not None:
            string, fret = token.split('_')[1:]
            beat['notes'].append((7 - int(string[1:]), 'X' if fret[1:] == 'X' else int(fret[1:])))
        elif token == 'END_BAR':
            commit()
            if current is None:
                raise ValueError('END_BAR without BAR')
            current['duration'] = str(current.pop('_position'))
            bars.append(current)
            current = None
    if current is not None:
        raise ValueError('Unclosed TAB measure')
    return bars
