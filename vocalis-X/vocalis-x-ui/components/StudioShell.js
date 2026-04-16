import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import styles from "@/styles/Home.module.css";
import { NAV_ITEMS, FEATURE_CARDS, FAQS } from "@/lib/studioContent";

function computeParallaxStyle(event, depth = 14) {
  const rect = event.currentTarget.getBoundingClientRect();
  const px = (event.clientX - rect.left) / rect.width;
  const py = (event.clientY - rect.top) / rect.height;
  return {
    transform: `perspective(1400px) rotateX(${((0.5 - py) * depth).toFixed(2)}deg) rotateY(${((px - 0.5) * depth).toFixed(2)}deg) translateY(-3px)`,
    "--glow-x": `${(px * 100).toFixed(2)}%`,
    "--glow-y": `${(py * 100).toFixed(2)}%`,
  };
}

function resetParallax() {
  return { transform: "", "--glow-x": "50%", "--glow-y": "50%" };
}

const HERO_PROMO_CARDS = [
  {
    id: "promo-diffrhythm",
    kind: "promo",
    eyebrow: "DiffRhythm",
    title: "One prompt. One lyric sheet. One finished song.",
    body: "Turn a text prompt and lyrics into a full track, then push the best songs into a public showcase instead of leaving them buried in a private draft list.",
    accent: "sunset",
    atmosphere: {
      primary: "rgba(255, 145, 84, 0.30)",
      secondary: "rgba(255, 84, 125, 0.18)",
      outline: "rgba(255, 188, 149, 0.24)",
    },
  },
  {
    id: "promo-studio",
    kind: "promo",
    eyebrow: "Studio Flow",
    title: "Build the full DiffRhythm track in one pass.",
    body: "Generate, save, publish, and surface songs across the whole product so every signed-in user sees fresh work from the community.",
    accent: "ember",
    atmosphere: {
      primary: "rgba(255, 110, 76, 0.28)",
      secondary: "rgba(255, 198, 104, 0.18)",
      outline: "rgba(255, 164, 128, 0.24)",
    },
  },
];

const TECH_MARQUEE_ITEMS = [
  "DiffRhythm",
  "MusicGen",
  "OpenUtau",
  "Demucs",
  "Supabase",
  "Kaggle",
  "Transformers",
  "Vocalis-X",
];

function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

function SongPlayer({ song, compact = false }) {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [showLyrics, setShowLyrics] = useState(false);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;
    const handleTime = () => setCurrentTime(audio.currentTime || 0);
    const handleLoaded = () => setDuration(audio.duration || 0);
    const handleEnded = () => setIsPlaying(false);
    audio.addEventListener("timeupdate", handleTime);
    audio.addEventListener("loadedmetadata", handleLoaded);
    audio.addEventListener("ended", handleEnded);
    return () => {
      audio.removeEventListener("timeupdate", handleTime);
      audio.removeEventListener("loadedmetadata", handleLoaded);
      audio.removeEventListener("ended", handleEnded);
    };
  }, []);

  async function togglePlayback() {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
      return;
    }
    await audio.play();
    setIsPlaying(true);
  }

  function onSeek(event) {
    const audio = audioRef.current;
    if (!audio) return;
    const nextTime = Number(event.target.value);
    audio.currentTime = nextTime;
    setCurrentTime(nextTime);
  }

  return (
    <div className={styles.playerShell}>
      <audio ref={audioRef} src={song.audioUrl} preload="metadata" />
      <div className={styles.playerRow}>
        <button type="button" className={styles.playNowButton} onClick={togglePlayback}>
          <span className={styles.playNowIcon}>{isPlaying ? "||" : "▶"}</span>
          <span>{isPlaying ? "Pause Now" : "Play Now"}</span>
        </button>
        <div className={styles.playerTime}>
          <span>{formatTime(currentTime)}</span>
          <input
            type="range"
            min="0"
            max={Math.max(duration, 1)}
            step="0.1"
            value={Math.min(currentTime, Math.max(duration, 1))}
            onChange={onSeek}
            className={styles.playerSeek}
          />
          <span>{formatTime(duration)}</span>
        </div>
      </div>
      {!compact && song.lyrics ? (
        <>
          <button type="button" className={styles.lyricsToggle} onClick={() => setShowLyrics((value) => !value)}>
            {showLyrics ? "Hide Lyrics" : "Show Lyrics"}
          </button>
          {showLyrics ? <div className={styles.lyricsPanel}>{song.lyrics}</div> : null}
        </>
      ) : null}
    </div>
  );
}

function AuthModal(app) {
  if (!app.authOpen) return null;
  return (
    <div className={styles.authOverlay} onClick={() => app.setAuthOpen(false)}>
      <div className={styles.authModal} onClick={(event) => event.stopPropagation()}>
        <div className={styles.authHeader}>
          <div>
            <div className={styles.composerEyebrow}>Account</div>
            <h2>{app.authMode === "login" ? "Log In" : "Create Account"}</h2>
          </div>
          <button type="button" className={styles.authClose} onClick={() => app.setAuthOpen(false)}>
            x
          </button>
        </div>
        <form className={styles.authForm} onSubmit={app.handleAuthSubmit}>
          {app.authMode === "signup" ? (
            <label className={styles.field}>
              <span>Display Name</span>
              <input
                name="displayName"
                value={app.authForm.displayName}
                onChange={app.handleAuthInputChange}
                placeholder="Your artist name"
              />
            </label>
          ) : null}
          <label className={styles.field}>
            <span>Email</span>
            <input
              name="email"
              type="email"
              value={app.authForm.email}
              onChange={app.handleAuthInputChange}
              placeholder="you@example.com"
            />
          </label>
          <label className={styles.field}>
            <span>Password</span>
            <input
              name="password"
              type="password"
              value={app.authForm.password}
              onChange={app.handleAuthInputChange}
              placeholder="Minimum 6 characters"
            />
          </label>
          {app.authMessage ? <div className={styles.authMessage}>{app.authMessage}</div> : null}
          <button type="submit" className={styles.createButton} disabled={app.authBusy}>
            {app.authBusy ? "Working..." : app.authMode === "login" ? "Log In" : "Sign Up"}
          </button>
        </form>
        <div className={styles.authSwitch}>
          {app.authMode === "login" ? "Need an account?" : "Already have an account?"}{" "}
          <button
            type="button"
            className={styles.authSwitchButton}
            onClick={() => {
              app.setAuthMode((current) => (current === "login" ? "signup" : "login"));
            }}
          >
            {app.authMode === "login" ? "Sign up" : "Log in"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Header({ app, activeHref }) {
  return (
    <header className={styles.nav}>
      <div className={styles.brandWrap}>
        <div className={styles.brandBadge}>VX</div>
        <div>
          <div className={styles.brand}>Vocalis-X</div>
          <div className={styles.brandSub}>AI Song Builder</div>
        </div>
      </div>
      <div className={styles.navRight}>
        <nav className={styles.routeNav} aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`${styles.routeLink} ${activeHref === item.href ? styles.routeLinkActive : ""}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        {!app.user ? (
          <div className={styles.authActions}>
            <button type="button" className={styles.navGhost} onClick={() => { app.setAuthMode("login"); app.setAuthOpen(true); }}>
              Log In
            </button>
            <button type="button" className={styles.navCta} onClick={() => { app.setAuthMode("signup"); app.setAuthOpen(true); }}>
              Sign Up
            </button>
          </div>
        ) : (
          <div className={styles.profileShell}>
            <button type="button" className={styles.profileButton} onClick={() => app.setProfileOpen((value) => !value)}>
              <span className={styles.profileAvatar}>{app.profileInitials}</span>
              <span className={styles.profileName}>{app.displayName}</span>
            </button>
            {app.profileOpen ? (
              <div className={styles.profileMenu}>
                <div className={styles.profileMenuHeader}>
                  <strong>{app.displayName}</strong>
                  <span>{app.user.email}</span>
                </div>
                <button type="button" className={styles.profileMenuItem}>My Songs</button>
                <button type="button" className={styles.profileMenuItem}>Published Tracks</button>
                <button type="button" className={styles.profileMenuItem} onClick={app.handleLogout}>Log Out</button>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </header>
  );
}

function LibrarySection({ app }) {
  return (
    <section className={styles.librarySection}>
      <div className={styles.resultsHeader}>
        <h2>My Songs</h2>
        <span>{app.user ? "These songs belong to the authenticated user account." : "Guest view only. Log in to save songs to your own library."}</span>
      </div>
      {app.libraryMessage ? <div className={styles.libraryMessage}>{app.libraryMessage}</div> : null}
      <div className={styles.libraryGrid}>
        {app.songLibrary.map((song) => (
          <article
            key={song.id}
            className={`${styles.libraryCard} ${styles.parallaxSurface}`}
            onMouseMove={(event) => Object.assign(event.currentTarget.style, computeParallaxStyle(event, 9))}
            onMouseLeave={(event) => Object.assign(event.currentTarget.style, resetParallax())}
          >
            <div className={styles.libraryTop}>
              <div>
                <div className={styles.libraryStatus}>{song.status}</div>
                <h3>{song.title}</h3>
              </div>
              <div className={styles.visibilityBadge}>{song.visibility}</div>
            </div>
            <p>{song.prompt}</p>
            <div className={styles.libraryMeta}>
              <span>{song.createdAt}</span>
              <span>{song.audioUrl ? "Audio attached" : "Metadata only"}</span>
            </div>
            {song.audioUrl ? <SongPlayer song={song} /> : null}
            <div className={styles.libraryActions}>
              <button type="button" className={styles.secondaryAction} onClick={() => app.togglePublishSong(song)}>
                {song.visibility === "Private" ? "Publish" : "Unpublish"}
              </button>
              {song.audioUrl ? (
                <a className={styles.secondaryAction} href={song.audioUrl} download>
                  Download
                </a>
              ) : (
                <button type="button" className={styles.secondaryAction} disabled>
                  Download
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ShowcaseCard({ item, featured = false }) {
  const cardClass = featured ? styles.showcaseCardFeatured : "";
  if (item.kind === "promo") {
    return (
      <article className={`${styles.showcaseCard} ${cardClass} ${styles[item.accent] || ""}`}>
        <div className={styles.showcaseEyebrow}>{item.eyebrow}</div>
        <h3>{item.title}</h3>
        <p>{item.body}</p>
      </article>
    );
  }
  return (
    <article className={`${styles.showcaseCard} ${cardClass} ${featured ? styles.parallaxSurface : ""}`}>
      <div className={styles.showcaseEyebrow}>Published Song</div>
      <h3>{item.title}</h3>
      <div className={styles.showcaseArtist}>by {item.artistName}</div>
      <p>{item.prompt}</p>
      <div className={styles.showcaseMeta}>
        <span>{item.createdAt}</span>
        <span>{item.visibility}</span>
      </div>
      {item.audioUrl ? <SongPlayer song={item} compact /> : null}
    </article>
  );
}

export default function StudioShell({
  app,
  activeHref,
  kicker,
  title,
  description,
  logos,
  composer,
  results,
  pageNote,
  children,
}) {
  const showcaseCards = useMemo(
    () => [...HERO_PROMO_CARDS, ...(app.publicSongs || []).map((song) => ({ ...song, kind: "song" }))],
    [app.publicSongs]
  );
  const [activeShowcaseIndex, setActiveShowcaseIndex] = useState(0);

  useEffect(() => {
    setActiveShowcaseIndex(0);
  }, [showcaseCards.length]);

  useEffect(() => {
    if (showcaseCards.length <= 1) {
      return undefined;
    }
    const timer = setInterval(() => {
      setActiveShowcaseIndex((current) => (current + 1) % showcaseCards.length);
    }, 6200);
    return () => clearInterval(timer);
  }, [showcaseCards.length]);

  const featuredCard = showcaseCards[activeShowcaseIndex] || HERO_PROMO_CARDS[0];
  const heroAtmosphere = featuredCard.atmosphere || HERO_PROMO_CARDS[0].atmosphere;

  return (
    <main className={styles.page}>
      {app.booting ? (
        <div className={styles.loaderScreen}>
          <div className={styles.loaderOrb} />
          <div className={styles.loaderContent}>
            <div className={styles.loaderWordmark}>Vocalis-X</div>
            <div className={styles.loaderWave} aria-hidden="true"><span /><span /><span /><span /><span /></div>
            <p>Warming up the studio, loading voices, and routing the signal chain.</p>
          </div>
        </div>
      ) : null}
      <AuthModal {...app} />
      <div className={styles.bgGlowTop} />
      <div className={styles.bgGlowBottom} />
      <Header app={app} activeHref={activeHref} />
      <section
        className={styles.hero}
        style={{
          "--hero-primary": heroAtmosphere.primary,
          "--hero-secondary": heroAtmosphere.secondary,
          "--hero-outline": heroAtmosphere.outline,
        }}
      >
        <div className={styles.heroAtmosphere} />
        <div className={styles.heroTop}>
          <div className={styles.heroText}>
            <div className={styles.kicker}>{kicker}</div>
            <h1>{title}</h1>
            <p>{description}</p>
            <div className={styles.logoRow}>
              {(logos || []).map((item) => <span key={item}>{item}</span>)}
            </div>
            {pageNote ? <div className={styles.pageNote}>{pageNote}</div> : null}
          </div>
          <section className={styles.showcaseSection}>
            <div className={styles.showcaseHeader}>
              <h2>Live Published Songs</h2>
              <span>{app.user ? "Promoted across every signed-in user page." : "Log in to see the live community showcase."}</span>
            </div>
            <div className={styles.showcaseStage}>
              <ShowcaseCard item={featuredCard} featured />
            </div>
            <div className={styles.showcaseDots}>
              {showcaseCards.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  className={`${styles.showcaseDot} ${index === activeShowcaseIndex ? styles.showcaseDotActive : ""}`}
                  onClick={() => setActiveShowcaseIndex(index)}
                  aria-label={`Showcase item ${index + 1}`}
                />
              ))}
            </div>
          </section>
        </div>
        <div className={styles.heroComposer}>{composer}</div>
        <div className={styles.techMarquee}>
          <div className={styles.techTrack}>
            {[...TECH_MARQUEE_ITEMS, ...TECH_MARQUEE_ITEMS].map((item, index) => (
              <span key={`${item}-${index}`} className={styles.techChip}>{item}</span>
            ))}
          </div>
        </div>
      </section>
      {results}
      {children}
      <LibrarySection app={app} />
      <section className={styles.featureSection}>
        {FEATURE_CARDS.map((card) => (
          <article
            key={card.title}
            className={`${styles.featureCard} ${styles[card.accent]} ${styles.parallaxSurface}`}
            onMouseMove={(event) => Object.assign(event.currentTarget.style, computeParallaxStyle(event, 9))}
            onMouseLeave={(event) => Object.assign(event.currentTarget.style, resetParallax())}
          >
            <h3>{card.title}</h3>
            <p>{card.body}</p>
          </article>
        ))}
      </section>
      <section className={styles.faqSection}>
        <div className={styles.faqHeader}>
          <h2>Common Questions</h2>
          <span>Built around your current backend flow</span>
        </div>
        <div className={styles.faqList}>
          {FAQS.map((question) => (
            <div key={question} className={styles.faqItem}>
              <span>{question}</span>
              <span>+</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
