import { useEffect, useRef, useState } from 'react';
import type { JobProgressEvent } from '../api/types';
import { jobEventsUrl } from '../api/client';

/** Subscribe to /ws/jobs; reconnects with backoff. `online` drives the status dot in the header. */
export function useJobEvents(onEvent: (event: JobProgressEvent) => void, url: string = jobEventsUrl()) {
  const [online, setOnline] = useState(false);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let delay = 500;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(url);
      socket.onopen = () => {
        delay = 500;
        setOnline(true);
      };
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as JobProgressEvent;
          if (event.type === 'job.progress') handler.current(event);
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = () => {
        setOnline(false);
        if (closed) return;
        timer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 10_000);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, [url]);

  return online;
}
