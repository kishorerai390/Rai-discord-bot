"""
Unit and Integration Tests for Rai Community OS Web Platform and Shared API.
Tests all endpoints, database operations, auth workflows, outbox sync, and privacy gates.
"""

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiohttp
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from config import COMMUNITY_GUILD_ID
from database.database import Database
from web.server import RaiCommunityOSServer
from web.auth import SESSION_COOKIE_NAME


class TestRaiCommunityWebPlatform(AioHTTPTestCase):
    """Integration test suite for the Rai Community OS Web Platform."""

    async def get_application(self) -> web.Application:
        # Create unique temp db directory for complete isolation
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_community_web.db"
        self.db = Database(self.db_path)
        await self.db.connect()

        # Mock bot instance
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.latency = 0.042
        self.bot.guilds = [MagicMock()]
        self.bot.tree.get_commands.return_value = [MagicMock() for _ in range(70)]

        # Mock guild for permissions
        self.guild = MagicMock()
        self.guild.id = COMMUNITY_GUILD_ID
        self.guild.owner_id = 999999
        self.bot.get_guild.return_value = self.guild

        # Instantiate Server
        self.server = RaiCommunityOSServer(bot=self.bot, db=self.db, port=8099)
        app = web.Application()
        self.server.setup_routes(app)
        return app

    async def tearDownAsync(self) -> None:
        try:
            await super().tearDownAsync()
        except Exception:
            pass
        await self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @unittest_run_loop
    async def test_01_ui_routes_render_html(self):
        """Verify UI routes return HTTP 200 with HTML content."""
        routes = ["/", "/discover", "/brain", "/projects", "/creators", "/gaming", "/resources", "/events", "/status"]
        for r in routes:
            resp = await self.client.get(r)
            self.assertEqual(resp.status, 200)
            text = await resp.text()
            self.assertIn("RAI COMMUNITY OS", text)

    @unittest_run_loop
    async def test_02_telemetry_stats_and_health(self):
        """Verify /api/stats and /health return valid data."""
        resp = await self.client.get("/api/stats")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["status"], "online")
        self.assertIn("ping_ms", data["data"])

        h_resp = await self.client.get("/health")
        self.assertEqual(h_resp.status, 200)
        h_data = await h_resp.json()
        self.assertEqual(h_data["status"], "healthy")

    @unittest_run_loop
    async def test_03_auth_dev_login_and_session(self):
        """Verify dev login creates a valid session, cookie, and user state."""
        # Unauthenticated state
        me_resp = await self.client.get("/api/auth/me")
        me_data = await me_resp.json()
        self.assertFalse(me_data["data"]["authenticated"])

        # Dev Login
        login_resp = await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 12345678, "username": "TestGamer", "is_admin": True},
        )
        self.assertEqual(login_resp.status, 200)
        login_data = await login_resp.json()
        self.assertTrue(login_data["success"])
        self.assertIn("session_id", login_data["data"])

        # Verify authenticated state
        me_resp2 = await self.client.get("/api/auth/me")
        me_data2 = await me_resp2.json()
        self.assertTrue(me_data2["data"]["authenticated"])
        self.assertEqual(me_data2["data"]["user"]["username"], "TestGamer")
        self.assertTrue(me_data2["data"]["user"]["is_admin"])

        # Logout
        logout_resp = await self.client.post("/api/auth/logout")
        self.assertEqual(logout_resp.status, 200)

        # Confirm logged out
        me_resp3 = await self.client.get("/api/auth/me")
        me_data3 = await me_resp3.json()
        self.assertFalse(me_data3["data"]["authenticated"])

    @unittest_run_loop
    async def test_04_profile_management_and_privacy(self):
        """Verify profile updating and privacy controls."""
        # Authenticate as User A
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 11111, "username": "UserAlpha", "is_admin": False},
        )

        # Update profile
        update_resp = await self.client.put(
            "/api/profiles/me",
            json={
                "bio": "Lead Editor and Motion Designer",
                "skills": "After Effects, Premiere, FL Studio",
                "interests": "Montages, Cyberpunk, Valorant",
                "is_visible": 1,
            },
        )
        self.assertEqual(update_resp.status, 200)
        u_data = await update_resp.json()
        self.assertEqual(u_data["data"]["bio"], "Lead Editor and Motion Designer")

        # Get own profile
        prof_resp = await self.client.get("/api/profiles/11111")
        self.assertEqual(prof_resp.status, 200)
        p_data = await prof_resp.json()
        self.assertTrue(p_data["data"]["is_self"])

        # Set to private (0)
        await self.client.put("/api/profiles/me", json={"is_visible": 0})

        # Switch to User B
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 22222, "username": "UserBeta", "is_admin": False},
        )

        # User B trying to view User A's private profile should be rejected (403)
        p_resp2 = await self.client.get("/api/profiles/11111")
        self.assertEqual(p_resp2.status, 403)

    @unittest_run_loop
    async def test_05_projects_tasks_and_outbox_sync(self):
        """Verify project creation, Kanban task workflow, and sync outbox enqueuing."""
        # Authenticate
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 33333, "username": "ProjectDirector", "is_admin": False},
        )

        # Create Project
        p_resp = await self.client.post(
            "/api/projects",
            json={"name": "Cyberpunk AMV Montage", "project_type": "creator"},
        )
        self.assertEqual(p_resp.status, 201)
        p_data = await p_resp.json()
        proj_id = p_data["data"]["id"]
        self.assertEqual(p_data["data"]["sync_status"], "DISCORD_SYNC_QUEUED")

        # Verify sync outbox has event
        pending_events = await self.db.fetch_pending_sync_events()
        self.assertTrue(len(pending_events) >= 1)
        self.assertEqual(pending_events[0]["event_type"], "PROJECT_CREATED")

        # Create Task
        t_resp = await self.client.post(
            f"/api/projects/{proj_id}/tasks",
            json={"title": "Rough Cut Export", "status": "TODO", "priority": "HIGH"},
        )
        self.assertEqual(t_resp.status, 201)
        task_id = (await t_resp.json())["data"]["id"]

        # Advance Task to IN_PROGRESS then DONE
        await self.client.put(f"/api/projects/{proj_id}/tasks/{task_id}", json={"status": "IN_PROGRESS"})
        await self.client.put(f"/api/projects/{proj_id}/tasks/{task_id}", json={"status": "DONE"})

        # Get Project Details
        proj_details_resp = await self.client.get(f"/api/projects/{proj_id}")
        self.assertEqual(proj_details_resp.status, 200)
        proj_details = await proj_details_resp.json()
        tasks = proj_details["data"]["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "DONE")

    @unittest_run_loop
    async def test_06_creator_portfolios(self):
        """Verify publishing creator portfolio entries."""
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 44444, "username": "VisualArtist", "is_admin": False},
        )

        resp = await self.client.post(
            "/api/creators/portfolio",
            json={
                "title": "Neon Grid 3D Animation",
                "category": "3D & Animation",
                "description": "Blender cycles render with custom procedural shaders.",
                "tools_used": "Blender, After Effects",
                "tags": "3d,neon,cyberpunk",
                "external_links": "https://artstation.com/example",
            },
        )
        self.assertEqual(resp.status, 201)

        # List portfolios
        c_resp = await self.client.get("/api/creators")
        self.assertEqual(c_resp.status, 200)
        c_data = await c_resp.json()
        self.assertTrue(len(c_data["data"]) >= 1)
        self.assertEqual(c_data["data"][0]["title"], "Neon Grid 3D Animation")

    @unittest_run_loop
    async def test_07_gaming_lfg_hub(self):
        """Verify posting and joining LFG squads."""
        # Host posts LFG
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 55555, "username": "SquadCaptain", "is_admin": False},
        )
        post_resp = await self.client.post(
            "/api/gaming/lfg",
            json={
                "game": "Free Fire",
                "role": "Ranked Squad",
                "note": "Need 3 players with mic for push",
                "max_players": 4,
            },
        )
        self.assertEqual(post_resp.status, 201)
        lfg_id = (await post_resp.json())["data"]["id"]

        # Teammate joins squad
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 66666, "username": "TeammateOne", "is_admin": False},
        )
        join_resp = await self.client.post(f"/api/gaming/lfg/{lfg_id}/join")
        self.assertEqual(join_resp.status, 200)
        j_data = await join_resp.json()
        self.assertIn(66666, j_data["data"]["current_players"])

    @unittest_run_loop
    async def test_08_community_events_and_rsvp(self):
        """Verify listing events and RSVP actions."""
        # Create event directly in DB
        ev_id = await self.db.create_community_event(
            guild_id=COMMUNITY_GUILD_ID,
            title="RAI Community Tournament",
            event_type="gaming",
            start_time="2026-10-15 18:00 UTC",
            description="All-star gaming championship with prizes.",
            creator_id=77777,
        )

        # User RSVPs
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 88888, "username": "AttendeeBob", "is_admin": False},
        )
        rsvp_resp = await self.client.post(f"/api/events/{ev_id}/rsvp")
        self.assertEqual(rsvp_resp.status, 200)
        r_data = await rsvp_resp.json()
        self.assertTrue(r_data["data"]["rsvpd"])

        # Check participants
        ev_list_resp = await self.client.get("/api/events")
        ev_list = await ev_list_resp.json()
        match = [e for e in ev_list["data"] if e["id"] == ev_id]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["attendees_count"], 1)

    @unittest_run_loop
    async def test_09_resource_library(self):
        """Verify submitting and retrieving community resources."""
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 99999, "username": "ResourceGuru", "is_admin": False},
        )
        sub_resp = await self.client.post(
            "/api/resources",
            json={
                "title": "Cinematic Sound Effects Pack",
                "category": "Editing",
                "description": "50+ royalty free whooshes, impacts and risers.",
                "link": "https://example.com/sfx.zip",
            },
        )
        self.assertEqual(sub_resp.status, 201)

        # List resources
        res_list = await self.client.get("/api/resources?category=Editing")
        data = await res_list.json()
        self.assertTrue(len(data["data"]) >= 1)
        self.assertEqual(data["data"][0]["title"], "Cinematic Sound Effects Pack")

    @unittest_run_loop
    async def test_10_idea_board_and_voting(self):
        """Verify idea proposal, upvoting, and comments."""
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 10101, "username": "ThinkerOne", "is_admin": False},
        )
        idea_resp = await self.client.post(
            "/api/ideas",
            json={
                "title": "Add Monthly Lofi Chill Nights",
                "category": "Events",
                "description": "Weekly casual music sharing and listening room.",
            },
        )
        self.assertEqual(idea_resp.status, 201)
        idea_id = (await idea_resp.json())["data"]["id"]

        # Voter two votes
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 20202, "username": "VoterTwo", "is_admin": False},
        )
        vote_resp = await self.client.post(f"/api/ideas/{idea_id}/vote", json={"direction": 1})
        self.assertEqual(vote_resp.status, 200)

        # Comment on idea
        comm_resp = await self.client.post(
            f"/api/ideas/{idea_id}/comment",
            json={"content": "Great idea! I can DJ some tracks."},
        )
        self.assertEqual(comm_resp.status, 201)

        # List comments
        comments_resp = await self.client.get(f"/api/ideas/{idea_id}/comments")
        c_data = await comments_resp.json()
        self.assertEqual(len(c_data["data"]), 1)
        self.assertEqual(c_data["data"][0]["author_name"], "VoterTwo")

    @unittest_run_loop
    async def test_11_rai_brain_knowledge_search(self):
        """Verify Rai Brain search indexes wiki, resources, and knowledge with citations."""
        # Add a wiki guide
        await self.db.get_or_create_wiki_article(
            slug="editing-workflow",
            title="Video Editing Workflow Guidelines",
            category="Tutorials",
            content="Always organize project assets, proxy 4K clips, and export ProRes master files.",
        )

        brain_resp = await self.client.get("/api/brain/search?q=editing")
        self.assertEqual(brain_resp.status, 200)
        data = await brain_resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["total_matches"] >= 1)
        self.assertTrue(len(data["data"]["citations"]) >= 1)

    @unittest_run_loop
    async def test_12_mission_control_and_doctor_diagnostics(self):
        """Verify staff mission control overview, emergency safe mode, and doctor probes."""
        # Regular user should be forbidden (403)
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 30303, "username": "RegularMember", "is_admin": False},
        )
        mc_resp = await self.client.get("/api/mission-control/overview")
        self.assertEqual(mc_resp.status, 403)

        # Staff user authorized (200)
        await self.client.post(
            "/api/auth/dev-login",
            json={"user_id": 40404, "username": "AdminCommander", "is_admin": True},
        )
        mc_resp2 = await self.client.get("/api/mission-control/overview")
        self.assertEqual(mc_resp2.status, 200)

        # Toggle emergency safe mode
        em_resp = await self.client.post("/api/mission-control/emergency", json={"enabled": True})
        self.assertEqual(em_resp.status, 200)
        em_data = await em_resp.json()
        self.assertTrue(em_data["data"]["safe_mode_active"])

        # Rai doctor endpoint
        doc_resp = await self.client.get("/api/doctor")
        self.assertEqual(doc_resp.status, 200)
        doc_data = await doc_resp.json()
        self.assertTrue(doc_data["success"])

    @unittest_run_loop
    async def test_13_community_constellation_graph(self):
        """Verify Constellation visualizer returns valid nodes and links."""
        res = await self.client.get("/api/labs/constellation")
        self.assertEqual(res.status, 200)
        data = await res.json()
        self.assertTrue(data["success"])
        self.assertIn("nodes", data["data"])
        self.assertIn("links", data["data"])
        self.assertTrue(len(data["data"]["nodes"]) >= 1)


if __name__ == "__main__":
    unittest.main()
