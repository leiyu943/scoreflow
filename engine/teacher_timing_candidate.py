"""Load the retained, patched HOMR XML exporter without training dependencies."""
import importlib.util
from pathlib import Path
import sys

_module = None
def exporter():
    global _module
    if _module is None:
        path = Path(__file__).resolve().parent / 'vendor/music_xml_generator.py'
        spec = importlib.util.spec_from_file_location('scoreflow_fixed_repeat_exporter', path)
        _module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = _module
        spec.loader.exec_module(_module)
    return _module
