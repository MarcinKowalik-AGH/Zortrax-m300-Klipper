# Marcin Kowalik <mkowalik@agh.edu.pl>
# m300_release.py - Udostępnia wersję wydania hosta i formatuje informację o wersji oprogramowania MCU.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Public distribution identity; protocol/firmware IDs remain separate."""
import re

VERSION = '1.0.0-rc.30'


def display_mcu_version(raw):
    """Hide development suffixes only in presentation, never in ABI checks."""
    text = str(raw or 'Unavailable')
    match = re.fullmatch(r'(\d+\.\d+\.\d+(?:\.\d+)?)(?:-[A-Za-z0-9_.-]+)?', text)
    return match[1] if match else text
