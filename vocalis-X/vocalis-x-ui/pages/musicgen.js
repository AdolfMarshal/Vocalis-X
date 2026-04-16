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

export default function MusicGenPage() {
  const app = useStudioApp();
  const { musicGen, setMusicGen } = useGenerationStore();
  const emotion = deriveEmotion(musicGen.padX, musicGen.padY);

  function updateField(field, value) {
    setMusicGen((current) => ({ ...current, [field]: value }));
  }

  function handlePadClick(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    setMusicGen((current) => ({
      ...current,
      padX: Math.min(Math.max(x, 0), 1),
      padY: Math.min(Math.max(1 - y, 0), 1),
    }));
  }

  function validate() {
    const nextErrors = {};
    if (musicGen.prompt.trim().length < 8) nextErrors.prompt = "Describe the instrumental in at least 8 characters.";
    if (musicGen.durationSec < 5 || musicGen.durationSec > 180) nextErrors.durationSec = "Duration must be between 5 and 180 seconds.";
    if (musicGen.temperature < 0.1 || musicGen.temperature > 2) nextErrors.temperature = "Temperature must be between 0.1 and 2.";
    if (musicGen.topK < 1 || musicGen.topK > 500) nextErrors.topK = "Top-k must be between 1 and 500.";
    setMusicGen((current) => ({ ...current, errors: nextErrors }));
    return Object.keys(nextErrors).length === 0;
  }

  async function generateMusic() {
    if (!validate()) {
      setMusicGen((current) => ({ ...current, status: "Fix the highlighted fields before generating." }));
      return;
    }
    setMusicGen((current) => ({ ...current, loading: true, status: "Generating instrumental..." }));
    try {
      const response = await fetch("http://localhost:8000/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          song_name: "MusicGen Instrumental",
          creative_prompt: musicGen.prompt,
          tempo: 0.5,
          energy: musicGen.padX,
          darkness: musicGen.padY,
          emotion,
          instrumentation: [],
          generation_config: {
            model_name: musicGen.modelName,
            duration_sec: Number(musicGen.durationSec),
            temperature: Number(musicGen.temperature),
            top_k: Number(musicGen.topK),
            musicgen_cloud_enabled: musicGen.useKaggle,
          },
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      if (!data.audio_url) throw new Error("Missing audio_url in response.");
      const resolvedAudioUrl = `http://localhost:8000${data.audio_url}`;
      setMusicGen((current) => ({
        ...current,
        audioUrl: resolvedAudioUrl,
        status: data.warning || "Instrumental ready",
        loading: false,
      }));
      await app.saveGeneratedSongRecord({
        id: `generated-${Date.now()}`,
        title: (musicGen.prompt.trim().split(/\s+/).slice(0, 4).join(" ") || "Instrumental").slice(0, 42),
        status: "Ready",
        visibility: "Private",
        prompt: musicGen.prompt,
        lyrics: null,
        createdAt: "Just now",
        audioUrl: resolvedAudioUrl,
        vocalsUrl: null,
        instrumentalUrl: resolvedAudioUrl,
      });
    } catch (error) {
      setMusicGen((current) => ({
        ...current,
        status: error.message || "MusicGen generation failed.",
        loading: false,
      }));
    }
  }

  const composer = (
    <section className={styles.composer}>
      <div className={styles.composerHeader}>
        <div>
          <div className={styles.composerEyebrow}>MusicGen</div>
          <h2>Instrumental generation only</h2>
        </div>
      </div>
      <textarea className={styles.promptInput} rows={5} value={musicGen.prompt} onChange={(event) => updateField("prompt", event.target.value)} placeholder="Describe the beat, instrumentation, arrangement, and production style. This route generates music only." />
      {musicGen.errors.prompt ? <div className={styles.validationText}>{musicGen.errors.prompt}</div> : null}
      <div className={styles.panelGrid}>
        <div className={styles.panelBlock}>
          <h3>Model</h3>
          <label className={styles.field}>
            <span>MusicGen Model</span>
            <select value={musicGen.modelName} onChange={(event) => updateField("modelName", event.target.value)}>
              <option value="facebook/musicgen-small">musicgen-small</option>
              <option value="facebook/musicgen-medium">musicgen-medium</option>
            </select>
          </label>
          <label className={styles.toggleRow}><input type="checkbox" checked={musicGen.useKaggle} onChange={(event) => updateField("useKaggle", event.target.checked)} />Use Kaggle cloud worker</label>
        </div>
        <div className={styles.panelBlock}>
          <h3>Sampling</h3>
          <div className={styles.inlineFields}>
            <label className={styles.field}><span>Duration</span><input type="number" value={musicGen.durationSec} onChange={(event) => updateField("durationSec", Number(event.target.value))} /></label>
            <label className={styles.field}><span>Temperature</span><input type="number" step="0.1" value={musicGen.temperature} onChange={(event) => updateField("temperature", Number(event.target.value))} /></label>
            <label className={styles.field}><span>Top-k</span><input type="number" value={musicGen.topK} onChange={(event) => updateField("topK", Number(event.target.value))} /></label>
          </div>
          {musicGen.errors.durationSec ? <div className={styles.validationText}>{musicGen.errors.durationSec}</div> : null}
          {musicGen.errors.temperature ? <div className={styles.validationText}>{musicGen.errors.temperature}</div> : null}
          {musicGen.errors.topK ? <div className={styles.validationText}>{musicGen.errors.topK}</div> : null}
        </div>
        <div className={styles.panelBlock}>
          <h3>Semantic Pad</h3>
          <div className={styles.padCard}>
            <div className={styles.pad} onClick={handlePadClick}>
              <div className={styles.padDot} style={{ left: `${musicGen.padX * 100}%`, top: `${(1 - musicGen.padY) * 100}%` }} />
            </div>
            <div className={styles.padValues}>
              <span>Energy {musicGen.padX.toFixed(2)}</span>
              <span>Darkness {musicGen.padY.toFixed(2)}</span>
              <span>Joy {emotion.joy}</span>
              <span>Sadness {emotion.sadness}</span>
              <span>Tension {emotion.tension}</span>
            </div>
          </div>
        </div>
      </div>
      <div className={styles.composerActions}>
        <div className={styles.statusPill}>{musicGen.status || "Ready for instrumental generation"}</div>
        <button type="button" className={styles.createButton} onClick={generateMusic} disabled={musicGen.loading}>{musicGen.loading ? "Generating..." : "Generate Instrumental"}</button>
      </div>
    </section>
  );

  const results = (
    <section className={styles.resultsSection}>
      <div className={styles.resultsHeader}><h2>Music-Only Output</h2><span>{musicGen.loading ? "MusicGen running" : "Instrumental route only"}</span></div>
      <div className={styles.resultsGrid}>
        <article className={styles.resultCard}>
          <div className={styles.resultLabel}>Generated Music</div>
          {musicGen.audioUrl ? (
            <>
              <audio controls src={musicGen.audioUrl} className={styles.audio} />
              <a className={styles.audioLink} href={musicGen.audioUrl} target="_blank" rel="noreferrer">Open generated music</a>
            </>
          ) : (
            <p>Your music-only output will appear here.</p>
          )}
        </article>
        <article className={styles.resultCard}>
          <div className={styles.resultLabel}>Persistence</div>
          <p>MusicGen prompt, generation state, and finished output now live in a shared store so route changes do not wipe the in-flight job or its result.</p>
        </article>
      </div>
    </section>
  );

  return (
    <StudioShell
      app={app}
      activeHref="/musicgen"
      kicker="Dedicated instrumental route"
      title="Generate music only with MusicGen."
      description="This page isolates the text-to-music workflow so you can generate instrumentals without DiffRhythm, lyrics, or OpenUtau settings getting in the way."
      logos={["MusicGen", "Audiocraft", "Text to Music", "Vocalis-X"]}
      composer={composer}
      results={results}
      pageNote="MusicGen state now persists across route changes, and the backend uses user-provided duration instead of the old sample-based timing."
    />
  );
}
