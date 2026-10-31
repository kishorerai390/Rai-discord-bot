# Rai / MusicMaid 3D Emoji Setup

This feature uses a centralized emoji registry for music-player controls and other bot embeds. The repository already has Unicode fallbacks; custom assets are opt-in so missing emoji IDs never break messages or buttons.

## Find a matching pack

Browse the 3D category on Emoji.gg: https://emoji.gg/packs/3d

For the screenshot's mix of glossy/cute figures, butterflies, sparkles and dark-aesthetic icons, also browse:
- Shiny packs: https://emoji.gg/packs/shiny
- Butterfly packs: https://emoji.gg/packs/butterfly
- Aesthetic packs: https://emoji.gg/packs/aesthetic
- Kawaii packs: https://emoji.gg/packs/kawaii

Choose a pack whose uploader permits reuse and check the pack's license/terms before using it in a public bot. The screenshot alone does not identify the original pack, so these are discovery starting points rather than a claim that any one pack is the exact source.

## Recommended deployment path

1. Download a pack from its source and keep an attribution/license note with the assets.
2. Upload the selected files as **application emojis** in Discord Developer Portal for the Rai/MusicMaid application. This avoids requiring the bot to share a guild with an emoji-hosting server. Discord currently supports application-owned emojis through its API; check the current application emoji quota and file-size limit before uploading.
3. Copy each uploaded emoji's exact Discord tag, including its name and ID, for example `<:rai_play3d:123456789012345678>` or `<a:rai_loading3d:123456789012345678>`.
4. Configure the corresponding environment variable with the `app:` prefix. Example:

```env
EMOJI_LOGO=app:<:rai_mascot3d:123456789012345678>
EMOJI_PLAY=app:<:rai_play3d:123456789012345678>
EMOJI_PAUSE=app:<:rai_pause3d:123456789012345678>
EMOJI_PREVIOUS=app:<:rai_previous3d:123456789012345678>
EMOJI_NEXT=app:<:rai_next3d:123456789012345678>
EMOJI_SKIP=app:<:rai_skip3d:123456789012345678>
EMOJI_STOP=app:<:rai_stop3d:123456789012345678>
EMOJI_QUEUE=app:<:rai_queue3d:123456789012345678>
EMOJI_LOADING=app:<a:rai_loading3d:123456789012345678>
EMOJI_SUCCESS=app:<:rai_success3d:123456789012345678>
EMOJI_ERROR=app:<:rai_error3d:123456789012345678>
EMOJI_SPARKLES=app:<:rai_sparkles3d:123456789012345678>
EMOJI_PREMIUM=app:<:rai_premium3d:123456789012345678>
```

Replace every example ID/name with the exact tag from your application. These are examples, not real uploaded emoji IDs. Set only the keys you actually uploaded. Leave other keys unset to retain the existing fallback.

## Behavior and safety

- `app:<emoji-tag>` tells the registry the emoji belongs to the Discord application. Application emojis are not necessarily present in `bot.get_emoji()` guild cache.
- Ordinary guild emoji overrides keep the existing accessibility check.
- Invalid/missing configuration falls back to the current Unicode emoji.
- No bot token is needed in the emoji configuration; never put secrets in these variables.
- Apply these variables to the bot service's environment, then restart/redeploy the bot. They are not browser/web-site variables unless that web process also generates Discord messages.
- Run `pytest tests/test_application_emoji_overrides.py tests/test_premium_emoji_and_branding.py` before deployment.

## Scope

The existing `EmojiManager` is used by the music player and shared theme/embed builders. Some legacy commands may still hard-code Unicode emoji; migrate those incrementally only after tests identify their paths. Do not bulk-rewrite unrelated bot messages.
