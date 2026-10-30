# Rem MusicMaid Product & Website Roadmap

## AI Smart DJ
- Configurable Auto-DJ queue target (25/50/100) and queue-fill meter.
- Bounded batch refill below a low-water mark; never exceed configured queue capacity.
- Manual requests always outrank recommendations.
- Mood/energy modes: chill, sad, hype, romantic, focus, gaming, party and relaxing.
- Anti-repeat memory for played/skipped tracks and artists.
- Similar artists, genre/decade radio, discovery and recommendation feedback.
- Validate every source before presenting a recommendation as playable.

## Premium player
- Persistent Now Playing card: artwork, artist, requester, source, progress and queue position.
- Responsive controls: play/pause, skip, previous, seek, volume, mute, repeat, shuffle and autoplay.
- Volume changes must reach the active audio backend; display only backend-confirmed volume.
- Live queue with reorder, remove, clear and play-next.
- Lyrics and synced highlighting where supported.
- Compact mobile player, accessible keyboard controls and session/queue recovery.

## Community music games
- Guess the song with short previews, answer validation and cooldowns.
- Song battles with timed voting and winners.
- Song of the day, music trivia and community playlist voting.
- Listening parties, weekly leaderboards, streaks and badges.
- Admin controls for channels, permissions, rewards and moderation.

## Website sections
1. **Overview:** bot/voice/node health, current track, listeners, queue depth and recent errors.
2. **Live Player:** Now Playing, progress, actual volume slider, playback controls and live queue.
3. **Smart DJ Studio:** mood, energy, genres, artist exclusions, repeat avoidance, queue target and radio mode.
4. **Community:** game lobby, active rounds, battles, voting, leaderboards and shared playlists.
5. **Library:** favorites, playlists, history, export/import and private personal collections.
6. **Analytics:** top tracks/artists/genres, listening time, request activity and source reliability.
7. **Server Settings:** DJ roles, allowed channels, queue capacity, volume cap, vote-skip and announcements.
8. **Diagnostics:** backend/node status, resolver timings, source attempts and safe copyable error references.

## Reliability and acceptance criteria
- Keep resolver, queue, player and UI changes isolated and testable.
- Bounded concurrency, timeouts, backoff and source cooldown awareness.
- Idempotent controls; preserve manual queue priority; prevent duplicate recommendations.
- Volume down must measurably reduce actual backend gain and show confirmed volume.
- Auto-DJ must maintain configured queue depth without exceeding capacity or displacing manual tracks.
- Test queue boundaries, volume calls/persistence, autoplay priority, reconnects and UI reconciliation.
- Never expose tokens/cookies/secrets in diagnostics.
- Never restart production during active playback without explicit approval.

## Delivery order
1. Fix and test real playback volume synchronization across active backends.
2. Diagnose the Auto-DJ queue ceiling; add bounded batch refill and telemetry.
3. Add mood/energy Smart DJ and anti-repeat feedback.
4. Upgrade live player and mobile dashboard.
5. Add community games and leaderboards.
6. Add analytics, diagnostics and session recovery polish.
