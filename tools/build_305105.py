"""Build reviewed M300-305-105-R1 sources. Does not contact a printer."""
from pathlib import Path
import hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
R3='b173c37335e45394bce51828f2988e614825b370'
BASE='aee1204f0ba741ca09cf569d6ed3ff2f31ec8ecc'

def main():
    extras=ROOT/'host/klippy/extras';template=ROOT/'host/update_template'
    if not (extras/'m300_temperature_policy.py').exists():
        # Reviewed host-only delta; never imports the old Orca directory.
        files=subprocess.check_output(['git','diff','--name-only',BASE,R3,'--','host','PORT.json'],text=True).splitlines()
        for name in files:
            assert name=='PORT.json' or name.startswith('host/')
            data=subprocess.check_output(['git','show',R3+':'+name])
            p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    mcu=(extras/'m300_mcu.py').read_text()
    assert 'HOT_RAW_MAX = 1941' in mcu and 'BED_RAW_MIN = 1741' in mcu and 'BED_RAW_MAX = 3941' in mcu
    baselines=json.loads((template/'SUPPORTED_BASELINES.json').read_text())
    for name in ('m300_temperature_policy.py','m300_menu.py'):
        p=extras/name;baselines[name]=sorted(set(baselines.get(name,[])+[hashlib.sha256(p.read_bytes()).hexdigest()]))
    (template/'SUPPORTED_BASELINES.json').write_text(json.dumps(baselines,indent=2)+'\n')
    p=extras/'m300_temperature_policy.py';s=p.read_text()
    s=s.replace("REVISION = 'M300-R3-TARGET-LIMITS'", "REVISION = 'M300-305-105-R1'")
    s=s.replace("'extruder': 270.","'extruder': 305.")
    s=s.replace("config.getfloat('hotend_target_max', 270., minval=170., maxval=270.)", "config.getfloat('hotend_target_max', 305., minval=170., maxval=305.)")
    s=s.replace("requested_limits=dict(self.limits), thermal_ceiling_increased=False)","requested_limits=dict(self.limits),\n                    hardware_validation='USER_REPORTED_2026-11-11',\n                    user_reported_targets={'extruder': 305., 'heater_bed': 105.},\n                    automated_hardware_test=False,\n                    independent_mcu_guard_changed=False)")
    start=s.index('"""');end=s.index('"""',start+3)
    s=s[:start]+'"""305/105C normal-operation target policy. User reports successful hardware\noperation2026-11-11; software tests do not claim physical validation.\nSeparate measured-temperature cutoffs310/120 fit the unchanged independent\nMCU ADC guard1941/1741/3941. No PWM, sensor conversion or motion changes.\n"""'+s[end+3:]
    p.write_text(s)
    p=extras/'m300_menu.py';s=p.read_text().replace("range(170, 301, 10) if kind == 'HOTEND'", "sorted(set([*range(170, 301, 10), 305])) if kind == 'HOTEND'");p.write_text(s)
    p=ROOT/'host/config/m300_classic_base.cfg';s=p.read_text()
    s=s.replace('# Stock heater/sensor retained with Micro Swiss M2580; no higher limit is qualified.\nmax_temp: 270','# User-reported305C operation; shutdown310C within unchanged MCU ceiling.\nmax_temp: 310')
    if '[m300_temperature_policy]' not in s:s=s.replace('[m300_io]','[m300_temperature_policy]\nhotend_target_max: 305\nbed_target_max: 105\n\n[m300_io]')
    p.write_text(s)
    p=template/'install.py';s=p.read_text()
    s=s.replace('def plan(root, config, *, organize_config=False):','def plan(root, config, *, organize_config=False, thermal_305105=False):')
    if 'm300_thermal_config.apply_to_plan' not in s:
        s=s.replace('    return [(p, p.read_bytes() if p.exists() else None, data)\n', '    import m300_thermal_config\n    if thermal_305105:\n        m300_thermal_config.apply_to_plan(desired, config, tree)\n    return [(p, p.read_bytes() if p.exists() else None, data)\n')
    s=s.replace('changes = plan(root, config, organize_config=args.organize_config)','changes = plan(root, config, organize_config=args.organize_config, thermal_305105=True)')
    s=s.replace("'host_update': 'R16.12',", "'host_update': 'R16.12 + M300-305-105-R1',\n                  'target_limits': {'extruder': 305, 'heater_bed': 105},\n                  'sensor_shutdown_limits': {'extruder': 310, 'heater_bed': 120},\n                  'hardware_validation': 'USER_REPORTED_2026-11-11',")
    p.write_text(s)
    shutil.copy2(ROOT/'tools/m300_thermal_config.py',template/'m300_thermal_config.py')
    shutil.copy2(ROOT/'tools/test_thermal_305105.py',template/'tests/test_thermal_305105.py')
    meta=json.loads((ROOT/'PORT.json').read_text());meta['self_contained_host_tests']=768
    (ROOT/'PORT.json').write_text(json.dumps(meta,indent=2)+'\n')
    record={'revision':'M300-305-105-R1','operating_target_max':{'extruder':305,'heater_bed':105},'sensor_shutdown_limits':{'extruder':310,'heater_bed':120},'independent_mcu_adc_guard':{'hot_max':1941,'bed_min':1741,'bed_max':3941},'mcu_changed':False,'sensor_conversion_changed':False,'normal_native_operation':True,'hardware_acceptance':{'source':'user statement in conversation','date':'2026-11-11','result':'user confirms305/105 and normal operation','assistant_performed_hardware_test':False,'all_materials_qualified':False},'installed_on_printer_by_this_work':False}
    (ROOT/'docs/en/THERMAL305_ACCEPTANCE.json').write_text(json.dumps(record,indent=2)+'\n')
    guide=('# M300 — normalna praca305/105°C\n\nUżytkownik potwierdził11.11.2026 test305°C hotendu/105°C stołu i normalną pracę. Status USER_REPORTED; nie deklarujemy własnego testu sprzętowego ani testów wszystkich filamentów.\n\nNastawy305/105; odcięcia czujników310/120. Niezależne limity ADC MCU1941/1741/3941 bez zmian, bez flashowania MCU. Przeliczniki czujników, PID, prędkości, przyspieszenia, homing180°C, makra i grafiki pozostają. Natywne grzanie/ruch działają jak wcześniej. OLED oferuje305/105; Fluidd może pokazywać próg awaryjny310/120, ale backend odrzuca nastawy ponad305/105.\n\n## Instalacja na Orange Pi, tylko na postoju\nRozpakuj pakiet. Plan: `python3 install.py --root ~/klipper --config ~/printer_data/config/printer.cfg`. Następnie `sudo systemctl stop klipper`, ta sama komenda z `--apply`, potem `sudo systemctl start klipper`. Przy innych katalogach wskaż rzeczywiste ścieżki. Instalator aktualizuje także właściwe dołączone cfg; nie dopisuj drugiego ekstrudera. Zachowuje PID i rotation_distance oraz tworzy receipt do rollback. W razie REFUSED nie wymuszaj nadpisania nieznanych plików.\n\nPo instalacji wywołaj `ZORTRAX_TEMPERATURE_LIMITS` i `STATUS`. Oczekiwane target_limits305/105, sensor_shutdown_limits310/120. Nie uruchamia to grzania. Import Orca nie instaluje tej aktualizacji hosta. Pakiet profili2.5.0 jest w osobnym repo.\n\nProfile PEEK/PEI pozostają widoczne, ale400/370/360°C przekracza305; START_PRINT odrzuca taki plik przed przygotowaniem. Nie podniesiono limitu poza305 i nie wyłączono zabezpieczeń.\n')
    (ROOT/'docs/en/THERMAL305_INSTALL_PL.md').write_text(guide)
    (template/'README_305_105_PL.md').write_text(guide)
    print(json.dumps(record))

if __name__=='__main__':main()
