"""Explicit305/105 migration. No PID, sensor conversion or motion retuning."""
import re
POLICY='[m300_temperature_policy]\nhotend_target_max: 305\nbed_target_max: 105\n'
TARGETS={'extruder':('M300_HOTEND_STOCK_LINEAR_LAB','310'),'heater_bed':('M300_BED_STOCK_TABLE_LAB','120')}

def transform(text):
    head,sep,tail=text.partition('#*# <---------------------- SAVE_CONFIG ---------------------->')
    seen=[]
    def block(match):
        section,body=match.group(1).strip().lower(),match.group(2)
        if section not in TARGETS and section!='m300_temperature_policy':return match.group(0)
        seen.append(section)
        def put(body,key,value):
            pattern=r'(?mi)^([ \t]*'+re.escape(key)+r'[ \t]*[:=])[ \t]*[^\n]*$'
            if len(re.findall(pattern,body))>1:raise ValueError('Duplicate '+section+'.'+key)
            if re.search(pattern,body):return re.sub(pattern,lambda m:m.group(1)+' '+value,body)
            return body.rstrip()+'\n'+key+': '+value+'\n'
        if section in TARGETS:
            sensor,limit=TARGETS[section]
            m=re.search(r'(?mi)^\s*sensor_type\s*[:=]\s*([^#;\n]+)',body)
            if not m or m.group(1).strip()!=sensor:raise ValueError('305/105 migration requires reviewed stock sensor conversion for '+section)
            body=put(body,'max_temp',limit)
        else:
            body=put(body,'hotend_target_max','305');body=put(body,'bed_target_max','105')
        return '['+match.group(1)+']'+body
    head=re.sub(r'(?m)^\[([^\]\n]+)\]([^\[]*(?=^\[|\Z))',block,head)
    return head+sep+tail,seen

def apply_to_plan(desired,root,original_tree):
    counts={'extruder':0,'heater_bed':0,'m300_temperature_policy':0}
    configs=[p for p in desired if p.parent==root.parent and (p.suffix=='.cfg' or p in original_tree)]
    configs += [p for p in original_tree if p not in configs]
    for p in configs:
        data=desired.get(p,p.read_bytes() if p.exists() else b'')
        text,seen=transform(data.decode())
        for section in seen:counts[section]+=1
        desired[p]=text.encode()
    if counts['extruder']!=1 or counts['heater_bed']!=1 or counts['m300_temperature_policy']>1:
        raise ValueError('Ambiguous thermal configuration: '+str(counts))
    if not counts['m300_temperature_policy']:
        text=desired[root].decode();m=re.search(r'(?m)^#\*#.*SAVE_CONFIG',text);at=m.start() if m else len(text)
        desired[root]=(text[:at].rstrip()+'\n\n'+POLICY+'\n'+text[at:]).encode()
