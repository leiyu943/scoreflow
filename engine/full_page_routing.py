"""Whole-page, pixel-only masking and the new mixed -> staff experiment route."""
import argparse
import json
from pathlib import Path
from PIL import Image
from score_image_routing import detect_staffs

def prepare_page(image,dest):
    image=Path(image);dest=Path(dest)
    dest.mkdir(parents=True,exist_ok=True)
    _,_,staffs=detect_staffs(image)
    staffs.sort(key=lambda r:r['lines'][0])
    kinds={r['kind'] for r in staffs}
    if not kinds:raise ValueError('No reliable staff detected; manual review required')
    layout='mixed_5_6' if kinds=={'staff','tab'} else 'five_only' if kinds=={'staff'} else 'six_only'
    with Image.open(image) as source:original=source.convert('RGB')
    # Page dimensions and symbol coordinates are preserved. No crop/resize.
    original_path=dest/'original_page.png'
    if image.resolve()!=original_path.resolve():original.save(original_path)
    outputs={'original':str(original_path)}
    audits={}
    if layout=='mixed_5_6':
        from whole_page_mask import create_mask
        from collections import Counter
        for kind in ('staff','tab'):
            masked,audit=create_mask(original,staffs,kind)
            path=dest/(kind+'_masked_page.png');masked.save(path)
            _,_,after=detect_staffs(path)
            expected=sum(s['kind']==kind for s in staffs)
            if Counter(s['kind'] for s in after)!=Counter({kind:expected}):
                raise ValueError('Mask staff count changed; manual review required')
            outputs[kind+'_mask']=str(path);audits[kind]=audit
    selected=outputs['staff_mask'] if layout=='mixed_5_6' else outputs['original']
    route={'layout':layout,'engine':'homr' if 'staff' in kinds else 'tabbox',
           'selected_input':selected,'images':outputs,'size':list(original.size),
           'staffs':staffs,'mask_audit':audits,'crop_used':False,
           'mixed_policy':'whole page with TAB whitened -> five-line HOMR -> rules',
           'tab_model_invoked_for_mixed':False,'reference_used_for_routing':False,
           'execution_phase':'staff baseline first; TAB correction/training deferred'}
    (dest/'routing.json').write_text(json.dumps(route,ensure_ascii=False,indent=2),encoding='utf-8')
    return route

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('image',type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();print(json.dumps(prepare_page(a.image,a.output),ensure_ascii=True))

