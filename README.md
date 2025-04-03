# Kemono Fetch Bot

A Discord bot designed to fetch webnovel content from Kemono creator pages, compile it into EPUB files, and provide an interactive chapter selection experience. Built with Python using the `discord.py` library, this bot integrates with the Kemono API to retrieve posts, supports image embedding, and offers role-based command access for both users and admins.

## Features

- **Fetch Command**: Retrieve chapters from a Kemono creator by name (from a stored list) or URL, with options to specify the number of chapters or skip specific ones.
- ![Image](https://github.com/user-attachments/assets/f6345126-3bbf-4d6e-aa0a-d880712af584)
- ![Image](https://github.com/user-attachments/assets/982113d1-199f-40b7-b8d1-eb436ab22df0)
- **Interactive Chapter Selection**: Browse and select chapters via a paginated Discord UI, with support for fetching additional pages dynamically.
- **EPUB Generation**: Compile selected chapters into an EPUB file with embedded images, sent directly to the user’s DMs.
- **Admin Commands**: Add or remove creators from a text-based list (`creators.txt`) with admin-only commands.
- **Autocomplete**: Suggests creator names as you type for the fetch command.
- ![Image](https://github.com/user-attachments/assets/48935721-9f0a-48f1-8b99-4159efec1ab9)
- **Role-Based Access**: Restrict commands to specific roles and channels, configurable during setup.
- **Logging**: Tracks bot activity and errors in a `bot.log` file.

## Prerequisites

- Python 3.8+
- A Discord bot token (create one via the [Discord Developer Portal](https://discord.com/developers/applications))
- A Discord server (Guild) where the bot will operate
- Required Python packages (see Installation)

## Installation

1. **Download bot.py**  
   Download the bot.py in the Repository

2. **Install Dependencies**  
   Install the required Python packages:  
   ```pip install discord.py aiohttp ebooklib```

3. **Set Up Configuration**  
   On first run, the bot will prompt you to enter:
   - Discord bot token
   - Guild ID (discord server ID)
   - Fetch channel ID (where `/fetch` is allowed)
   - Allowed role names (for `/fetch` access)
   - Admin role names (for `/add_creator` and `/remove_creator`)  
   These will be saved to `config.json`. Alternatively, create `config.json` manually:  
   ```json
   {
     "BOT_TOKEN": "your-bot-token",
     "GUILD_ID": "your-guild-id",
     "FETCH_CHANNEL_ID": "channel-id-for-fetch",
     "ALLOWED_ROLES": ["role1", "role2"],
     "ADMIN_ROLES": ["admin-role"]
   }
   ```

4. **(Optional) Pre-populate Creators**  
   Create a `creators.txt` file with creator names and their Kemono URLs:  
   ```
   creatorName = https://kemono.su/api/v1/service/user/user-id
   anotherCreator = https://kemono.su/api/v1/patreon/user/another-id
   ```

## Usage

1. **Run the Bot**  
   ```python bot.py```

2. **Invite the Bot**  
   Ensure the bot is invited to your server with the necessary permissions (Manage Messages, Send Messages, Embed Links).

3. **Commands**  
   - `/fetch <creator> [num_chapters] [skip_chapters]`: Fetch content from a creator. Use a name from `creators.txt` or a Kemono URL. Optionally specify how many chapters to fetch or a comma-separated list of chapter numbers to skip (e.g., `1,3,5`).  
     - If `num_chapters` is omitted, an interactive chapter selector appears.
   - `/add_creator <name> <url>`: (Admin only) Add a creator to `creators.txt`.  
   - `/remove_creator <name>`: (Admin only) Remove a creator from `creators.txt`.

4. **Example**  
   - Fetch 5 chapters: `/fetch creatorName 5`  
   - Fetch with skips: `/fetch creatorName 10 2,4`  (fetches last 10 posts but skips the 2nd and 4th most recent posts. 8 chapters are fetched)
   - Interactive mode: `/fetch https://kemono.su/api/v1/patreon/user/12345`

## How It Works

- **Fetching Content**: The bot queries the Kemono API, supports Patreon URL conversion, and retrieves chapters with titles, content, and images.
- **EPUB Creation**: Using `ebooklib`, it compiles chapters into an EPUB, embedding images downloaded from Kemono’s CDN.
- **Pagination**: The chapter selector fetches 50 chapters at a time, with a UI showing 25 per page, and dynamically loads more as needed.
- **Role Checks**: Commands are restricted to specific roles and the designated fetch channel.

## File Structure

- `bot.py`: Main bot script.
- `config.json`: Stores bot configuration (generated on first run).
- `creators.txt`: List of creator names and URLs (optional, created if missing).
- `bot.log`: Log file for bot activity and errors.

## Troubleshooting

- **Bot Not Responding**: Check `bot.log` for errors, ensure the token is valid, and verify the bot has permissions in the server.
- **No Chapters Found**: Confirm the Kemono URL is valid and the creator has public posts.
- **Permission Denied**: Ensure your role matches the allowed/admin roles in `config.json`.

## Future ideas maybe:
- Use logs to identify most requested creators and prioritize those creators in auto-complete suggestions.
- Make the add and remove creator commands optional during setup. (Pros - fewer commands and more flexibility. Cons - none, it's just optional now)
- Add an (optional) option during setup to add an admin log channel to send bot logs.
- Create an async que for high bot activity. Perhaps a command cooldown for users as well, just in case.
- Low-priority - During setup, allow for a request to be sent to Kemono for an account favorites list and create the creators.txt file for auto-complete suggestions. (Would require entering login credentials.) This is easy enough to implement but it's an unfavorable solution to me.
