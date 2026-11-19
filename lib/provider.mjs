import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const providerName = 'hpc-style-for-ai';
const skillUrl = new URL('../skills/hpc-style-for-ai/SKILL.md', import.meta.url);
const rootUrl = new URL('../skills/hpc-style-for-ai/', import.meta.url);

// Registration advertises a small entry; detailed rules are loaded on demand.
export function createProvider(control, rank) {
    const candidate = Object.freeze({
        name: 'hpc-style-for-ai',
        description: '各类 HPC 项目的通用设计与评审：计算契约、成本模型、数据运动、绑定时机、执行粒度、依赖与工程取舍。用于科学计算架构、实现、重构和优化，不默认某门语言、网格框架或硬件后端。',
        invocation: Object.freeze({ modelInvocable: true, userInvocable: true }),
        source: 'bundled', provider: providerName, rank,
        locator: 'skills/hpc-style-for-ai/SKILL.md',
        path: fileURLToPath(skillUrl),
        resourceBase: Object.freeze({ kind: 'directory', path: fileURLToPath(rootUrl) }),
    });
    function signalFor(options) {
        control.signal.throwIfAborted();
        options.signal?.throwIfAborted();
        return options.signal ? AbortSignal.any([control.signal, options.signal]) : control.signal;
    }
    return {
        name: providerName,
        async list(options = {}) {
            signalFor(options);
            return [candidate];
        },
        async get(requested, options = {}) {
            const signal = signalFor(options);
            if (requested.name !== candidate.name || requested.locator !== candidate.locator) {
                return undefined;
            }
            const raw = await readFile(skillUrl, { encoding: 'utf8', signal });
            const content = raw.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '');
            const { rank: _rank, locator: _locator, ...summary } = candidate;
            return { ...summary, content };
        },
    };
}
