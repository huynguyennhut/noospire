"""Install the pinned official Nuclei Linux x86-64 release locally after SHA-256 verification.

Does not run scans or download templates. Run from the repository root.
"""
from pathlib import Path
import hashlib
import io
import json
import os
import platform
import urllib.request
import zipfile

VERSION = '3.11.1'
URL = f'https://github.com/projectdiscovery/nuclei/releases/download/v{VERSION}/nuclei_{VERSION}_linux_amd64.zip'
ARCHIVE_SHA256 = 'ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6'
BINARY_SHA256 = 'c49588140f357cbdddd5436dec11201953a4c5390faeec90777f9ee2cfd70251'
ROOT = Path(__file__).resolve().parent.parent


def main():
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise SystemExit('This verified installer supports Linux x86-64 only.')
    target = ROOT / 'storage/tools/nuclei' / VERSION
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = target / 'release.json'
    binary = target / 'nuclei'
    if marker.exists() and binary.exists():
        prior = json.loads(marker.read_text())
        if (hashlib.sha256(binary.read_bytes()).hexdigest() == BINARY_SHA256 == prior.get('binary_sha256')
                and prior.get('archive_sha256') == ARCHIVE_SHA256):
            print(json.dumps({'installed': True, 'version': VERSION, 'binary': str(binary), 'reused': True}))
            return
        raise SystemExit('Existing local release failed integrity validation; preserved for inspection.')
    request = urllib.request.Request(URL, headers={'User-Agent': 'NOOSFORGE-local-scanner-installer'})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(60_000_001)
    if len(raw) > 60_000_000 or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise SystemExit('Official release archive size/hash mismatch; no binary installed.')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.getinfo('nuclei')
        if info.file_size > 200_000_000:
            raise SystemExit('Unexpected binary size; no binary installed.')
        contents = archive.read(info)
    if hashlib.sha256(contents).hexdigest() != BINARY_SHA256:
        raise SystemExit('Extracted binary hash mismatch; no binary installed.')
    fd = os.open(binary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
    with os.fdopen(fd, 'wb') as output:
        output.write(contents)
    marker.write_text(json.dumps({'version': VERSION, 'source': URL, 'archive_sha256': ARCHIVE_SHA256,
                                  'binary_sha256': hashlib.sha256(contents).hexdigest()}, indent=2)+'\n')
    marker.chmod(0o600)
    print(json.dumps({'installed': True, 'version': VERSION, 'binary': str(binary), 'reused': False}))


if __name__ == '__main__':
    main()
