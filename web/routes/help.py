"""web/routes/help.py — Help center page."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

FAQS = [
    {
        "question": "How do I invite Voicelink to my server?",
        "answer": "Click the 'Add to Discord' button on the homepage and select your server. Make sure you grant all the required permissions so the bot can connect to voice channels and send messages.",
        "related_command": None,
    },
    {
        "question": "Why is Voicelink not joining my voice channel?",
        "answer": "Make sure you are already in a voice channel before running /play. Also verify the bot has the 'Connect' and 'Speak' permissions in that channel. If it's a private channel, the bot must be explicitly allowed.",
        "related_command": "play",
    },
    {
        "question": "How do I set up a DJ role?",
        "answer": "Create a Discord role named 'DJ' (exact name, case-insensitive) in your server. Members with this role will be able to use restricted commands. You can also use /djrole to assign a custom role name.",
        "related_command": "djrole",
    },
    {
        "question": "Does Voicelink support Spotify?",
        "answer": "Yes! Paste any Spotify track, album, or playlist URL and Voicelink will resolve it to the best matching audio source. Playlists are limited to 100 tracks per load to keep queue performance snappy.",
        "related_command": "play",
    },
    {
        "question": "How do I get lyrics for a song?",
        "answer": "Use /lyrics while a track is playing to fetch lyrics for the current song. You can also provide a song name: /lyrics Blinding Lights The Weeknd.",
        "related_command": "lyrics",
    },
    {
        "question": "Can I save playlists?",
        "answer": "Yes! Use /playlist create <name> to create a playlist, /playlist add <name> to add the current track, and /playlist load <name> to queue it up again anytime.",
        "related_command": "playlist create",
    },
    {
        "question": "How do I use the web player?",
        "answer": "Log in with Discord using the Login button in the top-right corner, select your server from the dropdown in the Player page, and control your bot in real-time through the browser.",
        "related_command": None,
    },
    {
        "question": "My slash commands aren't showing up. What do I do?",
        "answer": "Slash commands can take up to 1 hour to register after the bot joins your server. Try typing / in the message box to force a refresh. If the issue persists, kick and re-invite the bot with the correct scopes (bot + applications.commands).",
        "related_command": None,
    },
    {
        "question": "Can I lock the bot to a specific text channel?",
        "answer": "Yes, administrators can use /channel #my-channel to restrict all bot interactions to a single text channel. Run /channel without arguments to remove the restriction.",
        "related_command": "channel",
    },
    {
        "question": "How do I reset the bot's settings for my server?",
        "answer": "Currently, individual settings can be reset via their respective commands (e.g., /djrole with no argument clears the DJ role). A full server reset command is planned for a future update.",
        "related_command": None,
    },
]


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    templates = request.app.state.templates
    ctx = request.app.state.base_context(request)
    ctx["faqs"] = FAQS
    return templates.TemplateResponse("help.html", ctx)

