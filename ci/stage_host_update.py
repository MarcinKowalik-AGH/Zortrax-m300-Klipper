#!/usr/bin/env python3
# Marcin Kowalik <mkowalik@agh.edu.pl>
# stage_host_update.py - Składa katalog instalacyjny hosta z bieżących źródeł i generuje jego manifest.
"""Assemble the Orange Pi host update from the checked-out source."""
from project import ROOT, stage_host_update


if __name__ == '__main__':
    print(stage_host_update(ROOT / '.ci/host-update'))
