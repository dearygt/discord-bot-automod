# discord-bot-automod
# 🤖 auto Moderation Bot

An advanced moderation bot for Discord, powered by the KYS Moderation API! This bot helps you keep your server safe and free from unwanted content by detecting inappropriate words and phrases and applying moderation actions like timeouts.

## ✨ Key Features

* **Inappropriate Content Detection:** Uses an external API to analyze messages and detect offensive content.
* **Automatic Timeout:** Automatically applies timeouts to users who violate rules, with a configurable random duration.
* **Private Messages (DMs):** Notifies affected users about the reason for their moderation.
* **Logging Channel (Logs):** Records all moderation actions in a dedicated channel for easy oversight.
* **In-Server Configuration:**
    * Set a logging channel.
    * Define the random timeout duration range.
    * Configure roles that can bypass moderation.
    * Optionally, limit monitoring to a specific server.
* **Slash Commands:** Easy configuration and management via intuitive Discord commands.

## 🚀 Quick Start Guide

Follow these steps to get your bot up and running.

### 1. Requirements

* Python 3.8 or higher
* A Discord account and permissions to create a bot application.
* An API Key from the website.
### 2. Obtaining Your  API Key

For the bot to function, you need an API Key from the KYS Moderation API.

1.  **Visit the Website:** Go to the official   API page: [https://test-hub.kys.gay/](https://test-hub.kys.gay/)
2.  **Generate Your API Key:** Follow the instructions on the website to register and generate your API Key.
3.  **Need Help?** If you encounter any difficulties, you can join the  Discord server for support: [ Discord Invite Link]( @⚓・Community 
https://discord.gg/3wKTDFMwvN) 

### 3. Discord Bot Setup

1.  **Create a Bot Application:** Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2.  Create a new application, give it a name, and navigate to the "Bot" section.
3.  Click "Add Bot."
4.  Under "Privileged Gateway Intents," enable:
    * `PRESENCE INTENT`
    * `SERVER MEMBERS INTENT`
    * `MESSAGE CONTENT INTENT`
5.  Copy your bot's **TOKEN**. You will need it later.
6.  Invite the bot to your server with the necessary permissions (`moderate_members`, `send_messages`).

### 4. Local Setup

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/dearygt/discord-bot-automod
    ls
    ```
2.  **Create a Virtual Environment (Optional, but Recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    (If you don't have a `requirements.txt`, create one by running `pip freeze > requirements.txt` after installing `nextcord`, `python-dotenv`, `aiohttp`, etc.)
    Ensure your `requirements.txt` includes:
    ```
    nextcord
    python-dotenv
    aiohttp
    ```
4.  **Create a `.env` file:**
    In the root directory of your project, create a file named `.env` and add your keys:
    ```
    DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
    API_URL_BASE=https://test-hub.kys.gay/api/moderate_words/analyze](https://test-hub.kys.gay/api/moderate_words/analyze
    API_KEY=YOUR_KYS_API_KEY
    ```
    * Replace `YOUR_DISCORD_BOT_TOKEN` with the Bot Token you copied from Discord.
    * Replace `YOUR_KYS_API_KEY` with the API Key you obtained from https://test-hub.kys.gay/
    * `API_URL_BASE` should already be correct, but double-check.

### 5. Run the Bot

From your terminal (with your virtual environment activated if you created one), run:

```bash
python bot.py
