/**
 * 给图片右下角添加品牌logo水印
 * 自动根据右下角区域亮度选择黑/白logo
 *
 * 用法（2026-04-23 起支持多 glob + 显式 --logo）:
 *   node add_logo.js <image_glob> [<image_glob> ...] [--logo <logo_dir>]
 *
 * 示例:
 *   node add_logo.js "素材/01.png"
 *   node add_logo.js "素材/*.png"
 *   node add_logo.js "素材/*.png" "截图/*.png" "素材/charts/*.png"
 *   node add_logo.js "素材/*.png" --logo "<你的 logo 目录>"
 *
 * 向后兼容：如果只有两个 positional 参数，且第二个参数是目录路径（不含 * 通配符）且能读到，
 * 将其当作旧版 logo_dir 用（保留 legacy 行为）。
 */
const fs = require('fs');
const path = require('path');

const JIMP_PATH = 'jimp';
// logo 目录来自你的 profile：优先 $SANSHENG_WRITE_PROFILE_DIR/brand，未配置时回退仓内
// profile.example/brand（把 logo.png / logo-black.png 放进去即可）。也可用 --logo 显式覆盖。
const DEFAULT_LOGO_DIR = process.env.SANSHENG_WRITE_PROFILE_DIR
  ? path.join(process.env.SANSHENG_WRITE_PROFILE_DIR, 'brand')
  : path.resolve(__dirname, '../profile.example/brand');

// 固化排除清单：① hero 等小图尺寸太小，打水印影响观感；② logo-white/logo-black 本身就是品牌 logo，
// 给它再叠一层水印会 logo 套 logo（用 "素材/*.png" 通配批量加水印时会误伤名片 logo）
const SKIP_FILES = ['hero.png', 'hero.jpg', 'bgm_cover.png', 'bgm_cover.jpg', 'music_cover.png', 'music_cover.jpg', 'logo-white.png', 'logo-black.png'];
// ③ news-* 前缀 = 人物/事件新闻真实照片（非本号产物），打品牌水印等于冒认版权
const SKIP_PREFIXES = ['news-'];

async function addLogo(imagePath, logoDir) {
  const fname = path.basename(imagePath).toLowerCase();
  if (SKIP_FILES.includes(fname) || SKIP_PREFIXES.some(p => fname.startsWith(p))) {
    console.log(`  ⏭  跳过 ${path.basename(imagePath)}（组件小图/新闻照，不打水印）`);
    return;
  }
  try {
    const { Jimp } = require(JIMP_PATH);

    const img = await Jimp.read(imagePath);
    const imgW = img.bitmap.width;
    const imgH = img.bitmap.height;

    // 分析右下角 35% 区域的平均感知亮度
    const sampleX = Math.floor(imgW * 0.65);
    const sampleY = Math.floor(imgH * 0.65);
    let totalBrightness = 0;
    let pixelCount = 0;

    for (let y = sampleY; y < imgH; y++) {
      for (let x = sampleX; x < imgW; x++) {
        const color = img.getPixelColor(x, y);
        const r = (color >> 24) & 0xff;
        const g = (color >> 16) & 0xff;
        const b = (color >> 8)  & 0xff;
        totalBrightness += 0.299 * r + 0.587 * g + 0.114 * b;
        pixelCount++;
      }
    }

    const avgBrightness = totalBrightness / pixelCount;
    // 🔴 按右下角亮度自适应选黑/白 logo（否则永远硬贴一版，浅底图上白 logo 会隐形）：
    //   - 右下角偏亮（> 阈值，浅底/米白）→ logo-black.png（深字，浅底可见）
    //   - 右下角偏暗（≤ 阈值，深底/彩色）→ logo.png（白字，深底可见）
    // 约定：profile/brand/ 下放两版 logo —— logo.png（白字，深底用）+ logo-black.png（深字，浅底用）。
    const LIGHT_BG_THRESHOLD = 128; // 感知亮度 0-255 的中点
    const isLightBg = avgBrightness > LIGHT_BG_THRESHOLD;
    const logoFile = isLightBg ? 'logo-black.png' : 'logo.png';
    const logoPath = path.join(logoDir, logoFile);

    console.log(`  右下角亮度 ${avgBrightness.toFixed(0)} → ${isLightBg ? '浅底，用深字 logo' : '深底，用白字 logo'}（${logoFile}）`);

    // logo宽度 = 图片宽度的 12%，透明度 35%
    const logo = await Jimp.read(logoPath);
    const logoW = Math.floor(imgW * 0.12);
    logo.resize({ w: logoW });
    logo.opacity(0.35);

    // 右下角，距边缘 2% padding
    const padX = Math.floor(imgW * 0.02);
    const padY = Math.floor(imgH * 0.02);
    const posX = imgW - logo.bitmap.width - padX;
    const posY = imgH - logo.bitmap.height - padY;

    img.composite(logo, posX, posY);
    await img.write(imagePath);
    console.log(`  ✅ ${path.basename(imagePath)}`);
  } catch (error) {
    console.error(`  ❌ ${path.basename(imagePath)}: ${error.message}`);
    throw error;
  }
}

/**
 * 解析 CLI 参数：
 *   - 显式 `--logo <path>` 指定 logo 目录
 *   - 其余所有 positional 参数都是图片路径或 glob
 *   - 向后兼容：两个 positional 参数时，若第二个是存在的目录且不含通配符，仍当作 legacy logo_dir
 */
function parseArgs(argv) {
  const positional = [];
  let logoDir = null;

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--logo' || a === '-l') {
      logoDir = argv[++i];
    } else if (a.startsWith('--logo=')) {
      logoDir = a.slice('--logo='.length);
    } else {
      positional.push(a);
    }
  }

  // 向后兼容 legacy: `add_logo.js <image> <logo_dir>`
  if (!logoDir && positional.length === 2) {
    const second = positional[1];
    if (!second.includes('*') && fs.existsSync(second) && fs.statSync(second).isDirectory()) {
      logoDir = second;
      positional.pop();
    }
  }

  return { globs: positional, logoDir: logoDir || DEFAULT_LOGO_DIR };
}

function expandGlob(pattern) {
  if (!pattern.includes('*')) {
    return [pattern];
  }
  const dir = path.dirname(pattern);
  const base = path.basename(pattern);
  if (!fs.existsSync(dir)) return [];
  const re = new RegExp('^' + base.replace(/\./g, '\\.').replace(/\*/g, '.*') + '$');
  return fs.readdirSync(dir)
    .filter(f => re.test(f))
    .map(f => path.join(dir, f));
}

async function main() {
  const { globs, logoDir } = parseArgs(process.argv.slice(2));

  if (!globs.length) {
    console.error('用法: node add_logo.js <image_glob> [<image_glob> ...] [--logo <logo_dir>]');
    process.exit(1);
  }

  // 展开所有 glob 并去重
  const seen = new Set();
  const files = [];
  for (const g of globs) {
    for (const f of expandGlob(g)) {
      const abs = path.resolve(f);
      if (!seen.has(abs)) {
        seen.add(abs);
        files.push(f);
      }
    }
  }

  if (!files.length) {
    console.error('⚠️ 未匹配到任何文件，请检查 glob 模式');
    process.exit(1);
  }

  console.log(`🎬 开始添加水印 (共 ${files.length} 张图片，Logo 目录: ${logoDir}):`);
  for (const f of files) {
    console.log(`处理: ${f}`);
    await addLogo(path.resolve(f), logoDir);
  }
  console.log('✨ 完成！');
}

main().catch(e => { console.error('❌ 批处理失败', e.message); process.exit(1); });
