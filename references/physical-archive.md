# 文章实体归档

适用场景：文章已经完成公众号收尾及所有获授权的社媒、播客等任务，需要把整篇目录从当前工作树交付到独立的永久成品根。

## 两类归档不要混用

- `pipeline.py archive`：只登记作品库、刷新派生视图与推荐卡，不搬文件。
- `pipeline.py handoff-assets`：只导出给人工上传使用的浅层临时资产包，不是文章长期存档。
- `pipeline.py physical-archive`：复制并校验整篇文章目录，负责永久文件交付。

## 前置条件

1. 作品库 `archive` 已完成且能通过验证。
2. 公众号、已明确授权的小红书/微博、播客及其他会继续写文章目录的任务都已结束。
3. 当前文章没有第二个写者；同一文章一次只运行一个实体归档命令。
4. `.env` 或环境变量已配置 `SANSHENG_WRITE_ARCHIVE_DIR`。该值必须是已存在的绝对目录，不能使用 `@workspace`。

## 命令

```bash
python "$SKILL/scripts/pipeline.py" --dir "<文章过程目录>" physical-archive --delete-source
```

临时覆盖永久根时可显式给出：

```bash
python "$SKILL/scripts/pipeline.py" --dir "<文章过程目录>" physical-archive \
  --archive-root "<绝对永久归档根>" --delete-source
```

## 安全合同

1. 源目录名必须符合“编号-选题”，并包含 `.state.json` 与 `article-meta.yaml`。
2. 源目录和永久根不得互相包含，也不得是符号链接或 Junction。
3. 每篇文章使用独占锁；已有任务或遗留锁时拒绝并发执行。
4. 先快照全部相对路径、字节数和 SHA-256，再复制到永久根同盘的临时目录。
5. 临时副本与源快照一致、且复制期间源目录未变化，才放置到最终目录。
6. 目标同路径同哈希时幂等跳过，目标独有文件保留；文件/目录类型冲突或同路径哈希不同一律中止，不覆盖。
7. 最终目录必须再次包含源快照的全部目录和文件，才写 `_physical-archive-receipt.json`。
8. 只有显式提供 `--delete-source`，并在删除前再次复验源与目标，才清理工作树源目录。任何失败都优先保留源目录。

凭证记录 `archived_from`、永久根、最终目标、源文件数、总字节、manifest SHA-256 和源目录是否删除；历史发布/社媒 receipt 保持原样，不改写其当时的绝对证据路径。

实体归档只做本地文件交付，不触发 Git 合并、Skill Release、网站部署或平台发布。若后续仍要继续制作图片、改稿或补分发，先不要运行。
