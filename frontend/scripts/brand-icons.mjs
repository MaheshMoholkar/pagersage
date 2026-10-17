// Regenerate the web icons from the logo in docs/brand/. Run after changing the logo:
//   cd frontend && npm run brand
// Writes (all committed):
//   app/icon.svg            favicon for modern browsers (the mark)
//   app/favicon.ico         16 + 32 px PNGs in an .ico, for everything else
//   app/apple-icon.png      180 px home-screen icon
//   public/icon-192.png     web manifest icons (app/manifest.ts)
//   public/icon-512.png
//   app/opengraph-image.png 1200x630 link preview: the dark wordmark on the page ground
// Uses sharp, which Next installs.

import { copyFile, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import sharp from "sharp";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const brand = join(web, "..", "docs", "brand");
const mark = await readFile(join(brand, "mark.svg"));
const wordmark = await readFile(join(brand, "logo-dark.svg"));

const png = (svg, size) => sharp(svg, { density: 72 * (size / 64) * 2 }).resize(size, size).png();

/** An .ico holding PNG images (supported everywhere since Windows Vista). */
function ico(images) {
  const header = Buffer.alloc(6 + 16 * images.length);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2); // type: icon
  header.writeUInt16LE(images.length, 4);
  let offset = header.length;
  images.forEach(({ size, data }, i) => {
    const entry = 6 + 16 * i;
    header.writeUInt8(size >= 256 ? 0 : size, entry);
    header.writeUInt8(size >= 256 ? 0 : size, entry + 1);
    header.writeUInt16LE(1, entry + 4); // colour planes
    header.writeUInt16LE(32, entry + 6); // bits per pixel
    header.writeUInt32LE(data.length, entry + 8);
    header.writeUInt32LE(offset, entry + 12);
    offset += data.length;
  });
  return Buffer.concat([header, ...images.map((i) => i.data)]);
}

await copyFile(join(brand, "mark.svg"), join(web, "app", "icon.svg"));
const small = await Promise.all(
  [16, 32].map(async (size) => ({ size, data: await png(mark, size).toBuffer() })),
);
await writeFile(join(web, "app", "favicon.ico"), ico(small));
await png(mark, 180).toFile(join(web, "app", "apple-icon.png"));
await png(mark, 192).toFile(join(web, "public", "icon-192.png"));
await png(mark, 512).toFile(join(web, "public", "icon-512.png"));

// Link preview: the wordmark (296x64) at 2.5x, centred on the page ground colour.
const logo = await sharp(wordmark, { density: 72 * 2.5 }).png().toBuffer();
const { width, height } = await sharp(logo).metadata();
await sharp({ create: { width: 1200, height: 630, channels: 4, background: "#121628" } })
  .composite([{ input: logo, left: Math.round((1200 - width) / 2), top: Math.round((630 - height) / 2) }])
  .png()
  .toFile(join(web, "app", "opengraph-image.png"));

console.log("Wrote app/icon.svg, favicon.ico, apple-icon.png, opengraph-image.png, public/icon-*.png");
