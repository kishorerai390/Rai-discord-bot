import unittest
from unittest.mock import MagicMock
import discord

from utils.permissions import is_admin_or_owner, is_founder_or_owner, is_guild_owner


class TestMajorPermissionsLockdown(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.owner_id = 1457380609641938981  # rf.rai_006

    def test_owner_is_granted_access(self):
        owner = MagicMock(spec=discord.Member)
        owner.id = 1457380609641938981
        owner.guild = self.guild
        owner.roles = []

        self.assertTrue(is_founder_or_owner(owner))

    def test_bot_itself_is_granted_access(self):
        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 1554732669072445532
        bot_member.guild = self.guild
        bot_member.roles = []
        self.guild.me = bot_member

        self.assertTrue(is_founder_or_owner(bot_member))

    def test_founder_role_holder_is_granted_access_by_name(self):
        founder_member = MagicMock(spec=discord.Member)
        founder_member.id = 999111222
        founder_member.guild = self.guild

        role = MagicMock(spec=discord.Role)
        role.id = 1111111111111
        role.name = "👑 ┆ 𝐅𝐎𝐔𝐍𝐃𝐄𝐑 🍷"
        founder_member.roles = [role]

        self.assertTrue(is_founder_or_owner(founder_member))

    def test_founder_role_holder_is_granted_access_by_id(self):
        founder_member = MagicMock(spec=discord.Member)
        founder_member.id = 999111222
        founder_member.guild = self.guild

        role = MagicMock(spec=discord.Role)
        role.id = 1545494610489643038  # exact FOUNDER_ROLE_ID
        role.name = "Custom Role"
        founder_member.roles = [role]

        self.assertTrue(is_founder_or_owner(founder_member))

    def test_discord_admin_without_founder_is_denied_access(self):
        admin_member = MagicMock(spec=discord.Member)
        admin_member.id = 888222333
        admin_member.guild = self.guild

        admin_role = MagicMock(spec=discord.Role)
        admin_role.id = 22222222
        admin_role.name = "⚡ ┆ 𝐇𝐄𝐀𝐃 𝐀𝐃𝐌𝐈𝐍 ⚡"
        admin_member.roles = [admin_role]
        admin_member.guild_permissions = discord.Permissions(administrator=True)

        # Must be strictly FALSE — major commands locked only to founder
        self.assertFalse(is_founder_or_owner(admin_member))

    def test_regular_moderator_is_denied_access(self):
        mod_member = MagicMock(spec=discord.Member)
        mod_member.id = 777333444
        mod_member.guild = self.guild

        mod_role = MagicMock(spec=discord.Role)
        mod_role.id = 33333333
        mod_role.name = "🛡️ ┆ 𝐌𝐎𝐃𝐄𝐑𝐀𝐓𝐎𝐑 🛡️"
        mod_member.roles = [mod_role]
        mod_member.guild_permissions = discord.Permissions(ban_members=True, kick_members=True)

        self.assertFalse(is_founder_or_owner(mod_member))

    async def test_slash_command_predicate_enforcement(self):
        # Apply decorator to a dummy function to retrieve the predicate
        decorator = is_admin_or_owner()
        def dummy_cmd():
            pass
        wrapped = decorator(dummy_cmd)
        predicate = wrapped.__discord_app_commands_checks__[0]

        # Interaction by owner
        interaction_owner = MagicMock(spec=discord.Interaction)
        interaction_owner.guild = self.guild
        interaction_owner.user = MagicMock(spec=discord.Member)
        interaction_owner.user.id = 1457380609641938981
        interaction_owner.user.guild = self.guild
        interaction_owner.user.roles = []

        self.assertTrue(await predicate(interaction_owner))

        # Interaction by regular Admin
        interaction_admin = MagicMock(spec=discord.Interaction)
        interaction_admin.guild = self.guild
        interaction_admin.user = MagicMock(spec=discord.Member)
        interaction_admin.user.id = 555666777
        interaction_admin.user.guild = self.guild
        admin_role = MagicMock(spec=discord.Role)
        admin_role.id = 44444444
        admin_role.name = "Admin"
        interaction_admin.user.roles = [admin_role]
        interaction_admin.user.guild_permissions = discord.Permissions(administrator=True)

        self.assertFalse(await predicate(interaction_admin))


if __name__ == "__main__":
    unittest.main()
