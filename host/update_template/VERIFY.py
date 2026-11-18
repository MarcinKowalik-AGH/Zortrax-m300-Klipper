#!/usr/bin/env python3
# Marcin Kowalik <mkowalik@agh.edu.pl>
import json
from install import verify

print(json.dumps({'status': 'PASS_M300_HOST_PACKAGE',
                  'files_verified': verify()}))
