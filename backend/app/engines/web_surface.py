"""Bounded unauthenticated same-origin page assessment; never submits forms.

Response bodies exist only transiently for HTML parsing. Evidence retains checks,
status, counts and hashes, not HTML, cookies or learner data. Every request uses
vetted/pinned IPs, verified TLS and a fresh persisted scope/stop check.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import ssl
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from cryptography import x509

from backend.app.engines import public_web, tls_health, native_nuclei

MAX_REQUESTS = 12
MAX_BYTES = 1_000_000
MAX_BODY = 96 * 1024
MAX_SECONDS = 75
MAX_URLS = 64
HEADER_RULE_IDS = {rule: rule if rule.startswith('PUBLIC-TLS-') else 'SURFACE-'+rule
                   for rule in public_web.RULESET['rules']}
RULES = {
    **{HEADER_RULE_IDS[k]:v.replace('HEAD','GET') for k,v in public_web.RULESET['rules'].items()},
    **native_nuclei.RULES,
    'WEB-REFERRER-POLICY': 'HTML response sets a restrictive Referrer-Policy',
    'WEB-CSP-UNSAFE-EVAL': 'Enforced script policy does not allow unsafe-eval',
    'WEB-MIXED-CONTENT': 'HTTPS page has no HTTP script, stylesheet, iframe or form action',
    'WEB-COOKIE-SAMESITE-NONE': 'Cookies marked SameSite=None also have Secure',
}
RULESET = {'id': 'public-web-surface', 'version': '2026.11.17', 'rules': RULES,
           'native_nuclei_version':native_nuclei.VERSION,'native_template_sha256':native_nuclei.TEMPLATE_SHA256}
BLOCKED_SEGMENTS = {'logout', 'log-out', 'signout', 'sign-out', 'dang-xuat', 'delete', 'remove',
                    'unsubscribe', 'reset-password', 'confirm', 'activate', 'revoke', 'checkout', 'pay'}
STATIC = re.compile(r'\.(?:js|css|png|jpe?g|gif|svg|ico|woff2?|ttf|mp[34]|webm|pdf|zip|docx?|xlsx?)$', re.I)


def origin(url):
    p = urlsplit(url)
    return p.scheme, p.hostname, p.port or 443


def candidate(raw, base, root):
    try:
        value = urljoin(base, raw)
        p = urlsplit(value)
        if (origin(value) != origin(root) or p.query or p.username or p.password or '@' in p.path
                or len(p.path) > 256 or STATIC.search(p.path) or p.path.startswith(('/_next/', '/media/'))
                or any(s.lower() in BLOCKED_SEGMENTS for s in p.path.split('/'))):
            return None
        return public_web.normalized_url(value.split('#', 1)[0])
    except (ValueError, public_web.PolicyDenied):
        return None


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.external, self.mixed = [], set(), 0

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        value = data.get('href' if tag in ('a', 'link') else 'action' if tag == 'form' else 'src')
        if not value:
            return
        if tag == 'a' and len(self.links) < MAX_URLS:
            self.links.append(value)
        active = tag in ('script','iframe','form') or (tag=='link' and
            bool(set((data.get('rel') or '').lower().split()) & {'stylesheet','modulepreload'}))
        if active and value.lower().startswith('http://'):
            self.mixed += 1
        if value.startswith(('https://', 'http://', '//')):
            try:
                p = urlsplit('https:'+value if value.startswith('//') else value)
                if p.hostname and not p.username and not p.password and len(self.external) < 16:
                    self.external.add((p.scheme or 'https')+'://'+p.netloc)
            except ValueError:
                pass


def assess(status, headers, body, url):
    checks, meta = public_web.assess_headers(status, headers)
    for check in checks:
        check.update(id=HEADER_RULE_IDS[check['id']], location=url, detail=check['detail'].replace('HEAD', 'GET'))
    parser = PageParser()
    if 200 <= status < 300 and meta['content_type_html']:
        parser.feed(body.decode('utf-8', errors='replace'))
        by_name = {}
        for key, value in headers:
            by_name.setdefault(key, []).append(value)
        policies = by_name.get('referrer-policy', [])
        referrer = policies[-1].split(',')[-1].strip().lower() if policies else ''
        checks.append({**public_web._check('WEB-REFERRER-POLICY', referrer in
            ('no-referrer', 'same-origin', 'strict-origin', 'strict-origin-when-cross-origin'),
            'Restrictive Referrer-Policy on the observed HTML response.'), 'location': url})
        csp = by_name.get('content-security-policy', [])
        # Absence of CSP is covered by PUBLIC-CSP; do not manufacture a policy-strength PASS.
        script = []
        for header in csp:
            directives = {}
            for directive in header.split(';'):
                parts = directive.strip().lower().split()
                if parts:
                    directives.setdefault(parts[0],parts[1:])
            selected = directives.get('script-src',directives.get('default-src'))
            if selected is not None:
                script.append(selected)
        if script:
            unsafe = all("'unsafe-eval'" in s for s in script)
            checks.append({**public_web._check('WEB-CSP-UNSAFE-EVAL', not unsafe,
                'All applicable enforced script policies permit unsafe-eval.' if unsafe
                else 'No unsafe-eval in observed enforced script/default policy.', 'LOW'), 'location':url})
        checks.append({**public_web._check('WEB-MIXED-CONTENT', parser.mixed == 0,
            f'{parser.mixed} insecure active-resource/form references in this captured HTML page.'), 'location':url})
    cookies = [v for k,v in headers if k == 'set-cookie']
    if cookies and 200 <= status < 300:
        bad = sum(bool(re.search(r';\s*samesite\s*=\s*none\s*(?:;|$)', c,re.I)) and
                  not re.search(r';\s*secure\s*(?:;|$)', c,re.I) for c in cookies)
        checks.append({**public_web._check('WEB-COOKIE-SAMESITE-NONE',bad == 0,
            f'{bad} observed SameSite=None cookies lack Secure; names/values are not retained.'),'location':url})
    return checks, meta, parser


async def _body(reader, headers, limit, *, wire_limit=None):
    """Count HTTP framing too: tiny chunks must not bypass the run byte cap."""
    wire_limit = limit+2048 if wire_limit is None else wire_limit
    values = {}
    for key,value in headers:
        values.setdefault(key,[]).append(value)
    if values.get('content-encoding', ['identity']) != ['identity']:
        return b'', False, 0
    transfer = values.get('transfer-encoding', [])
    lengths = values.get('content-length', [])
    if transfer:
        if transfer != ['chunked'] or lengths:
            raise ValueError('AMBIGUOUS_FRAMING')
        out,consumed = bytearray(),0
        while True:
            line=bytearray()
            for _ in range(64):
                if consumed >= wire_limit:
                    return bytes(out),False,consumed
                line.extend(await reader.readexactly(1));consumed+=1
                if line.endswith(b'\r\n'):
                    break
            else:
                raise ValueError('INVALID_CHUNK')
            if not re.fullmatch(rb'[0-9a-fA-F]+\r\n',line):
                raise ValueError('INVALID_CHUNK')
            size=int(line.strip(),16)
            if wire_limit-consumed < 2:
                return bytes(out),False,consumed
            if size==0:
                trailer=await reader.readexactly(2);consumed+=2
                return bytes(out),trailer==b'\r\n',consumed
            if size > min(limit-len(out),wire_limit-consumed-2):
                return bytes(out),False,consumed
            out.extend(await reader.readexactly(size));consumed+=size
            if await reader.readexactly(2) != b'\r\n':
                raise ValueError('INVALID_CHUNK')
            consumed+=2
    if lengths:
        if len(lengths)!=1 or not re.fullmatch(r'[0-9]+',lengths[0]):
            raise ValueError('INVALID_LENGTH')
        n=int(lengths[0])
        if n > min(limit,wire_limit):
            return b'',False,0
        return await reader.readexactly(n),True,n
    out=bytearray()
    cap=min(limit+1,wire_limit)
    while len(out)<cap:
        more=await reader.read(cap-len(out))
        if not more:
            break
        out.extend(more)
    return bytes(out[:limit]),len(out)<=limit and reader.at_eof(),len(out)


async def fetch(url, *, budget, before_request, progress=None, scan_id=None):
    p = urlsplit(public_web.normalized_url(url))
    await before_request(url)
    ips = await tls_health.resolve_vetted(p.hostname,p.port or 443,False)
    await before_request(url)
    writer = None
    result = {'url':url,'status':None,'checks':[],'links':[],'external_origins':[],
              'bytes_sent':0,'bytes_received':0,'body_complete':False,'body_sha256':None}
    if progress is not None:
        progress.update(result)
        result = progress
    started = time.monotonic()
    try:
        reader,writer = await asyncio.open_connection(ips[0],p.port or 443,ssl=ssl.create_default_context(),
            server_hostname=p.hostname,limit=public_web.MAX_HEADER_BYTES)
        await before_request(url)
        request = (f'GET {p.path or "/"} HTTP/1.1\r\nHost: {p.netloc}\r\nUser-Agent: noosforge-public-surface/1.0\r\n'
                   'Accept: text/html,application/xhtml+xml\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n').encode('ascii')
        writer.write(request); result['bytes_sent'] = len(request); await writer.drain()
        head = await reader.readuntil(b'\r\n\r\n'); result['bytes_received'] = len(head)
        if len(head) > public_web.MAX_HEADER_BYTES:
            raise ValueError('HEADER_LIMIT')
        lines = head.decode('latin-1').split('\r\n')
        if not re.fullmatch(r'HTTP/1\.[01] [1-5][0-9]{2}(?: .*)?',lines[0]):
            raise ValueError('INVALID_STATUS')
        status = int(lines[0].split()[1]); result['status'] = status
        headers=[]
        for line in lines[1:]:
            if line:
                if ':' not in line or line[0].isspace():
                    raise ValueError('INVALID_HEADER')
                key,value=line.split(':',1);headers.append((key.strip().lower(),value.strip()))
        body=b''; complete=False
        if 200 <= status < 300:
            limit=max(0,min(MAX_BODY,budget-len(head)-len(request)-2048))
            body,complete,consumed=await _body(reader,headers,limit,wire_limit=max(0,budget-len(head)-len(request)))
            result['bytes_received']+=consumed
        checks,meta,parser=assess(status,headers,body if complete else b'',url)
        if not complete:
            checks=[c for c in checks if c['id'] != 'WEB-MIXED-CONTENT']
        if complete:
            result.update(links=parser.links,external_origins=sorted(parser.external),body_sha256=hashlib.sha256(body).hexdigest())
        result.update(checks=checks,body_complete=complete,**meta)
        cert = x509.load_der_x509_certificate(writer.get_extra_info('ssl_object').getpeercert(binary_form=True))
        days=(cert.not_valid_after_utc-datetime.now(timezone.utc)).total_seconds()/86400
        result['checks'][:0]=[{**public_web._check('PUBLIC-TLS-VERIFY',True,'TLS chain and hostname verified.'),'location':url},
            {**public_web._check('PUBLIC-TLS-EXPIRY',days>=14,'Certificate compared with 14-day expiry threshold.','HIGH'),'location':url}]
        result['latency_ms']=int((time.monotonic()-started)*1000)
        if 200 <= status < 300:
            native_checks,native_meta=await native_nuclei.analyze(headers,location=url,scan_id=scan_id)
            result['checks'].extend(native_checks)
            result['native_nuclei']=native_meta
        return result
    finally:
        result.setdefault('latency_ms',int((time.monotonic()-started)*1000))
        if writer:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(),0.5)
            except (OSError,TimeoutError):
                pass


async def measure(policy, *, timeout=MAX_SECONDS, before_request, scan_id=None):
    root=public_web.normalized_url(policy['url'])
    result={'url':root,'observed_at':datetime.now(timezone.utc).isoformat(),'measurement_type':'bounded_same_origin_get',
            'requests_sent':0,'bytes_sent':0,'bytes_received':0,'http_status':None,'checks':[],'pages':[],
            'coverage_gaps':['AUTHENTICATED_COVERAGE_NOT_CONFIGURED','INJECTION_NOT_EVALUATED',
                             'APPLICATION_HEALTH_ENDPOINT_NOT_CONFIGURED','SOURCE_CONTAINER_CLOUD_MOBILE_NOT_EVALUATED'],
            'candidate_origins':[],'application_health_assessed':False,'full_assessment_complete':False,
            'service_status':'unknown','error':None,'evaluated_checks':{}}
    result.update(request_attempts=0,byte_accounting='HTTP_bytes_with_framing; conservative_upper_bound_on_error')
    queue=[root];seen=set();external=set();started=time.monotonic()
    progress={}; remaining=0
    cap=min(MAX_REQUESTS,int(policy.get('max_requests',MAX_REQUESTS)))
    byte_cap=min(MAX_BYTES,int(policy.get('byte_budget',MAX_BYTES)))
    try:
        async with asyncio.timeout(min(timeout,MAX_SECONDS)):
            while queue and result['request_attempts'] < cap:
                url=queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                remaining=byte_cap-result['bytes_sent']-result['bytes_received']
                if remaining < public_web.MAX_HEADER_BYTES+4096:
                    result['coverage_gaps'].append('RUN_BYTE_BUDGET_REACHED');break
                if result['requests_sent']:
                    await asyncio.sleep(1)  # at most one request per second, serial sockets
                await before_request(url)
                result['request_attempts']+=1
                progress={}
                try:
                    async with asyncio.timeout(8):
                        page=await fetch(url,budget=remaining,before_request=before_request,progress=progress,scan_id=scan_id)
                except (public_web.PolicyDenied,tls_health.EgressDenied):
                    raise
                except ssl.SSLCertVerificationError:
                    check={**public_web._check('PUBLIC-TLS-VERIFY',False,
                        'TLS chain or hostname validation failed; no HTTP request was sent.','HIGH'),'location':url}
                    result['checks'].append(check)
                    result['evaluated_checks'][url]=[check['id']]
                    result['error']='TLS_VERIFICATION_FAILED'
                    result['coverage_gaps'].append('HTTP_OBSERVATION_INCOMPLETE')
                    break
                except (ssl.SSLError,OSError,TimeoutError,ValueError,asyncio.IncompleteReadError,asyncio.LimitOverrunError) as exc:
                    result['requests_sent']+=int(progress.get('bytes_sent',0)>0)
                    result['bytes_sent']+=progress.get('bytes_sent',0)
                    # A framing error may have consumed unreturned bytes; reserve this request's remaining allowance.
                    if progress.get('bytes_sent'):
                        result['bytes_received']+=max(0,remaining-progress['bytes_sent'])
                    result['error']=type(exc).__name__;result['coverage_gaps'].append('NETWORK_OR_PARSE_STOP');break
                result['requests_sent']+=int(page['bytes_sent']>0)
                result['bytes_sent']+=page['bytes_sent'];result['bytes_received']+=page['bytes_received']
                progress={}
                if result['http_status'] is None:
                    result['http_status']=page['status']
                result['checks'].extend(page['checks'])
                result['evaluated_checks'][url]=[c['id'] for c in page['checks']]
                result['pages'].append({k:v for k,v in page.items() if k not in ('links','checks','external_origins')})
                if page.get('native_nuclei',{}).get('status') == 'unavailable':
                    result['coverage_gaps'].append('NATIVE_NUCLEI_PASSIVE_UNAVAILABLE')
                for raw in page['links']:
                    nxt=candidate(raw,url,root)
                    if nxt and nxt not in seen and nxt not in queue and len(queue)<MAX_URLS:
                        queue.append(nxt)
                external.update(o for o in page['external_origins'] if origin(o)!=origin(root))
                if page['status'] == 429 or page['status'] >= 500 or page['latency_ms'] >= 5000:
                    result['coverage_gaps'].append('TARGET_DEGRADATION_STOP');break
                if page['status'] in (401,403):
                    result['coverage_gaps'].append('AUTHENTICATED_ROUTE_NOT_EVALUATED')
                if 300 <= page['status'] < 400:
                    result['coverage_gaps'].append('REDIRECT_NOT_FOLLOWED')
                if not page['body_complete'] and 200 <= page['status'] < 300:
                    result['coverage_gaps'].append('BODY_CHECKS_NOT_EVALUATED')
            if queue and result['request_attempts'] >= cap:
                result['coverage_gaps'].append('RUN_REQUEST_BUDGET_REACHED')
    except TimeoutError:
        # The total deadline cancels an in-flight fetch before its per-page handler
        # can account for it. Reserve its remaining allowance just like a framing error.
        if progress.get('bytes_sent'):
            result['requests_sent']+=1
            result['bytes_sent']+=progress['bytes_sent']
            result['bytes_received']+=max(0,remaining-progress['bytes_sent'])
        result['error']='TOTAL_TIMEOUT';result['coverage_gaps'].append('TOTAL_DEADLINE_REACHED')
    result.update(candidate_origins=sorted(external)[:16],latency_ms=int((time.monotonic()-started)*1000),
                  service_status='reachable' if result['http_status'] else 'unknown')
    result['coverage_gaps']=sorted(set(result['coverage_gaps']))
    return result


def rules_digest():
    return hashlib.sha256(json.dumps(RULESET,sort_keys=True).encode()).hexdigest()
