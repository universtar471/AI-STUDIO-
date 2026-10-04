import { useMemo, useState } from 'react';
import { api, artifactUrl, type Saved } from '../api/client';
import type { ProviderInfo, ProviderPolicy, RenderJob, RenderRequest, Scene, StylePack } from '../api/types';
import { costsMoney, eligibleProviders, isHealthy, offered } from '../lib/providers';

interface Props {
  projectId: string;
  scenes: Saved<Scene>[];
  packs: Saved<StylePack>[];
  providers: ProviderInfo[];
  onCreated: (jobs: Saved<RenderJob>[]) => void;
  confirm?: (message: string) => boolean;
}

export function GeneratePanel({ projectId, scenes, packs, providers, onCreated, confirm = window.confirm }: Props) {
  const [sceneIds, setSceneIds] = useState<string[]>([]);
  const [packId, setPackId] = useState('');
  const [ratio, setRatio] = useState('16:9');
  const [providerId, setProviderId] = useState('');
  const [policy, setPolicy] = useState<ProviderPolicy>('auto');
  const [imageSize, setImageSize] = useState('');
  const [seed, setSeed] = useState('');
  const [rawText, setRawText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const pack = packs.find((p) => p.id === packId);
  const referenceCount = pack?.references?.length ?? 0;
  const seedValue = seed.trim() === '' ? null : Number(seed);
  const eligible = useMemo(
    () => eligibleProviders(providers, { mode: 'sketchup_render', ratio, imageSize: imageSize || undefined, referenceCount, seed: seedValue }),
    [providers, ratio, imageSize, referenceCount, seedValue],
  );
  const ratios = offered(providers.filter((p) => p.capabilities.supported_modes.includes('sketchup_render')), 'supported_ratios');
  const sizes = offered(eligible, 'supported_sizes');
  const chosen = providers.find((p) => p.id === providerId);

  const toggle = (id: string) => setSceneIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));

  const submit = async () => {
    if (!sceneIds.length) return setError('Chọn ít nhất một cảnh.');
    let confirmHighCost = false;
    const paid = chosen ? costsMoney(chosen) : policy === 'cloud_only';
    if (paid && imageSize === '4K') {
      if (!confirm(`Ảnh 4K qua dịch vụ cloud có tính phí. Tạo ${sceneIds.length} ảnh?`)) return;
      confirmHighCost = true;
    }
    setBusy(true);
    setError('');
    try {
      const created: Saved<RenderJob>[] = [];
      for (const sceneId of sceneIds) {
        const body: RenderRequest = {
          project_id: projectId, mode: 'sketchup_render', source: { scene_id: sceneId }, ratio,
          provider_policy: policy, confirm_high_cost: confirmHighCost,
          ...(packId ? { style_pack_id: packId } : {}),
          ...(providerId ? { provider_id: providerId } : {}),
          ...(imageSize ? { image_size: imageSize } : {}),
          ...(seedValue != null && !Number.isNaN(seedValue) ? { seed: seedValue } : {}),
          ...(rawText.trim() ? { prompt: { raw_text: rawText.trim() } } : {}),
        };
        created.push(await api.createJob(body));
      }
      onCreated(created);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h3>Tạo ảnh</h3>
      <p className="muted">Chọn cảnh (chọn nhiều sẽ tạo nhiều job), chọn Style Pack rồi bấm Tạo ảnh.</p>
      <ul className="grid">
        {scenes.map((s) => (
          <li key={s.id} className={`thumb selectable${sceneIds.includes(s.id) ? ' selected' : ''}`}>
            <label>
              <input type="checkbox" checked={sceneIds.includes(s.id)} onChange={() => toggle(s.id)} aria-label={`Chọn cảnh ${s.name}`} />
              <img src={artifactUrl(s.rgb_artifact_id)} alt={s.name} />
              <span>{s.name}</span>
            </label>
          </li>
        ))}
        {!scenes.length && <li className="muted">Chưa có cảnh: thêm ở tab Cảnh.</li>}
      </ul>
      <div className="row">
        <label>Style Pack{' '}
          <select value={packId} onChange={(e) => setPackId(e.target.value)} aria-label="Style Pack cho job">
            <option value="">(không dùng)</option>
            {packs.map((p) => <option key={p.id} value={p.id}>{p.name} v{p.version}</option>)}
          </select>
        </label>
        <label>Tỉ lệ{' '}
          <select value={ratio} onChange={(e) => setRatio(e.target.value)} aria-label="Tỉ lệ">
            {(ratios.length ? ratios : ['16:9']).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
      </div>

      <details className="advanced">
        <summary>Nâng cao</summary>
        <div className="row">
          <label>Nguồn chạy{' '}
            <select value={policy} onChange={(e) => setPolicy(e.target.value as ProviderPolicy)} aria-label="Nguồn chạy">
              <option value="auto">Tự động (ưu tiên máy local)</option>
              <option value="local_only">Chỉ máy local</option>
              <option value="cloud_only">Chỉ cloud</option>
            </select>
          </label>
          <label>Provider{' '}
            <select value={providerId} onChange={(e) => setProviderId(e.target.value)} aria-label="Provider">
              <option value="">Tự chọn</option>
              {eligible.map((p) => (
                <option key={p.id} value={p.id} disabled={!isHealthy(p)}>
                  {p.id}{costsMoney(p) ? ' (tính phí)' : ''}{isHealthy(p) ? '' : ` (${p.health.status})`}
                </option>
              ))}
            </select>
          </label>
          <label>Cỡ ảnh{' '}
            <select value={imageSize} onChange={(e) => setImageSize(e.target.value)} aria-label="Cỡ ảnh">
              <option value="">Mặc định</option>
              {sizes.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Seed{' '}
            <input value={seed} onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ''))} inputMode="numeric" aria-label="Seed" />
          </label>
        </div>
        <label className="block">Prompt cuối (để trống thì app tự dựng)
          <textarea value={rawText} onChange={(e) => setRawText(e.target.value)} rows={4} aria-label="Prompt cuối" />
        </label>
      </details>

      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={busy || !sceneIds.length} onClick={submit}>
        {busy ? 'Đang gửi…' : `Tạo ảnh${sceneIds.length > 1 ? ` (${sceneIds.length} cảnh)` : ''}`}
      </button>
    </section>
  );
}
