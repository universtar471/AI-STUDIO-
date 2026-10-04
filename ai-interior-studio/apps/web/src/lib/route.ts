/** Project addresses live in the hash (#/projects/<id>) so a reload or the Back button keeps the user in place. */
export function projectIdFromHash(hash: string): string | undefined {
  const match = /^#\/projects\/([0-9a-f]{32})\/?$/i.exec(hash);
  return match ? match[1].toLowerCase() : undefined;
}

export const projectHash = (id?: string) => (id ? `#/projects/${id}` : '#/');
