import { useState, useCallback, useRef, useEffect } from "react";

/**
 * Text-to-Speech hook using Web Speech API (browser native, free).
 * Falls back gracefully if not supported.
 */
export function useTTS() {
  const [speaking, setSpeaking] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(() => localStorage.getItem("capos_autospeak") === "true");
  const [voiceIdx, setVoiceIdx] = useState(0);
  const [rate, setRate] = useState(1.0);
  const utteranceRef = useRef(null);

  const supported = typeof window !== "undefined" && "speechSynthesis" in window;

  const getVoices = useCallback(() => {
    if (!supported) return [];
    return speechSynthesis.getVoices();
  }, [supported]);

  // Preload voices (some browsers load asynchronously)
  useEffect(() => {
    if (!supported) return;
    speechSynthesis.getVoices();
    speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices();
  }, [supported]);

  const speak = useCallback((text) => {
    if (!supported || !text?.trim()) return;
    // Cancel any current speech
    speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    const voices = speechSynthesis.getVoices();

    // Try to find a good Spanish voice, or use default
    if (voices.length > 0) {
      const preferred = voices.find(v => v.lang.startsWith("es")) || voices[voiceIdx] || voices[0];
      utterance.voice = preferred;
    }

    utterance.rate = rate;
    utterance.pitch = 1.0;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);

    utteranceRef.current = utterance;
    speechSynthesis.speak(utterance);
  }, [supported, voiceIdx, rate]);

  const stop = useCallback(() => {
    if (!supported) return;
    speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const toggleAutoSpeak = useCallback(() => {
    setAutoSpeak(prev => {
      const next = !prev;
      localStorage.setItem("capos_autospeak", String(next));
      return next;
    });
  }, []);

  return {
    supported,
    speaking,
    autoSpeak,
    speak,
    stop,
    toggleAutoSpeak,
    setRate,
    rate,
    getVoices,
  };
}
