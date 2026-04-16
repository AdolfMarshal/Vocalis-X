import { useMemo } from "react";
import StudioShell from "@/components/StudioShell";
import { useStudioApp } from "@/lib/useStudioApp";
import { useGenerationStore } from "@/lib/generationStore";
import styles from "@/styles/Home.module.css";

function deriveEmotion(nextPadX, nextPadY) {
  return {
    joy: Number((nextPadX * nextPadY).toFixed(2)),
    sadness: Number(((1 - nextPadX) * (1 - nextPadY)).toFixed(2)),
    tension: Number((nextPadX * (1 - nextPadY)).toFixed(2)),
  };
}

export default function DiffRhythmPage() {
  const app = useStudioApp();
  const { diffRhythm, setDiffRhythm } = useGenerationStore();
  const emotion = useMemo(() => deriveEmotion(diffRhythm.padX, diffRhythm.padY), [diffRhythm.padX, diffRhythm.padY]);

  function updateField(field, value) {
    setDiffRhythm((current) => ({ ...current, [field]: value }));
  }

  function handlePadClick(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    setDiffRhythm((current) => ({
      ...current,
      padX: Math.min(Math.max(x, 0), 1),
      padY: Math.min(Math.max(1 - y, 0), 1),
    }));
  }

  function validate() {
    const nextErrors = {};
    if (diffRhythm.textPrompt.trim().length < 8) nextErrors.textPrompt = "Describe the track in at least 8 characters.";
    if (diffRhythm.lyrics.trim().length < 12) nextErrors.lyrics = "Paste enough lyrics to shape the vocal pipeline.";
    if (diffRhythm.openutauWaitSec < 5 || diffRhythm.openutauWaitSec > 900) nextErrors.openutauWaitSec = "OpenUtau wait must be between 5 and 900 seconds.";
    if (diffRhythm.openutauBpm < 40 || diffRhythm.openutauBpm > 240) nextErrors.openutauBpm = "BPM must be between 40 and 240.";
    if (diffRhythm.vocalsGain <= 0 || diffRhythm.vocalsGain > 4) nextErrors.vocalsGain = "Vocals gain must be between 0.01 and 4.";
    if (diffRhythm.instrumentalGain <= 0 || diffRhythm.instrumentalGain > 4) nextErrors.instrumentalGain = "Instrumental gain must be between 0.01 and 4.";
    if (diffRhythm.autotuneStrength < 0 || diffRhythm.autotuneStrength > 1) nextErrors.autotuneStrength = "Autotune strength must be between 0 and 1.";
    if (diffRhythm.autotuneMaxShift <= 0 || diffRhythm.autotuneMaxShift > 6) nextErrors.autotuneMaxShift = "Max pitch shift must be between 0.1 and 6.";
    setDiffRhythm((current) => ({ ...current, errors: nextErrors }));
    return Object.keys(nextErrors).length === 0;
  }

  async function generateMusic() {
    if (!validate()) {
      setDiffRhythm((current) => ({ ...current, status: "Fix the highlighted fields before generating." }));
      return;
    }
    setDiffRhythm((current) => ({ ...current, loading: true, status: "Generating your song..." }));
    try {
      const response = await fetch("http://localhost:8000/generate_with_vocals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          creative_prompt: diffRhythm.textPrompt,
          prompt_config: { genre_lock: true },
          tempo: 0.5,
          energy: diffRhythm.padX,
          darkness: diffRhythm.padY,
          emotion,
          instrumentation: [],
          lyrics: diffRhythm.lyrics,
          instrumental_path: diffRhythm.instrumentalPath || undefined,
          reuse_last_instrumental: diffRhythm.reuseLastInstrumental,
          generation_config: { model_name: "facebook/musicgen-medium" },
          singing_config: {
            enabled: diffRhythm.openutauEnabled,
            pipeline_mode: "diffrhythm",
            backend: "openutau",
            language: "en",
            openutau_exe_path: diffRhythm.openutauExePath || undefined,
            openutau_autostart: diffRhythm.openutauAutostart,
            openutau_wait_sec: Number(diffRhythm.openutauWaitSec) || 20,
            openutau_bpm: Number(diffRhythm.openutauBpm) || 120,
            openutau_base_tone: Number(diffRhythm.openutauBaseTone) || 72,
            openutau_export_dir: diffRhythm.openutauExportDir || "output",
            vocals_gain: Number(diffRhythm.vocalsGain) || 0.45,
            instrumental_gain: Number(diffRhythm.instrumentalGain) || 1.4,
            autotune_enabled: diffRhythm.autotuneEnabled,
            autotune_strength: Number(diffRhythm.autotuneStrength) || 0.55,
            autotune_max_shift: Number(diffRhythm.autotuneMaxShift) || 1.25,
            autotune_scale_mode: diffRhythm.autotuneScaleMode || "auto",
          },
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      if (!data.audio_url) throw new Error("Missing audio_url in response.");
      const resolvedAudioUrl = `http://localhost:8000${data.audio_url}`;
      const resolvedVocalsUrl = data.vocals_url ? `http://localhost:8000${data.vocals_url}` : null;
      setDiffRhythm((current) => ({
        ...current,
        audioUrl: resolvedAudioUrl,
        vocalsUrl: resolvedVocalsUrl,
        status: data.warning || "Song ready",
        loading: false,
      }));
      await app.saveGeneratedSongRecord({
        id: `generated-${Date.now()}`,
        title: (diffRhythm.textPrompt.trim().split(/\s+/).slice(0, 4).join(" ") || "Untitled Song").slice(0, 42),
        status: data.warning ? "Fallback Output" : "Ready",
        visibility: "Private",
        prompt: diffRhythm.textPrompt,
        lyrics: diffRhythm.lyrics,
        createdAt: "Just now",
        audioUrl: resolvedAudioUrl,
        vocalsUrl: resolvedVocalsUrl,
        instrumentalUrl: data.instrumental_url ? `http://localhost:8000${data.instrumental_url}` : null,
      });
    } catch (error) {
      setDiffRhythm((current) => ({ ...current, status: error.message || "Generation failed.", loading: false }));
    }
  }

  const composer = (
    <section className={styles.composer}>
      <div className={styles.composerHeader}>
        <div>
          <div className={styles.composerEyebrow}>DiffRhythm</div>
          <h2>Prompt to full vocal track</h2>
        </div>
        <button type="button" className={styles.advancedToggle} onClick={() => updateField("showAdvanced", !diffRhythm.showAdvanced)}>
          {diffRhythm.showAdvanced ? "Hide Advanced" : "Advanced"}
        </button>
      </div>
      <textarea className={styles.promptInput} rows={4} value={diffRhythm.textPrompt} onChange={(event) => updateField("textPrompt", event.target.value)} placeholder="Describe the sound, production, references, and vocal feeling..." />
      {diffRhythm.errors.textPrompt ? <div className={styles.validationText}>{diffRhythm.errors.textPrompt}</div> : null}
      <textarea className={styles.lyricsInput} rows={6} value={diffRhythm.lyrics} onChange={(event) => updateField("lyrics", event.target.value)} placeholder="Paste your lyrics here. Sections like [Verse] and [Chorus] are fine." />
      {diffRhythm.errors.lyrics ? <div className={styles.validationText}>{diffRhythm.errors.lyrics}</div> : null}
      <div className={styles.composerActions}>
        <div className={styles.statusPill}>{diffRhythm.status || "Ready when you are"}</div>
        <button type="button" className={styles.createButton} onClick={generateMusic} disabled={diffRhythm.loading}>{diffRhythm.loading ? "Generating..." : "Create Song"}</button>
      </div>
      {diffRhythm.showAdvanced ? (
        <div className={styles.advancedPanel}>
          <div className={styles.panelGrid}>
            <div className={styles.panelBlock}>
              <h3>Vocal Engine</h3>
              <label className={styles.toggleRow}><input type="checkbox" checked={diffRhythm.openutauEnabled} onChange={(event) => updateField("openutauEnabled", event.target.checked)} />Enable OpenUtau vocals</label>
              <label className={styles.field}><span>OpenUtau EXE</span><input value={diffRhythm.openutauExePath} onChange={(event) => updateField("openutauExePath", event.target.value)} /></label>
              <div className={styles.inlineFields}>
                <label className={styles.field}><span>Wait Sec</span><input type="number" value={diffRhythm.openutauWaitSec} onChange={(event) => updateField("openutauWaitSec", Number(event.target.value))} /></label>
                <label className={styles.field}><span>BPM</span><input type="number" value={diffRhythm.openutauBpm} onChange={(event) => updateField("openutauBpm", Number(event.target.value))} /></label>
              </div>
              {diffRhythm.errors.openutauWaitSec ? <div className={styles.validationText}>{diffRhythm.errors.openutauWaitSec}</div> : null}
              {diffRhythm.errors.openutauBpm ? <div className={styles.validationText}>{diffRhythm.errors.openutauBpm}</div> : null}
            </div>
            <div className={styles.panelBlock}>
              <h3>Mix + Routing</h3>
              <label className={styles.toggleRow}><input type="checkbox" checked={diffRhythm.openutauAutostart} onChange={(event) => updateField("openutauAutostart", event.target.checked)} />Autostart OpenUtau</label>
              <label className={styles.toggleRow}><input type="checkbox" checked={diffRhythm.autotuneEnabled} onChange={(event) => updateField("autotuneEnabled", event.target.checked)} />Post-export autotune</label>
              <label className={styles.toggleRow}><input type="checkbox" checked={diffRhythm.reuseLastInstrumental} onChange={(event) => updateField("reuseLastInstrumental", event.target.checked)} />Reuse last instrumental</label>
              <label className={styles.field}><span>Export Dir</span><input value={diffRhythm.openutauExportDir} onChange={(event) => updateField("openutauExportDir", event.target.value)} /></label>
            </div>
            <div className={styles.panelBlock}>
              <h3>Controls</h3>
              <div className={styles.inlineFields}>
                <label className={styles.field}><span>Vocals Gain</span><input type="number" step="0.05" value={diffRhythm.vocalsGain} onChange={(event) => updateField("vocalsGain", Number(event.target.value))} /></label>
                <label className={styles.field}><span>Inst Gain</span><input type="number" step="0.05" value={diffRhythm.instrumentalGain} onChange={(event) => updateField("instrumentalGain", Number(event.target.value))} /></label>
              </div>
              <div className={styles.inlineFields}>
                <label className={styles.field}><span>Autotune Strength</span><input type="number" step="0.05" value={diffRhythm.autotuneStrength} onChange={(event) => updateField("autotuneStrength", Number(event.target.value))} /></label>
                <label className={styles.field}><span>Max Shift</span><input type="number" step="0.05" value={diffRhythm.autotuneMaxShift} onChange={(event) => updateField("autotuneMaxShift", Number(event.target.value))} /></label>
              </div>
              <div className={styles.inlineFields}>
                <label className={styles.field}><span>Scale Mode</span><select value={diffRhythm.autotuneScaleMode} onChange={(event) => updateField("autotuneScaleMode", event.target.value)}><option value="auto">auto</option><option value="major">major</option><option value="minor">minor</option><option value="off">off</option></select></label>
                <label className={styles.field}><span>Instrumental Path</span><input value={diffRhythm.instrumentalPath} onChange={(event) => updateField("instrumentalPath", event.target.value)} /></label>
              </div>
              {diffRhythm.errors.vocalsGain ? <div className={styles.validationText}>{diffRhythm.errors.vocalsGain}</div> : null}
              {diffRhythm.errors.instrumentalGain ? <div className={styles.validationText}>{diffRhythm.errors.instrumentalGain}</div> : null}
              {diffRhythm.errors.autotuneStrength ? <div className={styles.validationText}>{diffRhythm.errors.autotuneStrength}</div> : null}
              {diffRhythm.errors.autotuneMaxShift ? <div className={styles.validationText}>{diffRhythm.errors.autotuneMaxShift}</div> : null}
            </div>
            <div className={styles.panelBlock}>
              <h3>Semantic Pad</h3>
              <div className={styles.padCard}>
                <div className={styles.pad} onClick={handlePadClick}><div className={styles.padDot} style={{ left: `${diffRhythm.padX * 100}%`, top: `${(1 - diffRhythm.padY) * 100}%` }} /></div>
                <div className={styles.padValues}><span>Energy {diffRhythm.padX.toFixed(2)}</span><span>Darkness {diffRhythm.padY.toFixed(2)}</span><span>Joy {emotion.joy}</span><span>Sadness {emotion.sadness}</span><span>Tension {emotion.tension}</span></div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );

  const results = (
    <section className={styles.resultsSection}>
      <div className={styles.resultsHeader}><h2>Latest Output</h2><span>{diffRhythm.loading ? "Pipeline running" : "Waiting for render"}</span></div>
      <div className={styles.resultsGrid}>
        <article className={styles.resultCard}>
          <div className={styles.resultLabel}>Final Song</div>
          {diffRhythm.audioUrl ? <><audio controls src={diffRhythm.audioUrl} className={styles.audio} /><a className={styles.audioLink} href={diffRhythm.audioUrl} target="_blank" rel="noreferrer">Open rendered audio</a></> : <p>Your final mix will appear here after generation.</p>}
        </article>
        <article className={styles.resultCard}>
          <div className={styles.resultLabel}>Vocals</div>
          {diffRhythm.vocalsUrl ? <audio controls src={diffRhythm.vocalsUrl} className={styles.audio} /> : <p>No isolated vocal render yet.</p>}
        </article>
      </div>
    </section>
  );

  return (
    <StudioShell
      app={app}
      activeHref="/"
      kicker="One prompt. One lyric sheet. One finished song."
      title="Build the full DiffRhythm track in one pass."
      description="This route keeps the complete song pipeline: prompt, lyrics, DiffRhythm generation, optional OpenUtau refinement, and final mix delivery."
      logos={["DiffRhythm", "Demucs", "OpenUtau", "Vocalis-X"]}
      composer={composer}
      results={results}
      pageNote="DiffRhythm prompt, generation state, and finished outputs now persist across route changes while the backend keeps processing."
    />
  );
}
