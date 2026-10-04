import { artifactUrl, type Saved } from '../api/client';
import type { RenderJob, Scene } from '../api/types';
import { STATE_LABEL, firstImage, isActive } from '../lib/jobs';

interface Props {
  jobs: Saved<RenderJob>[];
  scenes: Saved<Scene>[];
  onOpen: (job: Saved<RenderJob>) => void;
}

export function sourceImage(job: RenderJob, scenes: Saved<Scene>[]): string | undefined {
  if (job.request.source?.artifact_id) return job.request.source.artifact_id;
  return scenes.find((s) => s.id === job.request.source?.scene_id)?.rgb_artifact_id;
}

export function HistoryPanel({ jobs, scenes, onOpen }: Props) {
  return (
    <section>
      <h3>Lịch sử</h3>
      <ul className="grid">
        {jobs.map((job) => {
          const image = firstImage(job) ?? sourceImage(job, scenes);
          const scene = scenes.find((s) => s.id === job.request.source?.scene_id);
          return (
            <li key={job.id}>
              <button className={`thumb job state-${job.state}`} onClick={() => onOpen(job)} aria-label={`Mở job ${job.id}`}>
                {image ? <img src={artifactUrl(image)} alt="" className={firstImage(job) ? '' : 'faded'} /> : <div className="placeholder" />}
                <span>{scene?.name ?? 'Ảnh'} · r{job.revision ?? 1}</span>
                <span className="badge">{STATE_LABEL[job.state ?? 'DRAFT']}</span>
                {isActive(job.state) && <progress max={1} value={job.progress ?? 0} aria-label="Tiến độ" />}
              </button>
            </li>
          );
        })}
        {!jobs.length && <li className="muted">Chưa có job nào.</li>}
      </ul>
    </section>
  );
}
