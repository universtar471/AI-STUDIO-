import type { JobProgressEvent, JobState, RenderJob } from '../api/types';
import type { Saved } from '../api/client';

export const ACTIVE_STATES: JobState[] = ['DRAFT', 'QUEUED', 'RUNNING', 'FINALIZING'];

export const STATE_LABEL: Record<JobState, string> = {
  DRAFT: 'Nháp', QUEUED: 'Chờ chạy', RUNNING: 'Đang chạy', REVIEW: 'Chờ duyệt', RETRY: 'Đã làm lại',
  APPROVED: 'Đã duyệt', FINALIZING: 'Đang làm final', DONE: 'Xong', FAILED: 'Lỗi', CANCELLED: 'Đã hủy',
};

export const isActive = (state?: JobState) => !!state && ACTIVE_STATES.includes(state);

/** Merge a live event into the list. Unknown jobs are reported so the caller can refetch them. */
export function applyEvent(jobs: Saved<RenderJob>[], event: JobProgressEvent): { jobs: Saved<RenderJob>[]; unknown: boolean } {
  let found = false;
  const next = jobs.map((job) => {
    if (job.id !== event.job_id) return job;
    found = true;
    return { ...job, state: event.state, progress: event.progress, stage: event.stage ?? job.stage };
  });
  return { jobs: found ? next : jobs, unknown: !found };
}

/** Replace or insert a job, newest first. */
export function upsertJob(jobs: Saved<RenderJob>[], job: Saved<RenderJob>): Saved<RenderJob>[] {
  const rest = jobs.filter((j) => j.id !== job.id);
  return [job, ...rest].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''));
}

/** Which buttons make sense, following the job state machine in docs/contracts.md. */
export function actionsFor(job: RenderJob) {
  const state = job.state ?? 'DRAFT';
  return {
    approve: state === 'REVIEW',
    retry: state === 'REVIEW' || state === 'FAILED',
    cancel: state === 'DRAFT' || state === 'QUEUED' || state === 'RUNNING',
    finalize: state === 'APPROVED' && job.request.mode !== 'upscale',
  };
}

export const firstImage = (job: RenderJob) => job.result?.artifact_ids?.[0];
