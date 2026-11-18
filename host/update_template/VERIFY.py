#!/usr/bin/env python3
# Marcin Kowalik <mkowalik@agh.edu.pl>
# VERIFY.py - Sprawdza sumy plików pakietu hosta przed zainstalowaniem go na Orange Pi.
import json
from install import verify

print(json.dumps({'status': 'PASS_M300_HOST_PACKAGE',
                  'files_verified': verify()}))
