import hashlib
from pathlib import Path
import pytest
from scripts.title_only_reuse import verify_title_only, title_and_body

def freeze(root,text):
    sha=hashlib.sha256(text.encode()).hexdigest();p=root/'素材/stylebook-sources'/f'{sha}.md';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return sha

def test_title_only_reuse_requires_real_same_body(tmp_path):
    old=freeze(tmp_path,'---\ntitle: 原标题\ncategory: share\n---\n正文说明。\n')
    new=freeze(tmp_path,'---\ntitle: 新标题\ncategory: share\n---\n正文说明。\n')
    assert verify_title_only(tmp_path,old,new)['original_title']=='原标题'
    for text in ['---\ntitle: 新标题\ncategory: share\n---\n改变正文。\n','---\ntitle: 新标题\ncategory: other\n---\n正文说明。\n','---\ntitle: 新标题\n---\n']:
        changed=freeze(tmp_path,text)
        with pytest.raises(ValueError):verify_title_only(tmp_path,old,changed)
    p=tmp_path/'素材/stylebook-sources'/f'{old}.md';p.write_text('tampered')
    with pytest.raises(ValueError):verify_title_only(tmp_path,old,new)


def test_h1_only_title_change(tmp_path):
    old=freeze(tmp_path,"# 旧标题\n\n正文。\n")
    new=freeze(tmp_path,"# 新标题\n\n正文。\n")
    assert verify_title_only(tmp_path,old,new)["current_title"]=="新标题"
    with pytest.raises(ValueError):title_and_body("# 空文\n")
