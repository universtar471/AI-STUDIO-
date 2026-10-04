import { useEffect, useState } from 'react';
import { api, type Saved } from '../api/client';
import type { Project, ProjectType } from '../api/types';

const TYPES: Record<ProjectType, string> = { apartment: 'Căn hộ', house: 'Nhà ở', office: 'Văn phòng', retail: 'Cửa hàng' };

export function ProjectsView({ onOpen }: { onOpen: (project: Saved<Project>) => void }) {
  const [projects, setProjects] = useState<Saved<Project>[]>([]);
  const [name, setName] = useState('');
  const [type, setType] = useState<ProjectType>('apartment');
  const [error, setError] = useState('');

  useEffect(() => {
    api.projects().then(setProjects).catch((e) => setError(e.message));
  }, []);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const project = await api.createProject({ name: name.trim(), type });
      setName('');
      onOpen(project);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section>
      <h2>Dự án</h2>
      <form className="row" onSubmit={create}>
        <input placeholder="Tên dự án mới" value={name} onChange={(e) => setName(e.target.value)} aria-label="Tên dự án" />
        <select value={type} onChange={(e) => setType(e.target.value as ProjectType)} aria-label="Loại dự án">
          {Object.entries(TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <button type="submit">Tạo dự án</button>
      </form>
      {error && <p className="error">{error}</p>}
      <ul className="cards">
        {projects.map((p) => (
          <li key={p.id}>
            <button className="card" onClick={() => onOpen(p)}>
              <strong>{p.name}</strong>
              <span>{TYPES[p.type ?? 'apartment']}</span>
            </button>
          </li>
        ))}
        {!projects.length && <li className="muted">Chưa có dự án nào.</li>}
      </ul>
    </section>
  );
}
