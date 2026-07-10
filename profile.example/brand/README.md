# brand/ -- 品牌 logo 水印（可选）

把两版 logo 放进你自己 profile 的 `brand/` 目录（复制本目录结构）：

| 文件 | 用在哪 |
|---|---|
| `logo.png` | 白字版，配图右下角为深底时用 |
| `logo-black.png` | 深字版，配图右下角为浅底时用 |

`scripts/add_logo.js` 会按配图右下角亮度自动二选一。
不放 logo 也没关系 -- 水印环节会打印说明后自动跳过，不影响发布链。
