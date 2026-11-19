import { BUNDLED_SKILL_RANK } from '@deepseek-ai/dsh-skill';
import { createProvider } from './lib/provider.mjs';

export const name = 'hpc-style-for-ai';
export const inject = ['skills'];

export function apply(ctx) {
    ctx.skills.registerProvider((control) => createProvider(control, BUNDLED_SKILL_RANK));
}
