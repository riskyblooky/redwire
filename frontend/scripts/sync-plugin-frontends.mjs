#!/usr/bin/env node
/**
 * Mirror plugin frontend directories into the Next.js app tree.
 *
 * Each plugin at ``backend/plugins/<slug>/frontend/`` gets copied to
 * ``frontend/src/app/plugins/<slug>/`` before ``next build`` / ``next dev``
 * so Next's file-based router picks it up. Plugin authors write React
 * pages the same way they would in core.
 *
 * Runs via package.json's ``prebuild`` and ``predev`` hooks — no daemons.
 *
 * Idempotent + tolerates deletions:
 *   * Every managed directory is stamped with ``.plugin-managed`` so a
 *     later run can identify what it owns.
 *   * Directories whose backing plugin frontend is gone are removed.
 *   * Directories NOT stamped (e.g. a hand-authored page under
 *     ``src/app/plugins/foo/``) are left alone — we never touch code
 *     the developer didn't tell us we owned.
 *
 * Path resolution: this script sits at ``frontend/scripts/`` and expects
 * ``backend/plugins/`` to be a sibling of ``frontend/`` in the repo. In
 * container builds the same relative shape holds because the Docker
 * COPY steps preserve it.
 */
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const FRONTEND_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(FRONTEND_ROOT, '..');
const APP_PLUGINS_TARGET = path.join(FRONTEND_ROOT, 'src', 'app', 'plugins');

// Where plugin source lives. Precedence:
//   1. PLUGINS_SOURCE_DIR env var (explicit override for oddball layouts)
//   2. /backend-plugins  — dev-mode bind mount (see docker-compose.yml)
//   3. ../backend/plugins — host-side repo layout
// The frontend container has ./frontend bind-mounted but NOT
// ./backend/plugins, so (3) fails inside the container. (2) is our
// dev-container fix; in prod the Dockerfile COPYs plugins/ into the
// build stage before this script runs so (3) works there.
const CANDIDATE_SOURCES = [
    process.env.PLUGINS_SOURCE_DIR,
    '/backend-plugins',
    path.join(REPO_ROOT, 'backend', 'plugins'),
].filter(Boolean);

// Marker file dropped at the root of every synced plugin dir. Any dir
// containing this stamp is fair game for the cleanup pass; anything
// missing it is developer-authored and left alone.
const MANAGED_MARKER = '.plugin-managed';

async function pathExists(p) {
    try { await fs.access(p); return true; } catch { return false; }
}

async function readdirSafe(dir) {
    try { return await fs.readdir(dir, { withFileTypes: true }); }
    catch { return []; }
}

async function copyDir(src, dest) {
    // Node 16.7+ supports fs.cp with recursive
    await fs.mkdir(dest, { recursive: true });
    const entries = await fs.readdir(src, { withFileTypes: true });
    for (const entry of entries) {
        const srcPath = path.join(src, entry.name);
        const destPath = path.join(dest, entry.name);
        if (entry.isDirectory()) {
            await copyDir(srcPath, destPath);
        } else if (entry.isFile()) {
            await fs.copyFile(srcPath, destPath);
        }
        // Symlinks and other types are skipped intentionally.
    }
}

async function isManagedDir(dir) {
    return pathExists(path.join(dir, MANAGED_MARKER));
}

async function removeIfManaged(dir) {
    if (await isManagedDir(dir)) {
        await fs.rm(dir, { recursive: true, force: true });
        return true;
    }
    return false;
}

async function resolvePluginsSource() {
    for (const candidate of CANDIDATE_SOURCES) {
        if (await pathExists(candidate)) return candidate;
    }
    return null;
}

async function discoverSourcePlugins(pluginsSource) {
    const entries = await readdirSafe(pluginsSource);
    const plugins = [];
    for (const entry of entries) {
        if (!entry.isDirectory()) continue;
        if (entry.name.startsWith('.') || entry.name.startsWith('_')) continue;
        const frontendDir = path.join(pluginsSource, entry.name, 'frontend');
        if (await pathExists(frontendDir)) {
            plugins.push({
                slug: entry.name.replace(/_/g, '-'),          // URL segment style
                sourceName: entry.name,                        // On-disk name
                frontendDir,
            });
        }
    }
    return plugins;
}

async function main() {
    const pluginsSource = await resolvePluginsSource();
    if (!pluginsSource) {
        console.log(
            '[sync-plugin-frontends] no plugin source dir found (tried: '
            + CANDIDATE_SOURCES.join(', ') + '); skipping.'
        );
        return;
    }
    console.log(`[sync-plugin-frontends] source: ${pluginsSource}`);

    const sourcePlugins = await discoverSourcePlugins(pluginsSource);
    const sourceSlugs = new Set(sourcePlugins.map(p => p.slug));

    await fs.mkdir(APP_PLUGINS_TARGET, { recursive: true });

    // 1) Cleanup: remove any managed dirs whose source plugin is gone.
    // Only touches dirs stamped with .plugin-managed — leaves
    // hand-authored routes under src/app/plugins/ alone.
    const existing = await readdirSafe(APP_PLUGINS_TARGET);
    let removed = 0;
    for (const entry of existing) {
        if (!entry.isDirectory()) continue;
        const dir = path.join(APP_PLUGINS_TARGET, entry.name);
        if (sourceSlugs.has(entry.name)) continue;
        if (await removeIfManaged(dir)) {
            removed++;
            console.log(`[sync-plugin-frontends] removed stale: plugins/${entry.name}`);
        }
    }

    // 2) Sync: for each source plugin, wipe the managed dir and re-copy.
    // Wiping avoids stale files when a plugin author renames or removes
    // a page. Hand-authored dirs (no marker) are refused with a warning
    // so we don't clobber intentional local overrides.
    let synced = 0;
    for (const plugin of sourcePlugins) {
        const target = path.join(APP_PLUGINS_TARGET, plugin.slug);
        if (await pathExists(target) && !(await isManagedDir(target))) {
            console.warn(
                `[sync-plugin-frontends] WARN: ${target} exists and is NOT `
                + `stamped as managed. Refusing to overwrite hand-authored code. `
                + `To let this script own the directory, remove it manually first.`
            );
            continue;
        }
        // Wipe then re-copy so removed files disappear.
        await fs.rm(target, { recursive: true, force: true });
        await copyDir(plugin.frontendDir, target);
        // Stamp so future runs know we own it.
        await fs.writeFile(
            path.join(target, MANAGED_MARKER),
            `# Auto-generated by frontend/scripts/sync-plugin-frontends.mjs\n`
            + `# Source: backend/plugins/${plugin.sourceName}/frontend/\n`
            + `# Edits here will be overwritten on next build. Edit the plugin source.\n`,
        );
        synced++;
        console.log(`[sync-plugin-frontends] synced: ${plugin.sourceName} -> plugins/${plugin.slug}`);
    }

    // 3) Generate the extension registry file. Plugin authors drop
    // component files at plugins/<slug>/frontend/extensions/<name>.tsx;
    // this file maps "<slug>:<name>" to a next/dynamic import so
    // <PluginSlot> can look them up at render time without any
    // runtime module loader (Next needs the import paths at build
    // time for tree-shaking + code-splitting).
    const registryImports = [];
    const registryEntries = [];
    for (const plugin of sourcePlugins) {
        const extensionsDir = path.join(APP_PLUGINS_TARGET, plugin.slug, 'extensions');
        if (!(await pathExists(extensionsDir))) continue;
        const walk = async (dir) => {
            const entries = await readdirSafe(dir);
            for (const entry of entries) {
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    await walk(full);
                } else if (entry.isFile() && entry.name.endsWith('.tsx')) {
                    const rel = path.relative(APP_PLUGINS_TARGET, full).replace(/\\/g, '/');
                    const name = rel.replace(/\.tsx$/, '');
                    const key = `${plugin.slug}:${entry.name.replace(/\.tsx$/, '')}`;
                    registryImports.push(
                        `import * as _${registryImports.length} from './${name}';`
                    );
                    registryEntries.push(
                        `    '${key}': _${registryImports.length - 1}.default,`
                    );
                }
            }
        };
        await walk(extensionsDir);
    }

    const registryPath = path.join(APP_PLUGINS_TARGET, '_extensions.generated.tsx');
    const registryBody = [
        '// AUTO-GENERATED by frontend/scripts/sync-plugin-frontends.mjs.',
        '// Do not edit — regenerated on every next dev / next build.',
        '// Maps "<plugin-slug>:<component-basename>" to the exported default.',
        '',
        ...registryImports,
        '',
        'export const PLUGIN_EXTENSION_COMPONENTS: Record<string, any> = {',
        ...registryEntries,
        '};',
        '',
    ].join('\n');
    await fs.writeFile(registryPath, registryBody);

    console.log(
        `[sync-plugin-frontends] done — synced ${synced}, `
        + `removed ${removed} stale, ${sourcePlugins.length} plugin(s) with frontend/, `
        + `${registryEntries.length} extension component(s) registered.`
    );
}

main().catch((err) => {
    console.error('[sync-plugin-frontends] failed:', err);
    process.exit(1);
});
