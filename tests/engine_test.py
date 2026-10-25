"""Headless exports and inference routing tests; no GPU/GUI dependency."""
from fractions import Fraction
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from score_pipeline_core import write_event_midi,tab_events,tab_musicxml,xml_score

class CoreTests(unittest.TestCase):
    def test_midi_is_saved_with_real_notes_and_exact_triplet_ticks(self):
        events=[{'pitch':64,'start':'0','duration':'1/3','velocity':80},{'pitch':67,'start':'1/3','duration':'2/3','velocity':90}]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.mid';write_event_midi(p,events,[{'start':'0','meter':[4,4]}],108)
            data=p.read_bytes();self.assertEqual(data[:4],b'MThd');self.assertEqual(struct.unpack('>H',data[12:14])[0],960)
            self.assertIn(bytes([144,64,80]),data);self.assertIn(bytes([144,67,90]),data);self.assertTrue(data.endswith(b'\x00\xff\x2f\x00'))
    def test_tab_strings_frets_and_tuplets_roundtrip_musicxml(self):
        bars=[{'index':1,'meter':[4,4],'duration':'1','notes':[{'pitch':64,'string':1,'fret':0,'offset':'0','duration':'1/3'},{'pitch':67,'string':1,'fret':3,'offset':'1/3','duration':'2/3'}]}]
        events,meters=tab_events(bars)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.musicxml';tab_musicxml(p,bars);read,_,_=xml_score(p)
            self.assertEqual([Fraction(e['start']) for e in read],[Fraction(0),Fraction(1,3)])
            self.assertEqual([Fraction(e['duration']) for e in read],[Fraction(1,3),Fraction(2,3)])
            root=ET.parse(p).getroot();self.assertEqual(root.findtext('.//technical/fret'),'0')
    def test_no_qt_dependency_in_extracted_engine(self):
        root=Path(__file__).resolve().parents[1]/'engine'
        for f in root.glob('*.py'):
            self.assertNotIn('PyQt',f.read_text(encoding='utf-8'),f.name)
            self.assertNotIn('midi_editor',f.read_text(encoding='utf-8'),f.name)

if __name__=='__main__':unittest.main()
