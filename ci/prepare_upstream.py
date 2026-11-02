#!/usr/bin/env python3
"""Fetch and verify exactly one pinned public Klipper source archive."""
import argparse
import json
from pathlib import Path
from project import META, pristine_tree, upstream_archive

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive', type=Path)
args = parser.parse_args()
archive = upstream_archive(args.archive)
tree = pristine_tree(archive)
print(json.dumps({'status': 'PINNED_UPSTREAM_VERIFIED',
                  'commit': META['upstream_commit'],
                  'archive_sha256': META['upstream_archive_sha256'],
                  'pristine_tree': str(tree)}))
