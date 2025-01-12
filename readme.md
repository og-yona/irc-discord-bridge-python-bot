# IRC Discord Bridge Relay Bot with Python

- The bot relays IRC and Discord events both ways, including: messages, replies, reactions, pins, edits (and IRC joins/parts/quits/renames/kicks/topics)
- *(Optional)* Discord Channel specific webhook allows relaying of IRC-messages look close to regular discord messages (with the BOT/APP -tag)
- Set up multiple IRC<->Discord -channel pairs - or use the bot with just a single one
- IRC users can mention @discordusers from IRC - filter out @everyone & @here
- Query !topic or !who - Bot relays info between channels *(all/more bot-commands explained at the end of readme)*
- Additional Quality of Life features for IRC, such as message included URL parsing and short information relaying to IRC about the URL *(simulating Discord web-info 'embeds')*
- Written in Python and *heavily commented and explained in code & settings* - easy to customize to fit your specific needs
- Localization/Bot phrases available for English and Finnish *(and Savonian)*
- *(More details about features at the end of readme)*

## Requirements & Python Libraries

- A minimum of Python 3.9 (?) 
- Install the following python libraries using pip ( 'pip install <libraryname>' ) :
  - [irc](https://pypi.org/project/irc/)
  - [discord.py](https://pypi.org/project/discord.py/)
  - [discord-webhook](https://pypi.org/project/discord-webhook/)
  - Used for IRC URL-information/QOL -features:
  - [requests](https://pypi.org/project/requests/)
  - [bs4](https://pypi.org/project/beautifulsoup4/)
- Note: Bot might run on lower versions of Python, but have not been tested.

## Installation - Discord Bot Creation - Running

1. Clone/Download this repository and configure 'settings.json' with your IRC & Discord settings
    - *'settings.json' has comments and descriptions of settings marked with "_c#"*
    - Important settings for IRC: server/port/bot_nickname/bot_owner
    - Important settings for Discord: token/server/bot_owner
    - Channel Sets ('channel_sets') - use the numerical Discord channel ID as the key, and for values set the related Discord webhook and the matching IRC-channel

2. Add a new application and bot user to your Discord account (on the [Discord Developer Portal](https://discord.com/developers/applications)) -  then invite your bot to a server you manage with invite link:
- **https://discordapp.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot&permissions=3072**
    - *Replace *'CLIENT_ID'* with your (newly created?) application's client_id*
    - *The above invitation link will open up a Discord page, allowing you to invite the bot to servers you manage. Invite gives bot permission to view the selected server's channel messages and post new messages.*
    - *Note: The &permissions=3072 is important to allow your bot to see the channels and send messages. (This part is missing from default Discord Dev -page invitation link)*  

3. Run the bot with 'python3 main.py' *(preferably inside a screen of course)*

**For all the features of the bot to work you'll need to enable all the Intents *('Presence-', 'Server Members-' and 'Message Content Intent')* in the Bot page of your Discord Bot Application**

## License & Credits
Feel free to fork this repo copy/borrow stuff for your own projects, if doing so, providing a link to here would be nice.

A lot of the core code and ideas are borrowed from the following two repositories, if you need or want a simpler bot instead, you should look into these:
- https://github.com/OrpheusGr/Discord-IRC-Bridge
- https://github.com/milandamen/Discord-IRC-Python

## Full (?) Features List

- Relays IRC & Discord events to both ways, in addition to basic messages, relays:
    - Discord to IRC also: Edits, Replies, Reactions, Pinned messages
    - IRC to Discord also: Joins, Parts, Quits, Renames, Kicks, Topic changes
- You can set up multiple channel sets for messages to be relayed between them.
    - E.g #foo to be bridged with Discord channel 292838383893930 (Discord channel ID)
    - And #python to be bridged with Discord channel 404949399393939
    - You can do this for as many or as few channel combinations as you need
    - Set up a channel specific webhook for more clean experience
        - *With empty hook - the messages are simply "spoken" through the Discord bot with IRC-nickname as prefix to message.*
    - You may edit/add/delete channel sets from 'settings.json' (once you're done you need to restart the bot for the changes to take effect.)
- Uses *(can use)* webhooks to spoof IRC nicks as Discord "users"
    - Messages from IRC can be sent to Discord through a webhook, making them look almost like real Discord Users (with a bot tag). 
    - With no webhook given - messages will be relayed directly through the bot
- Bot ops for both IRC and Discord that can use moderation/maintainance commands.
- IRC users can mention Discord users by including @DiscordNickname in the IRC-messages.
- But Block/Filter out the @everyone and @here
    - Mentioning a user from IRC to Discord requires the @ in front of Discord user's Nickname on the server (which can be viewed from IRC with !who)
- IRC color codes such as bold and italics are converted to Discord equivalents and vice versa.
- The following commands are provided - functioning from both IRC and Discord:
    - !help - list the commands and extra info about usage of any of the below commands
    - !who - When typed from IRC will print the Discord users and their status (online/away/offline) - typed from Discord will print out the IRC-channel users
    - !topic - When typed from IRC, prints the Discord channel topic to IRC - and when typed from Discord, prints out the IRC channel topic to Discord
    - !status - Will print out the current bot/bridge uptime
    - !info - Will print out general info about messages being relayed and how to mention discord users from IRC
    - !speak *[lang-code]* - Change the bot's language/phrases the bot is using. 'lang_code' being one of the languages found in settings.json under 'localization'. *(Saved on clean !shutdown)*
    - !btc - Fetches the current BTC/USD -value from CoinMarketCap and prints it out to linked IRC and Discord channels
    - !stock *[stocksymbol]* - Fetches the current STOCK/USD -value of stock symbol from finance.yahoo.com and prints it out to linked IRC and Discord channels
    - !ignorequits *[ircuser]* - if there is a IRC-user with unstable connection causing spam on Discord, you can ignore this user for the JOINS/PARTS/QUITS with this command. *(Saved on clean !shutdown)*
    - !shutdown to kill the bot. (only for botops) (works on IRC too)
        - *On 'clean' shutdown the runtime-settings, such as used language and ignored IRC-part/quit/join-users are saved to settings.json, so they will be loaded on next time the bot runs.*
- Additional Quality of Life features for IRC:
    - Check messages for URLs, and if found, parse and report to IRC:
        - The webpage title (if available)
        - Youtube video duration (if available)
        - Short description of the webpage (if available)
- Localization for English and Finnish (and Savonian)
    - Add your own languages/localizations to settings.json
    - Or edit one of the existing languages for even easier and faster customization.
    - Change language during bot runtime with !speak 'lang_code_in_settings' - currently used bot language is saved when clean !shutdown
