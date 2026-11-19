import test from 'node:test';
import assert from 'node:assert/strict';
import { access } from 'node:fs/promises';
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
