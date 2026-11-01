import { useCallback, useRef, useState } from 'react';

/**
 * Hook for managing auto-dismissing toast notifications.
 */
export function useToast(autoDismissMs = 3800) {
  const [toast, setToast] = useState(null); // { message, type: 'success' | 'error' | 'info' }
  const timerRef = useRef(null);

  const showToast = useCallback((message, type = 'success') => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    setToast({ message, type });
    timerRef.current = setTimeout(() => {
      setToast(null);
    }, autoDismissMs);
  }, [autoDismissMs]);

  const dismissToast = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    setToast(null);
  }, []);

  return { toast, showToast, dismissToast };
}

