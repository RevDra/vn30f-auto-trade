import { useState, useEffect, useRef, useCallback } from "react";
import type { WSMessage } from "../types/api";

type WSStatus = "connecting" | "connected" | "disconnected";

export function useWebSocket(url: string) {
  const [status, setStatus] = useState<WSStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);

  const connect = useCallback(() => {
    try {
      setStatus("connecting");
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        // Send ping every 30s to keep alive
        const ping = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        }, 30000);
        ws.addEventListener("close", () => clearInterval(ping));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WSMessage;
          if ("type" in data && (data as Record<string, unknown>).type === "pong") return;
          setLastMessage(data);
        } catch { /* ignore non-JSON */ }
      };

      ws.onclose = () => {
        setStatus("disconnected");
        wsRef.current = null;
        // Auto-reconnect after 3s
        reconnectTimer.current = window.setTimeout(connect, 3000);
      };

      ws.onerror = () => ws.close();
    } catch {
      setStatus("disconnected");
    }
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { status, lastMessage };
}
