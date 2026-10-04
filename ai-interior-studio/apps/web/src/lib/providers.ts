import type { ProviderInfo, RenderMode } from '../api/types';

export interface ProviderNeeds {
  mode: RenderMode;
  ratio: string;
  imageSize?: string;
  referenceCount: number;
  seed?: number | null;
}

/** Providers that can serve this request. Unsupported ones are hidden, unhealthy ones stay visible but marked. */
export function eligibleProviders(providers: ProviderInfo[], needs: ProviderNeeds): ProviderInfo[] {
  return providers.filter(({ capabilities: c }) => {
    if (!c.supported_modes.includes(needs.mode)) return false;
    if (needs.referenceCount > (c.max_reference_images ?? 0)) return false;
    if (needs.referenceCount > 1 && !c.supports_multi_reference) return false;
    if (c.supported_ratios?.length && !c.supported_ratios.includes(needs.ratio)) return false;
    if (needs.imageSize && c.supported_sizes?.length && !c.supported_sizes.includes(needs.imageSize)) return false;
    if (needs.seed != null && !c.supports_seed) return false;
    return true;
  });
}

/** Union of sizes/ratios offered by the given providers, in first-seen order. */
export function offered(providers: ProviderInfo[], key: 'supported_sizes' | 'supported_ratios'): string[] {
  const seen: string[] = [];
  for (const p of providers) for (const value of p.capabilities[key] ?? []) if (!seen.includes(value)) seen.push(value);
  return seen;
}

export const isHealthy = (p: ProviderInfo) => p.health.status === 'ok';

export const costsMoney = (p: ProviderInfo) => Boolean(p.capabilities.has_usage_cost);
