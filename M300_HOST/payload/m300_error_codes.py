# SPDX-License-Identifier: GPL-3.0-or-later
"""Classic M300 1.3.1 error vocabulary; presentation never detects a fault.

Keep ambiguous hardware diagnoses unnumbered. In particular PE15 does not
prove which platform connector failed, and an ADC rail does not prove heat.
"""
import json
import logging
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name('m300_error_codes.json').read_text())
CODES = {item['code']: item for item in CATALOG['codes']}
KINDS = {item['kind']: item for item in CATALOG['native']}
NONE, SHUTDOWN, TIMER, STEPPER, LINK, ESTOP, PLATFORM, SENSOR, GUARD = range(9)


def clean(value, limit=240):
    return ' '.join(str(value or '').replace('|', '/').split())[:limit]


def descriptor(code=0, kind=SHUTDOWN, *, fatal=True):
    meta = CODES[code] if code in CODES else KINDS.get(kind, KINDS[SHUTDOWN])
    if not code and kind == SHUTDOWN and not fatal:
        # An unnumbered operational notice does not assert a native shutdown.
        return dict(meta, title='Procedure failed', oled='Procedure failed',
                    action='Read the original cause, correct it, then repeat the procedure.',
                    hint=['Check original cause', 'Repeat when ready'])
    return meta


def classify(reason, source='', fatal=False):
    """Return (OEM code or 0, native kind), or None for unrelated input errors.

    Exact, typed owner reports take precedence over this conservative adapter
    for native Klipper messages. Never infer a broken cable from any failure.
    """
    text = clean(reason, 2048).lower().replace('_', ' ').replace('-', ' ')
    origin = source.lower()
    if origin == 'm300_models':
        if text.startswith('wrong model family'):
            return 76, NONE
        if text.startswith('required firmware is newer'):
            return 40, NONE
        return 3, NONE
    if origin == 'm300_sd':
        return (4 if 'timeout' in text or 'read failed' in text else 2), NONE
    if text in ('unable to get file list', 'unable to open file'):
        return 2, NONE
    if text == 'pid calibrate interrupted':
        return 0, SHUTDOWN
    if any(s in text for s in ('timer too close', 'rescheduled timer in the past')):
        return 0, TIMER
    if 'stepper too far in past' in text or 'step timer' in text:
        return 0, STEPPER
    if 'm112' in text or 'shutdown due to emergency' in text:
        return 0, ESTOP
    if any(s in text for s in ('lost communication with mcu', 'heartbeat',
                                'klipper disconnected', 'connection lost')):
        return 0, LINK
    if 'small' in text and ('platform connector' in text or 'platform small connector' in text):
        return 30, NONE
    if 'large' in text and ('platform connector' in text or 'platform large connector' in text):
        return 31, NONE
    if 'platform connector' in text or 'platform cable' in text:
        return 0, PLATFORM
    if 'main extruder cable' in text or 'extruder ribbon connection' in text:
        return 32, NONE
    if 'extruder gear' in text or 'filament jam confirmed' in text:
        return 35, NONE
    if 'perforated plate contacts' in text:
        return 33, NONE
    hot = 'extruder' in text or 'hotend' in text or 'nozzle' in text
    bed = 'heater bed' in text or 'heatbed' in text or 'bed thermistor' in text
    if any(s in text for s in ('thermistor', 'adc out of range', 'adc stale',
                                'adc raw range', 'temperature sensor', 'invalid adc')):
        return (15 if hot else 14 if bed else 0), SENSOR
    if any(s in text for s in ('overheat', 'overtemp', 'maximum temperature', 'max temp')):
        return (12 if bed else 11 if hot else 0), SENSOR
    if hot and any(s in text for s in ('unexpected', 'temperature drop')) and 'drop' in text:
        return 13, NONE
    if hot and any(s in text for s in ('not heating', 'heating failed', 'heating timeout',
                                      'heating timed out')):
        return 10, NONE
    if any(s in text for s in ('endstop', 'no trigger on x', 'no trigger on y')):
        # Z contact probing is distinct from XY endstop diagnosis.
        if not any(s in text for s in ('stepper z', 'probe', 'pc7')):
            return 34, NONE
    if any(s in text for s in ('probing failed', 'probe failed', 'no trigger on probe',
                                'pc7', 'no release', 'contact remained', 'nozzle contact',
                                'no trigger on stepper z', 'endstop stepper z still triggered',
                                'native probe returned an invalid position',
                                'contact lies outside the usable z search range',
                                'outside native z search window',
                                'probe did not', 'probe triggered', 'precision z reference failed')):
        return 42, NONE
    if 'calibration' in origin or any(s in text for s in
            ('calibration failed', 'calibration: ', 'bed span is too large',
             'too many invalid samples', 'adjustment limit')):
        return 41, NONE
    if any(s in text for s in ('wrong model family', 'different printer model')):
        return 76, NONE
    if 'required firmware is newer' in text or 'update the firmware' in text:
        return 40, NONE
    if 'newer z suite' in text or 'z suite version' in text:
        return 75, NONE
    if 'no models on sd' in text:
        return 101, NONE
    if 'sd' in origin or 'sd card' in text or text.startswith('m300 sd:'):
        return (4 if 'timeout' in text or 'read failed' in text else 2), NONE
    if 'model snapshot read failed' in text:
        return 4, NONE
    if 'models' in origin or any(s in text for s in
            ('crc mismatch', 'invalid record', 'truncated record', 'record count mismatch',
             'zcode header', 'zcode record', 'binary rejected')):
        return 3, NONE
    return (0, SHUTDOWN) if fatal else None


def identity(record):
    if record.get('code'):
        prefix = 'Notice' if record.get('severity') == 'info' and not record.get('fatal') else 'Error'
        return '%s #%03d' % (prefix, record['code'])
    return 'Klipper error'


def report(printer, reason, *, source, code=None, kind=NONE, fatal=False):
    """Explicit fault sink; reporting must never interrupt safety cleanup.

    Owners call this only for an actual failed operation. Input rejections
    remain ordinary command errors. The same exception retains its first
    typed diagnosis across nested SD/import/procedure boundaries.
    """
    try:
        service = printer.lookup_object('m300_errors', None)
        if service is None:
            return None
        exception = reason if isinstance(reason, BaseException) else None
        previous = getattr(exception, '_m300_error_id', None)
        current = getattr(service, 'current', None)
        if current and previous == current['id']:
            if current['fatal'] or not fatal:
                return current
            code, kind, reason = current['code'], current['kind'], current['reason']
        if code is None:
            found = classify(reason, source, fatal)
            code, kind = found if found is not None else (0, SHUTDOWN)
        record = service.record(reason, source=source, code=code, kind=kind, fatal=fatal)
        if exception is not None and isinstance(record, dict):
            exception._m300_error_id = record['id']
        return record
    except Exception:
        logging.exception('M300 fault report unavailable; owner safety cleanup continues')
        return None
