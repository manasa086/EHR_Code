/**
 * useSSE — subscribes to the backend SSE stream and dispatches named events
 * to handler callbacks.
 *
 * Usage:
 *   useSSE({
 *     case_created:        (data) => ...,
 *     case_updated:        (data) => ...,
 *     reconciliation_done: (data) => ...,
 *     data_quality_done:   (data) => ...,
 *     decision_recorded:   (data) => ...,
 *   });
 *
 * EventSource auto-reconnects on drop. Handlers are kept in a ref so the
 * effect never needs to re-run when parent state changes.
 */
import { useEffect, useRef } from "react";

const BASE    = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";
const API_KEY = import.meta.env.VITE_API_KEY  || "dev-secret-key";

const SSE_EVENTS = [
  "connected",
  "heartbeat",
  "reconciliation_done",
  "data_quality_done",
  "case_created",
  "case_updated",
  "decision_recorded",
];

export function useSSE(handlers) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    const url = `${BASE}/events?api_key=${encodeURIComponent(API_KEY)}`;
    const es = new EventSource(url);

    SSE_EVENTS.forEach((eventType) => {
      es.addEventListener(eventType, (e) => {
        const handler = handlersRef.current[eventType];
        if (!handler) return;
        try {
          handler(JSON.parse(e.data));
        } catch {
          handler({});
        }
      });
    });

    es.onerror = () => {
      // EventSource handles reconnection automatically — no action needed
    };

    return () => es.close();
  }, []); // runs once per mount — stable URL, handlers via ref
}
