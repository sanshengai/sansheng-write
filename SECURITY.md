# 安全策略 · Security Policy

## 别把密钥提交进 PR

这个仓库的所有密钥都走 `.env`（已在 `.gitignore` 里），配色 / 身份卡这类
「私有但非密」的东西走 `profile/`（你自己的目录，不在仓里）。

仓库自带一道提交前护栏，会拦下形似密钥的内容。**请在你的 clone 里打开它**：

```bash
git config core.hooksPath .githooks
```

它会在 `git commit` 时扫描暂存区，命中 Google / OpenAI / GitHub token 等格式
以及 Windows 个人路径就拒绝提交。**不要通过放宽模式或 `--no-verify` 来绕过它** --
它拦下你，通常是真的拦下了什么。

## 报告漏洞

发现安全问题（尤其是可能泄露使用者密钥或个人数据的路径），
请**不要**开公开 issue。发邮件到 <sandypoli@gmail.com>，我会尽快回。

## 这个 skill 会碰你的什么

| 它读 | 它写 |
|---|---|
| `.env` 里的 API key（只读、不打印、报错时打码） | `<数据目录>/` 下你的文章与 `works.yaml` |
| `profile/` 下你的品牌配置与语料 | 排版产出的 HTML / 图片 |
| 你让它读的文章草稿 | `playbook.md` / `lessons.yaml`（你的写作规则） |

它**不会**把你的语料、草稿或密钥发送到任何地方。生图 / 发布是你显式调用时
才会打对应的 API，端点在 `.env.example` 里写明。
