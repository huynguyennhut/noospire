"""Pinned Nuclei response-header analysis in a filesystem/network namespace.

No URL target, network interface, platform environment or arbitrary templates are
passed to Nuclei. Only a sanitized header-only local response enters the sandbox.
This is a passive subdriver, not the historical broad native scanner adapter.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from backend.app.core.process_safety import process_safety

ROOT = Path(__file__).resolve().parents[3]
VERSION = '3.11.1'
BINARY_SHA256 = 'c49588140f357cbdddd5436dec11201953a4c5390faeec90777f9ee2cfd70251'
TEMPLATE = Path(__file__).parent / 'templates/nuclei'
TEMPLATE_FILES = ('powered-by.yaml', 'server-version.yaml')
TEMPLATE_SHA256 = 'c20fff0a0bd12a15273458ac3d84a37e803b445739f8966abf9cd8e99ba5ed02'
RULES = {'NUCLEI-SERVER-VERSION':'Public response advertises a server version',
         'NUCLEI-POWERED-BY':'Public response advertises a framework header'}
MATCHERS = {'noosforge-public-server-version':'NUCLEI-SERVER-VERSION',
            'noosforge-public-powered-by':'NUCLEI-POWERED-BY'}
BINARY = ROOT / f'storage/tools/nuclei/{VERSION}/nuclei'


@lru_cache(maxsize=4)
def _verify(binary_stat, template_stat):
    if hashlib.sha256(BINARY.read_bytes()).hexdigest() != BINARY_SHA256:
        return False
    digest = hashlib.sha256()
    for name in TEMPLATE_FILES:
        digest.update(name.encode()+b'\0'+(TEMPLATE/name).read_bytes())
    return digest.hexdigest() == TEMPLATE_SHA256


@lru_cache(maxsize=1)
def sandbox_available():
    bwrap=shutil.which('bwrap')
    if not bwrap:
        return False
    try:
        r=subprocess.run([bwrap,'--unshare-net','--ro-bind','/','/','--','/bin/true'],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            timeout=3,env={'PATH':'/usr/bin:/bin'})
        return r.returncode == 0
    except (OSError,subprocess.TimeoutExpired):
        return False


def available():
    try:
        b=BINARY.stat()
        stats=tuple((p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns) for p in (TEMPLATE/n for n in TEMPLATE_FILES))
        return (os.access(BINARY,os.X_OK) and _verify((b.st_ino,b.st_size,b.st_mtime_ns),
            stats) and sandbox_available())
    except OSError:
        return False


def command(input_dir):
    return [shutil.which('bwrap'),'--unshare-all','--die-with-parent','--new-session',
        '--ro-bind',str(BINARY),'/nuclei','--ro-bind',str(TEMPLATE),'/templates',
        '--ro-bind',str(input_dir),'/input','--proc','/proc','--dev','/dev',
        '--tmpfs','/tmp','--tmpfs','/home','--clearenv','--setenv','HOME','/home',
        '--setenv','XDG_CONFIG_HOME','/home/config','--setenv','XDG_CACHE_HOME','/home/cache',
        '--setenv','DISABLE_NUCLEI_TEMPLATES_PUBLIC_DOWNLOAD','true','--chdir','/input',
        '/nuclei','-passive','-target','/input','-t','/templates/powered-by.yaml','-t','/templates/server-version.yaml','-jsonl','-silent','-nc',
        '-duc','-ni','-omit-raw','-omit-template','-no-stdin']


async def analyze(headers, *, location, scan_id=None):
    metadata={'driver':'nuclei','version':VERSION,'mode':'passive_headers_network_isolated',
              'template_sha256':TEMPLATE_SHA256,'status':'unavailable','checks_evaluated':0}
    if not available():
        return [],{**metadata,'reason':'VERIFIED_NUCLEI_OR_NETWORK_SANDBOX_UNAVAILABLE'}
    identity=scan_id or uuid.uuid4()
    # Only the fields this reviewed template examines; no body, cookie or credential enters the process.
    selected=[(k,v) for k,v in headers if k in ('server','x-powered-by')]
    if any(len(v)>128 or not all(32 <= ord(c) < 127 for c in v) for _,v in selected):
        return [],{**metadata,'reason':'HEADER_METADATA_EXCEEDS_REVIEWED_INPUT_BOUNDS'}
    kept=selected
    raw=('HTTP/1.1 200 OK\r\n'+''.join(f'{k}: {v}\r\n' for k,v in kept)+'Content-Length: 0\r\n\r\n').encode('ascii')
    proc=None
    try:
        with tempfile.TemporaryDirectory(prefix='noospire-nuclei-passive-') as folder:
            p=Path(folder)/'response.txt';p.write_bytes(raw);p.chmod(0o600)
            proc=await asyncio.create_subprocess_exec(*command(folder),stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env={'PATH':'/usr/bin:/bin'},
                **process_safety.get_safe_subprocess_kwargs(memory_limit_mb=4096,cpu_limit_seconds=8,max_open_files=256))
            await process_safety.register_pid(identity,proc.pid)
            async with asyncio.timeout(10):
                out,err=await asyncio.gather(proc.stdout.read(65537),proc.stderr.read(16385))
                await proc.wait()
            if proc.returncode != 0 or len(out)>65536 or len(err)>16384:
                return [],{**metadata,'reason':'NATIVE_ANALYSIS_FAILED_OR_OUTPUT_LIMIT'}
            matched=set()
            for line in out.splitlines():
                row=json.loads(line)
                if row.get('template-id') not in MATCHERS or row.get('matcher-status') is not True:
                    raise ValueError('unexpected native output')
                matched.add(MATCHERS[row['template-id']])
            checks=[{'id':rule,'status':'FAIL' if rule in matched else 'PASS','severity':'INFO','location':location,
                     'detail':'Native Nuclei matched public header metadata; no vulnerable version or exploit is established.'
                        if rule in matched else 'The reviewed native header matcher did not match this captured response.'}
                    for rule in RULES]
            return checks,{**metadata,'status':'succeeded','checks_evaluated':len(checks),'matches':len(matched)}
    except (OSError,TimeoutError,ValueError,json.JSONDecodeError):
        return [],{**metadata,'reason':'NATIVE_ANALYSIS_FAILED'}
    finally:
        if proc is not None:
            # Includes cancellation, deadline and stdout overflow; leave no sandbox child behind.
            await asyncio.to_thread(process_safety.terminate_process_tree,identity)
            await proc.wait()
