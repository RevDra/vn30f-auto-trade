import { useState } from "react";
import { postApi } from "../hooks/useApi";

interface Props {
  hasPosition: boolean;
  onOrderPlaced: () => void;
}

export function OrderPanel({ hasPosition, onOrderPlaced }: Props) {
  const [volume, setVolume] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<string | null>(null);

  const execute = async (action: string) => {
    setLoading(true);
    setError(null);
    try {
      if (action === "CLOSE") {
        await postApi("/close-position");
      } else {
        await postApi("/order", { action, volume });
      }
      onOrderPlaced();
      setConfirmAction(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Order failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-surface-card rounded-lg border border-gray-800 p-4">
      <h2 className="text-sm font-medium text-gray-400 mb-3">Order Panel</h2>

      {/* Volume input */}
      <div className="flex items-center gap-2 mb-4">
        <label className="text-xs text-gray-500">Volume</label>
        <button
          className="px-2 py-1 bg-gray-700 rounded hover:bg-gray-600 text-sm"
          onClick={() => setVolume(Math.max(1, volume - 1))}
        >−</button>
        <input
          type="number"
          min={1}
          max={500}
          value={volume}
          onChange={(e) => setVolume(Math.max(1, Math.min(500, Number(e.target.value) || 1)))}
          className="w-16 text-center bg-surface border border-gray-700 rounded px-2 py-1 text-sm"
        />
        <button
          className="px-2 py-1 bg-gray-700 rounded hover:bg-gray-600 text-sm"
          onClick={() => setVolume(Math.min(500, volume + 1))}
        >+</button>
      </div>

      {/* Action buttons */}
      {confirmAction ? (
        <div className="space-y-2">
          <p className="text-xs text-gray-400">
            Confirm {confirmAction} {confirmAction !== "CLOSE" ? `× ${volume}` : ""}?
          </p>
          <div className="flex gap-2">
            <button
              className="flex-1 py-2 bg-accent-blue rounded font-medium text-sm hover:opacity-90 disabled:opacity-50"
              onClick={() => execute(confirmAction)}
              disabled={loading}
            >
              {loading ? "..." : "Confirm"}
            </button>
            <button
              className="flex-1 py-2 bg-gray-700 rounded text-sm hover:bg-gray-600"
              onClick={() => setConfirmAction(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button
            className="flex-1 py-2.5 bg-accent-green/90 hover:bg-accent-green rounded font-medium text-sm text-white"
            onClick={() => setConfirmAction("LONG")}
          >
            LONG
          </button>
          <button
            className="flex-1 py-2.5 bg-accent-red/90 hover:bg-accent-red rounded font-medium text-sm text-white"
            onClick={() => setConfirmAction("SHORT")}
          >
            SHORT
          </button>
          <button
            className="flex-1 py-2.5 bg-gray-600 hover:bg-gray-500 rounded font-medium text-sm disabled:opacity-30"
            onClick={() => setConfirmAction("CLOSE")}
            disabled={!hasPosition}
          >
            CLOSE
          </button>
        </div>
      )}

      {error && <div className="mt-2 text-xs text-accent-red">{error}</div>}
    </div>
  );
}
