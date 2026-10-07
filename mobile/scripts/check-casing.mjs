#!/usr/bin/env node
// Resolve every local import against the real filesystem, comparing each path
// segment case-sensitively. Windows resolves "./Foo" to foo.tsx and builds fine;
// macOS and the iOS build do not. This turns that into a local failure.
import { readdirSync, statSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const MOBILE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(MOBILE_ROOT, 'src');
const SOURCE_EXT = ['.ts', '.tsx', '.js', '.jsx'];
// Extensions an import may omit, in the order a bundler tries them.
const RESOLVE_ORDER = ['', '.ts', '.tsx', '.js', '.jsx', '.ios.ts', '.ios.tsx'];

const IMPORT_RE =
  /(?:import|export)\s+(?:[\w*{}\n\r\t, ]+\s+from\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\)/g;

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (SOURCE_EXT.some((e) => entry.endsWith(e))) out.push(full);
  }
  return out;
}

// True only if every segment of `target` matches the on-disk entry exactly.
// Reading the parent directory is what makes this case-sensitive on Windows.
function existsCaseSensitive(target) {
  const rel = relative(MOBILE_ROOT, target);
  if (rel.startsWith('..')) return false;
  let current = MOBILE_ROOT;
  for (const segment of rel.split(sep)) {
    let entries;
    try {
      entries = readdirSync(current);
    } catch {
      return false;
    }
    if (!entries.includes(segment)) return false;
    current = join(current, segment);
  }
  return true;
}

// Mirror the bundler: try the bare path, then each extension, then index files.
function resolveImport(base) {
  for (const ext of RESOLVE_ORDER) {
    const candidate = base + ext;
    if (!existsCaseSensitive(candidate)) continue;
    try {
      if (statSync(candidate).isFile()) return candidate;
    } catch {
      /* fall through to index lookup */
    }
  }
  for (const ext of SOURCE_EXT) {
    const candidate = join(base, `index${ext}`);
    if (existsCaseSensitive(candidate)) return candidate;
  }
  return null;
}

const problems = [];
let checked = 0;

for (const file of walk(SRC)) {
  const source = readFileSync(file, 'utf8');
  for (const match of source.matchAll(IMPORT_RE)) {
    const spec = match[1] ?? match[2] ?? match[3];
    // Only local imports can have a casing bug; node_modules is out of scope.
    if (!spec || (!spec.startsWith('.') && !spec.startsWith('@/'))) continue;

    const base = spec.startsWith('@/')
      ? join(MOBILE_ROOT, spec.startsWith('@/assets/') ? spec.slice(2) : join('src', spec.slice(2)))
      : resolve(dirname(file), spec);

    checked++;
    if (!resolveImport(base)) {
      const line = source.slice(0, match.index).split('\n').length;
      problems.push(`${relative(MOBILE_ROOT, file)}:${line}  cannot resolve '${spec}'`);
    }
  }
}

if (problems.length > 0) {
  console.error(`\nCasing/resolution check FAILED — ${problems.length} bad import(s):\n`);
  for (const p of problems) console.error(`  ${p}`);
  console.error(
    '\nThese resolve on Windows but will fail on macOS and the iOS build.\n' +
      'Fix the import to match the real filename exactly (including case).\n'
  );
  process.exit(1);
}

console.log(`Casing check passed — ${checked} local imports resolve exactly.`);
