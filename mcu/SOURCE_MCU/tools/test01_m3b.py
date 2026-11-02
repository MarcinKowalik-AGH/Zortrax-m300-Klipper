#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Offline-only adaptation of the user's M300Boot v1.1 ibtool.py.
# Full original and license: docs/boot_reference. No UART or flash actions.
import argparse,hashlib,json,struct
from pathlib import Path
BASE=0x08008000
LIMIT=0x0803A000-BASE
MAGIC=b'M3BOOT1\0'
HEADER=struct.Struct('<8sHHIIIII32s')
TARGET=0x3143334D

def vectors(data):
 if not 8<=len(data)<=LIMIT:raise ValueError('payload outside M300 application slot')
 sp,pc=struct.unpack_from('<II',data)
 if not 0x20000000<sp<=0x2000BC00 or sp&7:raise ValueError('invalid aligned MSP')
 if not pc&1 or not BASE+8<=pc&~1<=BASE+len(data)-2:raise ValueError('invalid application reset vector')
 return sp,pc

def pack(data):
 vectors(data)
 return HEADER.pack(MAGIC,64,1,TARGET,BASE,len(data),0,0,hashlib.sha256(data).digest())+data

def inspect(data):
 if len(data)<72:raise ValueError('truncated M3B')
 magic,size,ver,target,base,n,flags,reserved,digest=HEADER.unpack_from(data)
 if (magic,size,ver,target,base,flags,reserved)!=(MAGIC,64,1,TARGET,BASE,0,0):raise ValueError('incompatible M3B header')
 payload=data[64:]
 if len(payload)!=n or hashlib.sha256(payload).digest()!=digest:raise ValueError('payload length or digest mismatch')
 sp,pc=vectors(payload)
 return {'format':'M3BOOT1','application_base':hex(base),'application_end_exclusive':hex(base+n),
   'payload_bytes':n,'payload_sha256':digest.hex(),'initial_msp':hex(sp),'reset_vector':hex(pc),
   'bootloader_modified':False,'flashed':False,'hardware_verified':False}

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['pack','inspect']);p.add_argument('source',type=Path);p.add_argument('destination',nargs='?',type=Path);a=p.parse_args()
 data=a.source.read_bytes()
 if a.action=='pack':
  if not a.destination:p.error('destination required')
  data=pack(data)
  with a.destination.open('xb') as f:f.write(data)
 print(json.dumps(inspect(data),indent=2))
if __name__=='__main__':main()
