#!/usr/bin/env python3
import json
from install import verify

print(json.dumps({'status': 'PASS_M300_HOST_R16_12_NORMAL_UI_PACKAGE',
                  'files_verified': verify()}))
