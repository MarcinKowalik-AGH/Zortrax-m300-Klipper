"""Use the exact calibration-preserving migration shipped to Orange Pi."""
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('m300_update_profile',
    Path(__file__).resolve().parents[1] / 'host/update_template/m300_profile.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
blocks, split_saved = module.blocks, module.split_saved
convert_text, read_tree = module.convert_text, module.read_tree
