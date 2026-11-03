#!/usr/bin/env python3
"""Assemble the Orange Pi host update from the checked-out source."""
from project import ROOT, stage_host_update


if __name__ == '__main__':
    print(stage_host_update(ROOT / '.ci/host-update'))
