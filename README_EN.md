# sansheng-write · A Chinese Long-Form Writing Engine

> **A Claude Code skill that runs the whole chain: topic → outline → draft → revision → typeset HTML → cover art. Feed it your corpus, it grows your voice.**

[中文](./README.md) | **English**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/sandypoli-boop/sansheng-write?style=flat)](../../stargazers)
[![Last commit](https://img.shields.io/github/last-commit/sandypoli-boop/sansheng-write)](../../commits/main)

> **Note on language.** This skill writes **Chinese** long-form articles. Its rules target
> Chinese clichés, and its typesetting targets WeChat Official Account's HTML restrictions.
> The code and docs are usable in English, but the writing methodology is not language-agnostic.

---

## See the output before you install

**↓ 20-second screen recording: a full WeChat long-form article, from locked topic to finished typesetting, running the whole chain.**

https://github.com/user-attachments/assets/7b5d8a8c-7caf-41e3-957e-5c2428859c79

Say "write me an article about X" and it runs:

```
topic triage → outline (with opening-strategy routing) → draft → revision (3-layer de-AI filter)
   → title (5 forged candidates) → typesetting (10 components + contract gates) → images / cover
```

Quality is not left to good intentions. It is enforced by **contract gates**:
non-compliant output exits with code 2 and never reaches publish.

```console
$ python scripts/format_layout.py final.html --all --check
  ✅ Converted 3 native H2 into numbered PART headings
  ✅ Table branding done (themed header / row dividers / zebra rows / rounded container)
  ✅ Converted 3 emphasis markers into theme-colored text
  ⚠️  2 warnings (non-blocking), 0 errors
```

Gates check half-width punctuation, bold density, part-of-speech ratio, a cliché blacklist,
infographic count, cover aspect ratio, and more.

---

## What it is

A **Chinese long-form writing methodology plus a typesetting engine**, packaged as a Claude Code skill.

It is **not** a one-shot "title in, article out" generator. It is a disciplined pipeline:
each stage has rules it must read, each artifact has a gate it must pass.
You are the writer here, not the client.

### The six rules for sounding human

Not sentence-level disguise -- these are demands on the content itself:

1. **Cash the "so what"** -- after every claim, ask the reader's "so what?" and answer it
2. **Ground the analogy** -- every abstract judgment needs a scene the reader's hands have touched
3. **Anchor with an odd detail** -- key scenes need a detail too strange to have been invented
4. **Write yourself dumb** -- no authority posture; trade self-deprecation for trust
5. **Lead paragraphs concretely** -- first sentence gives a person, event, image, or number
6. **Inter-sentence gravity** -- each sentence ends with a hook the next one catches

**Honest boundary**: these six are enforced by *feeding and self-discipline*, not by machines.
The `exit 2` gates only catch surface fingerprints regex can see. Semantic humanity is not
regex-testable, and a model auditing itself cannot see it either -- only a *different* model
doing a semantic diff can.

---

## Out of the box vs. after you feed it

**Read this section. It matters more than everything above.**

| | What you get |
|---|---|
| **Out of the box** (no profile) | The full methodology engine: structure, discipline, de-AI filtering, typesetting. Output is clean and does not read like AI boilerplate |
| **After feeding** (your own `profile/corpus/`) | All of the above, **plus your own voice** |

**Without your corpus, output approaches generic AI writing. That is by design, not a defect.**

Voice grows out of your corpus, not out of prompt engineering. This repository ships
**no real author's style manual**: such manuals are distilled from copyrighted work and are not
mine to hand out -- and besides, *who you imitate should be your choice*.

Instead you get:

- A [HOW-TO for building your own author style manual](profile.example/corpus/authors/README.md)
  (three steps, including a distillation prompt you can paste)
- A [sample manual for a fictional author](profile.example/corpus/authors/example-author.compact.md)
- An [original "sounds human" sample set](profile.example/corpus/voice-samples.md), injected
  automatically when you have no corpus of your own

By the way: **the first manual worth building is your own.** Feed it the 20 pieces you like best
of your own writing. The manual that comes out will show you habits you never noticed.

---

## Three usage tiers

Each tier works standalone. **A missing component degrades that one step, never the whole chain.**

### ① Methodology only (zero setup)

```bash
pip install pyyaml
python scripts/setup_check.py     # tells you which tier you can reach
```

### ② + WeChat HTML typesetting

```bash
# also install: bun (runs the markdown→HTML converter) + Node 18+
cd scripts && npm install         # jimp: logo watermark on images
```

### ③ Fully automatic through publish

```bash
cp .env.example .env              # your own keys
```

### Dependency matrix

| Dependency | Needed for | If missing | Install |
|---|---|---|---|
| Python 3.10+ / PyYAML | ① | Nothing runs | `pip install pyyaml` |
| Pillow | ③ | No image resize / compression | `pip install pillow` |
| bun | ② | markdown→HTML conversion fails | [bun.sh](https://bun.sh) |
| Node 18+ / jimp | ② | No logo watermark | `cd scripts && npm install` |
| **baoyu-skills plugin** | hard dep from ② | md→HTML / publish / infographics / image-cards all break | in Claude Code: `/plugin marketplace add JimLiu/baoyu-skills`; its keys live in **its own** `~/.baoyu-skills/.env` (WeChat keys `WECHAT_APP_ID`/`WECHAT_APP_SECRET`) |
| `GOOGLE_API_KEY` | ③ | No image generation (OpenAI-compatible endpoint can stand in) | AI Studio or Vertex Express; the script routes by key prefix |
| `MINIMAX_API_KEY` | ③ optional | Article BGM is skipped | pure easter egg |
| WeChat appid/secret | ③ | Output lands as HTML; you paste it yourself | configure in baoyu's `~/.baoyu-skills/.env` (**not** this repo's .env); also whitelist your IP in the console |
| playwright / matplotlib | ③ optional | No SVG→PNG, no data charts | `pip install playwright matplotlib` |

---

## Install

```bash
# via Claude Code plugin marketplace
claude plugin marketplace add sandypoli-boop/sansheng-write
claude plugin install sansheng-write

# or clone + symlink
git clone https://github.com/sandypoli-boop/sansheng-write.git
ln -s "$(pwd)/sansheng-write" ~/.claude/skills/sansheng-write
```

## Updating

How you update depends on how you installed:

- **Via the plugin marketplace**: `claude plugin marketplace update`, then `claude plugin update sansheng-write`
- **Via clone + symlink**: `git pull` in the repo -- the symlink picks it up immediately, no reinstall

To hear about new versions: watch the repo's [Releases](../../releases), or click **Watch -> Custom -> Releases** and GitHub will notify you. See the [CHANGELOG](CHANGELOG.md) for what changed in each version.

## Quick start

```bash
python scripts/setup_check.py
cp -r profile.example ~/my-writing-profile
export SANSHENG_WRITE_PROFILE_DIR=~/my-writing-profile
export SANSHENG_WRITE_DATA_DIR=~/my-articles
$EDITOR ~/my-writing-profile/context.md      # tell it who you are
```

## Configuration

Three-layer separation -- **code lives in the repo, your things live in your own directory**:

| Layer | Holds | Where |
|---|---|---|
| ① repo | code + methodology | here |
| ② profile | colors / byline / identity card / corpus (**private but not secret**) | `SANSHENG_WRITE_PROFILE_DIR` |
| ③ secrets | API keys (**read from env only, never printed, redacted in errors**) | `.env` (gitignored) |

No profile? It falls back to the bundled `profile.example/` (neutral colors, placeholder byline).
That is a normal path, not an error.

**Reskin in one line** (`profile/brand.yaml`):

```yaml
theme: "sage"      # slate (default) | ink | sage | jade | amber | plum
```

You never touch a hex in the templates -- `process_theme()` swaps them at the end of typesetting.

## Privacy

- Keys are read from env / `.env` only, **never printed**, and redacted in error messages.
- The observation log (`_skill-observations.jsonl`) is **local-only, never uploaded**; article
  names are hashed by default. Turn it off entirely: `SANSHENG_WRITE_TELEMETRY=off`.
- Your corpus, drafts, and keys go nowhere. Image generation and publishing only call their
  APIs when you explicitly invoke them.

---

## About the author

<p align="center">
  <a href="https://sanshengai.top"><strong>🌐 sanshengai.top</strong></a> ·
  <a href="https://namecard.xiaoyuzhoufm.com/nnl8x"><strong>🎧 Xiaoyuzhou</strong></a> ·
  <a href="https://weibo.com/u/7546221967"><strong>Weibo</strong></a> ·
  <a href="https://www.xiaohongshu.com/user/profile/5c716b6d000000001000f5c4"><strong>Xiaohongshu</strong></a> ·
  <a href="mailto:sandypoli@gmail.com"><strong>✉️ Email</strong></a>
</p>

I am **叁笙 (sansheng)**. I make content with AI, and build tools with AI. I run a personal site,
[叁笙早安 AI](https://sanshengai.top): a daily AI brief every morning, long-form essays, and a pile
of small things I wrote for myself -- book distillations, a career-AI-risk self-test, a curated
GitHub treasure list, an AI freebies board.

This skill is what I ground out of my real writing workflow. Every article it wrote, I revised by
hand -- and those revisions turned back into its rules. It works for me, so I cleaned it,
stripped the private bits, and opened it up. Use it, or make it yours.

<p align="center">
  <img src="assets/qrcode-gongzhonghao.png" alt="WeChat Official Account" width="200">
  <br><sub>WeChat Official Account · 叁笙早安AI</sub>
</p>

---

## Credits & Dependencies

### Credits

- **[baoyu-skills](https://github.com/JimLiu/baoyu-skills)** by [宝玉 / JimLiu](https://github.com/JimLiu) (MIT) --
  the upstream markdown→HTML converter, infographic and publishing toolchain. This skill's
  typesetting post-processor runs on top of its output, and borrows from how it organizes skills.
  **Not bundled -- install it yourself.**

- **[gzh-design-skill](https://github.com/isjiamu/gzh-design-skill)** by 甲木 × 摸鱼小李 (AGPL-3.0) --
  a major methodological reference for the typesetting layer: the "article type → component recipe"
  table, visual hierarchy and per-article color quotas, cover copy strategy, the dual gate of
  "template-source lint + output HTML verification", and the centered placeholder convention.
  Ideas only: this repo's component HTML and verification scripts are independent implementations
  containing none of its code or templates. **Not bundled; the two projects do not depend on each other.**

- **[WeWrite](https://github.com/oaker-io/wewrite)** by [oaker-io](https://github.com/oaker-io) (MIT) --
  the overall design of the "learn from my edits" flywheel (lessons → playbook aggregation,
  pattern taxonomy) and the four-strategy content-enhancement framing come from this project;
  the scripts are independent implementations. **Not bundled.**

- **[humanizer](https://github.com/blader/humanizer)** by [blader](https://github.com/blader) (MIT) --
  the taxonomy of four high-frequency AI sentence patterns in the anti-AI filter comes from this project.

Where `references/` cites Orwell, Asimov, Zhu Guangqian or Corey Haines, those are **attributed
citations of a method** (the six rules, the window-pane metaphor, the four reader relations,
Seven Sweeps). Stripping the attribution while keeping the rule would be plagiarism.
That is a different thing from packaging up someone's style manual, which this repo does not do.

### Runtime dependencies (not bundled -- install yourself)

| Dependency | License | Purpose |
|---|---|---|
| [jimp](https://github.com/jimp-dev/jimp) | MIT | logo watermark on images |
| [PyYAML](https://pyyaml.org/) | MIT | config and works registry |
| [Pillow](https://python-pillow.org/) | MIT-CMU | image resize / compression |
| [Playwright](https://playwright.dev/) | Apache-2.0 | SVG→PNG (optional) |
| [matplotlib](https://matplotlib.org/) | PSF-based (BSD-compatible) | data charts (optional) |
| baoyu-skills | MIT | markdown→HTML / infographics / publishing |

CJK data charts need a CJK font. Prefer OFL-licensed
[Noto Sans CJK](https://github.com/notofonts/noto-cjk) over the proprietary fonts bundled with Windows.

### License compatibility

Distributed under **MIT**. **No third-party source is bundled** (`scripts/node_modules/` is
gitignored and produced by your own `npm install`). Everything above is a **runtime dependency**;
their licenses do not bear on this repo's distribution, and each has been checked and labeled.

---

## License

[MIT](LICENSE) © 2026 叁笙 (sansheng)
