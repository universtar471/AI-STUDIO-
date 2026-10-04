import { useCallback, useRef, useState } from 'react';
import type { Saved } from './api/client';
import type { JobProgressEvent, Project } from './api/types';
import { ProjectView } from './components/ProjectView';
import { ProjectsView } from './components/ProjectsView';
import { useJobEvents } from './hooks/useJobEvents';

export function App() {
  const [project, setProject] = useState<Saved<Project>>();
  const handlers = useRef(new Set<(event: JobProgressEvent) => void>());
  const online = useJobEvents((event) => handlers.current.forEach((h) => h(event)));
  const subscribe = useCallback((handler: (event: JobProgressEvent) => void) => {
    handlers.current.add(handler);
    return () => { handlers.current.delete(handler); };
  }, []);

  return (
    <div className="app">
      <header className="row spread">
        <h1><button className="link" onClick={() => setProject(undefined)}>AI Interior Studio</button></h1>
        <span className={`status ${online ? 'on' : 'off'}`}>{online ? 'Đã kết nối backend' : 'Mất kết nối backend'}</span>
      </header>
      {project ? <ProjectView project={project} subscribe={subscribe} /> : <ProjectsView onOpen={setProject} />}
    </div>
  );
}
