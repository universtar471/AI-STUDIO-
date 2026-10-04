import { describe, expect, it } from 'vitest';
import type { ProviderInfo, RenderJob } from '../api/types';
import type { Saved } from '../api/client';
import { actionsFor, applyEvent, upsertJob } from './jobs';
import { eligibleProviders, offered } from './providers';

const provider = (id: string, caps: Partial<ProviderInfo['capabilities']>, status: 'ok' | 'unavailable' = 'ok'): ProviderInfo => ({
  id, health: { status }, capabilities: { supported_modes: ['sketchup_render'], ...caps },
});
const mock = provider('mock', { supports_local: true, supports_multi_reference: true, max_reference_images: 16, supported_ratios: ['16:9', '1:1'], supported_sizes: ['1K', '2K'], supports_seed: true });
const cloud = provider('gemini', { has_usage_cost: true, supports_multi_reference: true, max_reference_images: 13, supported_ratios: ['16:9', '21:9'], supported_sizes: ['1K', '4K'] }, 'unavailable');

const job = (id: string, state: RenderJob['state'], created = '2026-10-05T00:00:00Z'): Saved<RenderJob> => ({
  id, project_id: 'p', state, created_at: created, request: { project_id: 'p', mode: 'sketchup_render', source: { scene_id: 's' } },
});

describe('eligibleProviders', () => {
  it('hides providers that cannot serve the request', () => {
    const needs = { mode: 'sketchup_render' as const, ratio: '16:9', referenceCount: 2 };
    expect(eligibleProviders([mock, cloud], needs).map((p) => p.id)).toEqual(['mock', 'gemini']);
    expect(eligibleProviders([mock, cloud], { ...needs, ratio: '21:9' }).map((p) => p.id)).toEqual(['gemini']);
    expect(eligibleProviders([mock, cloud], { ...needs, imageSize: '4K' }).map((p) => p.id)).toEqual(['gemini']);
    expect(eligibleProviders([mock, cloud], { ...needs, seed: 7 }).map((p) => p.id)).toEqual(['mock']);
    expect(eligibleProviders([mock, cloud], { ...needs, referenceCount: 14 }).map((p) => p.id)).toEqual(['mock']);
    expect(eligibleProviders([mock], { ...needs, mode: 'plan_concept' })).toEqual([]);
  });

  it('collects offered sizes in order', () => {
    expect(offered([mock, cloud], 'supported_sizes')).toEqual(['1K', '2K', '4K']);
  });
});

describe('job helpers', () => {
  it('applies live events and flags unknown jobs', () => {
    const list = [job('a', 'QUEUED')];
    const hit = applyEvent(list, { job_id: 'a', state: 'RUNNING', progress: 0.4, stage: 'mock' });
    expect(hit.unknown).toBe(false);
    expect(hit.jobs[0]).toMatchObject({ state: 'RUNNING', progress: 0.4, stage: 'mock' });
    expect(applyEvent(list, { job_id: 'zzz', state: 'RUNNING', progress: 0 }).unknown).toBe(true);
  });

  it('upserts newest first without duplicates', () => {
    let list = [job('a', 'REVIEW', '2026-10-05T01:00:00Z')];
    list = upsertJob(list, job('b', 'QUEUED', '2026-10-05T02:00:00Z'));
    list = upsertJob(list, job('a', 'APPROVED', '2026-10-05T01:00:00Z'));
    expect(list.map((j) => [j.id, j.state])).toEqual([['b', 'QUEUED'], ['a', 'APPROVED']]);
  });

  it('offers only actions the state machine allows', () => {
    expect(actionsFor(job('a', 'REVIEW'))).toEqual({ approve: true, retry: true, cancel: false, finalize: false });
    expect(actionsFor(job('a', 'FAILED'))).toEqual({ approve: false, retry: true, cancel: false, finalize: false });
    expect(actionsFor(job('a', 'RUNNING'))).toEqual({ approve: false, retry: false, cancel: true, finalize: false });
    expect(actionsFor(job('a', 'APPROVED')).finalize).toBe(true);
    expect(Object.values(actionsFor(job('a', 'RETRY'))).some(Boolean)).toBe(false);
  });
});
