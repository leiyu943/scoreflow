import json
from fractions import Fraction
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from assemble import assemble
from score_pipeline_core import xml_score

class PageAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def page(self,name,parts,meter=(4,4),transpose=None):
        folder=self.root/name;folder.mkdir()
        root=ET.Element('score-partwise',version='4.0');pl=ET.SubElement(root,'part-list')
        for pi,items in enumerate(parts):
            pid='P'+str(pi+1);sp=ET.SubElement(pl,'score-part',id=pid);ET.SubElement(sp,'part-name').text='Guitar'
            part=ET.SubElement(root,'part',id=pid);m=ET.SubElement(part,'measure',number='1');a=ET.SubElement(m,'attributes')
            ET.SubElement(a,'divisions').text='960';t=ET.SubElement(a,'time');ET.SubElement(t,'beats').text=str(meter[0]);ET.SubElement(t,'beat-type').text=str(meter[1])
            c=ET.SubElement(a,'clef');ET.SubElement(c,'sign').text='G';ET.SubElement(c,'line').text='2'
            if transpose is not None:tr=ET.SubElement(a,'transpose');ET.SubElement(tr,'chromatic').text=str(transpose)
            for pitch,duration,*ties in items:
                n=ET.SubElement(m,'note')
                if pitch is None:ET.SubElement(n,'rest')
                else:
                    p=ET.SubElement(n,'pitch');ET.SubElement(p,'step').text='C';ET.SubElement(p,'octave').text=str(pitch//12-1)
                    if pitch%12:ET.SubElement(p,'alter').text=str(pitch%12)
                ET.SubElement(n,'duration').text=str(int(Fraction(duration)*960))
                for tie in ties:ET.SubElement(n,'tie',type=tie)
        xml=folder/'score.musicxml';ET.ElementTree(root).write(xml,encoding='utf-8',xml_declaration=True)
        events,meters,bpm=xml_score(xml)
        geo=folder/'geometry.json';geo.write_text('[]')
        data={'events':events,'meters':meters,'bpm':bpm,'image':'fixture.png','source_image':'fixture.png','geometry':str(geo),'musicxml':str(xml),'folder':str(folder),'route':{'detected_layout':'five_only'}}
        result=folder/'result.json';result.write_text(json.dumps(data),encoding='utf-8')
        return {'id':name,'name':name+'.png','result':str(result)}
    def join(self,*pages):
        manifest=self.root/'manifest.json';manifest.write_text(json.dumps({'pages':pages}),encoding='utf-8')
        return assemble(manifest,self.root/'complete')
    def test_trailing_rests_are_preserved_between_pages(self):
        a=self.page('a',[[(60,1),(None,3)]]);b=self.page('b',[[(64,2),(None,2)]])
        r=self.join(a,b)
        self.assertEqual([e['start'] for e in r['events']],['0','4']);self.assertEqual(r['duration'],'8')
        self.assertEqual(r['pages'][1]['start'],'4')
    def test_fractional_pickup_is_not_rounded_to_a_full_bar(self):
        a=self.page('a',[[(60,'1/3'),(62,'1/6')]]);b=self.page('b',[[(64,'1/3')]])
        r=self.join(a,b);self.assertEqual(r['pages'][1]['start'],'1/2');self.assertEqual(r['duration'],'5/6')
        self.assertEqual(Fraction(r['events'][-1]['start']),Fraction(1,2))
    def test_tie_continues_across_page_without_retrigger(self):
        a=self.page('a',[[(60,4,'start')]]);b=self.page('b',[[(60,1,'stop'),(None,3)]])
        r=self.join(a,b);self.assertEqual(len(r['events']),1);self.assertEqual(r['events'][0]['duration'],'5');self.assertEqual(r['duration'],'8')
        self.assertEqual(len(r['pages'][1]['events']),1)
    def test_page_order_controls_musical_order(self):
        a=self.page('a',[[(60,1)]]);b=self.page('b',[[(64,2)]])
        r=self.join(b,a);self.assertEqual([e['pitch'] for e in r['events']],[64,60]);self.assertEqual(r['pages'][1]['start'],'2')
    def test_shorter_part_does_not_pull_next_page_forward(self):
        a=self.page('a',[[(60,4)],[(48,1)]]);b=self.page('b',[[(64,1)],[(52,1)]])
        r=self.join(a,b)
        self.assertEqual(sorted(Fraction(e['start']) for e in r['events'] if e['pitch'] in (64,52)),[Fraction(4),Fraction(4)])
    def test_changed_part_count_keeps_complete_midi(self):
        a=self.page('a',[[(60,4)],[(48,4)]]);b=self.page('b',[[(64,1)]])
        r=self.join(a,b);self.assertEqual(len(r['events']),3);self.assertEqual(r['musicxml'],'');self.assertTrue(Path(r['midi']).is_file())
    def test_page_local_transpose_is_reset(self):
        a=self.page('a',[[(72,1)]],transpose=-12);b=self.page('b',[[(64,1)]])
        r=self.join(a,b);self.assertEqual([e['pitch'] for e in r['events']],[60,64])
    def test_meter_changes_are_offset_to_global_timeline(self):
        a=self.page('a',[[(60,4)]],meter=(4,4));b=self.page('b',[[(64,'3/2')]],meter=(3,8))
        r=self.join(a,b);self.assertEqual(r['meters'],[{'start':'0','meter':[4,4]},{'start':'4','meter':[3,8]}])

if __name__=='__main__':unittest.main()
