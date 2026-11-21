import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import create_demo
import manifest
import newspic
import wechat_draft as wx


def fixture(path, pages=3):
    create_demo.create(path,pages)
    data=newspic.load_newspic(path)
    data['demo_only']=False
    data['author']='Test Editor'
    manifest.write_json(path/'newspic.json',data)
    for i,name in enumerate(newspic.output_files(data)):
        Image.new('RGB',(1080,1440),(30+i*20,50,90)).save(path/name)
    manifest.write_render_manifest(path,data)
    return data


class FakeClient:
    def __init__(self, evidence):
        self.account='unit-test-account'
        self.evidence=evidence;evidence.mkdir(parents=True,exist_ok=True)
        self.records=[];self.images={};self.calls=[];self.fail_upload_at=None
        self.timeout_after_add=False;self.mutate_on_get=None;self.get_count=0
        self.corrupt_image=False

    def call(self,endpoint,payload=None,**kwargs):
        self.calls.append(endpoint)
        payload=payload or {}
        if endpoint.endswith('/batchget'):
            records=self.records if endpoint=='draft/batchget' else []
            start=payload['offset'];items=records[start:start+payload['count']]
            return {'total_count':len(records),'item':copy.deepcopy(items)}
        if endpoint=='material/add_material':
            n=self.calls.count(endpoint)
            if n==self.fail_upload_at:raise wx.DeliveryError('simulated material failure')
            ident=f'image-{len(self.images)+1}';self.images[ident]=kwargs['image_path'].read_bytes()
            return {'media_id':ident}
        if endpoint=='draft/add':
            article=copy.deepcopy(payload['articles'][0]);article.pop('author',None)
            article['thumb_media_id']=article['image_info']['image_list'][0]['image_media_id']
            ident=f'draft-{len(self.records)+1}'
            self.records.append({'media_id':ident,'content':{'news_item':[article]}})
            if self.timeout_after_add:raise wx.DeliveryError('simulated response loss')
            return {'media_id':ident}
        if endpoint=='draft/update':
            record=next(r for r in self.records if r['media_id']==payload['media_id'])
            article=copy.deepcopy(payload['articles']);article.pop('author',None)
            article['thumb_media_id']=article['image_info']['image_list'][0]['image_media_id']
            record['content']['news_item']=[article]
            return {'errcode':0}
        if endpoint=='draft/get':
            self.get_count+=1
            record=next(r for r in self.records if r['media_id']==payload['media_id'])
            if self.mutate_on_get==self.get_count:
                record['content']['news_item'][0]['content']+=' backend edit'
            return copy.deepcopy(record['content'])
        if endpoint=='material/get_material':
            if self.corrupt_image:
                return next(iter(self.images.values()))
            return self.images[payload['media_id']]
        raise AssertionError(endpoint)


class ContractTests(unittest.TestCase):
    def test_source_contract_and_freshness(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);data=fixture(path)
            self.assertTrue(newspic.validate_newspic(path,data)['passed'])
            data['cards'][1]['note']+=' 新增文字。'
            self.assertFalse(newspic.validate_newspic(path,data)['passed'])

    def test_source_hash_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);data=fixture(path)
            Image.new('RGB',(1600,1100),'red').save(path/data['cards'][0]['image'])
            self.assertFalse(newspic.validate_newspic(path,data,require_rendered=False)['passed'])

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);data=fixture(path);data['cards'][0]['image']='../outside.png'
            self.assertFalse(newspic.validate_newspic(path,data,require_rendered=False)['passed'])

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);path=parent/'draft';data=fixture(path)
            outside=parent/'outside.png';Image.new('RGB',(10,10)).save(outside)
            (path/'images/escape.png').symlink_to(outside)
            data['cards'][0]['image']='images/escape.png'
            self.assertFalse(newspic.validate_newspic(path,data,require_rendered=False)['passed'])

    def test_seven_page_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);data=fixture(path,7)
            self.assertEqual(newspic.output_files(data)[-1],'newspic-07.png')
            self.assertTrue(newspic.validate_newspic(path,data)['passed'])

    def test_duplicate_source_basename_does_not_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);data=fixture(path)
            # An exact relative path must be present, even if a different folder uses the same basename.
            src=json.loads((path/'sources.json').read_text())
            used=data['cards'][0]['image']
            next(record for record in src['images'] if record['file']==used)['file']='another/'+Path(used).name
            manifest.write_json(path/'sources.json',src)
            self.assertFalse(newspic.validate_newspic(path,data,require_rendered=False)['passed'])


class CoverLayoutTests(unittest.TestCase):
    def test_cover_fills_canvas_and_respects_focal_point(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            for count in (3,7):
                with self.subTest(pages=count):
                    path=Path(tmp)/str(count);create_demo.create(path,count)
                    data=newspic.load_newspic(path);data['cards'][0]['focal_point']={'x':.75,'y':.6}
                    page=browser.new_page(viewport={'width':1080,'height':1440})
                    (path/'newspic.html').write_text(newspic.build_html(path,data),encoding='utf-8')
                    page.goto((path/'newspic.html').as_uri(),wait_until='networkidle')
                    page.evaluate('document.fonts.ready')
                    boxes=page.evaluate('''() => {
                      const card=document.querySelector('.multi-cover');
                      const image=card.querySelector('.media'),shade=card.querySelector('.multi-shade');
                      const copy=card.querySelector('.multi-cover-copy');
                      const rect=e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]};
                      const s=getComputedStyle(image);
                      return {card:rect(card),image:rect(image),shade:rect(shade),fit:s.objectFit,
                        position:s.objectPosition,padding:s.padding,border:s.borderWidth,radius:s.borderRadius,
                        copyBackground:getComputedStyle(copy).backgroundColor,copyBottom:copy.getBoundingClientRect().bottom};
                    }''')
                    self.assertEqual(boxes['card'],boxes['image'])
                    self.assertEqual(boxes['card'],boxes['shade'])
                    self.assertEqual(boxes['fit'],'cover');self.assertEqual(boxes['position'],'75% 60%')
                    for prop in ('padding','border','radius'):self.assertEqual(boxes[prop],'0px')
                    self.assertEqual(boxes['copyBackground'],'rgba(0, 0, 0, 0)')
                    self.assertLess(boxes['copyBottom'],1440*.55)
                    page.close()
            browser.close()


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'draft';self.data=fixture(self.path)
        self.client=FakeClient(self.path/'.wechat/test-evidence')

    def test_create_readback_and_author_absence(self):
        result=wx.save(self.path,self.client,self.data)
        self.assertTrue(result['passed']);self.assertIsNone(result['author_readback'])
        self.assertFalse(result['published']);self.assertEqual(self.client.calls.count('draft/add'),1)
        self.assertEqual(result['image_count'],3)

    def test_rerun_only_verifies_existing_identity(self):
        first=wx.save(self.path,self.client,self.data)
        second=wx.save(self.path,self.client,self.data)
        self.assertEqual(first['media_id'],second['media_id'])
        self.assertEqual(self.client.calls.count('draft/add'),1)

    def test_duplicate_found_on_second_page_prevents_upload(self):
        for i in range(21):
            article={'title':'unrelated '+str(i),'content':'different'}
            if i==20:article['title']=self.data['title']
            self.client.records.append({'media_id':f'old-{i}','content':{'news_item':[article]}})
        with self.assertRaises(wx.DeliveryError):wx.save(self.path,self.client,self.data)
        self.assertNotIn('material/add_material',self.client.calls)
        self.assertNotIn('draft/add',self.client.calls)

    def test_response_loss_recovers_without_second_add(self):
        self.client.timeout_after_add=True
        with self.assertRaises(wx.DeliveryError):wx.save(self.path,self.client,self.data)
        self.assertEqual(wx.read_state(self.path)['status'],'outcome_uncertain')
        with self.assertRaises(wx.DeliveryError):wx.save(self.path,self.client,self.data)
        wx.inspect(self.path,self.client,self.data)
        result=wx.verify(self.path,self.client,self.data)
        self.assertTrue(result['passed']);self.assertEqual(self.client.calls.count('draft/add'),1)

    def test_partial_upload_cache_resumes(self):
        self.client.fail_upload_at=2
        with self.assertRaises(wx.DeliveryError):wx.save(self.path,self.client,self.data)
        self.client.fail_upload_at=None
        result=wx.save(self.path,self.client,self.data)
        self.assertTrue(result['passed']);self.assertEqual(len(self.client.images),3)
        self.assertEqual(self.client.calls.count('material/add_material'),4)

    def test_remote_image_mismatch_is_reported_after_save(self):
        self.client.corrupt_image=True
        result=wx.save(self.path,self.client,self.data)
        self.assertFalse(result['passed']);self.assertTrue(result['draft_saved'])
        self.assertEqual(wx.read_state(self.path)['status'],'saved_with_differences')

    def test_update_preserves_backend_comment_settings(self):
        result=wx.save(self.path,self.client,self.data)
        remote=self.client.records[0]['content']['news_item'][0]
        remote['need_open_comment']=0;remote['only_fans_can_comment']=1
        wx.inspect(self.path,self.client,self.data)
        self.data['cards'][1]['note']+=' 经本次修订。'
        manifest.write_json(self.path/'newspic.json',self.data);manifest.write_render_manifest(self.path,self.data)
        updated=wx.save(self.path,self.client,self.data,update_id=result['media_id'],snapshot_path=self.path/'.wechat/snapshot.json')
        self.assertTrue(updated['passed']);self.assertEqual(self.client.calls.count('draft/update'),1)
        remote=self.client.records[0]['content']['news_item'][0]
        self.assertEqual(remote['need_open_comment'],0);self.assertEqual(remote['only_fans_can_comment'],1)

    def test_backend_edit_after_snapshot_prevents_update(self):
        result=wx.save(self.path,self.client,self.data)
        wx.inspect(self.path,self.client,self.data)
        self.client.records[0]['content']['news_item'][0]['content']+=' user edit'
        with self.assertRaises(wx.DeliveryError):
            wx.save(self.path,self.client,self.data,update_id=result['media_id'],snapshot_path=self.path/'.wechat/snapshot.json')
        self.assertNotIn('draft/update',self.client.calls)

    def test_backend_edit_during_upload_prevents_update(self):
        result=wx.save(self.path,self.client,self.data)
        wx.inspect(self.path,self.client,self.data)
        self.client.mutate_on_get=self.client.get_count+2
        with self.assertRaises(wx.DeliveryError):
            wx.save(self.path,self.client,self.data,update_id=result['media_id'],snapshot_path=self.path/'.wechat/snapshot.json')
        self.assertNotIn('draft/update',self.client.calls)

    def test_demo_cannot_save(self):
        self.data['demo_only']=True
        with self.assertRaises(wx.DeliveryError):wx.save(self.path,self.client,self.data)
        self.assertEqual(self.client.calls,[])

    def test_local_changes_after_submission_cannot_be_certified(self):
        wx.save(self.path,self.client,self.data)
        self.data['title']='变更后的内容必须重新审核与渲染'
        with self.assertRaises(wx.DeliveryError):wx.verify(self.path,self.client,self.data)


class TransportTests(unittest.TestCase):
    def client(self,path):
        client=object.__new__(wx.Client);client.token='test-token';client.evidence=path;client.audit=[]
        client.session=unittest.mock.Mock();return client

    def test_unicode_payload_is_utf8_not_ascii_escapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=self.client(Path(tmp))
            client.session.post.return_value.status_code=200
            client.session.post.return_value.content=b'{"errcode":0}'
            client.call('draft/update',{'title':'中文标题'})
            body=client.session.post.call_args.kwargs['data']
            self.assertIn('中文标题'.encode(),body);self.assertNotIn(b'\\u4e2d',body)

    def test_transport_errors_do_not_expose_token_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=self.client(Path(tmp))
            client.session.post.side_effect=requests.ConnectionError('sensitive URL test-token test-secret')
            with self.assertRaises(wx.DeliveryError) as error:client.call('draft/get',{})
            self.assertNotIn('test-token',str(error.exception))
            audit=(Path(tmp)/'request_audit.json').read_text()
            self.assertNotIn('test-token',audit);self.assertNotIn('test-secret',audit)

    def test_publish_endpoint_never_reaches_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=self.client(Path(tmp))
            with self.assertRaises(wx.DeliveryError):client.call('freepublish/submit',{})
            client.session.post.assert_not_called()

    def test_allowlist_error_only_exposes_code_and_ip(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=self.client(Path(tmp));client.session.post.return_value.status_code=200
            client.session.post.return_value.content=json.dumps({'errcode':40164,'errmsg':'invalid ip 192.0.2.10; internal secret details'}).encode()
            with self.assertRaises(wx.ApiError) as error:client.call('draft/get',{})
            self.assertEqual(error.exception.allowlist_ip,'192.0.2.10')
            self.assertNotIn('internal secret',str(error.exception))


if __name__=='__main__':unittest.main()
