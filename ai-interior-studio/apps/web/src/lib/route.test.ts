import { describe, expect, it } from 'vitest';
import { projectHash, projectIdFromHash } from './route';

describe('project routes', () => {
  const id = 'cd0855ce5b194cb2a80876c7bbd4eb0b';
  it('round-trips a project id through the hash', () => {
    expect(projectIdFromHash(projectHash(id))).toBe(id);
    expect(projectIdFromHash(`#/projects/${id.toUpperCase()}/`)).toBe(id);
  });
  it('ignores anything else', () => {
    for (const hash of ['', '#/', '#/projects/', '#/projects/xyz', `#/projects/${id}/extra`]) {
      expect(projectIdFromHash(hash)).toBeUndefined();
    }
    expect(projectHash()).toBe('#/');
  });
});
