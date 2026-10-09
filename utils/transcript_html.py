"""
HTML Discord Dark-Mode Transcript Generator for Rai Tickets.
Renders high-fidelity offline Discord chat transcripts complete with
avatars, timestamps, attachments, embeds, and Discord styling.
"""

from __future__ import annotations

import datetime
import html
import re
from typing import List
import discord

DARK_MODE_CSS = """
:root {
    --bg-primary: #313338;
    --bg-secondary: #2b2d31;
    --bg-tertiary: #1e1f22;
    --text-normal: #dbdee1;
    --text-muted: #949ba4;
    --text-header: #f2f3f5;
    --brand: #5865f2;
    --interactive-hover: #35373c;
    --border-subtle: #3f4147;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    font-family: 'gg sans', 'Noto Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
}

body {
    background-color: var(--bg-primary);
    color: var(--text-normal);
    line-height: 1.375rem;
    font-size: 16px;
    padding: 24px;
}

.container {
    max-width: 1000px;
    margin: 0 auto;
    background: var(--bg-secondary);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    border: 1px solid var(--border-subtle);
}

.header {
    background: var(--bg-tertiary);
    padding: 20px 24px;
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.header-title {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-header);
    display: flex;
    align-items: center;
    gap: 10px;
}

.badge {
    background: var(--brand);
    color: #ffffff;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    text-transform: uppercase;
    font-weight: 700;
}

.meta-stats {
    font-size: 13px;
    color: var(--text-muted);
}

.chat-log {
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.message-group {
    display: flex;
    gap: 16px;
    padding: 6px 10px;
    border-radius: 8px;
    transition: background-color 0.15s ease;
}

.message-group:hover {
    background-color: var(--interactive-hover);
}

.avatar {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
    margin-top: 2px;
}

.message-body {
    flex-grow: 1;
    overflow-wrap: break-word;
}

.message-header {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 4px;
}

.author-name {
    font-weight: 600;
    color: var(--text-header);
    font-size: 15px;
}

.bot-tag {
    background: #5865f2;
    color: #ffffff;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 4px;
    border-radius: 3px;
    vertical-align: middle;
}

.timestamp {
    font-size: 12px;
    color: var(--text-muted);
}

.message-text {
    color: var(--text-normal);
    font-size: 15px;
    white-space: pre-wrap;
    word-break: break-word;
}

.attachment-box {
    margin-top: 8px;
}

.attachment-img {
    max-width: 400px;
    max-height: 300px;
    border-radius: 8px;
    border: 1px solid var(--border-subtle);
}

.embed-box {
    margin-top: 8px;
    background: var(--bg-tertiary);
    border-left: 4px solid var(--brand);
    border-radius: 4px;
    padding: 12px 16px;
    max-width: 550px;
}

.embed-title {
    font-weight: 700;
    color: var(--text-header);
    margin-bottom: 6px;
    font-size: 14px;
}

.embed-desc {
    color: var(--text-normal);
    font-size: 13px;
    white-space: pre-wrap;
}

.footer {
    background: var(--bg-tertiary);
    padding: 12px 24px;
    border-top: 1px solid var(--border-subtle);
    font-size: 12px;
    color: var(--text-muted);
    text-align: center;
}
"""


def _format_markdown(text: str) -> str:
    """Escapes HTML and basic Discord markdown."""
    escaped = html.escape(text)
    # Bold **text**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    # Italic *text*
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    # Inline code `code`
    escaped = re.sub(r"`([^`]+)`", r"<code style='background:#1e1f22;padding:2px 4px;border-radius:4px;font-family:monospace;'>\1</code>", escaped)
    return escaped


async def generate_html_transcript(channel: discord.TextChannel, closer: Optional[discord.User | discord.Member] = None) -> str:
    """Generates a standalone dark-mode HTML transcript of the channel history."""
    messages: List[discord.Message] = []
    async for m in channel.history(limit=500, oldest_first=True):
        messages.append(m)

    guild_name = html.escape(channel.guild.name)
    channel_name = html.escape(channel.name)
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")
    closer_name = html.escape(str(closer)) if closer else "Staff"

    messages_html = []
    for msg in messages:
        author = msg.author
        avatar_url = author.display_avatar.url if author.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
        timestamp = msg.created_at.strftime("%m/%d/%Y %I:%M %p")
        bot_badge = '<span class="bot-tag">BOT</span>' if author.bot else ''
        author_display = html.escape(author.display_name)

        content_html = ""
        if msg.content:
            content_html = f'<div class="message-text">{_format_markdown(msg.content)}</div>'

        attachments_html = ""
        for att in msg.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                attachments_html += f'<div class="attachment-box"><a href="{att.url}" target="_blank"><img class="attachment-img" src="{att.url}" alt="Attachment"></a></div>'
            else:
                attachments_html += f'<div class="attachment-box"><a style="color:#5865f2;" href="{att.url}" target="_blank">📎 {html.escape(att.filename)}</a></div>'

        embeds_html = ""
        for emb in msg.embeds:
            color_hex = f"#{emb.color.value:06x}" if emb.color else "#5865f2"
            emb_title = f'<div class="embed-title">{html.escape(emb.title)}</div>' if emb.title else ""
            emb_desc = f'<div class="embed-desc">{_format_markdown(emb.description)}</div>' if emb.description else ""
            embeds_html += f'<div class="embed-box" style="border-left-color: {color_hex};">{emb_title}{emb_desc}</div>'

        msg_block = f"""
        <div class="message-group">
            <img class="avatar" src="{avatar_url}" alt="Avatar">
            <div class="message-body">
                <div class="message-header">
                    <span class="author-name">{author_display}</span>
                    {bot_badge}
                    <span class="timestamp">{timestamp}</span>
                </div>
                {content_html}
                {attachments_html}
                {embeds_html}
            </div>
        </div>
        """
        messages_html.append(msg_block)

    full_chat = "\n".join(messages_html) if messages_html else "<div style='color:var(--text-muted);padding:20px;text-align:center;'>No messages in ticket history.</div>"

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript: #{channel_name} — {guild_name}</title>
    <style>
{DARK_MODE_CSS}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <div class="header-title">
                    <span>#{channel_name}</span>
                    <span class="badge">Ticket Closed</span>
                </div>
                <div class="meta-stats">Server: {guild_name} • Closed by {closer_name} • {now_str}</div>
            </div>
            <div class="meta-stats">
                <strong>{len(messages)}</strong> messages archived
            </div>
        </div>
        <div class="chat-log">
{full_chat}
        </div>
        <div class="footer">
            ✦ {guild_name} Support Desk • Archived by The Raivora Luxury Sentinel ✦
        </div>
    </div>
</body>
</html>
"""
    return doc
