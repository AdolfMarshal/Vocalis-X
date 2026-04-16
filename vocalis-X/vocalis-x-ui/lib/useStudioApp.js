import { useEffect, useMemo, useState } from "react";
import { supabase } from "@/lib/supabaseClient";
import { EMPTY_AUTH, GUEST_LIBRARY } from "@/lib/studioContent";

function formatCreatedAt(value) {
  if (!value) return "Just now";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return "Just now";
  }
}

function mapSongRow(song) {
  return {
    id: song.id,
    title: song.title,
    status: song.status || "Draft",
    visibility: song.visibility === "public" ? "Public" : "Private",
    prompt: song.prompt || "No prompt saved",
    createdAt: formatCreatedAt(song.created_at),
    audioUrl: song.audio_url || null,
    vocalsUrl: song.vocals_url || null,
    lyrics: song.lyrics || "",
    artistName:
      song.artistName ||
      song.profiles?.display_name ||
      song.display_name ||
      "Unknown Artist",
  };
}

export function useStudioApp() {
  const [booting, setBooting] = useState(true);
  const [session, setSession] = useState(null);
  const [profile, setProfile] = useState(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState(EMPTY_AUTH);
  const [authBusy, setAuthBusy] = useState(false);
  const [authMessage, setAuthMessage] = useState("");
  const [profileOpen, setProfileOpen] = useState(false);
  const [songLibrary, setSongLibrary] = useState(GUEST_LIBRARY);
  const [publicSongs, setPublicSongs] = useState([]);
  const [libraryMessage, setLibraryMessage] = useState("");

  const user = session?.user || null;
  const displayName =
    profile?.display_name ||
    user?.user_metadata?.display_name ||
    user?.email?.split("@")[0] ||
    "Guest";
  const profileInitials = useMemo(() => {
    const parts = displayName.split(" ").filter(Boolean);
    return ((parts[0]?.[0] || "G") + (parts[1]?.[0] || "")).toUpperCase();
  }, [displayName]);

  useEffect(() => {
    const timer = setTimeout(() => setBooting(false), 1200);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!supabase) {
      setLibraryMessage("Supabase client is not configured.");
      return undefined;
    }
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (active) setSession(data.session || null);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession || null);
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    async function loadUserData() {
      if (!supabase || !user) {
        setProfile(null);
        setSongLibrary(GUEST_LIBRARY);
        setPublicSongs([]);
        setLibraryMessage("");
        return;
      }
      const [
        { data: profileRow, error: profileError },
        { data: songRows, error: songsError },
      ] = await Promise.all([
        supabase.from("profiles").select("*").eq("id", user.id).maybeSingle(),
        supabase.from("songs").select("*").eq("user_id", user.id).order("created_at", { ascending: false }),
      ]);
      setProfile(profileRow || null);
      if (profileError) {
        setLibraryMessage(`Profile load failed: ${profileError.message}`);
      }
      if (!songsError && Array.isArray(songRows)) {
        setSongLibrary(songRows.map(mapSongRow));
        if (!profileError) {
          setLibraryMessage("");
        }
      } else {
        setSongLibrary([]);
        setLibraryMessage(
          `Songs query failed: ${songsError?.message || "Unknown Supabase error"}`
        );
      }
    }
    loadUserData();
  }, [user]);

  useEffect(() => {
    async function loadPublicSongs() {
      if (!supabase || !user) {
        setPublicSongs([]);
        return;
      }
      const { data, error } = await supabase
        .from("songs")
        .select("*")
        .eq("visibility", "public")
        .order("created_at", { ascending: false })
        .limit(12);
      if (error || !Array.isArray(data)) {
        setPublicSongs([]);
        return;
      }
      const userIds = [...new Set(data.map((song) => song.user_id).filter(Boolean))];
      let profileMap = new Map();
      if (userIds.length) {
        const { data: profiles } = await supabase
          .from("profiles")
          .select("id, display_name")
          .in("id", userIds);
        profileMap = new Map((profiles || []).map((profile) => [profile.id, profile.display_name]));
      }
      const atmospheres = [
        {
          primary: "rgba(255, 145, 84, 0.30)",
          secondary: "rgba(255, 84, 125, 0.18)",
          outline: "rgba(255, 188, 149, 0.24)",
        },
        {
          primary: "rgba(80, 182, 255, 0.24)",
          secondary: "rgba(90, 120, 255, 0.16)",
          outline: "rgba(146, 196, 255, 0.22)",
        },
        {
          primary: "rgba(120, 255, 180, 0.20)",
          secondary: "rgba(28, 204, 171, 0.16)",
          outline: "rgba(124, 255, 214, 0.20)",
        },
        {
          primary: "rgba(235, 123, 255, 0.22)",
          secondary: "rgba(111, 64, 255, 0.16)",
          outline: "rgba(220, 162, 255, 0.20)",
        },
      ];
      setPublicSongs(
        data.map((song, index) =>
          mapSongRow({
            ...song,
            artistName: profileMap.get(song.user_id) || "Unknown Artist",
            atmosphere: atmospheres[index % atmospheres.length],
          })
        )
      );
    }
    loadPublicSongs();
  }, [user]);

  function handleAuthInputChange(event) {
    const { name, value } = event.target;
    setAuthForm((current) => ({ ...current, [name]: value }));
  }

  async function handleAuthSubmit(event) {
    event.preventDefault();
    if (!supabase) {
      setAuthMessage("Supabase client is not configured.");
      return;
    }
    setAuthBusy(true);
    setAuthMessage("");
    try {
      if (authMode === "signup") {
        const { error } = await supabase.auth.signUp({
          email: authForm.email,
          password: authForm.password,
          options: { data: { display_name: authForm.displayName || authForm.email.split("@")[0] } },
        });
        if (error) throw error;
        setAuthMessage("Account created. Check your email if confirmation is enabled.");
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email: authForm.email,
          password: authForm.password,
        });
        if (error) throw error;
        setAuthOpen(false);
        setProfileOpen(false);
      }
      setAuthForm(EMPTY_AUTH);
    } catch (error) {
      setAuthMessage(error.message || "Authentication failed.");
    } finally {
      setAuthBusy(false);
    }
  }

async function handleLogout() {
    if (!supabase) return;
    await supabase.auth.signOut();
    setProfileOpen(false);
    setProfile(null);
    setSongLibrary(GUEST_LIBRARY);
    setPublicSongs([]);
    setLibraryMessage("");
    setSession(null);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("vx-reset-generation-store"));
    }
  }

  async function saveGeneratedSongRecord(payload) {
    if (!supabase || !user) {
      setLibraryMessage("Log in to save songs to your library.");
      return;
    }
    const { data, error } = await supabase
      .from("songs")
      .insert({
        user_id: user.id,
        title: payload.title,
        prompt: payload.prompt,
        lyrics: payload.lyrics,
        audio_url: payload.audioUrl,
        vocals_url: payload.vocalsUrl,
        instrumental_url: payload.instrumentalUrl,
        status: payload.status.toLowerCase(),
        visibility: "private",
      })
      .select()
      .single();
    if (error || !data) {
      setLibraryMessage(`Song generated, but save failed: ${error?.message || "Unknown Supabase error"}`);
      setSongLibrary((current) => [payload, ...current]);
      return;
    }
    setSongLibrary((current) => [mapSongRow(data), ...current]);
  }

  async function togglePublishSong(song) {
    const nextVisibility = song.visibility === "Private" ? "public" : "private";
    const nextStatus = song.visibility === "Private" ? "published" : "draft";
    if (!supabase || !user || String(song.id).startsWith("demo-")) {
      setSongLibrary((current) =>
        current.map((entry) =>
          entry.id === song.id
            ? {
                ...entry,
                visibility: nextVisibility === "public" ? "Public" : "Private",
                status: nextStatus === "published" ? "Published" : "Draft",
              }
            : entry
        )
      );
      return;
    }
    if (String(song.id).startsWith("generated-")) {
      const { data, error } = await supabase
        .from("songs")
        .insert({
          user_id: user.id,
          title: song.title,
          prompt: song.prompt,
          lyrics: song.lyrics || null,
          audio_url: song.audioUrl || null,
          vocals_url: song.vocalsUrl || null,
          instrumental_url: song.instrumentalUrl || null,
          status: nextStatus,
          visibility: nextVisibility,
        })
        .select()
        .single();
    if (error || !data) {
      setLibraryMessage(`Could not publish song: ${error?.message || "Unknown Supabase error"}`);
      return;
    }
      setSongLibrary((current) => current.map((entry) => (entry.id === song.id ? mapSongRow(data) : entry)));
      if (data.visibility === "public") {
        setPublicSongs((current) => [mapSongRow(data), ...current.filter((entry) => entry.id !== data.id)].slice(0, 12));
      }
      return;
    }
    const { data, error } = await supabase
      .from("songs")
      .update({ visibility: nextVisibility, status: nextStatus })
      .eq("id", song.id)
      .eq("user_id", user.id)
      .select()
      .single();
    if (error || !data) {
      setLibraryMessage(`Could not update song visibility: ${error?.message || "Unknown Supabase error"}`);
      return;
    }
    setSongLibrary((current) => current.map((entry) => (entry.id === song.id ? mapSongRow(data) : entry)));
    setPublicSongs((current) => {
      const withoutCurrent = current.filter((entry) => entry.id !== data.id);
      if (data.visibility === "public") {
        return [mapSongRow(data), ...withoutCurrent].slice(0, 12);
      }
      return withoutCurrent;
    });
  }

  return {
    booting,
    user,
    displayName,
    profileInitials,
    authOpen,
    setAuthOpen,
    authMode,
    setAuthMode,
    authForm,
    authBusy,
    authMessage,
    handleAuthInputChange,
    handleAuthSubmit,
    profileOpen,
    setProfileOpen,
    handleLogout,
    songLibrary,
    publicSongs,
    libraryMessage,
    togglePublishSong,
    saveGeneratedSongRecord,
  };
}
