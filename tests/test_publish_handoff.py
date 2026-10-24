import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from publish_handoff import HandoffError, export_handoff


class HandoffTests(unittest.TestCase):
    def test_pipeline_export_cannot_bypass_producer_preflight(self):
        import pipeline
        with patch.object(pipeline,'prepare_publish_handoff',return_value=(None,['未定稿'])), \
             patch('publish_handoff.main') as export_main, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pipeline.cmd_export_publish(Path('.'),[]),2)
            export_main.assert_not_called()
        with patch.object(pipeline,'prepare_publish_handoff',return_value=({},[])), \
             patch('publish_handoff.main') as export_main, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pipeline.cmd_export_publish(Path('.'),[]),2)
            export_main.assert_not_called()
        with patch.object(pipeline,'prepare_publish_handoff',return_value=({'manifest_digest':'fixture'},[])), \
             patch('publish_handoff.main',return_value=0) as export_main:
            self.assertEqual(pipeline.cmd_export_publish(Path('.'),['fixture']),0)
            export_main.assert_called_once_with(['fixture'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'定稿.html').write_text('<h1>标题</h1><p>开始</p><!-- VIDEO: demo --><p>结束</p><img src="素材/photo.png">')
        (self.root/'定稿.md').write_text('# 标题\n<!-- VIDEO: demo -->')
        (self.root/'素材').mkdir()
        (self.root/'素材/photo.png').write_bytes(b'fixture-image')
        (self.root/'demo.mp4').write_bytes(b'fixture-video')
        self.targets = [dict(id='wechat', platform='wechat', account='main', content_type='article', endpoint='draft', title='标题')]
        self.media = [dict(id='demo',kind='video',path='demo.mp4',anchor='<!-- VIDEO: demo -->')]

    def tearDown(self):
        self.temp.cleanup()

    def export(self):
        return export_handoff(self.root, self.targets, media=self.media)

    def test_roundtrip_and_no_source_mutation(self):
        original = (self.root/'定稿.html').read_bytes()
        path = self.export(); data = json.loads(path.read_text())
        self.assertEqual(self.export(), path)
        self.assertEqual((self.root/'定稿.html').read_bytes(), original)
        self.assertEqual(data['media_slots'][0]['context'], dict(before='标题开始', after='结束'))
        self.assertIn('../../../素材/photo.png', path.with_name('article.html').read_text())
        self.assertEqual(len(data['assets']), 2)
        self.assertEqual(data['documents'][-1]['source_document_ids'], ['source-html','source-md'])

    def test_missing_and_duplicate_anchor_refused(self):
        for body in ('<p>无位置</p>', '<!-- VIDEO: demo -->'*2):
            (self.root/'定稿.html').write_text(body)
            with self.assertRaisesRegex(HandoffError, '唯一'): self.export()

    def test_undeclared_video_even_if_renderer_dropped_comment(self):
        (self.root/'定稿.html').write_text('<p>不应丢视频</p>')
        with self.assertRaisesRegex(HandoffError, '未交接'):
            export_handoff(self.root, self.targets)

    def test_symlink_escape_refused(self):
        (self.root/'demo.mp4').unlink(); (self.root/'demo.mp4').symlink_to(__file__)
        with self.assertRaisesRegex(HandoffError, '越界'): self.export()

    def test_source_revision_and_destination_are_locked(self):
        first = self.export()
        (self.root/'demo.mp4').write_bytes(b'changed-video')
        self.assertNotEqual(self.export(), first)
        self.targets[0].pop('endpoint')
        with self.assertRaisesRegex(HandoffError, '显式'): self.export()

    def test_unknown_audio_placeholder_refused(self):
        with (self.root/'定稿.html').open('a') as f:
            f.write('<p>（👉 删除本段文字，并插入 200 秒主题曲音频）</p>')
        with self.assertRaisesRegex(HandoffError, '未声明'): self.export()

    def test_original_html_not_overwritten_and_candidate_tamper_refused(self):
        path = self.export()
        path.with_name('article.html').write_text('someone changed it')
        with self.assertRaisesRegex(HandoffError, '拒绝覆盖'): self.export()


if __name__ == '__main__': unittest.main()
