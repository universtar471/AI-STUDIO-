import { useEffect, useState } from 'react';
import { api, artifactUrl, type Saved } from '../api/client';
import type { ReferenceRole, StylePack } from '../api/types';

export const ROLE_LABEL: Record<ReferenceRole, string> = {
  STYLE_MASTER: 'Ảnh phong cách chính', APPROVED_VIEW: 'View đã duyệt', BASE_PLAN: 'Ảnh gốc',
  CEILING: 'Trần', WALL: 'Tường', FLOOR: 'Sàn', CABINET: 'Tủ', FURNITURE: 'Đồ rời', LIGHTING: 'Đèn', DECOR: 'Trang trí',
};
// BASE_PLAN belongs to a scene or room, not a Style Pack, so it is not offered here.
const PACK_ROLES = (Object.keys(ROLE_LABEL) as ReferenceRole[]).filter((r) => r !== 'BASE_PLAN');

interface Props {
  projectId: string;
  packs: Saved<StylePack>[];
  onChanged: (pack: Saved<StylePack>) => void;
}

export function StylePackPanel({ projectId, packs, onChanged }: Props) {
  const [selectedId, setSelectedId] = useState<string | undefined>(packs[0]?.id);
  const [version, setVersion] = useState<number | undefined>();
  const [versions, setVersions] = useState<number[]>([]);
  const [shown, setShown] = useState<Saved<StylePack> | undefined>();
  const [role, setRole] = useState<ReferenceRole>('STYLE_MASTER');
  const [name, setName] = useState('');
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');

  const latest = packs.find((p) => p.id === selectedId);

  useEffect(() => {
    if (!selectedId && packs.length) setSelectedId(packs[0].id);
  }, [packs, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    api.stylePackVersions(selectedId).then(setVersions).catch(() => setVersions([]));
    if (version && version !== latest?.version) {
      api.stylePack(selectedId, version).then(setShown).catch((e) => setError(e.message));
    } else {
      setShown(latest);
    }
  }, [selectedId, version, latest]);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    const pack = await api.createStylePack({ name: name.trim(), project_id: projectId });
    setName('');
    setSelectedId(pack.id);
    setVersion(undefined);
    onChanged(pack);
  };

  const add = async (files: FileList | File[] | null) => {
    if (!files || !latest) return;
    setError('');
    try {
      let pack = latest;
      for (const file of Array.from(files)) pack = await api.addReference(latest.id, file, role);
      setVersion(undefined);
      onChanged(pack);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const readOnly = !!shown && !!latest && shown.version !== latest.version;

  return (
    <section>
      <h3>Style Pack</h3>
      <form className="row" onSubmit={create}>
        <select value={selectedId ?? ''} onChange={(e) => { setSelectedId(e.target.value); setVersion(undefined); }} aria-label="Chọn Style Pack">
          {!packs.length && <option value="">(chưa có)</option>}
          {packs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input placeholder="Tên Style Pack mới" value={name} onChange={(e) => setName(e.target.value)} aria-label="Tên Style Pack" />
        <button type="submit">Tạo</button>
      </form>

      {latest && (
        <>
          <div className="row">
            <label>
              Phiên bản{' '}
              <select value={version ?? latest.version} onChange={(e) => setVersion(Number(e.target.value))} aria-label="Phiên bản">
                {versions.map((v) => <option key={v} value={v}>v{v}{v === latest.version ? ' (mới nhất)' : ''}</option>)}
              </select>
            </label>
            <label>
              Vai trò cho ảnh thêm vào{' '}
              <select value={role} onChange={(e) => setRole(e.target.value as ReferenceRole)} aria-label="Vai trò">
                {PACK_ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </select>
            </label>
          </div>
          {readOnly ? (
            <p className="muted">Đang xem bản cũ v{shown?.version}: chỉ đọc. Thêm ảnh sẽ tạo bản mới từ v{latest.version}.</p>
          ) : (
            <div
              className={`dropzone${dragging ? ' over' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); add(Array.from(e.dataTransfer.files)); }}
            >
              Kéo thả ảnh tham chiếu vào đây ({ROLE_LABEL[role]}) hoặc{' '}
              <label className="link">
                chọn file
                <input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden onChange={(e) => add(e.target.files)} />
              </label>
            </div>
          )}
          {error && <p className="error">{error}</p>}
          <ul className="grid">
            {(shown ?? latest).references?.map((ref) => (
              <li key={ref.id ?? ref.artifact_id} className="thumb">
                <img src={artifactUrl(ref.artifact_id)} alt={ROLE_LABEL[ref.role]} />
                <span>{ROLE_LABEL[ref.role]}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
