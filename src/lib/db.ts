import Database from "better-sqlite3";
import path from "path";
import fs from "fs";

// Resolve database paths relative to workspace root
const ROOT_DIR = process.cwd();
const MUSIC_DB_PATH = path.join(ROOT_DIR, "data", "music.db");
const BOT_DB_PATH = path.join(ROOT_DIR, "data", "bot.db");

let musicDbInstance: Database.Database | null = null;
let botDbInstance: Database.Database | null = null;

function initMusicSchema(db: Database.Database): void {
  try {
    db.exec(`
      CREATE TABLE IF NOT EXISTS music_guild_settings (
        guild_id TEXT PRIMARY KEY,
        default_volume INTEGER DEFAULT 80,
        twenty_four_seven_enabled INTEGER DEFAULT 0,
        bound_channel_id TEXT,
        auto_leave_empty INTEGER DEFAULT 1,
        bitrate INTEGER DEFAULT 320,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS music_sessions (
        guild_id TEXT PRIMARY KEY,
        voice_channel_id TEXT,
        text_channel_id TEXT,
        state TEXT DEFAULT 'IDLE',
        is_playing INTEGER DEFAULT 0,
        is_paused INTEGER DEFAULT 0,
        volume INTEGER DEFAULT 80,
        current_track_json TEXT,
        current_track_title TEXT,
        current_track_author TEXT,
        current_track_url TEXT,
        current_track_thumbnail TEXT,
        current_track_duration INTEGER DEFAULT 0,
        position_seconds REAL DEFAULT 0,
        elapsed_seconds REAL DEFAULT 0,
        loop_mode TEXT DEFAULT 'off',
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS music_queues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        track_index INTEGER DEFAULT 0,
        position INTEGER DEFAULT 0,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        stream_url TEXT,
        author TEXT,
        artist TEXT,
        duration INTEGER DEFAULT 0,
        thumbnail TEXT,
        requester_name TEXT,
        requested_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS music_web_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        action TEXT NOT NULL,
        payload_json TEXT,
        user_id TEXT,
        status TEXT DEFAULT 'PENDING',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS music_playlists (
        id TEXT PRIMARY KEY,
        guild_id TEXT,
        user_id TEXT,
        name TEXT NOT NULL,
        description TEXT,
        tracks_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS music_favorites (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        author TEXT,
        thumbnail TEXT,
        duration INTEGER DEFAULT 0,
        added_at TEXT DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS web_sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        username TEXT,
        avatar TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT
      );
    `);
  } catch (err) {
    console.warn("Schema init notice (non-fatal):", err);
  }
}

function initBotSchema(db: Database.Database): void {
  try {
    db.exec(`
      CREATE TABLE IF NOT EXISTS web_sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        discord_user_id TEXT,
        username TEXT,
        discriminator TEXT DEFAULT '0',
        avatar TEXT,
        access_token TEXT,
        refresh_token TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT
      );
      -- Add discriminator column if upgrading from older schema
      ALTER TABLE web_sessions ADD COLUMN discriminator TEXT DEFAULT '0';
      ALTER TABLE web_sessions ADD COLUMN discord_user_id TEXT;
      ALTER TABLE web_sessions ADD COLUMN access_token TEXT;
      ALTER TABLE web_sessions ADD COLUMN refresh_token TEXT;
    `);
  } catch (err) {
    // ALTER TABLE throws if column already exists — this is expected and non-fatal
    if (String(err).includes("duplicate column")) {
      // Schema is already up-to-date
    } else {
      console.warn("Bot schema init notice (non-fatal):", err);
    }
  }
}

export function getMusicDb(): Database.Database {
  if (!musicDbInstance) {
    const dir = path.dirname(MUSIC_DB_PATH);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    musicDbInstance = new Database(MUSIC_DB_PATH);
    musicDbInstance.pragma("journal_mode = WAL");
    musicDbInstance.pragma("busy_timeout = 5000");
    initMusicSchema(musicDbInstance);
  }
  return musicDbInstance;
}

export function getBotDb(): Database.Database {
  if (!botDbInstance) {
    const dir = path.dirname(BOT_DB_PATH);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    botDbInstance = new Database(BOT_DB_PATH);
    botDbInstance.pragma("journal_mode = WAL");
    botDbInstance.pragma("busy_timeout = 5000");
    initBotSchema(botDbInstance);
  }
  return botDbInstance;
}

// =========================================================================
// QUERY HELPERS (Preserving existing schema & models)
// =========================================================================

export function getWebSessionByToken(token: string) {
  try {
    const db = getBotDb();
    const row = db
      .prepare(
        "SELECT * FROM web_sessions WHERE session_id = ? AND is_active = 1"
      )
      .get(token) as any;
    if (!row) return null;
    // Validate expiry server-side to prevent stale sessions
    if (row.expires_at) {
      try {
        const expiry = new Date(row.expires_at);
        if (!isNaN(expiry.getTime()) && expiry < new Date()) {
          return null;
        }
      } catch {
        // Malformed expiry — treat as still valid
      }
    }
    return row;
  } catch {
    return null;
  }
}

export function getGuildSettings(guildId: string) {
  try {
    const db = getMusicDb();
    const row = db
      .prepare("SELECT * FROM music_guild_settings WHERE guild_id = ?")
      .get(guildId);
    return row as any;
  } catch {
    return null;
  }
}

export function getActiveSession(guildId: string) {
  try {
    const db = getMusicDb();
    const row = db
      .prepare("SELECT * FROM music_sessions WHERE guild_id = ?")
      .get(guildId);
    return row as any;
  } catch {
    return null;
  }
}

export function getQueue(guildId: string) {
  try {
    const db = getMusicDb();
    try {
      return db
        .prepare(
          "SELECT * FROM music_queues WHERE guild_id = ? ORDER BY track_index ASC"
        )
        .all(guildId) as any[];
    } catch {
      return db
        .prepare(
          "SELECT * FROM music_queues WHERE guild_id = ? ORDER BY position ASC"
        )
        .all(guildId) as any[];
    }
  } catch {
    return [];
  }
}

export function getPlaylists(guildId?: string, userId?: string) {
  try {
    const db = getMusicDb();
    if (guildId && userId) {
      return db
        .prepare(
          "SELECT * FROM music_playlists WHERE guild_id = ? OR user_id = ? ORDER BY created_at DESC"
        )
        .all(guildId, userId) as any[];
    } else if (guildId) {
      return db
        .prepare(
          "SELECT * FROM music_playlists WHERE guild_id = ? ORDER BY created_at DESC"
        )
        .all(guildId) as any[];
    }
    return db
      .prepare("SELECT * FROM music_playlists ORDER BY created_at DESC LIMIT 50")
      .all() as any[];
  } catch {
    return [];
  }
}

export function getFavorites(userId: string) {
  try {
    const db = getMusicDb();
    return db
      .prepare(
        "SELECT * FROM music_favorites WHERE user_id = ? ORDER BY added_at DESC"
      )
      .all(userId) as any[];
  } catch {
    return [];
  }
}

export function isUserPremium(userId: string): boolean {
  if (!userId) return false;

  // Bot Creator and Owner Bypass
  const configuredOwners = (
    process.env.BOT_CREATOR_ID ||
    process.env.CREATOR_ID ||
    process.env.BOT_OWNER_ID ||
    process.env.BOT_OWNER_IDS ||
    process.env.OWNER_ID ||
    "1457380609641938981"
  )
    .split(",")
    .map((s) => s.trim());

  if (configuredOwners.includes(userId)) {
    return true;
  }

  try {
    const db = getMusicDb();
    const row = db
      .prepare(
        "SELECT is_premium FROM music_premium WHERE entity_id = ? AND is_premium = 1"
      )
      .get(userId);
    return Boolean(row);
  } catch {
    return false;
  }
}

export function getUserEntitlement(userId: string) {
  const isOwner = (
    process.env.BOT_CREATOR_ID ||
    process.env.CREATOR_ID ||
    process.env.BOT_OWNER_ID ||
    process.env.BOT_OWNER_IDS ||
    process.env.OWNER_ID ||
    "1457380609641938981"
  )
    .split(",")
    .map((s) => s.trim())
    .includes(userId);

  if (isOwner) {
    return {
      user_id: userId,
      is_premium: true,
      plan: "owner",
      status: "active" as const,
      current_period_end: null,
      cancel_at_period_end: false,
      provider: "bot_owner_grant",
      perks: {
        boosted_volume: true,
        twenty_four_seven: true,
        studio_dsp: true,
        unlimited_queue: true,
        priority_precaching: true,
        custom_bass: true,
      },
    };
  }

  try {
    const db = getMusicDb();
    const row = db
      .prepare(
        "SELECT * FROM music_premium WHERE entity_id = ? AND is_premium = 1"
      )
      .get(userId) as any;

    if (row) {
      return {
        user_id: userId,
        is_premium: true,
        plan: row.tier || "premium",
        status: "active" as const,
        current_period_end: row.expires_at || null,
        cancel_at_period_end: false,
        provider: "database_grant",
        perks: {
          boosted_volume: true,
          twenty_four_seven: true,
          studio_dsp: true,
          unlimited_queue: true,
          priority_precaching: true,
          custom_bass: true,
        },
      };
    }
  } catch {
    // fallback
  }

  return {
    user_id: userId,
    is_premium: false,
    plan: "free",
    status: "inactive" as const,
    current_period_end: null,
    cancel_at_period_end: false,
    provider: "none",
    perks: {
      boosted_volume: false,
      twenty_four_seven: false,
      studio_dsp: false,
      unlimited_queue: false,
      priority_precaching: false,
      custom_bass: false,
    },
  };
}

export function submitWebAction(
  guildId: string | number,
  action: string,
  payload: any = {},
  userId: string | number = "1457382179981099090"
): number {
  try {
    const db = getMusicDb();
    const now = new Date().toISOString();
    const info = db
      .prepare(
        `INSERT INTO music_web_actions (guild_id, action, payload_json, user_id, status, created_at)
         VALUES (?, ?, ?, ?, 'PENDING', ?)`
      )
      .run(String(guildId), action.toUpperCase(), JSON.stringify(payload), String(userId), now);
    return Number(info.lastInsertRowid);
  } catch (err) {
    console.error("submitWebAction error:", err);
    return -1;
  }
}

export function addFavorite(
  userId: string,
  title: string,
  url: string,
  duration: number = 0,
  artist: string = "Unknown",
  thumbnail?: string
) {
  try {
    const db = getMusicDb();
    const now = new Date().toISOString();
    db.prepare(
      `INSERT OR REPLACE INTO music_favorites (user_id, title, url, duration, artist, thumbnail, added_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).run(userId, title, url, duration, artist, thumbnail || null, now);
    return true;
  } catch (err) {
    console.error("addFavorite error:", err);
    return false;
  }
}

export function removeFavorite(userId: string, url: string) {
  try {
    const db = getMusicDb();
    db.prepare("DELETE FROM music_favorites WHERE user_id = ? AND url = ?").run(userId, url);
    return true;
  } catch (err) {
    console.error("removeFavorite error:", err);
    return false;
  }
}

export function savePlaylist(
  name: string,
  guildId: string,
  userId: string,
  tracks: any[]
) {
  try {
    const db = getMusicDb();
    const now = new Date().toISOString();
    const info = db
      .prepare(
        `INSERT INTO music_playlists (name, guild_id, user_id, tracks_json, track_count, created_at)
         VALUES (?, ?, ?, ?, ?, ?)`
      )
      .run(name, guildId, userId, JSON.stringify(tracks), tracks.length, now);
    return Number(info.lastInsertRowid);
  } catch (err) {
    console.error("savePlaylist error:", err);
    return -1;
  }
}

export function deletePlaylist(playlistId: number | string) {
  try {
    const db = getMusicDb();
    db.prepare("DELETE FROM music_playlists WHERE id = ?").run(Number(playlistId));
    return true;
  } catch (err) {
    console.error("deletePlaylist error:", err);
    return false;
  }
}

