// Optional integration smoke: node scripts/host-smoke.mjs /path/to/dsh-runtime
// Uses an isolated temporary copy; does not touch the live DSH profile.
import { mkdtemp, cp, mkdir, symlink, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

if (!process.argv[2]) { throw new Error('Pass the installed DSH runtime directory'); }
const requireHost = createRequire(join(resolve(process.argv[2]), 'package.json'));
const { Context } = await import(pathToFileURL(requireHost.resolve('@deepseek-ai/cordis')));
const { SkillRegistry, renderSkillContent } = await import(pathToFileURL(requireHost.resolve('@deepseek-ai/dsh-skill')));
const root = fileURLToPath(new URL('../', import.meta.url));
const stage = await mkdtemp(join(tmpdir(), 'hpc-style-host-'));
console.log(`Isolated smoke directory: ${stage}`);
for (const path of ['index.js', 'lib', 'skills', 'package.json']) {
    await cp(join(root, path), join(stage, path), { recursive: true });
}
await mkdir(join(stage, 'node_modules/@deepseek-ai'), { recursive: true });
await symlink(join(resolve(process.argv[2]), 'node_modules/@deepseek-ai/dsh-skill'),
    join(stage, 'node_modules/@deepseek-ai/dsh-skill'), 'dir');
const plugin = await import(pathToFileURL(join(stage, 'index.js')));
const ctx = new Context();
const registryFiber = ctx.plugin(SkillRegistry);
let pluginFiber;
try {
    await registryFiber.await();
    pluginFiber = ctx.plugin(plugin);
    await pluginFiber.await();
    const entries = await ctx.skills.list();
    assert.ok(entries.some((entry) => entry.name === 'hpc-style-for-ai'));
    const loaded = await ctx.skills.get('hpc-style-for-ai');
    assert.ok(loaded.content.includes('绑定时机决策必须回答的问题'));
    const rulesPath = join(loaded.resourceBase.path, 'references/rules.md');
    assert.ok((await readFile(rulesPath, 'utf8')).includes('### G05'));
    assert.ok(loaded.content.includes('references/execution-memory-contracts.md'));
    const contractsPath = join(loaded.resourceBase.path, 'references/execution-memory-contracts.md');
    assert.ok((await readFile(contractsPath, 'utf8')).includes('逻辑独立不必等于立即复制'));
    assert.doesNotMatch(loaded.content, /Kokkos|kokkos-study|kokkos-evidence/);
    assert.ok(renderSkillContent(loaded).includes('<skill_content'));
    console.log('Real DSH SkillRegistry discovery, load, relative resources, rendering: passed');
} finally {
    await pluginFiber?.dispose();
    await registryFiber.dispose();
}
