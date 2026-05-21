"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Reads microphone input level via the Web Audio API.
 *
 * Returns a value in [0, 1] representing the current RMS loudness.
 * Falls back to 0 if mic access is denied or the browser doesn't support
 * the API (Retell holds the mic stream — requesting a second stream from
 * the same device works on Chrome/Firefox without a second permission prompt).
 */
export function useMicLevel(active: boolean): number {
  const [level, setLevel] = useState(0);

  const cleanup = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!active) {
      cleanup.current?.();
      cleanup.current = null;
      setLevel(0);
      return;
    }

    let cancelled = false;
    let rafId     = 0;

    navigator.mediaDevices
      .getUserMedia({ audio: true, video: false })
      .then(stream => {
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return; }

        const ctx      = new AudioContext();
        const analyser = ctx.createAnalyser();
        analyser.fftSize                = 512;
        analyser.smoothingTimeConstant  = 0.7;

        ctx.createMediaStreamSource(stream).connect(analyser);

        const data = new Uint8Array(analyser.frequencyBinCount);

        const tick = () => {
          if (cancelled) return;
          analyser.getByteFrequencyData(data);

          // RMS of the frequency bins → perceptual loudness, clamped to [0,1]
          const rms = Math.sqrt(
            data.reduce((acc, v) => acc + v * v, 0) / data.length,
          ) / 128;
          setLevel(Math.min(1, rms * 2.5));

          rafId = requestAnimationFrame(tick);
        };
        tick();

        cleanup.current = () => {
          cancelled = true;
          cancelAnimationFrame(rafId);
          ctx.close();
          stream.getTracks().forEach(t => t.stop());
        };
      })
      .catch(() => {
        // Mic access denied or already held — CSS animation is the fallback.
        setLevel(0);
      });

    return () => {
      cancelled = true;
      cleanup.current?.();
      cleanup.current = null;
      setLevel(0);
    };
  }, [active]);

  return level;
}
