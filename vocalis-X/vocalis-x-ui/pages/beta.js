import StudioShell from "@/components/StudioShell";
import { useStudioApp } from "@/lib/useStudioApp";
import styles from "@/styles/Home.module.css";

export default function BetaPage() {
  const app = useStudioApp();

  const composer = (
    <section className={styles.composer}>
      <div className={styles.composerHeader}>
        <div>
          <div className={styles.composerEyebrow}>Beta Lab</div>
          <h2>Next patch in progress</h2>
        </div>
      </div>
      <div className={styles.emptyPanel}>
        <p>This route is reserved for the next experimental tool. The UI shell is live now so the app structure is ready before the feature ships.</p>
        <div className={styles.infoGrid}>
          <div className={styles.infoCard}><strong>Status</strong><span>Under development</span></div>
          <div className={styles.infoCard}><strong>Target</strong><span>Next patch release</span></div>
          <div className={styles.infoCard}><strong>UI state</strong><span>Shared shell already wired</span></div>
        </div>
      </div>
    </section>
  );

  const results = (
    <section className={styles.resultsSection}>
      <div className={styles.resultsHeader}><h2>Release Note</h2><span>Placeholder route</span></div>
      <div className={styles.resultsGrid}>
        <article className={styles.resultCard}>
          <div className={styles.resultLabel}>Message</div>
          <p>A new beta tool will be released in the next patch. This page keeps the route, styling, and navigation ready ahead of the actual feature.</p>
        </article>
        <article className={styles.resultCard}>
          <div className={styles.resultLabel}>Why keep it now?</div>
          <p>It lets users see the future slot in the product without mixing unfinished controls into the stable workflows.</p>
        </article>
      </div>
    </section>
  );

  return (
    <StudioShell
      app={app}
      activeHref="/beta"
      kicker="Under-development lane"
      title="The next beta tool lands here."
      description="This route is intentionally a polished placeholder instead of a broken experiment. It preserves the shared product shell while making it clear the feature is still in development."
      logos={["Beta", "Next Patch", "Shared UI", "Vocalis-X"]}
      composer={composer}
      results={results}
      pageNote="When you are ready, we can convert this route into the next production tool without redoing the overall navigation or design system."
    />
  );
}
