#!/usr/bin/env python3
"""Save and verify one WeChat newspic draft. No publish/send/delete endpoints."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re

import requests
from PIL import Image
import newspic
from manifest import digest, input_fingerprint, write_json

API = 'https://api.weixin.qq.com/cgi-bin/'
ALLOWED = frozenset({'token', 'draft/batchget', 'draft/get', 'draft/add', 'draft/update',
                     'material/add_material', 'material/get_material', 'freepublish/batchget'})


class DeliveryError(RuntimeError):
    """Messages must be safe to print: never include HTTP URLs or raw responses."""


class ApiError(DeliveryError):
    def __init__(self, code, allowlist_ip=None):
        self.code = code
        self.allowlist_ip = allowlist_ip
        super().__init__(f'WeChat error {code}' + (f'; allowlist IP: {allowlist_ip}' if allowlist_ip else ''))


def load_credentials(path=None):
    if path:
        try:
            values = json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
            app_id, app_secret = values['app_id'], values['app_secret']
        except (OSError, KeyError, ValueError, TypeError):
            raise DeliveryError('Cannot load credentials file; expected app_id and app_secret') from None
    else:
        app_id, app_secret = os.getenv('WECHAT_APP_ID'), os.getenv('WECHAT_APP_SECRET')
    if not app_id or not app_secret:
        raise DeliveryError('Set WECHAT_APP_ID / WECHAT_APP_SECRET or use --credentials outside the repository')
    return app_id, app_secret


class Client:
    def __init__(self, app_id, app_secret, evidence, *, direct=False):
        self.account = digest(app_id.encode())[:16]
        self.evidence = Path(evidence)
        self.audit = []
        self.session = requests.Session()
        # An explicit per-process choice; never changes the OS proxy or VPN.
        self.session.trust_env = not direct
        self.token = None
        auth = self.call('token', params={'grant_type':'client_credential','appid':app_id,'secret':app_secret})
        self.token = auth.get('access_token')
        if not self.token:
            raise DeliveryError('Authentication did not return a token')

    def call(self, endpoint, payload=None, *, params=None, image_path=None, binary=False):
        if endpoint not in ALLOWED:
            raise DeliveryError('Endpoint is outside the draft-only allowlist')
        if endpoint == 'token' and self.token is not None:
            raise DeliveryError('Authentication already completed')
        query = dict(params or {})
        if self.token:
            query['access_token'] = self.token
        entry = {'endpoint': endpoint, 'method':'GET' if endpoint == 'token' else 'POST'}
        self.audit.append(entry)
        try:
            kwargs = {'params':query,'timeout':60}
            if image_path:
                with Path(image_path).open('rb') as stream:
                    response = self.session.post(API+endpoint, files={'media':(Path(image_path).name,stream,'image/png')}, **kwargs)
            elif endpoint == 'token':
                response = self.session.get(API+endpoint, **kwargs)
            else:
                response = self.session.post(API+endpoint,
                    data=json.dumps(payload or {},ensure_ascii=False).encode('utf-8'),
                    headers={'Content-Type':'application/json; charset=utf-8'}, **kwargs)
            entry['http_status'] = response.status_code
            if response.status_code >= 400:
                raise DeliveryError(f'HTTP {response.status_code} from {endpoint}')
            raw = response.content
            if binary and not raw.lstrip().startswith(b'{'):
                return raw
            try:
                body = json.loads(raw.decode('utf-8'))
            except (ValueError, UnicodeError):
                raise DeliveryError(f'Invalid JSON response from {endpoint}') from None
            code = body.get('errcode',0)
            if code:
                ip = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b',str(body.get('errmsg',''))) if code == 40164 else None
                raise ApiError(code, ip.group(0) if ip else None)
            if binary:
                raise DeliveryError('Image endpoint returned JSON instead of image bytes')
            return body
        except requests.RequestException:
            raise DeliveryError(f'Network request failed at {endpoint}; result may be uncertain') from None
        finally:
            write_json(self.evidence/'request_audit.json',self.audit)


def normalized(text):
    return str(text or '').replace('\r\n','\n').strip()


def same_topic(article, data):
    if article.get('title') == data['title']:
        return True
    url = data['source_url'].rstrip('/')
    if str(article.get('content_source_url','')).rstrip('/') == url or url in str(article.get('content','')):
        return True
    title = str(article.get('title','')).casefold()
    return any(str(key).casefold() in title for key in data.get('topic_keywords',[]) if key)


def list_all(client, kind):
    if kind not in ('draft','freepublish'):
        raise DeliveryError('Unsupported listing')
    offset, records, seen, pages, total = 0, [], set(), [], None
    for _ in range(1000):
        body = client.call(kind+'/batchget',{'offset':offset,'count':20,'no_content':0})
        items, count = body.get('item',[]), body.get('total_count')
        if not isinstance(count,int) or not isinstance(items,list) or count < 0:
            raise DeliveryError('Invalid pagination response')
        if total is not None and total != count:
            raise DeliveryError('Remote list changed during pagination; inspect again')
        total = count
        pages.append({'offset':offset,'count':len(items),'total':total})
        for item in items:
            ident = item.get('media_id') or item.get('article_id')
            if not ident or ident in seen:
                raise DeliveryError('Duplicate or missing identity during pagination')
            seen.add(ident)
            articles = (item.get('content') or {}).get('news_item',[])
            if not isinstance(articles,list):
                raise DeliveryError('Invalid article list')
            for i, article in enumerate(articles):
                records.append((ident,i,article))
        offset += len(items)
        if offset >= total:
            return records,pages
        if not items:
            raise DeliveryError('Incomplete pagination')
    raise DeliveryError('Pagination limit reached')


def get_article(client, media_id):
    full = client.call('draft/get',{'media_id':media_id})
    items = full.get('news_item',[])
    if len(items) != 1 or items[0].get('article_type') != 'newspic':
        raise DeliveryError('Expected a single-article newspic draft; multi-article edits are unsupported')
    return items[0],full


def stable(article):
    keys = ('article_type','title','author','content','image_info','cover_info','thumb_media_id',
            'need_open_comment','only_fans_can_comment','content_source_url')
    return {key:article.get(key) for key in keys}


def stable_sha(article):
    return digest(json.dumps(stable(article),sort_keys=True,ensure_ascii=False).encode('utf-8'))


def state_dir(draft):
    path = draft/'.wechat'
    path.mkdir(exist_ok=True)
    return path


def read_state(draft):
    path = state_dir(draft)/'state.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def inspect(draft, client, data):
    records,pages = list_all(client,'draft')
    matches = [(ident,i,a) for ident,i,a in records if same_topic(a,data)]
    snapshots = []
    for ident,i,a in matches:
        if i != 0:
            raise DeliveryError('Matching topic belongs to a multi-article draft; reconcile manually')
        article,full = get_article(client,ident)
        item = {'media_id':ident,'account':client.account,'stable_sha256':stable_sha(article),'article':article}
        snapshots.append(item)
        write_json(client.evidence/'draft_get.json',full)
    result = {'account':client.account,'pages':pages,'matches':snapshots}
    write_json(state_dir(draft)/'snapshot.json',result)
    # Recover a lost response through exact text and material identity, never by another add.
    pending = read_state(draft)
    if pending.get('status') == 'outcome_uncertain' and pending.get('account') == client.account:
        expected = pending.get('expected',{})
        def image_ids(article):
            return [x.get('image_media_id') for x in article.get('image_info',{}).get('image_list',[])]
        exact = [s for s in snapshots if s['article'].get('title')==expected.get('title')
                 and normalized(s['article'].get('content'))==normalized(expected.get('content'))
                 and image_ids(s['article'])==image_ids(expected)]
        if len(exact)==1:
            pending.update(media_id=exact[0]['media_id'],status='saved_unverified')
            write_json(state_dir(draft)/'state.json',pending)
    return {'matching_count':len(matches),'snapshot':str(state_dir(draft)/'snapshot.json'),
            'matches':[{'media_id':s['media_id'],'title':s['article']['title']} for s in snapshots]}


def upload_images(draft, client, data):
    cache_path = state_dir(draft)/'uploads.json'
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    if cache.get('account') != client.account:
        cache = {'account':client.account,'images':{}}
    ids = []
    for name in newspic.output_files(data):
        path = draft/name
        sha = digest(path.read_bytes())
        if sha not in cache['images']:
            body = client.call('material/add_material',params={'type':'image'},image_path=path)
            if not body.get('media_id'):
                raise DeliveryError('Material upload did not return an identity')
            cache['images'][sha] = body['media_id']
            write_json(cache_path,cache)
        ids.append(cache['images'][sha])
    return ids


def expected_article(data, media_ids, existing=None):
    article = newspic.preview_payload(data)['articles'][0]
    if not data.get('author'):
        raise DeliveryError('Set author explicitly in newspic.json')
    article['author'] = data['author']
    article['image_info'] = {'image_list':[{'image_media_id':x} for x in media_ids]}
    if existing:
        # Preserve editor-controlled settings; updating these is outside this command's scope.
        for key in ('need_open_comment','only_fans_can_comment','cover_info'):
            if key in existing:
                article[key] = existing[key]
    return article


def verify(draft, client, data, media_id=None):
    state = read_state(draft)
    if state.get('account') != client.account or not state.get('expected'):
        raise DeliveryError('No submitted version for this account; inspect the draft first')
    if state.get('input_sha256') != input_fingerprint(draft,data):
        raise DeliveryError('Local content changed since submission; remote verification cannot certify this revision')
    media_id = media_id or state.get('media_id')
    if not media_id or (state.get('media_id') and media_id != state['media_id']):
        raise DeliveryError('Missing or conflicting draft identity')
    article,full = get_article(client,media_id)
    write_json(client.evidence/'draft_get.json',full)
    expected = state['expected']
    ids = [x['image_media_id'] for x in article.get('image_info',{}).get('image_list',[])]
    expected_ids = [x['image_media_id'] for x in expected['image_info']['image_list']]
    def crops(a):
        return {tuple(str(x.get(k,'')) for k in ('ratio','x1','y1','x2','y2'))
                for x in a.get('cover_info',{}).get('crop_percent_list',[])}
    checks = {'type':article.get('article_type')=='newspic','title':article.get('title')==expected['title'],
              'content':normalized(article.get('content'))==normalized(expected['content']),
              'image_order':ids==expected_ids,'cover':bool(ids) and article.get('thumb_media_id')==ids[0],
              'requested_crops_preserved':crops(expected).issubset(crops(article)),
              'author_not_conflicting':article.get('author') in (None,'',expected['author'])}
    image_checks=[]
    for name,ident in zip(newspic.output_files(data),ids):
        raw=client.call('material/get_material',{'media_id':ident},binary=True)
        with Image.open(io.BytesIO(raw)) as im:
            size=list(im.size)
        (client.evidence/('remote-'+name)).write_bytes(raw)
        image_checks.append({'file':name,'bytes_match':raw==(draft/name).read_bytes(),'dimensions':size,
                             'sha256':digest(raw)})
    checks['image_bytes_and_dimensions']=(len(image_checks)==len(data['cards']) and
        all(x['bytes_match'] and x['dimensions']==[1080,1440] for x in image_checks))
    records,pages=list_all(client,'draft')
    topic=[ident for ident,_,a in records if same_topic(a,data)]
    checks['unique_topic']=topic==[media_id]
    checks['unique_title']=[ident for ident,_,a in records if a.get('title')==expected['title']]==[media_id]
    publications,pub_pages=list_all(client,'freepublish')
    published=[ident for ident,_,a in publications if same_topic(a,data)]
    checks['published_false']=not published
    result={'passed':all(checks.values()),'checks':checks,'media_id':media_id,'title':expected['title'],
            'draft_saved':True,'published':bool(published),'author_submitted':expected['author'],
            'author_readback':article.get('author'),'image_count':len(ids),'image_checks':image_checks,
            'draft_pages':pages,'published_pages':pub_pages,'same_topic_count':len(topic),
            'verified_at':datetime.now(timezone.utc).isoformat()}
    write_json(client.evidence/'verification.json',result)
    state.update(status='verified' if result['passed'] else 'saved_with_differences',media_id=media_id,
                 verification=str((client.evidence/'verification.json').relative_to(draft)))
    write_json(state_dir(draft)/'state.json',state)
    return result


@contextmanager
def write_lock(draft):
    path=state_dir(draft)/'write.lock'
    try:
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        raise DeliveryError('A save lock exists. Verify no other save is running before removing a stale lock') from None
    os.close(fd)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def save(draft, client, data, *, update_id=None, snapshot_path=None):
    if data.get('demo_only'):
        raise DeliveryError('Layout-only examples cannot be uploaded')
    if not newspic.validate_newspic(draft,data)['passed']:
        raise DeliveryError('Local validation failed; render and inspect the current revision')
    with write_lock(draft):
        state=read_state(draft)
        if state and state.get('account') != client.account:
            raise DeliveryError('This draft has delivery state for another account')
        if state.get('status')=='outcome_uncertain':
            raise DeliveryError('Previous save outcome is uncertain; run inspect and verify before any new save')
        if state.get('media_id') and not update_id:
            return verify(draft,client,data)
        records,_=list_all(client,'draft')
        matches=[(ident,i,a) for ident,i,a in records if same_topic(a,data)]
        existing=None
        if update_id:
            if not snapshot_path:
                raise DeliveryError('Updates require a reviewed snapshot from inspect')
            snapshot=json.loads(Path(snapshot_path).read_text(encoding='utf-8'))
            candidates=[x for x in snapshot.get('matches',[]) if x['media_id']==update_id]
            if snapshot.get('account')!=client.account or len(candidates)!=1:
                raise DeliveryError('Snapshot identity/account mismatch')
            existing,full=get_article(client,update_id)
            if stable_sha(existing)!=candidates[0]['stable_sha256']:
                raise DeliveryError('Backend edits changed since inspection; reconcile and inspect again')
            if any(ident!=update_id for ident,_,_ in matches):
                raise DeliveryError('Another matching draft exists; do not merge or delete automatically')
            write_json(client.evidence/'before_update.json',full)
        elif matches:
            raise DeliveryError('A matching draft already exists; run inspect and preserve its edits')
        publications,_=list_all(client,'freepublish')
        if any(same_topic(a,data) for _,_,a in publications):
            raise DeliveryError('Matching published article found; reconcile identity before saving')
        approved=input_fingerprint(draft,data)
        ids=upload_images(draft,client,data)
        expected=expected_article(data,ids,existing)
        if input_fingerprint(draft,newspic.load_newspic(draft))!=approved or not newspic.validate_newspic(draft,data)['passed']:
            raise DeliveryError('Local files changed during uploads')
        if update_id:
            immediate,_=get_article(client,update_id)
            if stable_sha(immediate)!=stable_sha(existing):
                raise DeliveryError('Backend changed during uploads; no update sent')
        else:
            guarded,_=list_all(client,'draft')
            if any(same_topic(a,data) for _,_,a in guarded):
                raise DeliveryError('Matching draft appeared during uploads; no add sent')
        state={'account':client.account,'status':'outcome_uncertain','media_id':update_id,
               'input_sha256':approved,'expected':expected}
        write_json(state_dir(draft)/'state.json',state)
        operation='draft/update' if update_id else 'draft/add'
        payload={'media_id':update_id,'index':0,'articles':expected} if update_id else {'articles':[expected]}
        try:
            response=client.call(operation,payload)
        except ApiError:
            state['status']='save_rejected'
            write_json(state_dir(draft)/'state.json',state)
            raise
        ident=update_id or response.get('media_id')
        if not ident:
            raise DeliveryError('Save did not return an identity; outcome remains uncertain')
        state.update(media_id=ident,status='saved_unverified')
        write_json(state_dir(draft)/'state.json',state)
        return verify(draft,client,data,ident)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['plan','inspect','save','verify'])
    parser.add_argument('draft',type=Path)
    parser.add_argument('--credentials',help='Private JSON outside the repository; otherwise use environment variables')
    parser.add_argument('--direct',action='store_true',help='Ignore proxy environment variables for this process only')
    parser.add_argument('--confirm-draft-save',action='store_true',help='Use only when this draft write is authorized')
    parser.add_argument('--update',metavar='MEDIA_ID')
    parser.add_argument('--snapshot',type=Path)
    args=parser.parse_args()
    draft=args.draft.resolve()
    client=None
    try:
        data=newspic.load_newspic(draft)
        if args.command=='plan':
            result=newspic.validate_newspic(draft,data)
            print(json.dumps({'passed':result['passed'],'demo_only':bool(data.get('demo_only')),
                              'network_requests':0,'title':data['title'],'pages':len(data['cards']),
                              'checks':result['checks']},ensure_ascii=False,indent=2))
            return 0 if result['passed'] else 1
        if args.command=='save' and (not args.confirm_draft_save or data.get('demo_only')):
            raise DeliveryError('Saving requires authorized --confirm-draft-save and a non-demo draft')
        if args.command=='save' and not newspic.validate_newspic(draft,data)['passed']:
            raise DeliveryError('Local validation failed before account access')
        app_id,secret=load_credentials(args.credentials)
        evidence=state_dir(draft)/datetime.now(timezone.utc).strftime('attempt-%Y%m%dT%H%M%S%fZ')
        client=Client(app_id,secret,evidence,direct=args.direct)
        del secret
        if args.command=='inspect':result=inspect(draft,client,data)
        elif args.command=='verify':result=verify(draft,client,data)
        else:result=save(draft,client,data,update_id=args.update,snapshot_path=args.snapshot)
        print(json.dumps({k:v for k,v in result.items() if k!='image_checks'},ensure_ascii=False,indent=2))
        return 0 if result.get('passed',True) else 2
    except (DeliveryError, OSError, ValueError, KeyError, TypeError) as error:
        safe=str(error) if isinstance(error,DeliveryError) else type(error).__name__
        print(json.dumps({'error':safe,'published':None,'instructions':'Inspect stored state before retrying any uncertain save.'},ensure_ascii=False))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
