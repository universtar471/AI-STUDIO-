import { useState } from 'react';
import { api, artifactUrl, type Saved } from '../api/client';
import type { RenderJob, Scene } from '../api/types';
import { STATE_LABEL, actionsFor, firstImage, isActive } from '../lib/jobs';
import { CompareSlider } from './CompareSlider';
import { sourceImage } from './HistoryPanel';

interface Props {
  job: Saved<RenderJob>;
  jobs: Saved<RenderJob>[];
  scenes: Saved<Scene>[];
  onChanged: (jobs: Saved<RenderJob>[]) => void;
  onOpen: (jobId: string) => void;
  onClose: () => void;
}

export function JobDetail({ job, jobs, scenes, onChanged, onOpen, onClose }: Props) {
  const [error, setError] = useState('');
  const [compareWith, setCompareWith] = useState<string>('source');
  const actions = actionsFor(job);
  const result = firstImage(job);
  // Comparable: the source view, and any other finished job of the same scene (e.g. the job this one retried).
  const others = jobs.filter((j) => j.id !== job.id && firstImage(j) && j.request.source?.scene_id === job.request.source?.scene_id);
  const before = compareWith === 'source' ? sourceImage(job, scenes) : firstImage(jobs.find((j) => j.id === compareWith)!);

  const run = async (action: () => Promise<Saved<RenderJob>>) => {
    setError('');
    try {
      const changed = await action();
      const refreshed = changed.id === job.id ? [changed] : [changed, await api.job(job.id)];
      onChanged(refreshed);
      // Retry creates a new job: follow it so its progress is what the user sees next.
      if (changed.id !== job.id) onOpen(changed.id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="detail" role="dialog" aria-label="Chi tiết job">
      <header className="row spread">
        <h3>Job r{job.revision ?? 1} · {STATE_LABEL[job.state ?? 'DRAFT']}</h3>
        <button onClick={onClose}>Đóng</button>
      </header>

      {result && before ? (
        <>
          <label>So với{' '}
            <select value={compareWith} onChange={(e) => setCompareWith(e.target.value)} aria-label="So sánh với">
              <option value="source">Ảnh gốc SketchUp</option>
              {others.map((o) => <option key={o.id} value={o.id}>Job r{o.revision ?? 1} ({STATE_LABEL[o.state ?? 'DRAFT']})</option>)}
            </select>
          </label>
          <CompareSlider before={artifactUrl(before)} after={artifactUrl(result)} beforeLabel="Trước" afterLabel="Kết quả" />
        </>
      ) : result ? (
        <img className="full" src={artifactUrl(result)} alt="Kết quả" />
      ) : (
        <div className="pending">
          {isActive(job.state) ? <><progress max={1} value={job.progress ?? 0} /> {job.stage ?? ''}</> : 'Chưa có ảnh.'}
        </div>
      )}

      {job.error && <p className="error">{job.error.code}: {job.error.message}</p>}
      {error && <p className="error">{error}</p>}

      <div className="row">
        {actions.approve && <button className="primary" onClick={() => run(() => api.approve(job.id))}>Duyệt</button>}
        {actions.retry && <button onClick={() => run(() => api.retry(job.id))}>Làm lại</button>}
        {actions.cancel && <button onClick={() => run(() => api.cancel(job.id))}>Hủy</button>}
      </div>

      <dl className="facts">
        <dt>Provider</dt><dd>{job.provider_id ?? '—'}</dd>
        <dt>Seed</dt><dd>{job.result?.seed ?? job.request.seed ?? '—'}</dd>
        <dt>Style Pack</dt><dd>{job.request.style_pack_id ? `v${job.request.style_pack_version}` : '—'}</dd>
        {job.retry_of && <><dt>Làm lại từ</dt><dd>{job.retry_of.slice(0, 8)}</dd></>}
        {job.result?.metrics?.cost_estimate != null && <><dt>Chi phí ước tính</dt><dd>${job.result.metrics.cost_estimate}</dd></>}
      </dl>
      <details>
        <summary>Diễn biến trạng thái</summary>
        <ol>{job.history?.map((h, i) => <li key={i}>{STATE_LABEL[h.from_state]} → {STATE_LABEL[h.to_state]}{h.reason ? ` (${h.reason})` : ''}</li>)}</ol>
      </details>
    </div>
  );
}
