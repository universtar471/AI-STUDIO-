import { useCallback, useEffect, useState } from 'react';
import { api, type Saved } from '../api/client';
import type { JobProgressEvent, Project, ProviderInfo, RenderJob, Scene, StylePack } from '../api/types';
import { applyEvent, upsertJob } from '../lib/jobs';
import { GeneratePanel } from './GeneratePanel';
import { HistoryPanel } from './HistoryPanel';
import { JobDetail } from './JobDetail';
import { ScenesPanel } from './ScenesPanel';
import { StylePackPanel } from './StylePackPanel';

type Tab = 'scenes' | 'style' | 'generate' | 'history';
const TABS: [Tab, string][] = [['scenes', 'Cảnh'], ['style', 'Style Pack'], ['generate', 'Tạo ảnh'], ['history', 'Lịch sử']];

interface Props {
  project: Saved<Project>;
  subscribe: (handler: (event: JobProgressEvent) => void) => () => void;
}

export function ProjectView({ project, subscribe }: Props) {
  const [tab, setTab] = useState<Tab>('scenes');
  const [scenes, setScenes] = useState<Saved<Scene>[]>([]);
  const [packs, setPacks] = useState<Saved<StylePack>[]>([]);
  const [jobs, setJobs] = useState<Saved<RenderJob>[]>([]);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [openId, setOpenId] = useState<string>();
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.scenes(project.id), api.stylePacks(project.id), api.jobs(project.id), api.providers()])
      .then(([s, p, j, pr]) => {
        setScenes(s);
        setPacks(p);
        setJobs(j.reduce(upsertJob, [] as Saved<RenderJob>[]));
        setProviders(pr);
        if (s.length) setTab(j.length ? 'history' : 'generate');
      })
      .catch((e) => setError(e.message));
  }, [project.id]);

  const refetch = useCallback((id: string) => {
    api.job(id).then((job) => {
      if (job.project_id === project.id) setJobs((list) => upsertJob(list, job));
    }).catch(() => undefined);
  }, [project.id]);

  useEffect(() => subscribe((event) => {
    setJobs((list) => {
      const { jobs: next, unknown } = applyEvent(list, event);
      // Terminal states carry results/errors the event does not include: fetch the full job.
      if (unknown || ['REVIEW', 'FAILED', 'APPROVED', 'CANCELLED', 'DONE'].includes(event.state)) refetch(event.job_id);
      return next;
    });
  }), [subscribe, refetch]);

  const openJob = jobs.find((j) => j.id === openId);

  return (
    <section>
      <h2>{project.name}</h2>
      <nav className="tabs">
        {TABS.map(([key, label]) => (
          <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>
        ))}
      </nav>
      {error && <p className="error">{error}</p>}
      {tab === 'scenes' && <ScenesPanel projectId={project.id} scenes={scenes} onAdded={(s) => setScenes((l) => [...l, s])} />}
      {tab === 'style' && (
        <StylePackPanel projectId={project.id} packs={packs}
          onChanged={(p) => setPacks((l) => [p, ...l.filter((x) => x.id !== p.id)])} />
      )}
      {tab === 'generate' && (
        <GeneratePanel projectId={project.id} scenes={scenes} packs={packs} providers={providers}
          onCreated={(created) => { setJobs((l) => created.reduce(upsertJob, l)); setTab('history'); }} />
      )}
      {tab === 'history' && <HistoryPanel jobs={jobs} scenes={scenes} onOpen={(j) => setOpenId(j.id)} />}
      {openJob && (
        <JobDetail key={openJob.id} job={openJob} jobs={jobs} scenes={scenes} onClose={() => setOpenId(undefined)} onOpen={setOpenId}
          onChanged={(changed) => setJobs((l) => changed.reduce(upsertJob, l))} />
      )}
    </section>
  );
}
