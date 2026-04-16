import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { supabase } from "@/lib/supabaseClient";

const GenerationContext = createContext(null);

const DEFAULT_DIFFRHYTHM = {
  textPrompt: "",
  lyrics: "",
  padX: 0.5,
  padY: 0.5,
  audioUrl: null,
  vocalsUrl: null,
  status: "",
  loading: false,
  showAdvanced: false,
  errors: {},
  openutauEnabled: true,
  openutauExePath: "C:\\Users\\adolf\\OpenUtau\\OpenUtau.exe",
  openutauAutostart: true,
  openutauWaitSec: 20,
  openutauBpm: 120,
  openutauBaseTone: 72,
  openutauExportDir: "output\\openutau",
  vocalsGain: 0.45,
  instrumentalGain: 1.4,
  autotuneEnabled: true,
  autotuneStrength: 0.55,
  autotuneMaxShift: 1.25,
  autotuneScaleMode: "auto",
  reuseLastInstrumental: true,
  instrumentalPath: "",
};

const DEFAULT_MUSICGEN = {
  prompt: "",
  modelName: "facebook/musicgen-medium",
  durationSec: 30,
  temperature: 0.9,
  topK: 200,
  useKaggle: false,
  status: "",
  audioUrl: null,
  loading: false,
  errors: {},
  padX: 0.55,
  padY: 0.35,
};

function readStoredState(key, fallback) {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return fallback;
    return { ...fallback, ...JSON.parse(raw) };
  } catch {
    return fallback;
  }
}

export function GenerationProvider({ children }) {
  const [diffRhythm, setDiffRhythm] = useState(DEFAULT_DIFFRHYTHM);
  const [musicGen, setMusicGen] = useState(DEFAULT_MUSICGEN);
  const [userKey, setUserKey] = useState("guest");

  useEffect(() => {
    if (!supabase) {
      setUserKey("guest");
      return undefined;
    }
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (active) {
        setUserKey(data.session?.user?.id || "guest");
      }
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setUserKey(nextSession?.user?.id || "guest");
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    setDiffRhythm(readStoredState(`vx-diffrhythm:${userKey}`, DEFAULT_DIFFRHYTHM));
    setMusicGen(readStoredState(`vx-musicgen:${userKey}`, DEFAULT_MUSICGEN));
  }, [userKey]);

  useEffect(() => {
    const handleReset = () => {
      setDiffRhythm(DEFAULT_DIFFRHYTHM);
      setMusicGen(DEFAULT_MUSICGEN);
    };
    if (typeof window !== "undefined") {
      window.addEventListener("vx-reset-generation-store", handleReset);
    }
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("vx-reset-generation-store", handleReset);
      }
    };
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(`vx-diffrhythm:${userKey}`, JSON.stringify(diffRhythm));
    }
  }, [diffRhythm, userKey]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(`vx-musicgen:${userKey}`, JSON.stringify(musicGen));
    }
  }, [musicGen, userKey]);

  const value = useMemo(
    () => ({
      diffRhythm,
      setDiffRhythm,
      musicGen,
      setMusicGen,
    }),
    [diffRhythm, musicGen]
  );

  return <GenerationContext.Provider value={value}>{children}</GenerationContext.Provider>;
}

export function useGenerationStore() {
  const context = useContext(GenerationContext);
  if (!context) {
    throw new Error("useGenerationStore must be used within GenerationProvider");
  }
  return context;
}
