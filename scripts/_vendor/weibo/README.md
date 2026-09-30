# 内置微博发布脚本

- 来源：baoyu-skills（Jim Liu，MIT，见同目录 LICENSE），提交 1567581c26ec 的 `baoyu-post-to-weibo/scripts/weibo-post.ts`、`weibo-utils.ts`（含本机补丁），以及 `packages/baoyu-chrome-cdp/src/index.ts`（改名 `chrome-cdp.ts`）。
- 唯一改动：`weibo-utils.ts` 里把 `baoyu-chrome-cdp` 的包引用改成同目录 `./chrome-cdp.js`，运行不再需要 npm install。
- Chrome 登录目录仍是 `~/Library/Application Support/baoyu-skills/chrome-profile`，保留是为了沿用已登录的微博会话，不要改名。
- 运行方式同前：`bun _vendor/weibo/weibo-post.ts ...`（distribute.py 自动调用）。`SANSHENG_WRITE_WEIBO=baoyu` 回到宝玉插件。
