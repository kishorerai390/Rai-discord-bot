const getStoredToken = (): string => {
  try {
    return localStorage.getItem('rai_session_token') || '';
  } catch {
    return '';
  }
};

export const api = {
  get: async (url: string) => {
    try {
      const token = getStoredToken();
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (token) {
        headers['X-Session-Token'] = token;
        headers['Authorization'] = `Bearer ${token}`;
      }
      const res = await fetch(url, { headers, credentials: 'include' });
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
      const token = getStoredToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      };
      if (token) {
        headers['X-Session-Token'] = token;
        headers['Authorization'] = `Bearer ${token}`;
      }
      const res = await fetch(url, {
        method: 'POST',
        headers,
        credentials: 'include',
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
