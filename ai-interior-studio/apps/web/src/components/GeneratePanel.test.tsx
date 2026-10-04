import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ProviderInfo } from '../api/types';
import { GeneratePanel } from './GeneratePanel';

const providers: ProviderInfo[] = [
  { id: 'mock', health: { status: 'ok' }, capabilities: { supported_modes: ['sketchup_render'], supports_local: true, supports_multi_reference: true, max_reference_images: 16, supported_ratios: ['16:9'], supported_sizes: ['1K'] } },
  { id: 'gemini', health: { status: 'ok' }, capabilities: { supported_modes: ['sketchup_render'], has_usage_cost: true, supports_multi_reference: true, max_reference_images: 13, supported_ratios: ['16:9'], supported_sizes: ['1K', '4K'] } },
  { id: 'planonly', health: { status: 'ok' }, capabilities: { supported_modes: ['plan_concept'] } },
];
const scenes = [{ id: 's1', project_id: 'p', name: 'Living', rgb_artifact_id: 'a1' }, { id: 's2', project_id: 'p', name: 'Kitchen', rgb_artifact_id: 'a2' }];

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function mockFetch() {
  const bodies: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body));
    bodies.push(body);
    return new Response(JSON.stringify({ id: `job-${bodies.length}`, project_id: 'p', request: body, state: 'QUEUED' }), { status: 201 });
  }));
  return bodies;
}

describe('GeneratePanel', () => {
  it('hides providers that do not support the mode and marks paid ones', () => {
    render(<GeneratePanel projectId="p" scenes={scenes} packs={[]} providers={providers} onCreated={() => {}} />);
    const options = Array.from((screen.getByLabelText('Provider') as HTMLSelectElement).options).map((o) => o.textContent);
    expect(options).toEqual(['Tự chọn', 'mock', 'gemini (tính phí)']);
  });

  it('creates one job per selected scene with the advanced options', async () => {
    const bodies = mockFetch();
    const onCreated = vi.fn();
    render(<GeneratePanel projectId="p" scenes={scenes} packs={[]} providers={providers} onCreated={onCreated} />);
    fireEvent.click(screen.getByLabelText('Chọn cảnh Living'));
    fireEvent.click(screen.getByLabelText('Chọn cảnh Kitchen'));
    fireEvent.change(screen.getByLabelText('Seed'), { target: { value: '42' } });
    fireEvent.change(screen.getByLabelText('Prompt cuối'), { target: { value: 'warm oak' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh (2 cảnh)' }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(bodies).toHaveLength(2);
    expect(bodies[0]).toMatchObject({ source: { scene_id: 's1' }, seed: 42, prompt: { raw_text: 'warm oak' }, confirm_high_cost: false });
    expect(bodies[1]).toMatchObject({ source: { scene_id: 's2' } });
  });

  it('asks before a paid 4K render and sends confirm_high_cost', async () => {
    const bodies = mockFetch();
    const confirm = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<GeneratePanel projectId="p" scenes={scenes} packs={[]} providers={providers} onCreated={() => {}} confirm={confirm} />);
    fireEvent.click(screen.getByLabelText('Chọn cảnh Living'));
    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'gemini' } });
    fireEvent.change(screen.getByLabelText('Cỡ ảnh'), { target: { value: '4K' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh' }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(bodies).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh' }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ provider_id: 'gemini', image_size: '4K', confirm_high_cost: true });
  });
});
