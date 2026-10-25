# Rai 3D-style emoji pack setup

Rai already has a central `EmojiManager` with environment-variable overrides and Unicode fallbacks. This optional importer lets an administrator add a third-party emoji pack to a Discord server they control and then configure those custom emoji IDs for MusicMaid and other shared embed builders.

## Choose a pack

Start with the [Emoji.gg 3D packs directory](https://emoji.gg/packs/3d). The directory includes different 3D styles; inspect the preview and the creator's usage/license notes before downloading. For the screenshot style, look for glossy/cute figures, butterflies, sparkles and monochrome anime emotes. The screenshot alone does not identify the original pack, so this importer does not claim to reproduce the exact artwork.

Download a pack ZIP from its publisher and extract it locally. Do not commit the pack files to this repository unless you have the rights to redistribute them.

## Upload the selected pack

1. Invite the Rai bot to the target server and grant it **Create Expressions** permission (or the equivalent emoji-management permission).
2. Download/extract the pack to a local folder. Keep only the emoji files you actually want to upload; the script accepts PNG, JPEG, GIF and WebP files smaller than 256 KiB each.
3. Run from the repository root on your own computer. Use a temporary shell environment variable; never paste the bot token into source code or commit it.

Windows PowerShell:

```powershell
$env:DISCORD_BOT_TOKEN = "YOUR_BOT_TOKEN"
python scripts/import_emoji_pack.py "C:\path\to\extracted-pack" --guild-id YOUR_SERVER_ID
Remove-Item Env:DISCORD_BOT_TOKEN
```

The script prints mappings such as `EMOJI_PLAY=<:play:123456789012345678>`. Copy only mappings you want into the bot service's environment variables in Render. Choose semantic names such as `EMOJI_LOGO`, `EMOJI_PLAY`, `EMOJI_PAUSE`, `EMOJI_NEXT`, `EMOJI_QUEUE`, `EMOJI_LOADING`, `EMOJI_SUCCESS`, `EMOJI_ERROR`, `EMOJI_WARNING`, `EMOJI_SPARKLES`, and `EMOJI_FAVORITE`. The actual names depend on the uploaded filenames; rename a mapping key manually when appropriate.

Restart/redeploy the bot after setting variables. The configured custom emoji must remain accessible to the bot. If it is missing or inaccessible, `EmojiManager` should use its Unicode fallback instead of breaking a message.

## Important limits and safety

- This is an explicit, local admin tool; it does not auto-upload anything at bot startup or modify production automatically.
- Discord requires the appropriate server permission, and the bot must be in the target guild.
- Discord custom emoji uploads have a 256 KiB size limit. Server emoji capacity depends on the server's current limits/boosts.
- Use artwork according to the creator's terms. Do not upload private, stolen, or unauthorized emoji packs.
- Never expose `DISCORD_BOT_TOKEN` in logs, screenshots, GitHub, or Render build output.
- Custom emoji from a guild may not be available in another guild. Test with a non-critical embed before configuring the whole bot.

## Tests

Run the deterministic helper tests with:

```bash
python -m pytest tests/test_emoji_pack.py -q
```

The tests do not call Discord's API or upload any emoji.
