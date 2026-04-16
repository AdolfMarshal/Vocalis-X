import "@/styles/globals.css";
import { GenerationProvider } from "@/lib/generationStore";

export default function App({ Component, pageProps }) {
  return (
    <GenerationProvider>
      <Component {...pageProps} />
    </GenerationProvider>
  );
}
