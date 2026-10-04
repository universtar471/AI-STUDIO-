// Thin fetch wrapper over the backend. Types come from types.ts (generated from OpenAPI).
import type {
  FinalizeRequest, HealthResponse, Project, ProjectCreate, ProviderInfo, ReferenceRole, RenderJob,
  RenderRequest, Scene, StylePack, StylePackCreate,
} from './types';

/** Response models always carry an id even though the schema marks it optional (it has a default). */
export type Saved<T> = T & { id: string };

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let code = String(response.status);
    let message = response.statusText;
    try {
      const body = await response.json();
      code = body.code ?? code;
      message = body.message ?? (typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body));
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(response.status, code, message);
  }
  return response.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

const form = (fields: Record<string, string | Blob | undefined>): RequestInit => {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) if (value !== undefined) data.append(key, value);
  return { method: 'POST', body: data };
};

export const api = {
  health: () => request<HealthResponse>('/health'),
  providers: () => request<ProviderInfo[]>('/providers'),

  projects: () => request<Saved<Project>[]>('/projects'),
  project: (id: string) => request<Saved<Project>>(`/projects/${id}`),
  createProject: (body: ProjectCreate) => request<Saved<Project>>('/projects', json(body)),
  scenes: (projectId: string) => request<Saved<Scene>[]>(`/projects/${projectId}/scenes`),
  importScene: (projectId: string, file: File, name: string) =>
    request<Saved<Scene>>(`/projects/${projectId}/scenes/import`, form({ file, name })),

  stylePacks: (projectId: string) => request<Saved<StylePack>[]>(`/style-packs?project_id=${encodeURIComponent(projectId)}`),
  stylePack: (id: string, version?: number) =>
    request<Saved<StylePack>>(`/style-packs/${id}${version ? `?version=${version}` : ''}`),
  stylePackVersions: (id: string) => request<number[]>(`/style-packs/${id}/versions`),
  createStylePack: (body: StylePackCreate) => request<Saved<StylePack>>('/style-packs', json(body)),
  addReference: (packId: string, file: File, role: ReferenceRole) =>
    request<Saved<StylePack>>(`/style-packs/${packId}/references`, form({ file, role })),

  jobs: (projectId: string) => request<Saved<RenderJob>[]>(`/render/jobs?project_id=${encodeURIComponent(projectId)}`),
  job: (id: string) => request<Saved<RenderJob>>(`/render/jobs/${id}`),
  createJob: (body: RenderRequest) => request<Saved<RenderJob>>('/render/jobs', json(body)),
  approve: (id: string) => request<Saved<RenderJob>>(`/render/jobs/${id}/approve`, { method: 'POST' }),
  retry: (id: string) => request<Saved<RenderJob>>(`/render/jobs/${id}/retry`, { method: 'POST' }),
  cancel: (id: string) => request<Saved<RenderJob>>(`/render/jobs/${id}/cancel`, { method: 'POST' }),
  finalize: (id: string, body: FinalizeRequest = {}) => request<Saved<RenderJob>>(`/render/jobs/${id}/finalize`, json(body)),
};

export const artifactUrl = (artifactId: string) => `/artifacts/${artifactId}/file`;

export function jobEventsUrl(location: Location = window.location): string {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${location.host}/ws/jobs`;
}
