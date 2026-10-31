export const api = {
  get: async (url: string) => {
    try {
      const res = await fetch(url, { headers: { Accept: 'application/json' } });
      const raw = await res.json().catch(() => ({}));
      const data =
        raw && typeof raw === 'object' && raw.data && typeof raw.data === 'object' && !Array.isArray(raw.data)
          ? { ...raw.data, ...raw }
          : raw;
      return { data, status: res.status, ok: res.ok };
    } catch (e: any) {
      return { data: { error: e?.message || 'Network error' }, status: 500, ok: false };
    }
  },
  post: async (url: string, body?: any) => {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(body || {}),
      });
      const raw = await res.json().catch(() => ({}));
      const data =
        raw && typeof raw === 'object' && raw.data && typeof raw.data === 'object' && !Array.isArray(raw.data)
          ? { ...raw.data, ...raw }
          : raw;
      return { data, status: res.status, ok: res.ok };
    } catch (e: any) {
      return { data: { error: e?.message || 'Network error' }, status: 500, ok: false };
    }
  },
};
