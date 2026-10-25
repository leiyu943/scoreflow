"""Image-only routing, derived from frozen mixed smoke v1; Unicode-safe I/O."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from staff_barline_filter import reliable_staff_barlines

def save(path, payload):
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

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
    image = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
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

def visual_barlines(ink, staff):
    lines, spacing = staff['lines'], staff['spacing']
    band = ink[lines[0]:lines[-1] + 1]
    vertical = cv2.morphologyEx(band, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(3, round(band.shape[0] * .95)))))
    xs = clusters(np.where((vertical > 0).sum(axis=0) >= band.shape[0] * .90)[0], max(3, spacing * .5))
    xs = [x for x in xs if staff['left'] - spacing * .25 <= x <= staff['right'] + spacing * .25]
    if not xs or xs[0] > staff['left'] + spacing:
        xs.insert(0, staff['left'])
    if xs[-1] < staff['right'] - spacing:
        xs.append(staff['right'])
    return clusters(xs, max(3, spacing * .5))

def route_and_crop(image_path, dest):
    gray, ink, staffs = detect_staffs(image_path)
    tabs = [s for s in staffs if s['kind'] == 'tab']
    has_staff = any(s['kind'] == 'staff' for s in staffs)
    route = {'detected_layout': 'mixed_5_6' if tabs and has_staff else 'six_only' if tabs else 'five_only' if has_staff else 'unknown',
             'selected_engine': 'tabbox' if tabs else None,
             'selection_rule': 'if any six-line staff is detected, process TAB only',
             'staff_model_invoked': False, 'geometry_source': 'input image pixels only',
             'staffs': staffs, 'systems': [], 'barline_filter_version': 'attached_glyph_v2'}
    preview = Image.open(image_path).convert('RGB')
    draw = ImageDraw.Draw(preview)
    for index, tab in enumerate(tabs):
        lines, spacing = tab['lines'], tab['spacing']
        top = max(0, round(lines[0] - 2.8 * spacing))
        bottom = min(gray.shape[0], round(lines[-1] + 3 * spacing))
        above = [s['lines'][-1] for s in staffs if s['lines'][-1] < lines[0]]
        below = [s['lines'][0] for s in staffs if s['lines'][0] > lines[-1]]
        if above:
            top = max(top, round((max(above) + lines[0]) / 2))
        if below:
            bottom = min(bottom, round((min(below) + lines[-1]) / 2))
        left = max(0, tab['left'] - 20)
        right = min(gray.shape[1], tab['right'] + 21)
        # Pixel geometry only. A paired five-line staff may supply missing
        # vertical boundaries, but contributes no recognized musical content.
        tab_bars = visual_barlines(ink, tab)
        bar_x = list(tab_bars)
        staff_bars, raw_staff_bars, added, paired = [], [], [], None
        candidates = [s for s in staffs if s['kind'] == 'staff' and s['lines'][-1] < lines[0]]
        if candidates:
            candidate = max(candidates, key=lambda s: s['lines'][-1])
            between = [s for s in staffs if candidate['lines'][-1] < s['lines'][0] < lines[0]]
            if not between:
                raw_staff_bars = visual_barlines(ink, candidate)
                staff_bars = reliable_staff_barlines(ink,candidate,raw_staff_bars,tab)
                tolerance = max(spacing, candidate['spacing']) * .65
                # Both system endpoints must agree before borrowing boundaries;
                # otherwise this may be an unrelated staff/instrument.
                if staff_bars and abs(staff_bars[0] - tab_bars[0]) <= tolerance and abs(staff_bars[-1] - tab_bars[-1]) <= tolerance:
                    paired = candidate['lines']
                    for x in staff_bars[1:-1]:
                        if not any(abs(x - other) <= tolerance for other in tab_bars):
                            bar_x.append(x)
                            added.append(x)
                    bar_x.sort()
        crop = dest / f'tab_system_{index + 1}.png'
        preview.crop((left, top, right, bottom)).save(crop)
        draw.rectangle((left, top, right, bottom), outline='green', width=3)
        for x in bar_x:
            draw.line((x, top, x, bottom), fill='red', width=2)
        draw.text((left + 5, top + 2), f'TAB {index + 1}', fill='green')
        route['systems'].append({'index': index + 1, 'crop': str(crop),
                                 'bbox': [left, top, right, bottom], 'barlines_x': bar_x,
                                 'tab_barlines_x': tab_bars, 'paired_five_line_staff': paired,
                                 'five_line_barlines_x': staff_bars, 'staff_assisted_barlines_x': added,
                                 'five_line_barlines_raw_x': raw_staff_bars,
                                 'segmentation_needs_review': bool(added),
                                 'visual_segments': [{'index': i + 1, 'left': a, 'right': b}
                                                     for i, (a, b) in enumerate(zip(bar_x, bar_x[1:]))]})
    preview.save(dest / 'routing_preview.png')
    save(dest / 'routing.json', route)
    if not tabs:
        raise RuntimeError('No six-line staff detected; TAB smoke test declines this image.')
    return route
