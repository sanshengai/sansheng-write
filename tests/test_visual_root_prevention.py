import hashlib
import json
from pathlib import Path
import sys
import pytest
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from article_paths import process_file
from visual_inputs import bind_references, reference_paths
from visual_workflow import compile_visual_plan
from visual_retry import input_digest, retry_errors
from website_evidence import media_errors
from delivery_snapshot import file_link, write_snapshot
from test_visual_workflow import _article
import pipeline
import render_visuals


def test_compiler_rejects_conflict_before_creating_renderer_batch(tmp_path):
    cwd = _article(tmp_path)
    plan = json.loads((cwd / 'visual-plan.json').read_text())
    plan['cover']['visual_facts'] = ['严禁斜线、竖线或标点']
    plan['hero']['visual_facts'] = ['禁止植物、电脑、杯子、书籍、边框']
    (cwd / 'visual-plan.json').write_text(json.dumps(plan))
    result, errors = compile_visual_plan(cwd)
    assert result is None and any('斜线' in e for e in errors) and any('边框' in e for e in errors)
    assert not (cwd / '素材/render-batch.json').exists()
    plan['cover']['layout_options'] = {'tag_separator': 'space'}
    plan['hero']['layout_options'] = {'frame': 'none'}
    (cwd / 'visual-plan.json').write_text(json.dumps(plan))
    result, errors = compile_visual_plan(cwd)
    assert result is not None and errors == []
    prompts = '\n'.join(p.read_text() for p in (cwd / '素材/prompts').rglob('*.md'))
    assert 'wide whitespace separators' in prompts and 'Do not include frames or borders' in prompts
    assert 'thin slash dividers' not in prompts and 'Include one clear dotted frame' not in prompts
    # Mutation on the real compiler path: explicit option cannot waive an empty scene.
    plan['hero']['visual_facts'] = []
    (cwd / 'visual-plan.json').write_text(json.dumps(plan))
    assert compile_visual_plan(cwd)[1]


def test_references_bound_to_bytes_and_scope(tmp_path):
    Image.new('RGB', (20,20), 'green').save(tmp_path / 'ref.png')
    ref = {'file': 'ref.png', 'source_url': 'https://example.org/news', 'purpose': '心形及眼镜身份'}
    bound = bind_references(tmp_path, {'reference_images': [ref]})
    assert reference_paths(tmp_path, {'reference_images': bound}) == [tmp_path / 'ref.png']
    Image.new('RGB', (20,20), 'red').save(tmp_path / 'ref.png')
    with pytest.raises(ValueError, match='SHA256'):
        reference_paths(tmp_path, {'reference_images': bound})
    for mutation in [{**ref, 'file': '../ref.png'}, {**ref, 'purpose': ''}, {**ref, 'source_url': 'http://example.org'}]:
        with pytest.raises(ValueError):
            bind_references(tmp_path, {'reference_images': [mutation]})
    assert bind_references(tmp_path, {}) == []


def test_retry_blocks_renderer_not_just_reports_failure(tmp_path, monkeypatch):
    (tmp_path / 'visual-plan.json').write_text('{}')
    row = {'kind':'qa_verdict', 'label':'cover', 'outcome':'fail', 'failed_checks':['brand_palette_match'], 'input_digest':input_digest(tmp_path, 'cover'), 'render_seq':1}
    rows = [row, {**row, "render_seq":2}]
    for r in rows:
        render_visuals.log_attempt(tmp_path, r)
    monkeypatch.setattr(render_visuals, '_render_visual_candidates', lambda *a, **k: pytest.fail('must not render'))
    assert render_visuals.render_visuals(tmp_path, candidate_count=3)[1]
    diagnostic = json.loads(process_file(tmp_path, '_visual-retry-diagnostic.json').read_text())
    process_file(tmp_path, '_visual-retry-decision.json', for_write=True).write_text(json.dumps({'binding':diagnostic['binding'], 'action':'regenerate','reason':'已逐项确认输入及参考图齐全，但现图标题被对象遮挡，需带局部约束重生成。'}))
    assert retry_errors(tmp_path, rows) == []
    (tmp_path / 'visual-plan.json').write_text('{"cover":{"new":true}}')
    assert retry_errors(tmp_path, rows) == []
    assert retry_errors(tmp_path, []) == []


def test_video_and_audio_must_be_in_actual_entry(tmp_path):
    (tmp_path / '定稿.md').write_text('<!-- VIDEO: example -->')
    get = lambda url, method: (200, '')
    assert media_errors(tmp_path, 'OBS-1', 'https://site.example', '<h1>标题</h1>', get)
    src = 'https://media.example/v.mp4'
    (tmp_path / '_website-media.json').write_text(json.dumps({'entries':[{'src':src}]}))
    assert media_errors(tmp_path, 'OBS-1', 'https://site.example', f'<a src="{src}">link</a>', get)
    assert media_errors(tmp_path, 'OBS-1', 'https://site.example', f'<video><source src="{src}"></video>', get) == []
    process_file(tmp_path, '_music-manifest.json', for_write=True).write_text('{}')
    assert media_errors(tmp_path, 'OBS-1', 'https://site.example', f'<video src="{src}"></video>', get)
    body = f'<video src="{src}"></video><audio src="/song-assets/OBS-1/song.mp3"></audio>'
    assert media_errors(tmp_path, 'OBS-1', 'https://site.example', body, get) == []
    assert media_errors(tmp_path, 'OBS-1', 'https://site.example', body, lambda *a:(404,''))


def test_queued_exit_zero_stays_pending_and_not_resubmitted(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, 'brand', lambda:{'publish':{'website_command':'echo {code}', 'website_cwd':str(tmp_path)}})
    monkeypatch.setattr(pipeline, '_archived_code', lambda c:'OBS-1')
    monkeypatch.setattr(pipeline, '_uncommitted_archive_outputs', lambda *a:[])
    monkeypatch.setattr(pipeline, '_resolve_website_command', lambda c:(c,''))
    calls = []
    class Result:
        returncode=0
        stdout='JOB_ID=x JOB_STATE=queued'
        stderr=''
    runner = lambda *a, **k: calls.append(a) or Result()
    assert pipeline._run_website_sync(tmp_path, 'https://mp.weixin.qq.com/s/X', runner=runner, live_checker=lambda *a:False) is False
    assert json.loads(process_file(tmp_path, '_website-sync-receipt.json').read_text())['status'] == 'pending'
    assert pipeline._run_website_sync(tmp_path, 'https://mp.weixin.qq.com/s/X', runner=runner, live_checker=lambda *a:False) is False
    assert len(calls) == 1


def test_snapshot_links_and_missing_file_are_not_done(tmp_path):
    path = tmp_path / 'two words.mp3'
    path.write_bytes(b'a')
    assert '](<' in file_link(path)
    (tmp_path / '定稿.md').write_text('![新闻](素材/missing.png)')
    snap = write_snapshot(tmp_path)
    assert snap['assets'][0]['status'] == 'missing'
    assert '全部完成' not in (tmp_path / '交付状态.md').read_text()
    assert snap['plan']['theme_cover'] == 'generate'


def test_failed_qa_has_per_asset_log_and_immutable_evidence(tmp_path, monkeypatch):
    from test_visual_qa_contract import _article as qa_article, _reviewer
    import visual_qa
    cwd = qa_article(tmp_path)
    actual = visual_qa.run_visual_qa
    command = _reviewer(cwd, omit_style_contract=True)
    monkeypatch.setattr(visual_qa, 'run_visual_qa', lambda path: actual(path, reviewer_command=command))
    with pytest.raises(SystemExit):
        pipeline.cmd_visual_qa(cwd)
    rows = render_visuals.read_attempts(cwd)
    assert len(rows) == 6 and all(r['outcome'] == 'fail' for r in rows)
    assert all('style_contract_match' in r['failed_checks'] for r in rows)
    history = process_file(cwd, '_visual-qa.json').parent / 'visual-qa-history'
    assert list(history.glob('*.request.json')) and list((history/'images').glob('*.png'))
    snapshot = [json.loads(p.read_text()) for p in history.glob('*.json') if not p.name.endswith('.request.json')]
    assert snapshot[0]['errors'] and snapshot[0]['result']['status'] == 'fail'
    # An unchanged stale result must not be counted again if transport fails early.
    monkeypatch.setattr(visual_qa, 'run_visual_qa', lambda path:(None,['transport failed']))
    with pytest.raises(SystemExit):
        pipeline.cmd_visual_qa(cwd)
    rows = render_visuals.read_attempts(cwd)
    assert len(rows) == 7 and rows[-1]['label'] == '(batch)'


def test_reference_stays_outside_target_asset_set_and_final_seal(tmp_path):
    from test_visual_qa_contract import _article as qa_article, _reviewer
    from visual_qa import build_qa_request, run_visual_qa, final_byte_errors
    cwd = qa_article(tmp_path)
    Image.new('RGB', (20,20), 'green').save(cwd / 'ref.png')
    plan_path = cwd / 'visual-plan.json'
    plan = json.loads(plan_path.read_text())
    plan['cover']['reference_images'] = [{'file':'ref.png','source_url':'https://example.org/photo','purpose':'只比较产品轮廓'}]
    plan_path.write_text(json.dumps(plan))
    # Update the normal compile binding as the production compiler does.
    receipt_path = cwd / '素材/visual-compile-receipt.json'
    receipt = json.loads(receipt_path.read_text())
    from evidence import stable_digest
    receipt['plan_digest'] = stable_digest(plan)
    receipt['reference_images'] = {'cover':bind_references(cwd, plan['cover'])}
    receipt_path.write_text(json.dumps(receipt))
    request, errors = build_qa_request(cwd)
    assert not errors and len(request['assets']) == 6
    cover = next(a for a in request['assets'] if a['stage']=='cover')
    assert len(cover['reference_images']) == 1 and cover['required_checks']
    qa, errors = run_visual_qa(cwd, reviewer_command=_reviewer(cwd))
    assert not errors and qa
    Image.new('RGB', (20,20), 'red').save(cwd / 'ref.png')
    assert any('参考图' in e for e in final_byte_errors(cwd, qa))


def test_retry_decision_single_use_and_unrelated_prompt_does_not_reset(tmp_path):
    (tmp_path / 'visual-plan.json').write_text('{"cover":{}}')
    prompts = tmp_path / '素材/prompts/final'
    prompts.mkdir(parents=True)
    (prompts / 'cover.md').write_text('target prompt')
    row = {'kind':'qa_verdict','label':'cover','outcome':'fail','failed_checks':['text_match'], 'input_digest':input_digest(tmp_path,'cover'), 'render_seq':1}
    rows = [row,{**row,'render_seq':2}]
    assert retry_errors(tmp_path, rows)
    (prompts / 'hero.md').write_text('unrelated changed prompt')
    assert retry_errors(tmp_path, rows)
    assert retry_errors(tmp_path, [row,row]) == []  # Same produced image, not two rounds.
    diagnostic = json.loads(process_file(tmp_path,'_visual-retry-diagnostic.json').read_text())
    decision = {'binding':diagnostic['binding'],'action':'regenerate','reason':'已查明文字遮挡，需要针对标题区重生成'}
    process_file(tmp_path,'_visual-retry-decision.json',for_write=True).write_text(json.dumps(decision))
    assert retry_errors(tmp_path,rows,consume=True) == []
    assert retry_errors(tmp_path,rows)
    assert retry_errors(tmp_path,[*rows,{**row,'render_seq':3}])


def test_player_scope_wrong_article_and_old_body_are_rejected(tmp_path):
    src='https://media.example/v.mp4'
    (tmp_path / '定稿.md').write_text('这次发布的套餐规则已经发生了很大的变化。\n<!-- VIDEO: x -->')
    (tmp_path / '_website-media.json').write_text(json.dumps({'entries':[{'src':src}]}))
    process_file(tmp_path,'_music-manifest.json',for_write=True).write_text('{}')
    fetch=lambda *a:(200,'')
    fake=f'<img src="{src}"><video></video><img src="/song-assets/OTHER/song.mp3"><audio></audio>'
    errors=media_errors(tmp_path,'OBS-1','https://site.example',fake,fetch)
    assert any('正文' in e for e in errors) and any('视频' in e for e in errors) and any('主题曲' in e for e in errors)
    correct=f'<p>这次发布的套餐规则已经发生了很大的变化。</p><video src="{src}"></video><button class="song-player" data-src="/song-assets/OBS-1/song.mp3"></button><audio></audio>'
    assert media_errors(tmp_path,'OBS-1','https://site.example',correct,fetch) == []
    assert media_errors(tmp_path,'OBS-1','https://site.example',correct,lambda *a:(200,'','text/html'))


def test_package_entry_has_no_scripts_path_dependency(tmp_path):
    import subprocess
    result=subprocess.run([sys.executable,'-c',"from scripts.visual_workflow import compile_visual_plan; from scripts.visual_retry import retry_errors; from scripts.delivery_snapshot import build_snapshot; from scripts.website_evidence import media_errors; from pathlib import Path; assert compile_visual_plan(Path(r'"+str(tmp_path)+"'))[1]"],capture_output=True,text=True,cwd=str(Path(__file__).resolve().parents[1]))
    assert result.returncode == 0, result.stderr


def test_compiled_reference_cannot_silently_rebind(tmp_path):
    cwd=_article(tmp_path)
    Image.new('RGB',(20,20),'green').save(cwd/'ref.png')
    plan=json.loads((cwd/'visual-plan.json').read_text())
    plan['cover']['reference_images']=[{'file':'ref.png','source_url':'https://example.org/ref','purpose':'只比较轮廓'}]
    (cwd/'visual-plan.json').write_text(json.dumps(plan))
    receipt,errors=compile_visual_plan(cwd)
    assert not errors
    frozen=json.loads((cwd/'素材/visual-compile-receipt.json').read_text())['reference_images']['cover']
    Image.new('RGB',(20,20),'red').save(cwd/'ref.png')
    assert frozen != bind_references(cwd,plan['cover'])
    # The QA consumer checks the frozen identity, even with no SHA in the plan.
    from test_visual_qa_contract import _article as qa_article
    from visual_qa import build_qa_request
    (tmp_path/'qa').mkdir()
    qa_cwd=qa_article(tmp_path/'qa')
    Image.new('RGB',(20,20),'green').save(qa_cwd/'ref.png')
    qa_plan=json.loads((qa_cwd/'visual-plan.json').read_text())
    qa_plan['cover']['reference_images']=plan['cover']['reference_images']
    (qa_cwd/'visual-plan.json').write_text(json.dumps(qa_plan))
    rp=qa_cwd/'素材/visual-compile-receipt.json'
    qr=json.loads(rp.read_text())
    from evidence import stable_digest
    qr['plan_digest']=stable_digest(qa_plan);qr['reference_images']={'cover':bind_references(qa_cwd,qa_plan['cover'])}
    rp.write_text(json.dumps(qr))
    assert not build_qa_request(qa_cwd)[1]
    Image.new('RGB',(20,20),'red').save(qa_cwd/'ref.png')
    assert any('冻结' in e for e in build_qa_request(qa_cwd)[1])


def test_queued_cannot_be_overridden_by_old_live_page(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline,'brand',lambda:{'publish':{'website_command':'echo {code}','website_cwd':str(tmp_path)}})
    monkeypatch.setattr(pipeline,'_archived_code',lambda c:'OBS-1')
    monkeypatch.setattr(pipeline,'_resolve_website_command',lambda c:(c,''))
    monkeypatch.setattr(pipeline,'_uncommitted_archive_outputs',lambda *a:[])
    process_file(tmp_path,'_website-sync-receipt.json',for_write=True).write_text(json.dumps({'latest':{'deployment_state':'queued','job_id':'existing'}}))
    assert not pipeline._run_website_sync(tmp_path,'https://mp.weixin.qq.com/s/X',runner=lambda *a,**k:pytest.fail('must not submit'),live_checker=lambda *a:True)


def test_global_qa_structure_error_always_logged(tmp_path):
    pipeline._log_qa_verdict(tmp_path,{'assets':[{'path':'素材/cover.png','checks':{'text_match':True},'sha256':'x'}]},['visual QA 未绑定当前 request 字节'])
    rows=render_visuals.read_attempts(tmp_path)
    assert rows[-1]['label']=='(batch)' and rows[-1]['outcome']=='fail'


@pytest.mark.parametrize('mutation',[[],{'cover':['bad'],'hero':{},'infographics':[]},{'cover':{'reference_images':'bad'},'hero':{},'infographics':[]}])
def test_malformed_plan_is_a_rejection_not_crash(tmp_path,mutation):
    cwd=_article(tmp_path)
    (cwd/'visual-plan.json').write_text(json.dumps(mutation))
    result,errors=compile_visual_plan(cwd)
    assert result is None and errors


def test_website_source_digest_changes_with_same_filename_bytes(tmp_path):
    from delivery_snapshot import website_input_digest
    (tmp_path / '素材').mkdir()
    (tmp_path / '定稿.md').write_text('![新闻](素材/a.png)')
    (tmp_path / '素材/a.png').write_bytes(b'first')
    first = website_input_digest(tmp_path)
    (tmp_path / '素材/a.png').write_bytes(b'second')
    assert first != website_input_digest(tmp_path)
    second = website_input_digest(tmp_path)
    process_file(tmp_path,'_website-sync-receipt.json',for_write=True).write_text('{}')
    assert second == website_input_digest(tmp_path)


def test_ordered_list_uses_visible_text_not_markdown_numbers(tmp_path):
    (tmp_path / '定稿.md').write_text('1. 这是这篇文章需要展示的第一个完整要点。')
    assert media_errors(tmp_path,'OBS-1','https://site.example','<ol><li>这是这篇文章需要展示的第一个完整要点。</li></ol>',lambda *a:(200,'')) == []


def test_preflight_failure_does_not_consume_retry_decision(tmp_path):
    (tmp_path / 'visual-plan.json').write_text('{"cover":{}}')
    row={'kind':'qa_verdict','label':'cover','outcome':'fail','failed_checks':['text_match'],'input_digest':input_digest(tmp_path,'cover'),'render_seq':1}
    rows=[row,{**row,'render_seq':2}]
    for record in rows:
        render_visuals.log_attempt(tmp_path,record)
    retry_errors(tmp_path,rows)
    diagnostic=json.loads(process_file(tmp_path,'_visual-retry-diagnostic.json').read_text())
    decision_path=process_file(tmp_path,'_visual-retry-decision.json',for_write=True)
    decision_path.write_text(json.dumps({'binding':diagnostic['binding'],'action':'regenerate','reason':'已诊断标题遮挡，须重新生成'}))
    assert render_visuals.render_visuals(tmp_path)[1]  # No batch, so no paid call.
    assert not json.loads(decision_path.read_text()).get('used')


def test_hidden_or_unrelated_text_cannot_prove_current_article(tmp_path):
    (tmp_path/'定稿.md').write_text('这是当前版本应该出现的完整正文段落。')
    fetch=lambda *a:(200,'')
    for body in ['<article>旧正文</article><div hidden>这是当前版本应该出现的完整正文段落。</div>', '<article>旧正文</article><aside>这是当前版本应该出现的完整正文段落。</aside>', '<div style="display:none">这是当前版本应该出现的完整正文段落。</div>']:
        assert media_errors(tmp_path,'OBS-1','https://site.example',body,fetch)
    assert not media_errors(tmp_path,'OBS-1','https://site.example','<article><p>这是当前版本应该出现的完整正文段落。</p></article>',fetch)


def test_failed_render_then_repeat_old_image_does_not_count_two_images(tmp_path):
    (tmp_path/'visual-plan.json').write_text('{"cover":{}}')
    row={'kind':'qa_verdict','label':'cover','outcome':'fail','failed_checks':['text_match'],'input_digest':input_digest(tmp_path,'cover'),'render_seq':1,'output_sha256':'unchanged'}
    assert not retry_errors(tmp_path,[row,{'kind':'render','label':'cover','outcome':'renderer_timeout'}, {**row,'render_seq':2}])
    assert retry_errors(tmp_path,[row,{**row,'render_seq':2,'output_sha256':'new-image'}])


def test_queued_survives_frontend_preflight_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(pipeline,'brand',lambda:{'publish':{'website_command':'echo {code}','website_cwd':str(tmp_path)}})
    monkeypatch.setattr(pipeline,'_archived_code',lambda *a:pytest.fail('must not reach archive preflight'))
    process_file(tmp_path,'_website-sync-receipt.json',for_write=True).write_text(json.dumps({'latest':{'deployment_state':'queued','job_id':'keep-me'}}))
    for _ in range(2):
        assert not pipeline._run_website_sync(tmp_path,'https://mp.weixin.qq.com/s/X')
    assert json.loads(process_file(tmp_path,'_website-sync-receipt.json').read_text())['latest']['job_id']=='keep-me'


@pytest.mark.parametrize("changed", [False, True])
def test_finalize_rechecks_same_name_replaced_media(tmp_path, monkeypatch, changed):
    from delivery_snapshot import website_input_digest
    (tmp_path / '素材').mkdir()
    (tmp_path / '定稿.md').write_text('![新闻](素材/a.png)')
    image = tmp_path / '素材/a.png'
    image.write_bytes(b'first')
    state = {'steps': {name: {'status': 'done'} for name in (
        'publish_link', 'archive', 'archive_verify', 'moments_copy',
        'distribution', 'website_sync')}}
    state['steps']['website_sync']['media_input_digest'] = website_input_digest(tmp_path)
    if changed:
        image.write_bytes(b'replaced')
    calls = []
    monkeypatch.setattr(pipeline, '_finalize_preflight_errors', lambda *a: [])
    monkeypatch.setattr(pipeline, '_load_or_reset_finalize_state', lambda *a: state)
    monkeypatch.setattr(pipeline, '_run_website_sync', lambda *a: calls.append('sync') or True)
    monkeypatch.setattr(pipeline, '_mark_finalize_step', lambda *a: None)
    pipeline.cmd_finalize('https://mp.weixin.qq.com/s/TESTONLY', tmp_path)
    assert calls == (['sync'] if changed else [])
