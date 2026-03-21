// src/hooks/useWebSocket.js
import { useEffect, useRef, useState, useCallback } from "react";

export function useWebSocket(events = []) {
  const ws        = useRef(null);
  const [messages, setMessages] = useState([]);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url   = `${proto}://${window.location.host}/ws`;
    ws.current  = new WebSocket(url);

    ws.current.onopen = () => {
      setConnected(true);
      if (events.length) {
        ws.current.send(JSON.stringify({ type: "subscribe", events }));
      }
    };

    ws.current.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        setMessages(prev => [msg, ...prev].slice(0, 100)); // keep last 100
      } catch {}
    };

    ws.current.onclose = () => {
      setConnected(false);
      setTimeout(connect, 3000); // auto-reconnect
    };

    ws.current.onerror = () => ws.current?.close();
  }, []);

  useEffect(() => {
    connect();
    return () => ws.current?.close();
  }, [connect]);

  return { messages, connected };
}
