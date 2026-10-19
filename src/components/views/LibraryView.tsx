"use client";

import React, { useEffect, useState } from "react";
import { FolderHeart, Bookmark, Heart, Play, Trash2, Plus, Loader2 } from "lucide-react";
import { formatDuration, DEFAULT_TRACK_ARTWORK } from "@/lib/utils";
import type { Playlist, FavoriteItem } from "@/types/music";

interface LibraryViewProps {
  guildId: string;
  onEnqueue: (query: string) => Promise<boolean>;
  onOpenPlaylistModal: () => void;
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
}

export function LibraryView({
  guildId,
  onEnqueue,
  onOpenPlaylistModal,
  onShowToast,
}: LibraryViewProps) {
  const [tab, setTab] = useState<"playlists" | "favorites">("playlists");
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchLibraryData = async () => {
    setLoading(true);
    try {
      const [pRes, fRes] = await Promise.all([
        fetch(`/api/music/playlists?guild_id=${guildId}`),
        fetch("/api/music/favorites"),
      ]);

      const pData = await pRes.json();
      const fData = await fRes.json();

      if (pData.success) {
        if (Array.isArray(pData.data)) {
          setPlaylists(pData.data);
        } else if (pData.data && Array.isArray(pData.data.playlists)) {
          setPlaylists(pData.data.playlists);
        } else if (Array.isArray(pData.playlists)) {
          setPlaylists(pData.playlists);
        }
      }
      if (fData.success) {
        if (Array.isArray(fData.data)) {
          setFavorites(fData.data);
        } else if (fData.data && Array.isArray(fData.data.favorites)) {
          setFavorites(fData.data.favorites);
        } else if (Array.isArray(fData.favorites)) {
          setFavorites(fData.favorites);
        }
      }
    } catch (e: any) {
      console.warn("Library data fetch error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLibraryData();
  }, [guildId]);

  const handleDeletePlaylist = async (id: string | number, name: string) => {
    if (!confirm(`Delete playlist "${name}"?`)) return;
    try {
      const res = await fetch("/api/music/playlists/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ playlist_id: id, id, name, guild_id: guildId }),
      });
      const data = await res.json();
      if (data.success) {
        onShowToast(`Deleted playlist: ${name}`, "info");
        setPlaylists((prev) => prev.filter((p) => String(p.id) !== String(id)));
      } else {
        onShowToast(data.error?.message || data.error || "Failed to delete playlist", "danger");
      }
    } catch (e: any) {
      onShowToast(`Error: ${e.message}`, "danger");
    }
  };

  const handleLoadPlaylist = async (playlist: Playlist) => {
    // 1. First attempt authoritative backend load endpoint
    try {
      const res = await fetch("/api/music/playlists/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: playlist.name,
          guild_id: guildId,
          playlist_id: playlist.id,
        }),
      });
      const data = await res.json();
      if (data.success) {
        onShowToast(`Loaded "${playlist.name}" into queue! 🎶`, "success");
        return;
      }
    } catch {
      // Fallback to manual queue injection
    }

    // 2. Fallback to client-side sequential track enqueueing if tracks_json is present
    let tracks: any[] = [];
    try {
      tracks = typeof playlist.tracks_json === "string" ? JSON.parse(playlist.tracks_json) : playlist.tracks_json;
    } catch {
      tracks = [];
    }

    if (!Array.isArray(tracks) || tracks.length === 0) {
      onShowToast(`Playlist "${playlist.name}" loaded or has no client-side track snapshot`, "info");
      return;
    }

    onShowToast(`Enqueuing ${tracks.length} tracks from ${playlist.name}...`, "info");
    for (const t of tracks) {
      await onEnqueue(t.url || `${t.title} ${t.artist || ""}`);
    }
    onShowToast(`Enqueued all tracks from "${playlist.name}"! 🎶`, "success");
  };

  const handleRemoveFavorite = async (item: FavoriteItem) => {
    try {
      const res = await fetch("/api/music/favorites/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: item.url, title: item.title }),
      });
      const data = await res.json();
      if (data.success) {
        onShowToast(`Removed from favorites: ${item.title}`, "info");
        setFavorites((prev) => prev.filter((f) => f.url !== item.url));
      }
    } catch (e: any) {
      onShowToast(`Error: ${e.message}`, "danger");
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* HEADER CARD */}
      <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6 backdrop-blur-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400">
              <FolderHeart className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">Server Music Library</h2>
              <p className="text-xs text-(--text-muted) mt-0.5">
                Saved playlists, community snapshots, and your personal favorites.
              </p>
            </div>
          </div>

          <button
            onClick={onOpenPlaylistModal}
            className="btn btn-primary btn-sm flex items-center gap-1.5 self-start md:self-auto"
          >
            <Bookmark className="w-4 h-4" />
            <span>Save Current Queue</span>
          </button>
        </div>

        {/* TABS */}
        <div className="flex items-center gap-2 mt-6 border-b border-white/5 pb-2">
          <button
            onClick={() => setTab("playlists")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
              tab === "playlists"
                ? "bg-(--primary) text-white shadow-md shadow-purple-900/30"
                : "text-(--text-muted) hover:text-white hover:bg-white/5"
            }`}
          >
            <Bookmark className="w-4 h-4" />
            <span>Playlists ({playlists.length})</span>
          </button>

          <button
            onClick={() => setTab("favorites")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
              tab === "favorites"
                ? "bg-(--primary) text-white shadow-md shadow-purple-900/30"
                : "text-(--text-muted) hover:text-white hover:bg-white/5"
            }`}
          >
            <Heart className="w-4 h-4 text-rose-400" />
            <span>Favorites ({favorites.length})</span>
          </button>
        </div>
      </div>

      {/* CONTENT PANEL */}
      <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6 backdrop-blur-xl">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 text-(--cyan) gap-3">
            <Loader2 className="w-8 h-8 animate-spin" />
            <p className="text-sm font-semibold">Loading your library records...</p>
          </div>
        ) : tab === "playlists" ? (
          playlists.length === 0 ? (
            <div className="text-center py-16 text-(--text-muted) text-sm">
              📂 No playlists saved yet. Queue some tracks and click &quot;Save Current Queue&quot;!
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {playlists.map((pl) => (
                <div
                  key={pl.id}
                  className="rounded-2xl p-4 bg-white/5 border border-white/5 hover:border-(--card-border-hover) transition-all flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <h4 className="font-bold text-white text-base truncate" title={pl.name}>
                        {pl.name}
                      </h4>
                      <button
                        onClick={() => handleDeletePlaylist(pl.id, pl.name)}
                        className="text-rose-400 hover:text-rose-300 p-1 transition-colors"
                        title="Delete playlist"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                    <p className="text-xs text-(--text-muted)">
                      {pl.track_count || 0} Tracks • Created {new Date(pl.created_at).toLocaleDateString()}
                    </p>
                  </div>

                  <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between">
                    <button
                      onClick={() => handleLoadPlaylist(pl)}
                      className="btn btn-secondary btn-sm text-xs py-1.5 px-3 flex items-center gap-1.5 w-full justify-center"
                    >
                      <Play className="w-3.5 h-3.5 text-cyan-400" />
                      <span>Load to Queue</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )
        ) : favorites.length === 0 ? (
          <div className="text-center py-16 text-(--text-muted) text-sm">
            ❤️ No favorite tracks saved yet. Heart tracks while playing to access them here!
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {favorites.map((fav, idx) => (
              <div
                key={fav.id || idx}
                className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <img
                    src={fav.thumbnail || DEFAULT_TRACK_ARTWORK}
                    alt={fav.title}
                    onError={(e) => {
                      (e.target as HTMLImageElement).src = DEFAULT_TRACK_ARTWORK;
                    }}
                    className="w-11 h-11 rounded-lg object-cover shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white truncate" title={fav.title}>
                      {fav.title}
                    </p>
                    <p className="text-xs text-(--text-muted) truncate">{fav.artist || "Unknown"}</p>
                    <span className="text-[10px] font-mono text-(--text-dim)">
                      {formatDuration(fav.duration || 0)}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0 ml-2">
                  <button
                    onClick={() => onEnqueue(fav.url || `${fav.title} ${fav.artist}`)}
                    className="p-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/40 text-purple-300 border border-purple-500/30 transition-all"
                    title="Add to queue"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleRemoveFavorite(fav)}
                    className="p-1.5 rounded-lg text-rose-400 hover:bg-rose-500/20 transition-all"
                    title="Remove from favorites"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
