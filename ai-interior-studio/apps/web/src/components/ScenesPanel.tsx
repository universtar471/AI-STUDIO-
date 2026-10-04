import { useState } from 'react';
import { api, artifactUrl, type Saved } from '../api/client';
import type { Scene } from '../api/types';

interface Props {
  projectId: string;
  scenes: Saved<Scene>[];
  onAdded: (scene: Saved<Scene>) => void;
}

export function ScenesPanel({ projectId, scenes, onAdded }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    setError('');
    try {
      for (const file of Array.from(files)) {
        onAdded(await api.importScene(projectId, file, file.name.replace(/\.[^.]+$/, '')));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h3>Cảnh SketchUp</h3>
      <label className="button">
        {busy ? 'Đang tải lên…' : 'Thêm ảnh cảnh (PNG/JPG)'}
        <input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden onChange={(e) => upload(e.target.files)} />
      </label>
      {error && <p className="error">{error}</p>}
      <ul className="grid">
        {scenes.map((s) => (
          <li key={s.id} className="thumb">
            <img src={artifactUrl(s.rgb_artifact_id)} alt={s.name} />
            <span>{s.name}</span>
          </li>
        ))}
        {!scenes.length && <li className="muted">Chưa có cảnh. Xuất PNG từ SketchUp rồi thêm vào đây.</li>}
      </ul>
    </section>
  );
}
