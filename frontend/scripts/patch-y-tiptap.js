/**
 * Patch @tiptap/y-tiptap to fix collaborative cursor off-by-one.
 *
 * The upstream absolutePositionToRelativePosition uses assoc = -1
 * (left-association), which makes remote cursors stick to the LEFT
 * of newly typed characters. Changing to assoc = 0 (right-association)
 * makes cursors move WITH typed text, matching user expectations.
 *
 * Run automatically via npm postinstall.
 */
const fs = require('fs');
const path = require('path');

const distDir = path.join(__dirname, '..', 'node_modules', '@tiptap', 'y-tiptap', 'dist');

const files = ['y-tiptap.js', 'y-tiptap.cjs'];

let patched = 0;
for (const file of files) {
  const filePath = path.join(distDir, file);
  if (!fs.existsSync(filePath)) continue;

  let content = fs.readFileSync(filePath, 'utf8');
  // Match createRelativePositionFromTypeIndex calls with assoc -1
  const regex = /(createRelativePositionFromTypeIndex\([^,]+,\s*[^,]+,\s*)-1(\))/g;
  const matches = content.match(regex);
  if (matches && matches.length > 0) {
    content = content.replace(regex, '$10$2');
    fs.writeFileSync(filePath, content, 'utf8');
    console.log(`✅ Patched ${file} (${matches.length} replacements)`);
    patched++;
  } else {
    console.log(`ℹ️  ${file} already patched or pattern not found`);
  }
}

if (patched > 0) {
  console.log('✅ y-tiptap cursor association fix applied');
}
