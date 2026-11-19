"""Synthetic public-surface regressions; in-memory TLS and isolated SQLite only."""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.engines import public_web, web_surface, native_nuclei
from backend.app.engines.runner import Outcome, _upsert_findings
from backend.app.models.asset import Asset
from backend.app.models.defensive import ExecutionRecord, ExecutionAttempt
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scope import AssetAssessmentScope
from tests_pilot.test_public_web_monitor import approved_asset, fake_transport, API
from tests_pilot.test_m3_sbom_flow import owner_session, work_once

ROOT='https://surface.pilot-test.invalid/'

async def no_native(*args,**kwargs):
    return [],{'status':'unavailable','reason':'SYNTHETIC_TEST_NO_NATIVE'}

async def allowed(*args):
    return {}

async def surface_asset():
    aid=await approved_asset('surface')
    async with AsyncSessionLocal() as db:
        asset=await db.get(Asset,aid)
        asset.assessment_policy={'public_web':public_web.approval_policy(asset,asset.target_locator,'synthetic-owner',mode='surface')}
        grant=(await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id==aid))).scalars().one()
        grant.allowed_path_patterns=['/*'];grant.max_requests_per_run=12;grant.byte_budget=1_000_000
        await db.commit()
    return aid

@pytest.mark.parametrize('value',['https://third-party.invalid/a','https://surface.pilot-test.invalid.evil.invalid/a',
    'https://user:pw@surface.pilot-test.invalid/a','/logout','/delete/item','/checkout','/a?token=x',
    '/media/file.pdf','/_next/static/app.js','/a%2fb','/foo@bar.test'])
def test_discovered_link_boundaries(value):
    assert web_surface.candidate(value,ROOT,ROOT) is None


def test_html_policy_checks_do_not_store_body_cookies_or_fabricate_csp_pass():
    secret='SYNTHETIC-SENSITIVE-BODY-DO-NOT-STORE'
    checks,meta,parser=web_surface.assess(200,[('content-type','text/html'),('set-cookie','session=secret; SameSite=None')],
        (f'<a href="/about">About</a><script src="http://insecure.invalid/x.js"></script>{secret}').encode(),ROOT)
    result=json.dumps({'checks':checks,'meta':meta})
    assert secret not in result and 'session=secret' not in result
    assert any(c['id']=='WEB-MIXED-CONTENT' and c['status']=='FAIL' for c in checks)
    assert any(c['id']=='WEB-COOKIE-SAMESITE-NONE' and c['status']=='FAIL' for c in checks)
    assert not any(c['id']=='WEB-CSP-UNSAFE-EVAL' for c in checks)
    assert parser.links==['/about']

async def test_pinned_verified_get_no_credentials_and_no_body_retention(monkeypatch):
    body=b'<html><a href="/about">about</a>SYNTHETIC-BODY-SECRET</html>'
    response=b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
    _,writer=fake_transport(monkeypatch,response)
    monkeypatch.setattr(native_nuclei,'analyze',no_native)
    page=await web_surface.fetch(ROOT,budget=200_000,before_request=allowed)
    assert writer.closed and len(writer.requests)==1
    assert writer.requests[0].startswith(b'GET / HTTP/1.1\r\n')
    assert b'cookie:' not in writer.requests[0].lower() and b'authorization:' not in writer.requests[0].lower()
    assert page['body_complete'] and page['links']==['/about']
    assert 'SYNTHETIC-BODY-SECRET' not in json.dumps(page)
    assert len(page['body_sha256'])==64

async def test_chunked_framing_is_bounded_and_ambiguous_framing_is_rejected():
    r=asyncio.StreamReader();r.feed_data(b'4\r\ntest\r\n0\r\n\r\n');r.feed_eof()
    assert await web_surface._body(r,[('transfer-encoding','chunked')],10)==(b'test',True,14)
    r=asyncio.StreamReader();r.feed_data(b'fffffff\r\n');r.feed_eof()
    assert await web_surface._body(r,[('transfer-encoding','chunked')],10)==(b'',False,9)
    with pytest.raises(ValueError):
        await web_surface._body(r,[('transfer-encoding','chunked'),('content-length','5')],10)

async def test_partial_body_is_not_a_pass_for_mixed_content(monkeypatch):
    response=b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 99999999\r\n\r\n'
    _,writer=fake_transport(monkeypatch,response);monkeypatch.setattr(native_nuclei,'analyze',no_native)
    page=await web_surface.fetch(ROOT,budget=200_000,before_request=allowed)
    assert not page['body_complete'] and writer.closed
    assert not any(c['id']=='WEB-MIXED-CONTENT' for c in page['checks'])

async def test_scope_change_before_write_closes_socket_without_request(monkeypatch):
    _,writer=fake_transport(monkeypatch,b'HTTP/1.1 200 OK\r\n\r\n')
    calls=[]
    async def scope(url):
        calls.append(url)
        if len(calls)==3:
            raise public_web.PolicyDenied('TARGET_STOP_ACTIVE','synthetic stop')
    with pytest.raises(public_web.PolicyDenied):
        await web_surface.fetch(ROOT,budget=200_000,before_request=scope)
    assert not writer.requests and writer.closed

async def test_bfs_stops_on_degradation_and_never_follows_external_or_side_effect_links(monkeypatch):
    calls=[]
    async def fetch(url,**kwargs):
        calls.append(url)
        return {'url':url,'status':200 if len(calls)==1 else 503,'checks':[],
            'links':['/about','/logout','https://external.invalid/a','/next'],'external_origins':['https://external.invalid'],
            'bytes_sent':100,'bytes_received':1000,'latency_ms':1,'body_complete':True}
    monkeypatch.setattr(web_surface,'fetch',fetch)
    # No wall-clock sleep needed in this synthetic traversal test.
    async def spacing(seconds):
        assert seconds==1
    monkeypatch.setattr(web_surface.asyncio,'sleep',spacing)
    result=await web_surface.measure({'url':ROOT,'max_requests':12,'byte_budget':1_000_000},before_request=allowed)
    assert calls==[ROOT,ROOT+'about']
    assert result['requests_sent']==2
    assert 'TARGET_DEGRADATION_STOP' in result['coverage_gaps']
    assert result['candidate_origins']==['https://external.invalid']

async def test_scope_stop_is_propagated_instead_of_committing_partial_success(monkeypatch):
    async def stopped(*a,**kw):
        raise public_web.PolicyDenied('TARGET_STOP_ACTIVE','synthetic stop')
    monkeypatch.setattr(web_surface,'fetch',stopped)
    with pytest.raises(public_web.PolicyDenied):
        await web_surface.measure({'url':ROOT},before_request=allowed)

async def test_surface_dispatch_uses_real_queue_runner_and_page_locations(client,owner,monkeypatch):
    h=await owner_session(client);aid=await surface_asset()
    body=b'<html>synthetic</html>'
    _,writer=fake_transport(monkeypatch,b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
    monkeypatch.setattr(native_nuclei,'analyze',no_native)
    accepted=await client.post(API+'/runs',headers={**h,'Idempotency-Key':'synthetic-surface-run'},json={
        'selection':{'kind':'assets','asset_ids':[str(aid)]},'engines':['public_web'],'profile':'slow'})
    assert accepted.status_code==202,accepted.text
    assert await work_once()=='succeeded'
    rid=accepted.json()['executions'][0]['execution_id']
    detail=(await client.get(API+'/executions/'+rid)).json()
    assert detail['summary']['measurement_type']=='bounded_same_origin_get'
    assert detail['summary']['requests_sent']==1 and detail['summary']['pages'][0]['url']==ROOT
    assert writer.requests[0].startswith(b'GET ')
    assert 'NATIVE_NUCLEI_PASSIVE_UNAVAILABLE' in detail['summary']['coverage_gaps']

@pytest.mark.skipif(not native_nuclei.available(),reason='Pinned native Nuclei + network namespace not installed')
async def test_real_native_positive_negative_matchers_are_independent_and_secret_free():
    both,meta=await native_nuclei.analyze([('server','Fixture/1.2.3'),('x-powered-by','Fixture'),
        ('set-cookie','secret=SYNTHETIC-NEVER-FORWARD')],location=ROOT)
    assert meta['status']=='succeeded'
    assert {c['id'] for c in both if c['status']=='FAIL'}==set(native_nuclei.RULES)
    empty,meta=await native_nuclei.analyze([],location=ROOT)
    assert meta['status']=='succeeded' and all(c['status']=='PASS' for c in empty)
    assert 'SYNTHETIC-NEVER-FORWARD' not in json.dumps(both)

@pytest.mark.parametrize('policies,expected',[
    (["default-src 'unsafe-eval'; script-src 'self'"],'PASS'),
    (["default-src 'self'; script-src 'unsafe-eval'"],'FAIL'),
    (["script-src 'unsafe-eval'", "script-src 'self'"],'PASS'),
])
def test_enforced_csp_script_precedence_and_policy_intersection(policies,expected):
    checks,_,_=web_surface.assess(200,[('content-type','text/html')]+
        [('content-security-policy',p) for p in policies],b'<html></html>',ROOT)
    assert next(c['status'] for c in checks if c['id']=='WEB-CSP-UNSAFE-EVAL')==expected

async def test_chunk_framing_itself_cannot_exceed_wire_budget():
    reader=asyncio.StreamReader();reader.feed_data(b'1\r\na\r\n'*100+b'0\r\n\r\n');reader.feed_eof()
    body,complete,used=await web_surface._body(reader,[('transfer-encoding','chunked')],100,wire_limit=20)
    assert used<=20 and not complete and len(body)<4

async def test_total_deadline_accounts_for_inflight_request_and_closes_socket(monkeypatch):
    reader,writer=fake_transport(monkeypatch,b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n')
    # A stalled body after a real request write, rather than a fabricated timeout result.
    reader._eof=False
    result=await web_surface.measure({'url':ROOT},timeout=0.1,before_request=allowed)
    assert writer.closed and result['requests_sent']==1
    assert result['bytes_sent']+result['bytes_received']==web_surface.MAX_BYTES
    assert 'TOTAL_DEADLINE_REACHED' in result['coverage_gaps']

async def test_per_page_unevaluated_rule_preserves_finding_until_equivalent_recheck(client,owner,monkeypatch):
    h=await owner_session(client);aid=await surface_asset();phase=0
    async def measurement(*args,**kwargs):
        checks=[{'id':'WEB-MIXED-CONTENT','location':ROOT,'status':'FAIL' if phase==0 else 'PASS',
                 'severity':'LOW','detail':'Synthetic root mixed content'},
                {'id':'WEB-MIXED-CONTENT' if phase!=1 else 'PUBLIC-TLS-VERIFY','location':ROOT+'about',
                 'status':'FAIL' if phase==0 else 'PASS','severity':'LOW','detail':'Synthetic page check'}]
        return {'url':ROOT,'observed_at':datetime.now(timezone.utc).isoformat(),'measurement_type':'bounded_same_origin_get',
            'http_status':200,'bytes_sent':200,'bytes_received':200,'requests_sent':2,'checks':checks,'error':None,
            'pages':[{'url':ROOT,'status':200},{'url':ROOT+'about','status':201}],
            'evaluated_checks':{ROOT:[checks[0]['id']],ROOT+'about':[checks[1]['id']]}}
    monkeypatch.setattr(web_surface,'measure',measurement)
    async def launch(key):
        # Simulate the elapsed inter-run spacing on completed synthetic jobs only.
        from datetime import timedelta
        from sqlalchemy import update
        from backend.app.models.scan import Scan
        async with AsyncSessionLocal() as db:
            await db.execute(update(Scan).where(Scan.asset_id==aid,Scan.status=='COMPLETED')
                .values(started_at=datetime.now(timezone.utc)-timedelta(seconds=21)))
            await db.commit()
        r=await client.post(API+'/runs',headers={**h,'Idempotency-Key':key},json={
            'selection':{'kind':'assets','asset_ids':[str(aid)]},'engines':['public_web'],'profile':'light'})
        assert r.status_code==202,r.text
        assert await work_once()=='succeeded'
    await launch('surface-lifecycle-first')
    rows=(await client.get(API+'/findings',params={'asset_id':str(aid)})).json()['items']
    about=next(f for f in rows if f['target_location']==ROOT+'about')
    detail=(await client.get(API+'/findings/'+about['id'])).json()
    assert detail['evidence']['http_status']==201
    phase=1;await launch('surface-lifecycle-partial')
    assert (await client.get(API+'/findings/'+about['id'])).json()['status']=='NEW'
    phase=2;await launch('surface-lifecycle-equivalent')
    assert (await client.get(API+'/findings/'+about['id'])).json()['status']=='RESOLVED'

async def test_native_cancellation_reaps_the_registered_process(monkeypatch):
    import sys
    import psutil
    from backend.app.core.process_safety import process_safety
    started=asyncio.Event();pids=[]
    original=process_safety.register_pid
    async def registered(identity,pid,**kwargs):
        await original(identity,pid,**kwargs)
        pids.append(pid);started.set()
    monkeypatch.setattr(native_nuclei,'available',lambda:True)
    monkeypatch.setattr(native_nuclei,'command',lambda folder:[sys.executable,'-c','import time; time.sleep(60)'])
    monkeypatch.setattr(process_safety,'register_pid',registered)
    task=asyncio.create_task(native_nuclei.analyze([],location=ROOT))
    await asyncio.wait_for(started.wait(),3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task,4)
    assert pids and all(not psutil.pid_exists(pid) for pid in pids)

async def test_native_input_rejection_never_fabricates_negative_checks(monkeypatch):
    monkeypatch.setattr(native_nuclei,'available',lambda:True)
    checks,meta=await native_nuclei.analyze([('server','a'*129+'/1.2')],location=ROOT)
    assert checks==[] and meta['status']=='unavailable'
    assert meta['reason']=='HEADER_METADATA_EXCEEDS_REVIEWED_INPUT_BOUNDS'

async def test_traversal_request_cap_and_spacing_are_enforced(monkeypatch):
    calls=[];spacing=[]
    async def fetch(url,**kwargs):
        calls.append(url)
        return {'url':url,'status':200,'checks':[],'links':['/page-'+str(n) for n in range(30)],
            'external_origins':[],'bytes_sent':100,'bytes_received':100,'latency_ms':1,'body_complete':True}
    async def wait(seconds):
        spacing.append(seconds)
    monkeypatch.setattr(web_surface,'fetch',fetch);monkeypatch.setattr(web_surface.asyncio,'sleep',wait)
    result=await web_surface.measure({'url':ROOT,'max_requests':1000},before_request=allowed)
    assert len(calls)==result['requests_sent']==result['request_attempts']==12
    assert spacing==[1]*11
    assert 'RUN_REQUEST_BUDGET_REACHED' in result['coverage_gaps']

async def test_surface_invalid_tls_records_failure_without_http_or_unverified_retry(monkeypatch):
    _,writer=fake_transport(monkeypatch,b'',bad_tls=True)
    result=await web_surface.measure({'url':ROOT},before_request=allowed)
    assert result['requests_sent']==0 and writer.requests==[] and len(writer.connections)==1
    assert result['checks']==[{'id':'PUBLIC-TLS-VERIFY','status':'FAIL','severity':'HIGH','location':ROOT,
        'detail':'TLS chain or hostname validation failed; no HTTP request was sent.'}]
    assert result['evaluated_checks'][ROOT]==['PUBLIC-TLS-VERIFY']
    assert result['error']=='TLS_VERIFICATION_FAILED'

def test_installer_does_not_trust_a_self_consistent_modified_marker(tmp_path,monkeypatch):
    import hashlib
    from scripts import install_nuclei
    monkeypatch.setattr(install_nuclei,'ROOT',tmp_path)
    monkeypatch.setattr(install_nuclei.platform,'system',lambda:'Linux')
    monkeypatch.setattr(install_nuclei.platform,'machine',lambda:'x86_64')
    folder=tmp_path/'storage/tools/nuclei'/install_nuclei.VERSION;folder.mkdir(parents=True)
    raw=b'SYNTHETIC tampered binary';(folder/'nuclei').write_bytes(raw)
    (folder/'release.json').write_text(json.dumps({'archive_sha256':install_nuclei.ARCHIVE_SHA256,
        'binary_sha256':hashlib.sha256(raw).hexdigest()}))
    with pytest.raises(SystemExit,match='failed integrity'):
        install_nuclei.main()
    assert (folder/'nuclei').read_bytes()==raw
