import os
import random
import asyncio
import aiohttp
import nextcord
from nextcord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import sys
import json
import logging
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
import traceback

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('moderation_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

@dataclass
class BotConfig:
    log_channel_id: int = 0
    min_mute_duration_minutes: int = 30
    max_mute_duration_minutes: int = 60
    target_server_id: int = 0
    bypass_roles_ids: List[int] = None
    
    def __post_init__(self):
        if self.bypass_roles_ids is None:
            self.bypass_roles_ids = []

class ConfigManager:
    def __init__(self, config_file: str = 'bot_config.json'):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> BotConfig:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return BotConfig(**data)
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Error loading config file: {e}")
                return BotConfig()
        return BotConfig()
    
    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config.__dict__, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving config file: {e}")
    
    def update_config(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.save_config()

class ModerationAPI:
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={'User-Agent': 'DiscordModerationBot/1.0'}
            )
        return self.session
    
    async def analyze_text(self, text: str, retries: int = 3, backoff_factor: float = 0.5) -> Dict[str, Any]:
        if not self.api_key:
            logger.error("API_KEY not found in environment variables.")
            return {"error": "API_KEY not configured."}
        
        session = await self.get_session()
        target_url = f"{self.api_url}?text={text}&api_key={self.api_key}"
        
        logger.debug(f"API URL constructed: {target_url}")
        
        for attempt in range(retries):
            try:
                async with session.get(target_url) as response:
                    response_text = await response.text()
                    
                    if response.status >= 500:
                        logger.warning(f"API Server Error ({response.status}) on attempt {attempt + 1}/{retries}. Retrying...")
                        if attempt < retries - 1:
                            await asyncio.sleep(backoff_factor * (2 ** attempt))
                            continue
                    
                    if response.status >= 400:
                        logger.error(f"API Client Error ({response.status}): {response_text}")
                        return {"error": f"API Client Error: {response.status}"}
                    
                    try:
                        return json.loads(response_text)
                    except json.JSONDecodeError:
                        logger.error(f"API response is not valid JSON: {response_text}")
                        return {"error": "API response is not valid JSON"}
                        
            except aiohttp.ClientResponseError as e:
                logger.error(f"API HTTP Error: Status {e.status}, Message: '{e.message}'")
                if 400 <= e.status < 500:
                    return {"error": f"API Client Error: {e.status} - {e.message}"}
                elif e.status >= 500 and attempt < retries - 1:
                    await asyncio.sleep(backoff_factor * (2 ** attempt))
                    continue
                    
            except aiohttp.ClientConnectorError as e:
                logger.error(f"API Connection Error: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(backoff_factor * (2 ** attempt))
                    continue
                return {"error": "API connection error"}
                
            except Exception as e:
                logger.error(f"Unexpected error during API call: {e}")
                logger.error(traceback.format_exc())
                return {"error": "Unexpected API error"}
        
        logger.error(f"Failed to get successful response from API after {retries} attempts.")
        return {"error": "API call failed after multiple retries"}
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

class ModerationBot(commands.Bot):
    def __init__(self):
        intents = nextcord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        
        super().__init__(command_prefix="!", intents=intents)
        
        self.config_manager = ConfigManager()
        self.moderation_api = ModerationAPI(
            api_url=os.getenv("API_URL_BASE", "https://test-hub.kys.gay/api/moderate_words/analyze"),
            api_key=os.getenv("API_KEY")
        )
        
        self.user_cooldowns: Dict[int, float] = {}
        self.cooldown_duration_seconds = 5
        
        self.load_commands()
    
    def load_commands(self):
        
        @self.slash_command(name="set_log_channel", description="Set the moderation log channel.")
        @commands.has_permissions(manage_guild=True)
        async def set_log_channel(interaction: nextcord.Interaction, channel: nextcord.TextChannel):
            old_channel_id = self.config_manager.config.log_channel_id
            self.config_manager.update_config(log_channel_id=channel.id)
            
            old_channel_name = self.get_channel(old_channel_id).name if old_channel_id != 0 and self.get_channel(old_channel_id) else "not set"
            
            await interaction.response.send_message(
                f"Moderation log channel updated from `#{old_channel_name}` to `#{channel.name}`.",
                ephemeral=True
            )
            logger.info(f"Log channel updated to {channel.name} (ID: {channel.id}) by {interaction.user.display_name}.")
        
        @set_log_channel.error
        async def set_log_channel_error(interaction: nextcord.Interaction, error: commands.CommandError):
            if isinstance(error, commands.MissingPermissions):
                await interaction.response.send_message("You don't have permission to use this command. You need the 'Manage Guild' permission.", ephemeral=True)
            else:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        
        @self.slash_command(name="set_mute_duration", description="Set min and max random mute duration in minutes.")
        @commands.has_permissions(manage_guild=True)
        async def set_mute_duration(interaction: nextcord.Interaction, min_minutes: int, max_minutes: int):
            if min_minutes < 1 or max_minutes < 1:
                await interaction.response.send_message("Mute durations must be at least 1 minute.", ephemeral=True)
                return
            if min_minutes > max_minutes:
                await interaction.response.send_message("Minimum duration cannot be greater than maximum duration.", ephemeral=True)
                return
            
            old_min = self.config_manager.config.min_mute_duration_minutes
            old_max = self.config_manager.config.max_mute_duration_minutes
            
            self.config_manager.update_config(
                min_mute_duration_minutes=min_minutes,
                max_mute_duration_minutes=max_minutes
            )
            
            await interaction.response.send_message(
                f"Mute duration range updated from `{old_min}-{old_max}` minutes to `{min_minutes}-{max_minutes}` minutes.",
                ephemeral=True
            )
            logger.info(f"Mute duration updated to {min_minutes}-{max_minutes} minutes by {interaction.user.display_name}.")
        
        @set_mute_duration.error
        async def set_mute_duration_error(interaction: nextcord.Interaction, error: commands.CommandError):
            if isinstance(error, commands.MissingPermissions):
                await interaction.response.send_message("You don't have permission to use this command. You need the 'Manage Guild' permission.", ephemeral=True)
            elif isinstance(error, commands.BadArgument):
                await interaction.response.send_message("Invalid arguments. Please provide two integers for min and max minutes (e.g., `/set_mute_duration 30 60`).", ephemeral=True)
            else:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        
        @self.slash_command(name="set_target_server", description="Configure bot to monitor only one server (0 for all).")
        @commands.has_permissions(manage_guild=True)
        async def set_target_server(interaction: nextcord.Interaction, server_id: str):
            try:
                server_id_int = int(server_id)
            except ValueError:
                await interaction.response.send_message("Invalid server ID. Please provide a valid numeric ID or '0'.", ephemeral=True)
                return
            
            old_server_id = self.config_manager.config.target_server_id
            self.config_manager.update_config(target_server_id=server_id_int)
            
            old_server_name = self.get_guild(old_server_id).name if old_server_id != 0 and self.get_guild(old_server_id) else "all servers"
            new_server_name = self.get_guild(server_id_int).name if server_id_int != 0 and self.get_guild(server_id_int) else "all servers"
            
            await interaction.response.send_message(
                f"Target server for monitoring updated from `{old_server_name}` (ID: {old_server_id}) to `{new_server_name}` (ID: {server_id_int}).",
                ephemeral=True
            )
            logger.info(f"Target server updated to {server_id_int} by {interaction.user.display_name}.")
        
        @set_target_server.error
        async def set_target_server_error(interaction: nextcord.Interaction, error: commands.CommandError):
            if isinstance(error, commands.MissingPermissions):
                await interaction.response.send_message("You don't have permission to use this command. You need the 'Manage Guild' permission.", ephemeral=True)
            else:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        
        @self.slash_command(name="add_bypass_role", description="Add a role to bypass moderation.")
        @commands.has_permissions(manage_guild=True)
        async def add_bypass_role(interaction: nextcord.Interaction, role: nextcord.Role):
            if role.id in self.config_manager.config.bypass_roles_ids:
                await interaction.response.send_message(f"Role `{role.name}` is already in the bypass list.", ephemeral=True)
                return
            
            self.config_manager.config.bypass_roles_ids.append(role.id)
            self.config_manager.save_config()
            
            await interaction.response.send_message(
                f"Role `{role.name}` added to bypass list. Members with this role will not be moderated.",
                ephemeral=True
            )
            logger.info(f"Role {role.name} (ID: {role.id}) added to bypass list by {interaction.user.display_name}.")
        
        @add_bypass_role.error
        async def add_bypass_role_error(interaction: nextcord.Interaction, error: commands.CommandError):
            if isinstance(error, commands.MissingPermissions):
                await interaction.response.send_message("You don't have permission to use this command. You need the 'Manage Guild' permission.", ephemeral=True)
            elif isinstance(error, commands.BadArgument):
                await interaction.response.send_message("Invalid role. Please mention a role (e.g., `@Moderators`).", ephemeral=True)
            else:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        
        @self.slash_command(name="remove_bypass_role", description="Remove a role from the bypass list.")
        @commands.has_permissions(manage_guild=True)
        async def remove_bypass_role(interaction: nextcord.Interaction, role: nextcord.Role):
            if role.id not in self.config_manager.config.bypass_roles_ids:
                await interaction.response.send_message(f"Role `{role.name}` is not in the bypass list.", ephemeral=True)
                return
            
            self.config_manager.config.bypass_roles_ids.remove(role.id)
            self.config_manager.save_config()
            
            await interaction.response.send_message(
                f"Role `{role.name}` removed from bypass list.",
                ephemeral=True
            )
            logger.info(f"Role {role.name} (ID: {role.id}) removed from bypass list by {interaction.user.display_name}.")
        
        @remove_bypass_role.error
        async def remove_bypass_role_error(interaction: nextcord.Interaction, error: commands.CommandError):
            if isinstance(error, commands.MissingPermissions):
                await interaction.response.send_message("You don't have permission to use this command. You need the 'Manage Guild' permission.", ephemeral=True)
            else:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        
        @self.slash_command(name="config_status", description="Show current bot configuration.")
        @commands.has_permissions(manage_guild=True)
        async def config_status(interaction: nextcord.Interaction):
            config = self.config_manager.config
            
            embed = nextcord.Embed(
                title="🔧 Bot Configuration Status",
                color=nextcord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            log_channel = self.get_channel(config.log_channel_id)
            log_channel_name = log_channel.name if log_channel else "Not set"
            
            target_server = self.get_guild(config.target_server_id)
            target_server_name = target_server.name if target_server else "All servers"
            
            bypass_roles = []
            for role_id in config.bypass_roles_ids:
                role = interaction.guild.get_role(role_id) if interaction.guild else None
                if role:
                    bypass_roles.append(role.name)
            
            embed.add_field(name="Log Channel", value=f"#{log_channel_name}", inline=True)
            embed.add_field(name="Mute Duration", value=f"{config.min_mute_duration_minutes}-{config.max_mute_duration_minutes} minutes", inline=True)
            embed.add_field(name="Target Server", value=target_server_name, inline=True)
            embed.add_field(name="Bypass Roles", value=", ".join(bypass_roles) if bypass_roles else "None", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def timeout_user(self, member: nextcord.Member, duration_minutes: int, reason: str) -> bool:
        try:
            if not member.guild.me.guild_permissions.moderate_members:
                logger.error(f"Bot lacks 'Moderate Members' permission in guild '{member.guild.name}'. Cannot timeout {member.display_name}.")
                await self.send_dm_to_user(member, f"I tried to timeout you in **{member.guild.name}** but I don't have the necessary permissions (`Moderate Members`). Please contact a server administrator.")
                return False
            
            timeout_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            await member.timeout(timeout_until, reason=reason)
            logger.info(f"Timed out {member.display_name} for {duration_minutes} minutes.")
            return True
            
        except nextcord.Forbidden:
            logger.error(f"Bot doesn't have permissions to timeout {member.display_name}. (Discord Forbidden Error)")
            return False
        except Exception as e:
            logger.error(f"Error occurred while timing out {member.display_name}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def send_dm_to_user(self, user: nextcord.User, message_content: str) -> bool:
        try:
            await user.send(message_content)
            logger.info(f"DM sent to {user.display_name}.")
            return True
        except nextcord.Forbidden:
            logger.warning(f"Could not send DM to {user.display_name}. User might have DMs disabled.")
            return False
        except Exception as e:
            logger.error(f"Error occurred while sending DM to {user.display_name}: {e}")
            return False
    
    async def log_event(self, guild: nextcord.Guild, embed: nextcord.Embed) -> bool:
        log_channel_id = self.config_manager.config.log_channel_id
        if log_channel_id == 0:
            logger.info("Log channel ID not configured. Skipping event logging.")
            return False
        
        log_channel = guild.get_channel(log_channel_id)
        if log_channel:
            try:
                perms = log_channel.permissions_for(guild.me)
                if not perms.send_messages:
                    logger.error(f"Bot lacks 'Send Messages' permission in log channel {log_channel.name}. Cannot log event.")
                    return False
                
                await log_channel.send(embed=embed)
                logger.info(f"Event logged in channel #{log_channel.name}.")
                return True
                
            except nextcord.Forbidden:
                logger.error(f"Bot doesn't have permissions to send messages in log channel {log_channel.name}. (Discord Forbidden Error)")
                return False
            except Exception as e:
                logger.error(f"Error occurred while logging event: {e}")
                return False
        else:
            logger.error(f"Log channel with ID {log_channel_id} not found in guild {guild.name}.")
            return False
    
    def is_user_on_cooldown(self, user_id: int) -> bool:
        current_time = datetime.now(timezone.utc).timestamp()
        if user_id in self.user_cooldowns:
            last_call_time = self.user_cooldowns[user_id]
            if (current_time - last_call_time) < self.cooldown_duration_seconds:
                return True
        return False
    
    def update_user_cooldown(self, user_id: int):
        self.user_cooldowns[user_id] = datetime.now(timezone.utc).timestamp()
    
    def should_monitor_guild(self, guild_id: int) -> bool:
        target_server_id = self.config_manager.config.target_server_id
        return target_server_id == 0 or guild_id == target_server_id
    
    def has_bypass_role(self, member: nextcord.Member) -> bool:
        bypass_roles_ids = self.config_manager.config.bypass_roles_ids
        if not bypass_roles_ids:
            return False
        return any(role.id in bypass_roles_ids for role in member.roles)
    
    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')
        
        try:
            await self.sync_application_commands()
            logger.info("Slash commands synced globally.")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")
        
        logger.info("Performing initial permission checks...")
        for guild in self.guilds:
            me = guild.me
            
            if not me.guild_permissions.moderate_members:
                logger.warning(f"Bot lacks 'Moderate Members' permission in guild '{guild.name}'. Timeout functionality will fail.")
            
            log_channel_id = self.config_manager.config.log_channel_id
            if log_channel_id != 0:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    perms = log_channel.permissions_for(me)
                    if not perms.send_messages:
                        logger.warning(f"Bot lacks 'Send Messages' permission in configured log channel '{log_channel.name}' in guild '{guild.name}'. Logging will fail.")
                else:
                    logger.warning(f"Log channel with ID {log_channel_id} not found in guild '{guild.name}'. Logging will fail.")
            else:
                logger.info(f"Log channel ID not configured for guild '{guild.name}'. Logging will be skipped.")
        
        logger.info("Initial permission checks completed.")
    
    async def on_message(self, message: nextcord.Message):
        if message.author.bot:
            return
        
        if message.guild and not self.should_monitor_guild(message.guild.id):
            return
        
        if isinstance(message.author, nextcord.Member) and self.has_bypass_role(message.author):
            logger.info(f"User {message.author.display_name} has a bypass role. Skipping moderation.")
            return
        
        if self.is_user_on_cooldown(message.author.id):
            logger.info(f"User {message.author.display_name} is on cooldown. Skipping API call.")
            await self.send_dm_to_user(
                message.author,
                f"Hello {message.author.display_name}, your recent message was not sent for moderation "
                f"because you're on cooldown. Please wait a moment before sending another message that might trigger moderation."
            )
            return
        
        self.update_user_cooldown(message.author.id)
        
        logger.info(f"Processing message from {message.author.display_name} in #{message.channel.name}: {message.content}")
        
        api_response = await self.moderation_api.analyze_text(message.content)
        
        if api_response.get("error"):
            logger.error(f"Failed to get valid API response for message from {message.author.display_name}: {api_response['error']}")
            return
        
        flagged = api_response.get("flagged", False)
        flagged_word = api_response.get("flagged_word", "N/A")
        reason = api_response.get("reason", "No reason provided")
        
        if flagged:
            logger.warning(f"Message from {message.author.display_name} flagged! Word: '{flagged_word}', Reason: '{reason}'")
            
            if isinstance(message.author, nextcord.Member):
                mute_duration = random.randint(
                    self.config_manager.config.min_mute_duration_minutes,
                    self.config_manager.config.max_mute_duration_minutes
                )
                mute_reason = f"Flagged for '{flagged_word}' ({reason})"
                
                timeout_success = await self.timeout_user(message.author, mute_duration, mute_reason)
                
                dm_message = (
                    f"Your message in **{message.guild.name}** was flagged for moderation.\n"
                    f"**Reason:** {reason}\n"
                    f"**Flagged Word:** `{flagged_word}`\n"
                    f"You have been {'timed out' if timeout_success else 'flagged'} for **{mute_duration} minutes**."
                )
                await self.send_dm_to_user(message.author, dm_message)
                
                embed_color = nextcord.Color.orange() if timeout_success else nextcord.Color.red()
                log_embed = nextcord.Embed(
                    title="🚨 Message Flagged" + (" and User Timed Out 🚨" if timeout_success else " (Timeout Failed) 🚨"),
                    color=embed_color,
                    timestamp=datetime.now(timezone.utc)
                )
                log_embed.add_field(name="User", value=f"{message.author.display_name} (ID: {message.author.id})", inline=False)
                log_embed.add_field(name="Flagged Word", value=f"`{flagged_word}`", inline=True)
                log_embed.add_field(name="Reason", value=reason, inline=True)
                log_embed.add_field(name="Timeout Duration", value=f"{mute_duration} minutes", inline=True)
                log_embed.add_field(name="Channel", value=f"#{message.channel.name} (ID: {message.channel.id})", inline=True)
                log_embed.add_field(name="Timeout Status", value="✅ Success" if timeout_success else "❌ Failed", inline=True)
                log_embed.add_field(name="Message Content", value=f"```\n{message.content[:1000]}\n```", inline=False)
                log_embed.set_footer(text=f"Message ID: {message.id}")
                
                if message.guild:
                    await self.log_event(message.guild, log_embed)
            else:
                logger.warning(f"Could not timeout {message.author.display_name} as they are not a guild member.")
        
        await self.process_commands(message)
    
    async def close(self):
        await self.moderation_api.close()
        await super().close()

async def main():
    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    api_key = os.getenv("API_KEY")
    
    if not discord_token:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables. Please set it.")
        return
    
    if not api_key:
        logger.warning("API_KEY not found in environment variables. API calls might fail if the moderation service requires it.")
    
    bot = ModerationBot()
    try:
        await bot.start(discord_token)
    except nextcord.LoginFailure:
        logger.error("Failed to log in. Invalid Discord token provided. Please check your DISCORD_BOT_TOKEN.")
    except Exception as e:
        logger.error(f"An unexpected error occurred while running the bot: {e}")
        logger.error(traceback.format_exc())
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
