import test from 'node:test';
import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createProvider } from '../lib/provider.mjs';

function setup() {
    const controller = new AbortController();
    return { controller, provider: createProvider({ signal: controller.signal }, 600) };
}

test('advertises one invocable backend-neutral skill with an existing resource root', async () => {
    const { provider } = setup();
    const entries = await provider.list();
    assert.equal(entries.length, 1);
    const entry = entries[0];
    assert.equal(entry.name, 'hpc-style-for-ai');
    assert.equal(entry.rank, 600);
    assert.deepEqual(entry.invocation, { modelInvocable: true, userInvocable: true });
    await access(entry.path);
    await access(entry.resourceBase.path);
});

test('loads body on demand and does not expose frontmatter or selection rank', async () => {
    const { provider } = setup();
    const [entry] = await provider.list();
    const loaded = await provider.get(entry);
    assert.match(loaded.content, /^# HPC_Style_For_AI/m);
    assert.match(loaded.content, /references\/rules\.md/);
    assert.match(loaded.content, /模板/);
    assert.equal(loaded.rank, undefined);
    assert.equal(loaded.locator, undefined);
    assert.ok(!loaded.content.startsWith('---'));
});

test('entry loads general principles before optional mechanisms without case dependencies', async () => {
    const { provider } = setup();
    const [entry] = await provider.list();
    const loaded = await provider.get(entry);
    assert.match(loaded.content, /计算契约/);
    assert.match(loaded.content, /绑定时机/);
    assert.match(loaded.content, /binding-strategies\.md/);
    assert.ok(loaded.content.indexOf('references/rules.md') < loaded.content.indexOf('binding-strategies.md'));
    assert.doesNotMatch(loaded.content, /AMReX|FabArray|BoxArray|base-study|base-evidence/);
});

test('execution and memory guidance is discoverable but not eagerly injected', async () => {
    const { provider } = setup();
    const [entry] = await provider.list();
    const loaded = await provider.get(entry);
    assert.match(loaded.content, /references\/execution-memory-contracts\.md/);
    assert.match(loaded.content, /只加载当前设计问题需要的说明/);
    assert.doesNotMatch(loaded.content, /Kokkos|kokkos-study|kokkos-evidence|KM01|KE01/);
    const guide = await readFile(new URL('../skills/hpc-style-for-ai/references/execution-memory-contracts.md', import.meta.url), 'utf8');
    for (const term of ['共享什么', '隔离什么', '多种表示', '贡献应出现几次', '能触及', '已完成', '逻辑独立不必等于立即复制', '假设', '验证']) assert.ok(guide.includes(term), term);
    assert.doesNotMatch(guide, /AMReX|Kokkos|DualView|TeamThreadRange|MDRangePolicy|TeamPolicy|create_mirror|deep_copy|fence|scratch/);
    assert.doesNotMatch(guide, /^## .*?(镜像|具体实例|线程组|向量宽度|归约|扫描)/m);
});

test('curated rules preserve case-derived distinctions without prescribing a library', async () => {
    const rules = await readFile(new URL('../skills/hpc-style-for-ai/references/rules.md', import.meta.url), 'utf8');
    for (const term of ['0.3.1', '逻辑独立性', '多份表示', '职责与贡献次数', '版本有效', '工作完成', '实际条件', '候选方案', '计算语义']) assert.ok(rules.includes(term), term);
    assert.equal((rules.match(/^### G\d{2}：/gm) ?? []).length, 12);
    assert.doesNotMatch(rules, /AMReX|Kokkos|DualView|MDRangePolicy|TeamPolicy|TeamThreadRange|create_mirror|deep_copy|fence|scratch/);
    assert.doesNotMatch(rules, /创建镜像|执行域类型与具体实例|具体重载|vector length/);
});

test('packed distribution includes optional guidance, provenance, licenses and display resources', () => {
    const root = fileURLToPath(new URL('../', import.meta.url));
    const result = spawnSync('npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], { cwd: root, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });
    assert.equal(result.status, 0, result.stderr);
    const parsed = JSON.parse(result.stdout);
    const packed = Array.isArray(parsed) ? parsed[0] : Object.values(parsed)[0];
    const files = packed.files.map(({ path }) => path);
    for (const expected of ['skills/hpc-style-for-ai/references/execution-memory-contracts.md', 'evidence/kokkos-evidence.json', 'third_party/Kokkos-LICENSE', 'locale/zh.json', 'locale/en.json', 'assets/icon.svg', 'examples/kokkos_contracts.cpp']) assert.ok(files.includes(expected), expected);
    for (const path of files) assert.doesNotMatch(path, /(^|\/)(node_modules|__pycache__|\.git|\.env|build[^/]*)(\/|$)|\.(tgz|pyc)$/);
});

test('ignores unknown names and locators', async () => {
    const { provider } = setup();
    const [entry] = await provider.list();
    assert.equal(await provider.get({ ...entry, name: 'other' }), undefined);
    assert.equal(await provider.get({ ...entry, locator: '../secret' }), undefined);
});

test('honors caller cancellation in list and get', async () => {
    const { provider } = setup();
    const [entry] = await provider.list();
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(provider.list({ signal: controller.signal }), { name: 'AbortError' });
    await assert.rejects(provider.get(entry, { signal: controller.signal }), { name: 'AbortError' });
});

test('honors provider disposal in list and get', async () => {
    const { controller, provider } = setup();
    const [entry] = await provider.list();
    controller.abort();
    await assert.rejects(provider.list(), { name: 'AbortError' });
    await assert.rejects(provider.get(entry), { name: 'AbortError' });
});
