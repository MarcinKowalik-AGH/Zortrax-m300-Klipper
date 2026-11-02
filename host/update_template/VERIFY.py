#!/usr/bin/env python3
import json
from install import verify

print(json.dumps({'status': 'PASS_M300_HOST_R15_6_OEM_SLEEP_PACKAGE',
                  'files_verified': verify()}))
