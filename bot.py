import discord
from discord import app_commands
import asyncio
import logging
import aiohttp
import os
import json
from ebooklib import epub
import re

# Custom filter to exclude "RESUMED" messages from discord.gateway
class GatewayFilter(logging.Filter):
    def filter(self, record):
        return not (record.name == "discord.gateway" and "RESUMED" in record.msg)

handler = logging.FileHandler('bot.log')
handler.setLevel(logging.INFO)
handler.addFilter(GatewayFilter())
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Constants
CREATORS_FILE = 'creators.txt'

# Load configuration from setup
def setup_bot():
    config = {}
    if not os.path.exists('config.json'):
        config['BOT_TOKEN'] = input("Enter your Discord bot token: ")
        config['GUILD_ID'] = input("Enter your Discord Server ID: ")
        config['FETCH_CHANNEL_ID'] = input("Enter the channel ID where the fetch command is allowed: ")
        config['ALLOWED_ROLES'] = [role.strip() for role in input("Enter role names for fetch command access, separated by commas: ").split(',') if role.strip()]
        config['ADMIN_ROLES'] = [role.strip() for role in input("Enter role names for admin command access, separated by commas: ").split(',') if role.strip()]
        with open('config.json', 'w') as f:
            json.dump(config, f)
    else:
        with open('config.json', 'r') as f:
            config = json.load(f)
    
    if not os.path.exists(CREATORS_FILE):
        with open(CREATORS_FILE, 'w') as f:
            f.write('')
    
    return config['BOT_TOKEN'], config['GUILD_ID'], config['FETCH_CHANNEL_ID'], config['ALLOWED_ROLES'], config['ADMIN_ROLES']

# Load creators from txt file
def load_creators():
    creators = {}
    try:
        with open(CREATORS_FILE, 'r') as f:
            for line in f:
                if '=' in line:
                    name, url = map(str.strip, line.split('=', 1))
                    creators[name] = url
    except FileNotFoundError:
        logging.warning(f"{CREATORS_FILE} not found. Returning empty dict.")
    return creators

# Save creators to txt file
def save_creators(creators):
    with open(CREATORS_FILE, 'w') as f:
        for name, url in creators.items():
            f.write(f"{name} = {url}\n")

# Bot initialization
bot_token, guild_id, fetch_channel_id, allowed_roles, admin_roles = setup_bot()
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Paginated chapter selection view
class ChapterSelectView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, chapters: list, creator_name: str, url: str, page: int = 0):
        super().__init__(timeout=600)
        self.interaction = interaction
        self.chapters = chapters
        self.creator_name = creator_name
        self.url = url
        self.page = page
        self.per_page = 25
        self.pages = (len(chapters) + self.per_page - 1) // self.per_page
        self.kemono_page_size = 50
        self.kemono_pages_fetched = 1
        self.selected_chapters = set()
        self.update_select()

    def update_select(self):
        self.clear_items()
        start_idx = self.page * self.per_page
        end_idx = min((self.page + 1) * self.per_page, len(self.chapters))
        page_chapters = self.chapters[start_idx:end_idx]

        if not page_chapters:
            self.add_item(discord.ui.Button(label="No more chapters", style=discord.ButtonStyle.grey, disabled=True))
            return

        select = discord.ui.Select(
            placeholder=f"Select chapters (Page {self.page + 1}/{self.pages})",
            min_values=0,
            max_values=len(page_chapters),
            options=[
                discord.SelectOption(
                    label=f"#{i+1} {c.get('title', 'Untitled')[:75]}{'...' if len(c.get('title', 'Untitled')) > 75 else ''}",
                    value=str(i),
                    default=i in self.selected_chapters
                )
                for i, c in enumerate(page_chapters, start_idx)
            ]
        )
        select.callback = self.on_select
        self.add_item(select)

        # Check if all chapters on this page are selected
        all_selected = all(i in self.selected_chapters for i in range(start_idx, end_idx))
        all_button_label = "Deselect all on page" if all_selected else "Select all on page"
        all_button = discord.ui.Button(label=all_button_label, style=discord.ButtonStyle.green)
        all_button.callback = self.on_all
        self.add_item(all_button)

        prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.grey, disabled=self.page == 0)
        next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.grey, disabled=end_idx >= len(self.chapters) and not self.can_fetch_more())
        prev_button.callback = self.on_prev
        next_button.callback = self.on_next
        self.add_item(prev_button)
        self.add_item(next_button)

        download_button = discord.ui.Button(label="Download", style=discord.ButtonStyle.primary)
        download_button.callback = self.on_download
        self.add_item(download_button)

    def can_fetch_more(self):
        return len(self.chapters) == self.kemono_pages_fetched * self.kemono_page_size

    async def fetch_more_chapters(self):
        required_kemono_page = (self.page * self.per_page) // self.kemono_page_size + 1
        if required_kemono_page > self.kemono_pages_fetched:
            offset = self.kemono_pages_fetched * self.kemono_page_size
            new_chapters = await fetch_chapters(self.url, self.kemono_page_size, offset=offset)
            if new_chapters:
                self.chapters.extend(new_chapters)
                self.kemono_pages_fetched += 1
                self.pages = (len(self.chapters) + self.per_page - 1) // self.per_page
            return bool(new_chapters)
        return False

    async def on_select(self, interaction: discord.Interaction):
        selected = set(int(val) for val in interaction.data["values"])
        start_idx = self.page * self.per_page
        end_idx = min((self.page + 1) * self.per_page, len(self.chapters))
        page_indices = set(range(start_idx, end_idx))
        self.selected_chapters -= page_indices - selected
        self.selected_chapters |= selected
        self.update_select()  # Refresh the UI after selection
        await interaction.response.edit_message(view=self)

    async def on_all(self, interaction: discord.Interaction):
        start_idx = self.page * self.per_page
        end_idx = min((self.page + 1) * self.per_page, len(self.chapters))
        page_indices = set(range(start_idx, end_idx))
        # If all are selected, deselect them; otherwise, select all
        if all(i in self.selected_chapters for i in page_indices):
            self.selected_chapters -= page_indices
        else:
            self.selected_chapters.update(page_indices)
        self.update_select()
        await interaction.response.edit_message(view=self)

    async def on_prev(self, interaction: discord.Interaction):
        self.page -= 1
        self.update_select()
        await interaction.response.edit_message(view=self)

    async def on_next(self, interaction: discord.Interaction):
        self.page += 1
        await interaction.response.defer()
        await self.fetch_more_chapters()
        self.update_select()
        await interaction.edit_original_response(view=self)

    async def on_download(self, interaction: discord.Interaction):
        if not self.selected_chapters:
            await interaction.response.send_message("No chapters selected!", ephemeral=True, delete_after=5)
            return
        chapters_to_fetch = [self.chapters[i] for i in sorted(self.selected_chapters)]
        filename = generate_filename(chapters_to_fetch)
        epub_file = await create_epub(chapters_to_fetch, self.creator_name, self.creator_name, self.url, filename)
        with open(epub_file, 'rb') as file:
            await interaction.user.send(
                f"Fetched from **[{self.creator_name}](<{self.url.replace('/api/v1/', '/')}>)**.",
                file=discord.File(file, f"{filename}.epub")
            )
        logging.info(f"EPUB '{filename}.epub' sent to {interaction.user} for creator '{self.creator_name}'")
        await interaction.response.send_message("EPUB sent to your DMs!", ephemeral=True)
        os.remove(epub_file)

# Fetch command
@tree.command(name="fetch", description="Fetch chapters from a Kemono creator", guild=discord.Object(id=guild_id))
@app_commands.describe(
    creator="Creator name from list or a URL",
    num_chapters="Number of chapters to fetch (optional)",
    skip_chapters="Comma-separated list of chapter numbers to skip (optional)"
)
async def fetch(interaction: discord.Interaction, creator: str, num_chapters: int = None, skip_chapters: str = None):
    if not await check_role(interaction):
        return
    if str(interaction.channel_id) != fetch_channel_id:
        await interaction.response.send_message(f"This command can only be used in <#{fetch_channel_id}>.", ephemeral=True, delete_after=10)
        return

    logging.info(f"Fetch command used by {interaction.user} for creator '{creator}' with num_chapters={num_chapters}, skip_chapters={skip_chapters}")
    await interaction.response.defer(ephemeral=True)
    creators = load_creators()

    if creator in creators:
        url = creators[creator]
        creator_name = creator
    else:
        url = creator
        creator_name = None

    try:
        fixed_url = await fix_link(url)
        if not fixed_url:
            message = await interaction.followup.send("Invalid URL or creator name not found.", ephemeral=True)
            await message.delete(delay=10)
            return

        if not creator_name:
            parts = fixed_url.split('/')
            if len(parts) >= 8 and parts[3] == 'api' and parts[4] == 'v1':
                service, creator_id = parts[5], parts[7]
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://kemono.su/api/v1/{service}/user/{creator_id}/profile") as resp:
                        creator_name = (await resp.json()).get('name', 'Unknown') if resp.status == 200 else "Unknown"
            else:
                message = await interaction.followup.send("Invalid URL format.", ephemeral=True)
                await message.delete(delay=10)
                return

        if num_chapters is not None:
            all_chapters = await fetch_chapters(fixed_url, num_chapters)
            if not all_chapters:
                message = await interaction.followup.send("No chapters found.", ephemeral=True)
                await message.delete(delay=10)
                return
            if skip_chapters:
                skip_set = set(map(int, skip_chapters.split(',')))
                chapters_to_process = [c for i, c in enumerate(all_chapters, 1) if i not in skip_set][:num_chapters]
            else:
                chapters_to_process = all_chapters
            filename = generate_filename(chapters_to_process)
            epub_file = await create_epub(chapters_to_process, creator_name, creator_name, fixed_url, filename)
            with open(epub_file, 'rb') as file:
                await interaction.user.send(
                    f"Fetched from **[{creator_name}](<{fixed_url.replace('/api/v1/', '/')}>)**.",
                    file=discord.File(file, f"{filename}.epub")
                )
            logging.info(f"EPUB '{filename}.epub' sent to {interaction.user} for creator '{creator_name}'")
            message = await interaction.followup.send("EPUB sent to your DMs!", ephemeral=True)
            await message.delete(delay=10)
            os.remove(epub_file)
        else:
            initial_chapters = await fetch_chapters(fixed_url, 50)
            if not initial_chapters:
                message = await interaction.followup.send("No chapters found.", ephemeral=True)
                await message.delete(delay=10)
                return
            view = ChapterSelectView(interaction, initial_chapters, creator_name, fixed_url)
            message = await interaction.followup.send("Select chapters to fetch:", view=view, ephemeral=True)
            await message.delete(delay=600)

    except Exception as e:
        logging.error(f"Fetch command error: {e}")
        message = await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        await message.delete(delay=10)

# Autocomplete for creator parameter
async def creator_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    creators = load_creators()
    # Get all matching creators with their match positions
    matches_with_positions = [
        (name, name.lower().find(current.lower()))
        for name in creators.keys()
        if current.lower() in name.lower()
    ]
    # Sort by position first, then alphabetically within each position group
    sorted_matches = sorted(
        matches_with_positions,
        key=lambda x: (x[1], x[0].lower())
    )
    # Return up to 25 choices
    return [
        app_commands.Choice(name=name, value=name)
        for name, _ in sorted_matches
    ][:25]

fetch.autocomplete('creator')(creator_autocomplete)

# Add creator command (admin only)
@tree.command(name="add_creator", description="Add a creator to the list (Admin only)", guild=discord.Object(id=guild_id))
@app_commands.describe(name="Creator name", url="Kemono URL")
async def add_creator(interaction: discord.Interaction, name: str, url: str):
    if not await check_role(interaction, require_admin=True):
        return

    if not url.startswith("https://kemono.su/"):
        await interaction.response.send_message("URL must be a valid Kemono URL.", ephemeral=True, delete_after=10)
        return

    creators = load_creators()
    creators[name] = url
    save_creators(creators)
    await interaction.response.send_message(f"Added {name} with URL {url}", ephemeral=True, delete_after=10)

# Remove creator command (admin only)
@tree.command(name="remove_creator", description="Remove a creator from the list (Admin only)", guild=discord.Object(id=guild_id))
@app_commands.describe(name="Creator name")
async def remove_creator(interaction: discord.Interaction, name: str):
    if not await check_role(interaction, require_admin=True):
        return

    creators = load_creators()
    if name in creators:
        del creators[name]
        save_creators(creators)
        await interaction.response.send_message(f"Removed {name}", ephemeral=True, delete_after=10)
    else:
        await interaction.response.send_message(f"{name} not found.", ephemeral=True, delete_after=10)

# Fix link to API format
async def fix_link(link):
    if not link or not isinstance(link, str):
        return None
    link = link.strip()
    if "patreon.com" in link.lower():
        user_id = await get_patreon_id(link)
        return f"https://kemono.su/api/v1/patreon/user/{user_id}" if user_id else None
    if not link.startswith("http"):
        link = f"https://{link.lstrip('/')}"
    if link.startswith("https://kemono.su/") and not link.startswith("https://kemono.su/api/v1/"):
        link = link.replace("https://kemono.su/", "https://kemono.su/api/v1/")
    return link if "kemono.su/api/v1/" in link else None

# Get Patreon ID from URL
async def get_patreon_id(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    match = re.search(r'"creator":\s*{\s*"data":\s*{\s*"id":\s*"(\d+)"', text)
                    return match.group(1) if match else None
        except Exception as e:
            logging.error(f"Error getting Patreon ID: {e}")
            return None

# Fetch chapters from Kemono API with offset
async def fetch_chapters(feed_url, max_chapters, offset=0):
    chapters = []
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{feed_url}?o={offset}") as resp:
            if resp.status != 200:
                logging.error(f"Failed to fetch chapters: {resp.status}")
                return []
            chapters = await resp.json()
            return sorted(chapters[:max_chapters], key=lambda x: x.get('published', ''), reverse=True)

# Create EPUB file from chapters
async def create_epub(chapters, title, author, profile_url, filename):
    book = epub.EpubBook()
    book.set_language("en")
    book.set_title(title)
    book.add_author(author)
    chapters = sorted(chapters, key=lambda x: x['published'])
    epub_chapters = []

    async with aiohttp.ClientSession() as session:
        for i, chapter in enumerate(chapters, start=1):
            chapter_title = chapter['title']
            content = f"<h1>{chapter_title}</h1>\n<p>{chapter.get('content', '')}</p>"
            matches = re.findall(r'<img[^>]+src="([^"]+)"', content)
            for i2, match in enumerate(matches):
                full_url = "https://n4.kemono.su/data" + match
                try:
                    async with session.get(full_url) as resp:
                        if resp.status == 200:
                            media_type = resp.headers.get('Content-Type', 'image/jpeg')
                            image_name = match.split('/')[-1]
                            image_content = await resp.read()
                            image_item = epub.EpubItem(uid=f"img{i2+1}", file_name=f"images/{image_name}", 
                                                      media_type=media_type, content=image_content)
                            book.add_item(image_item)
                            content = content.replace(match, f"images/{image_name}")
                except Exception as e:
                    logging.error(f"Failed to download image {full_url}: {e}")
            
            chapter_epub = epub.EpubHtml(title=chapter_title, file_name=f'chap_{i:02}.xhtml', lang='en')
            chapter_epub.content = content
            epub_chapters.append(chapter_epub)
            book.add_item(chapter_epub)

    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + epub_chapters
    temp_filepath = os.path.join(os.getcwd(), f"{filename}.epub")
    epub.write_epub(temp_filepath, book)
    return temp_filepath

# Sanitize filename
def sanitize_filename(filename):
    return re.sub(r'[^\w\s-]', '', filename).strip() or "untitled"

# Generate filename from chapters
def generate_filename(chapters):
    if not chapters:
        return "empty_chapters"
    lowermost = chapters[-1].get('title', 'untitled')
    uppermost = chapters[0].get('title', 'untitled')
    return f"{sanitize_filename(lowermost[:15])}-{sanitize_filename(uppermost[:15])}" if len(chapters) > 1 else sanitize_filename(uppermost)

# Check user roles
async def check_role(interaction: discord.Interaction, require_admin=False):
    if not interaction.guild:
        await interaction.response.send_message("Commands only work in servers.", ephemeral=True, delete_after=10)
        return False
    author_roles = [role.name.lower() for role in interaction.user.roles]
    required_roles = admin_roles if require_admin else allowed_roles
    if any(role.lower() in author_roles for role in required_roles):
        return True
    await interaction.response.send_message(f"You lack {'admin' if require_admin else 'required'} role.", ephemeral=True, delete_after=10)
    return False

@client.event
async def on_disconnect():
    logging.info("Bot disconnected from Discord Gateway. Reconnect attempts may follow...")

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=guild_id))
    logging.info(f'{client.user} connected and commands synced to guild {guild_id}!')

client.run(bot_token)
