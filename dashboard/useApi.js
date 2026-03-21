// src/hooks/useApi.js
import { useState, useEffect, useCallback } from "react";

export function useApi(fetcher, deps = [], pollMs = 0) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const fetch_ = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, deps);

  useEffect(() => {
    fetch_();
    if (!pollMs) return;
    const id = setInterval(fetch_, pollMs);
    return () => clearInterval(id);
  }, [fetch_, pollMs]);

  return { data, loading, error, refetch: fetch_ };
}
