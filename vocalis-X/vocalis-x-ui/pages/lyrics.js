import { useState } from "react";
import StudioShell from "@/components/StudioShell";
import { useStudioApp } from "@/lib/useStudioApp";
import styles from "@/styles/Home.module.css";

const SONG_TYPES = ["Pop", "Rock", "Ballad", "R&B", "Rap", "Worship", "EDM", "Folk", "Cinematic"];
const TIME_SIGNATURES = ["3/4", "4/4", "6/8"];

export default function LyricsPage() {
  const app = useStudioApp();
  const [songType, setSongType] = useState("Pop");
  const [timeSignature, setTimeSignature] = useState("4/4");
  const [bpm, setBpm] = useState(120);
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const [result, setResult] = useState(null);

  function validate() {
    const nextErrors = {};
    if (!songType) nextErrors.songType = "Choose what type of lyrics to generate.";
    if (!TIME_SIGNATURES.includes(timeSignature)) nextErrors.timeSignature = "Choose 3/4, 4/4, or 6/8.";
    if (!Number.isFinite(bpm) || bpm < 40 || bpm > 240) nextErrors.bpm = "BPM must be between 40 and 240.";
    if (description.trim().length < 20) nextErrors.description = "Describe the song clearly in at least 20 characters.";
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function generateLyrics() {
    if (!validate()) {
      setStatus("Fix the highlighted fields before generating.");
      return;
    }
    setLoading(true);
    setStatus("Writing lyrics...");
    try {
      const response = await fetch("http://localhost:8000/generate_lyrics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          song_type: songType,
          time_signature: timeSignature,
          bpm: Number(bpm),
          description,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      setResult(data);
      setStatus("Lyrics generated");
    } catch (error) {
      setStatus(error.message || "Lyrics generation failed.");
    } finally {
      setLoading(false);
    }
  }

  const composer = (
    <section className={styles.composer}>
      <div className={styles.composerHeader}>
        <div>
          <div className={styles.composerEyebrow}>Lyrics</div>
          <h2>Shape the lyric brief before generation</h2>
        </div>
      </div>
      <div className={styles.panelGrid}>
        <div className={styles.panelBlock}>
          <h3>Song Brief</h3>
          <label className={styles.field}>
            <span>Type of song</span>
            <select value={songType} onChange={(event) => setSongType(event.target.value)}>
              {SONG_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          {errors.songType ? <div className={styles.validationText}>{errors.songType}</div> : null}
          <div className={styles.inlineFields}>
            <label className={styles.field}>
              <span>Time signature</span>
              <select value={timeSignature} onChange={(event) => setTimeSignature(event.target.value)}>
                {TIME_SIGNATURES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className={styles.field}><span>BPM</span><input type="number" value={bpm} onChange={(event) => setBpm(Number(event.target.value))} /></label>
          </div>
          {errors.timeSignature ? <div className={styles.validationText}>{errors.timeSignature}</div> : null}
          {errors.bpm ? <div className={styles.validationText}>{errors.bpm}</div> : null}
        </div>
        <div className={styles.panelBlock}>
          <h3>Describe the song</h3>
          <textarea className={styles.lyricsInput} rows={9} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Describe the story, mood, setting, emotional arc, and what the song should feel like." />
          {errors.description ? <div className={styles.validationText}>{errors.description}</div> : null}
          <div className={styles.helperText}>The backend uses the song type, time signature, BPM, and description together when drafting the lyric structure.</div>
        </div>
      </div>
      <div className={styles.composerActions}>
        <div className={styles.statusPill}>{status || "Set the lyric brief and meter first"}</div>
        <button type="button" className={styles.createButton} onClick={generateLyrics} disabled={loading}>{loading ? "Generating..." : "Generate Lyrics"}</button>
      </div>
    </section>
  );

  const results = (
    <section className={styles.resultsSection}>
      <div className={styles.resultsHeader}><h2>Lyrics Output</h2><span>{loading ? "Writing lyric draft" : "Structured lyric generation"}</span></div>
      <div className={styles.resultsGrid}>
        <article className={styles.resultCard}>
          <div className={styles.resultLabel}>Draft</div>
          {result ? (
            <div className={styles.outputPanel}>
              <div className={styles.outputMeta}><strong>{result.title}</strong><span>{result.song_type} | {result.time_signature} | {result.bpm} BPM</span></div>
              <pre className={styles.outputText}>{result.lyrics}</pre>
            </div>
          ) : <p>Your generated lyrics will appear here.</p>}
        </article>
        <article className={styles.resultCard}>
          <div className={styles.resultLabel}>Notes</div>
          {result ? <div className={styles.notesList}>{result.notes.map((note) => <p key={note}>{note}</p>)}</div> : <p>The generator notes and structure guidance will appear here.</p>}
        </article>
      </div>
    </section>
  );

  return (
    <StudioShell
      app={app}
      activeHref="/lyrics"
      kicker="Structured lyric generation"
      title="Generate lyrics from meter, BPM, and story direction."
      description="This page asks what type of song you want, the beat structure, the BPM, and a written brief. The lyric draft is generated from that full set of inputs."
      logos={["Song Type", "3/4 4/4 6/8", "BPM", "Vocalis-X"]}
      composer={composer}
      results={results}
      pageNote="Current backend generation is deterministic and local. If you want LLM-quality lyric writing later, we can swap this endpoint to an external model provider."
    />
  );
}
