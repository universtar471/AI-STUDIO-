import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type Saved } from './api/client';
import type { JobProgressEvent, Project } from './api/types';
import { ProjectView } from './components/ProjectView';
import { ProjectsView } from './components/ProjectsView';
import { useJobEvents } from './hooks/useJobEvents';
import { projectHash, projectIdFromHash } from './lib/route';

export function App() {
  const [project, setProject] = useState<Saved<Project>>();
  const handlers = useRef(new Set<(event: JobProgressEvent) => void>());
  const online = useJobEvents((event) => handlers.current.forEach((h) => h(event)));
  const subscribe = useCallback((handler: (event: JobProgressEvent) => void) => {
    handlers.current.add(handler);
    return () => { handlers.current.delete(handler); };
  }, []);

  // The hash is the source of truth: reload and Back/Forward land on the same project.
  useEffect(() => {
    const sync = () => {
      const id = projectIdFromHash(window.location.hash);
      if (!id) return setProject(undefined);
      api.project(id).then(setProject).catch(() => { window.location.hash = projectHash(); });
    };
    sync();
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);

  const open = (next?: Saved<Project>) => {
    if (next) setProject(next);
    window.location.hash = projectHash(next?.id);
  };

  return (
    <div className="app">
      <header className="row spread">
        <h1><button className="link" onClick={() => open(undefined)}>AI Interior Studio</button></h1>
        <span className={`status ${online ? 'on' : 'off'}`}>{online ? 'Đã kết nối backend' : 'Mất kết nối backend'}</span>
      </header>
      {project
        ? <ProjectView key={project.id} project={project} subscribe={subscribe} />
        : <ProjectsView onOpen={open} />}
    </div>
  );
}
