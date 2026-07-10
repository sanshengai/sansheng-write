# playbook -- 从你的改稿里长出来的写作规则

> **这个文件由脚本自动维护，不要手改。**
> 每次你手动改稿之后跑一次 `python scripts/learn_edits.py`，它会对比
> 「初稿 vs 定稿」的 diff，把你反复做的同一类修改提炼成一条规则，追加到下面。
>
> 规则攒够之后，`scripts/prep_writing.py` 会在你下次写作前把它们注入上下文 --
> 于是这个 skill 越用越像你，而不是越用越像 AI。

## 现在是空的，这是正常的

新装的仓库里没有任何规则。它们不该由别人替你填 --
别人的写作习惯写进你的 playbook，只会让你的文章变成别人的样子。

**怎么开始攒**：

```bash
# 1. 用这个 skill 写一篇，得到 初稿.md
# 2. 你自己动手改，改成你满意的 定稿.md
# 3. 让它学：
python scripts/learn_edits.py <文章目录>
```

跑三五篇之后回来看这个文件，你会看到一些你自己都没意识到的习惯。

## schema（脚本写入的格式）

```yaml
rules:
  - id: R001
    pattern: "段首出现『随着…的发展』"
    action: "换成一个具体的人 / 事 / 数字"
    confidence: 3          # 命中次数，越高越可信
    first_seen: "2026-01-01"
    evidence: "<你哪一篇文章的哪一处改动>"

reference_preferences:      # 你偏好读哪些 reference（自动统计）
voice_corpus_index:         # 指向 profile/corpus/ 里你的声纹语料
noise_filter_rules:         # 过滤掉噪声 diff（错别字、标点）的规则
```

## 一条规则也没有的时候会怎样

`prep_writing.py` 会退而注入 `profile/corpus/voice-samples.md`
（本项目原创的人味示例集），保证产出至少不是 AI 通稿。
这是基础及格线，不是你的风格 -- 风格得靠上面那三步攒。

---

<!-- 规则从这里开始追加，由 learn_edits.py 维护 -->

## rules

_(空)_
