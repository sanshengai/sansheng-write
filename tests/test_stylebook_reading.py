"""Actual prepublish consumer refuses stale or incomplete reading evidence."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from scripts.stylebook_reading import CHECKS, context, accept_reading, verify_reading, check_author_text
from scripts.stylebook_release import reading_errors
from scripts.stylebook_workflow import sha
from scripts import pipeline
from test_stylebook_evidence import completed


def test_quoted_list_parser_compatibility_preserves_wording_checks(tmp_path):
    (tmp_path/'定稿.md').write_text('> **划重点**\n> - 官方后台:数据准\n> - 成本为 -5 元\n')
    html = '<blockquote><strong>划重点</strong><ul><li>官方后台:数据准</li><li>成本为 -5 元</li></ul></blockquote>'
    assert check_author_text(tmp_path, html)
    for changed in [html.replace('数据准', ''), html.replace('-5', '5'),
                    '<blockquote>划重点<ul><li>成本为 -5 元</li><li>官方后台:数据准</li></ul></blockquote>']:
        with pytest.raises(ValueError, match='作者文字'):
            check_author_text(tmp_path, changed)


def test_code_list_marker_is_author_text(tmp_path):
    (tmp_path/'定稿.md').write_text('```text\n> 标题\n> - 原样代码\n```\n')
    assert check_author_text(tmp_path, '<pre>&gt; 标题\n&gt; - 原样代码</pre>')
    with pytest.raises(ValueError, match='作者文字'):
        check_author_text(tmp_path, '<pre>&gt; 标题\n&gt; 原样代码</pre>')


def prepared(tmp_path, monkeypatch):
    completed(tmp_path, monkeypatch, body=True)
    html = tmp_path/'定稿.html'
    html.write_text('<html><body><p>工具先下载，然后验证来源。</p><img src="素材/infographic-01.png"></body></html>')
    current = context(tmp_path)
    views = []
    for width in [390, 430, 900]:
        shot = tmp_path/f'synthetic-{width}.png'
        Image.new('RGB', (width, 844), 'ivory').save(shot)
        views.append({'width':width, 'viewport_height':844, 'document_width':width, 'document_height':844,
                      'images':[{**image,'loaded':True,'natural_width':1600,'display_width':width-64} for image in current['images']],
                      'screenshot':{'path':str(shot.relative_to(tmp_path)), 'sha256':sha(shot)}})
    observation = {'schema_version':1,'html_sha256':sha(html),
                   'source_strength':'host_attested_browser_and_native_reading', 'additional_independent_review':False,
                   'native_checks':dict.fromkeys(CHECKS,True),'views':views}
    path = tmp_path/'synthetic-reading-observation.json'
    path.write_text(json.dumps(observation))
    return path, observation


def test_reading_seal_reaches_actual_release_consumer_then_refuses_changed_html(tmp_path, monkeypatch):
    path,_ = prepared(tmp_path,monkeypatch)
    assert reading_errors(tmp_path)
    before = pipeline._pre_publish_errors(tmp_path)
    assert any('整篇阅读' in e for e in before)
    record,errors = accept_reading(tmp_path,path)
    assert not errors,errors
    assert record['additional_independent_review'] is False
    verify_reading(tmp_path)
    assert not reading_errors(tmp_path)
    after = pipeline._pre_publish_errors(tmp_path)
    assert not any('整篇阅读' in e for e in after)
    assert any('hero.png' in e for e in after)  # Other requirements still apply.
    with (tmp_path/'定稿.html').open('a') as out: out.write('<p>Changed reading layout</p>')
    assert reading_errors(tmp_path)
    assert any('整篇阅读' in e for e in pipeline._pre_publish_errors(tmp_path))


@pytest.mark.parametrize('mutation',['empty','missing_view','overflow','bad_image','wrong_image','short_screenshot','unread_text','false_independence','empty_html','missing_prose'])
def test_reading_rejects_real_failure_conditions(tmp_path,monkeypatch,mutation):
    path,value=prepared(tmp_path,monkeypatch)
    if mutation=='empty': value={}
    elif mutation=='missing_view': value['views'].pop()
    elif mutation=='overflow': value['views'][0]['document_width']=500
    elif mutation=='bad_image': value['views'][0]['images'][0]['loaded']=False
    elif mutation=='wrong_image': value['views'][0]['images'][0]['sha256']='0'*64
    elif mutation=='short_screenshot': value['views'][0]['document_height']=999
    elif mutation=='unread_text': value['native_checks']['required_text_readable']=False
    elif mutation=='false_independence': value['additional_independent_review']=True
    elif mutation=='missing_prose':
        (tmp_path/'定稿.html').write_text('<img src="素材/infographic-01.png">')
    else: (tmp_path/'定稿.html').write_bytes(b'')
    path.write_text(json.dumps(value))
    record,errors=accept_reading(tmp_path,path)
    assert record is None and errors
    assert reading_errors(tmp_path)


@pytest.mark.parametrize('mutation',['screenshot','observation','image','pointer'])
def test_bound_reading_inputs_invalidate_published_consumer(tmp_path,monkeypatch,mutation):
    path,value=prepared(tmp_path,monkeypatch)
    record,errors=accept_reading(tmp_path,path)
    assert not errors
    if mutation=='screenshot': (tmp_path/value['views'][0]['screenshot']['path']).write_bytes(b'changed')
    elif mutation=='observation': path.write_text('{}')
    elif mutation=='image': (tmp_path/'素材/infographic-01.png').write_bytes(b'changed')
    else: (tmp_path/'素材/stylebook-reading-review.json').write_text('{}')
    assert reading_errors(tmp_path)


def test_actual_reading_cli_rejects_missing_evidence_and_accepts_complete_fixture(tmp_path,monkeypatch):
    path,_=prepared(tmp_path,monkeypatch)
    entry=Path(__file__).resolve().parents[1]/'scripts/pipeline.py'
    command=[sys.executable,str(entry),'--dir',str(tmp_path),'accept-stylebook-reading','--observation',str(path)]
    run=subprocess.run(command,capture_output=True,text=True)
    assert run.returncode==0,run.stdout+run.stderr
    assert '未新增独立模型复核或发布文章' in run.stdout
    path.write_text('{}')
    refused=subprocess.run(command,capture_output=True,text=True)
    assert refused.returncode==2
    assert reading_errors(tmp_path)
