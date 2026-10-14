"""
MusicMaid — Legal Compliance Documents (Terms of Service & Privacy Policy).
Complies with Discord Developer Terms, GDPR guidelines, and data minimization standards.
"""

TERMS_OF_SERVICE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terms of Service — MusicMaid Discord Bot</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0e14;
            --surface: #141923;
            --border: #1f2736;
            --accent: #00e5ff;
            --text-main: #e2e8f0;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg);
            color: var(--text-main);
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.7;
            padding: 2rem 1rem;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 3rem 2.5rem;
            box-shadow: 0 10px 40px rgba(0, 229, 255, 0.05);
        }
        .header {
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }
        .badge {
            display: inline-block;
            background: rgba(0, 229, 255, 0.1);
            color: var(--accent);
            padding: 0.3rem 0.8rem;
            border-radius: 50px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        h1 {
            font-size: 2.2rem;
            color: #ffffff;
            margin-bottom: 0.5rem;
        }
        .effective-date {
            color: var(--text-muted);
            font-size: 0.95rem;
        }
        h2 {
            font-size: 1.4rem;
            color: #ffffff;
            margin-top: 2rem;
            margin-bottom: 0.8rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        p, li {
            color: var(--text-main);
            font-size: 1.02rem;
            margin-bottom: 1rem;
        }
        ul {
            padding-left: 1.5rem;
            margin-bottom: 1.2rem;
        }
        li {
            margin-bottom: 0.5rem;
        }
        .highlight-box {
            background: rgba(0, 229, 255, 0.05);
            border-left: 4px solid var(--accent);
            padding: 1rem 1.2rem;
            border-radius: 0 8px 8px 0;
            margin: 1.5rem 0;
        }
        a {
            color: var(--accent);
            text-decoration: none;
            transition: opacity 0.2s;
        }
        a:hover {
            opacity: 0.8;
            text-decoration: underline;
        }
        footer {
            margin-top: 3rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: var(--text-muted);
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="badge">Legal Document</span>
            <h1>Terms of Service</h1>
            <div class="effective-date">Last Updated: October 14, 2026 • Version 2.2.0</div>
        </div>

        <h2>1. Acceptance of Terms</h2>
        <p>By inviting, adding, or using <strong>MusicMaid</strong> ("the Bot", "we", "our") in your Discord server or accessing its associated Web Platform, you ("the User") agree to be bound by these Terms of Service. If you do not agree to these terms, please remove the Bot from your Discord server and discontinue use.</p>

        <h2>2. Discord Terms & Community Guidelines</h2>
        <p>MusicMaid operates on the Discord platform. You must comply with all <a href="https://discord.com/terms" target="_blank" rel="noopener">Discord Terms of Service</a> and <a href="https://discord.com/guidelines" target="_blank" rel="noopener">Discord Community Guidelines</a> at all times while using the Bot.</p>

        <h2>3. Use of Service & Music Playback</h2>
        <ul>
            <li><strong>Audio Streaming:</strong> MusicMaid provides high-fidelity audio playback by searching, resolving, and streaming publicly accessible audio from third-party media platforms (including YouTube and SoundCloud).</li>
            <li><strong>Third-Party Compliance:</strong> MusicMaid does not store, host, or distribute pirated or copyrighted audio files. We strictly honor all digital rights management and stream protocols provided by upstream platforms.</li>
            <li><strong>Spotify Integration:</strong> All Spotify link resolutions utilize official open metadata APIs to identify song titles and artists; no audio is ripped or downloaded from Spotify servers.</li>
        </ul>

        <h2>4. Prohibited Activities</h2>
        <p>When using MusicMaid, you agree NOT to:</p>
        <ul>
            <li>Spam, flood, or abuse commands in an attempt to disrupt voice service stability or cause denial-of-service.</li>
            <li>Attempt to reverse-engineer, exploit, or bypass rate limits, DSP equalizers, or platform controls.</li>
            <li>Use the Bot to broadcast illegal content, hate speech, or harassment in violation of Discord's Community Standards.</li>
        </ul>

        <h2>5. Availability and Service Limits</h2>
        <p>MusicMaid is provided on an "as is" and "as available" basis. While we strive for 24/7 continuous uptime, we cannot guarantee uninterrupted service due to potential network delays, third-party platform API changes, or server maintenance. We reserve the right to temporarily pause, update, or modify features without prior notice.</p>

        <h2>6. Termination of Access</h2>
        <p>We reserve the right to block access or restrict command permissions for any Discord server or user that engages in malicious activity, severe abuse, or attempts to disrupt service for other users.</p>

        <h2>7. Contact & Support</h2>
        <p>If you have questions regarding these Terms of Service, please join our official support community or contact the bot development team directly through Discord.</p>

        <footer>
            <div>MusicMaid • 24/7 Hi-Fi Discord Music Bot</div>
            <div><a href="/privacy">Privacy Policy</a></div>
        </footer>
    </div>
</body>
</html>
"""

PRIVACY_POLICY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy — MusicMaid Discord Bot</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0e14;
            --surface: #141923;
            --border: #1f2736;
            --accent: #00e5ff;
            --text-main: #e2e8f0;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg);
            color: var(--text-main);
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.7;
            padding: 2rem 1rem;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 3rem 2.5rem;
            box-shadow: 0 10px 40px rgba(0, 229, 255, 0.05);
        }
        .header {
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }
        .badge {
            display: inline-block;
            background: rgba(0, 229, 255, 0.1);
            color: var(--accent);
            padding: 0.3rem 0.8rem;
            border-radius: 50px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        h1 {
            font-size: 2.2rem;
            color: #ffffff;
            margin-bottom: 0.5rem;
        }
        .effective-date {
            color: var(--text-muted);
            font-size: 0.95rem;
        }
        h2 {
            font-size: 1.4rem;
            color: #ffffff;
            margin-top: 2rem;
            margin-bottom: 0.8rem;
        }
        p, li {
            color: var(--text-main);
            font-size: 1.02rem;
            margin-bottom: 1rem;
        }
        ul {
            padding-left: 1.5rem;
            margin-bottom: 1.2rem;
        }
        li {
            margin-bottom: 0.5rem;
        }
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin: 1.5rem 0;
            background: rgba(11, 14, 20, 0.5);
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border);
        }
        .data-table th, .data-table td {
            padding: 0.9rem 1.1rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
            font-size: 0.95rem;
        }
        .data-table th {
            background: rgba(0, 229, 255, 0.08);
            color: #ffffff;
            font-weight: 600;
        }
        a {
            color: var(--accent);
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        footer {
            margin-top: 3rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: var(--text-muted);
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="badge">Privacy Policy</span>
            <h1>Privacy Policy</h1>
            <div class="effective-date">Last Updated: October 14, 2026 • Compliant with Discord Developer Policy</div>
        </div>

        <p>This Privacy Policy explains how <strong>MusicMaid</strong> ("we", "our", or "the Bot") collects, uses, stores, and protects user and server data when you use our Discord bot application and associated web interfaces.</p>

        <h2>1. Data Minimization Commitment</h2>
        <p>We believe in strict data minimization. MusicMaid only processes the minimum data strictly required to deliver music playback, manage server song queues, and remember audio equalizer preferences.</p>

        <h2>2. Information We Collect</h2>
        <table class="data-table">
            <thead>
                <tr>
                    <th>Data Type</th>
                    <th>Purpose</th>
                    <th>Retention Period</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Server ID (Guild ID)</strong></td>
                    <td>Associating active voice sessions, volume settings, and queues with your Discord server.</td>
                    <td>Maintained while bot is in server. Cleared upon bot removal.</td>
                </tr>
                <tr>
                    <td><strong>Channel ID</strong></td>
                    <td>Sending interactive Now Playing panels and error alerts to the designated voice/text channel.</td>
                    <td>Transient session storage.</td>
                </tr>
                <tr>
                    <td><strong>User ID</strong></td>
                    <td>Attributing song requester names and saving personal favorite tracks if explicitly saved.</td>
                    <td>Until removed by user or guild.</td>
                </tr>
                <tr>
                    <td><strong>Song History & Queues</strong></td>
                    <td>Displaying recent songs and allowing queue resumption after network reconnection.</td>
                    <td>Stored in encrypted local SQLite database.</td>
                </tr>
            </tbody>
        </table>

        <h2>3. What We NEVER Collect</h2>
        <ul>
            <li>We do <strong>NOT</strong> record, listen to, or store any voice transmissions, conversations, or microphones.</li>
            <li>We do <strong>NOT</strong> collect or read personal direct messages (DMs).</li>
            <li>We do <strong>NOT</strong> collect personal identifying information (e.g., real names, email addresses, phone numbers, passwords, IP addresses).</li>
            <li>We do <strong>NOT</strong> sell, rent, or trade your data with any third-party brokers or advertisers.</li>
        </ul>

        <h2>4. Third-Party Services</h2>
        <p>To resolve requested music streams, MusicMaid communicates with third-party service APIs:</p>
        <ul>
            <li><strong>Discord API:</strong> Voice gateway signaling and slash command delivery.</li>
            <li><strong>YouTube / SoundCloud:</strong> Resolving public audio streams requested by users.</li>
            <li><strong>Spotify API:</strong> Fetching song titles and artist names for query matching.</li>
        </ul>

        <h2>5. Data Deletion & User Rights</h2>
        <p>You have full ownership of your data:</p>
        <ul>
            <li><strong>Automatic Deletion:</strong> Kicking or removing MusicMaid from your Discord server permanently cleans all stored server session states.</li>
            <li><strong>Manual Deletion:</strong> Server administrators can clear all stored queue history at any time using <code>/playlist clear</code> or <code>/settings reset</code>.</li>
            <li><strong>Direct Request:</strong> To request immediate deletion of any associated data, please contact the developer via Discord.</li>
        </ul>

        <h2>6. Changes to this Policy</h2>
        <p>We may periodically update this Privacy Policy to reflect feature additions or Discord API requirements. Any changes will be published here with an updated "Last Updated" timestamp.</p>

        <footer>
            <div>MusicMaid • Safe & Transparent Audio Engine</div>
            <div><a href="/terms">Terms of Service</a></div>
        </footer>
    </div>
</body>
</html>
"""
