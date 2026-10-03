"""
RAI Music Resolver Service.
Resolves track candidates or direct URLs into verified playable audio streams,
enforcing source pre-flight validation and generating structured diagnostic reports.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional, Tuple, Union

import discord

from music.provider import (
    MusicDiagnosticReport,
    MusicErrorCode,
    MusicProvider,
    QueryType,
    ResolutionResult,
    ResolvedTrack,
    TrackCandidate,
    generate_music_diagnostic_id,
)
from music.providers.direct import DirectAudioProvider
from music.providers.soundcloud import SoundCloudMusicProvider
from music.providers.youtube import YouTubeMusicProvider
from music.search_service import MusicSearchService

logger = logging.getLogger("Rai.MusicResolverService")


class MusicResolverService:
    """Validates and resolves candidates and URLs into playable audio sources."""

    def __init__(self, search_service: Optional[MusicSearchService] = None):
        self.search_service = search_service or MusicSearchService()

    async def resolve_track(
        self,
        target: Union[str, TrackCandidate],
        requester: discord.Member,
        guild_id: int,
        voice_channel_id: Optional[int] = None,
        bot: Optional[discord.Client] = None,
    ) -> ResolutionResult:
        """
        Takes candidate or URL, resolves playable stream, validates source integrity,
        and logs internal diagnostics upon failure.
        """
        request_id = uuid.uuid4().hex[:12]
        diagnostic_id = generate_music_diagnostic_id()

        if isinstance(target, TrackCandidate):
            query = target.url
            query_type = QueryType.DIRECT_URL
            candidate = target
        else:
            query = str(target).strip()
            query_type, _ = self.search_service.classify_query(query)
            candidate = None

        # 1. Identify provider
        provider = self.search_service.get_supported_provider(query, query_type)
        if not provider:
            diag = MusicDiagnosticReport(
                diagnostic_id=diagnostic_id,
                music_request_id=request_id,
                guild_id=guild_id,
                user_id=requester.id,
                voice_channel_id=voice_channel_id,
                query=query,
                query_type=query_type,
                provider="None",
                stage="PROVIDER_LOOKUP",
                error_code=MusicErrorCode.UNSUPPORTED_URL,
                error_message="No configured provider supports this query or URL.",
            )
            diag.log_and_report(bot)
            return ResolutionResult(
                is_success=False,
                diagnostic=diag,
                error_code=MusicErrorCode.UNSUPPORTED_URL,
                user_message=f"❌ This URL or format is not supported by configured music providers.\n\nDiagnostic: `{diagnostic_id}`",
            )

        # 2. Resolve stream URL
        resolved: Optional[ResolvedTrack] = None
        try:
            resolved = await provider.resolve(candidate or query, requester=requester)
        except Exception as exc:
            err_msg = str(exc)
            code = MusicErrorCode.SOURCE_RESOLUTION_FAILED
            if "bot" in err_msg.lower() or "403" in err_msg.lower():
                code = MusicErrorCode.PROVIDER_BLOCKED
            elif "timed out" in err_msg.lower() or "connection" in err_msg.lower():
                code = MusicErrorCode.NETWORK_ERROR

            diag = MusicDiagnosticReport(
                diagnostic_id=diagnostic_id,
                music_request_id=request_id,
                guild_id=guild_id,
                user_id=requester.id,
                voice_channel_id=voice_channel_id,
                query=query,
                query_type=query_type,
                provider=provider.name,
                stage="SOURCE_RESOLUTION",
                error_code=code,
                error_message=err_msg,
            )
            diag.log_and_report(bot)
            return ResolutionResult(
                is_success=False,
                diagnostic=diag,
                error_code=code,
                user_message=f"❌ Failed to extract audio stream from {provider.name}.\n\nDiagnostic: `{diagnostic_id}`",
            )

        # 3. Validate source stream integrity
        if not resolved or not resolved.stream_url:
            diag = MusicDiagnosticReport(
                diagnostic_id=diagnostic_id,
                music_request_id=request_id,
                guild_id=guild_id,
                user_id=requester.id,
                voice_channel_id=voice_channel_id,
                query=query,
                query_type=query_type,
                provider=provider.name,
                stage="STREAM_VALIDATION",
                error_code=MusicErrorCode.SOURCE_RESOLUTION_FAILED,
                error_message="Provider returned empty or invalid stream URL.",
            )
            diag.log_and_report(bot)
            return ResolutionResult(
                is_success=False,
                diagnostic=diag,
                error_code=MusicErrorCode.SOURCE_RESOLUTION_FAILED,
                user_message=f"❌ Could not resolve a playable audio stream for this track.\n\nDiagnostic: `{diagnostic_id}`",
            )

        return ResolutionResult(
            is_success=True,
            track=resolved,
            error_code=MusicErrorCode.SUCCESS,
        )
