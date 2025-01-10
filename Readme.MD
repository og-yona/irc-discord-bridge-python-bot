# IRC-Discord-Bridge
- A multi-channel IRC <-> Discord Bridge. 
- Relays IRC & Discord events to both ways, including: Messages, Replies, Reactions, Pinned messages (and IRC Joins/Parts/Quits/Renames/Kicks)
- Messages from IRC can be sent to Discord through a webhook, making them look almost like real Discord Users (with a bot tag). With no webhook given - messages will be relayed directly through the bot
- Query !topic or !who - Bot relays info between channels
- Allow @mention of users from IRC to Discord - But Block/Filter out the @everyone and @here
- Additional Quality of Life features for IRC, such as msg included URL parsing and short information relaying to IRC about the URL
- Localization for English and Finnish (and Savonian)
- (More details about features later)
- NOTE: To run this you'll need to have a clone exception set up on your IRCd's config or one to be requested from the IRC network's opers, as most networks allow 3 clones from the same IP. 

## Requirements
- A minimum of Python 3.9 (?) 
- Install the following python libraries using pip:

  - [irc](https://pypi.org/project/irc/)
  - [discord.py](https://pypi.org/project/discord.py/)
  - [discord-webhook](https://pypi.org/project/discord-webhook/)
  - [requests](https://pypi.org/project/requests/) (used for URL webpage title/description/video duration querying to IRC)
  - [bs4](https://pypi.org/project/beautifulsoup4/) (used for URL webpage title/description/video duration querying to IRC)

- Note: Lower versions down to 3.7 will probably run the bot but might limit it. 
discord.py version defaults to <2.0 if the Python version is 3.8 or lower.
Some feats on this bot need 2.0+

## Installation & Discord Bot Creation

- Clone/Download this repository and configure 'settings.json' with your IRC & Discord settings
    - the settings.json has comments and descriptions of settings marked with "_c#"
    - Required/important settings to change/notify for IRC are: 
        - server/port/bot_nickname/bot_owner
    - Required settings for Discord:
        - token/server/bot_owner
    - Set channel_sets - use Discord channel ID as the key, and for values set the linked webhook and IRC-channel

- Add a new application and bot user to your Discord account, (on the [Discord Developer Portal](https://discord.com/developers/applications)) then invite your bot to a server you manage:

https://discordapp.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot&permissions=3072  

- (Change CLIENT_ID to your application's client_id - The above invitation link will give bot permission to view channels/messages and post messages)

- Run the bot with 'python3 main.py' (preferably inside a screen of course)

**For all the features of the bot to work you'll need to enable all the Intents in the Bot page of your Discord Bot Application**.

## Features

- You can set up multiple channel sets for messages to be relayed between them.
    - E.g #foo to be bridged with Discord channel 292838383893930 (Discord channel ID)
    - And #python to be bridged with Discord channel 404949399393939
    - You can do this for as many channel combinations as you need
    - Set up a channel specific webhook for more clean experience - with empty hook the messages are simply relayed through the Discord bot
    - You may edit/add/delete channel sets from 'settings.json' (once you're done you need to restart the bot for the changes to take effect.)
- (Can use) Uses webhooks to spoof IRC nicks as Discord "users" (bot/app tag next to their name, all webhooks have it.)
- Bot ops for both IRC and Discord that can use moderation/maintainance commands.
- IRC users can mention Discord users by including @DiscordNickname in the IRC-messages.
- IRC color codes such as bold and italics are converted to Discord equivalents and vice versa.
- The following commands are provided - functioning from both IRC and Discord:
    - !help - list the commands and extra info about usage of any of the below commands
    - !who - When typed from IRC will print the Discord users and their status (online/away/offline) - typed from Discord will print out the IRC-channel users
    - !topic - When typed from IRC, prints the Discord channel topic to IRC - and when typed from Discord, prints out the IRC channel topic to Discord
    - !status - Will print out the current bot/bridge uptime
    - !info - Will print out general info about messages being relayed and how to mention discord users from IRC
    - !shutdown to kill the bot. (only for botops) (works on IRC too)  
- Relays IRC & Discord events to both ways, including:
    - Messages, Replies, Reactions, Pinned messages
    - (IRC) Joins/Parts/Quits/Renames/Kicks
- Messages from IRC can be sent to Discord through a webhook, making them look almost like real Discord Users (with a bot tag). 
    - With no webhook given - messages will be relayed directly through the bot
- Query !topic from IRC or Discord - bot relays the topic from linked channel
- Query !who from IRC or Discord - bot relays information about who are around/online from linked channel
    - Also !help !status !shutdown - etc. misc. commands available
- Allow @mention of users from IRC to Discord - But Block/Filter out the @everyone and @here
    - Mentioning a user from IRC to Discord requires the @ in front of Discord user's Nickname on the server (which can be viewed from IRC with !who)
- Additional Quality of Life features for IRC:
    - Check messages for URLs, and if found, parse and report to IRC:
        - The webpage title (if available)
        - Youtube video duration (if available)
        - Short description of the webpage (if available)
- Localization for English and Finnish (and Savonian)
    - Add your own languages/localizations to settings.json
    - Change language during bot runtime with !speak 'lang_code_in_settings'
- NOTE: To run this you'll need to have a clone exception set up on your IRCd's config or one to be requested from the IRC network's opers, as most networks allow 3 clones from the same IP. 

## License
Feel free to fork this repo copy/borrow stuff for your own projects but provide a link to this as credit!

A lot of the core code and core functions are "borrowed" from the following to repositories:
https://github.com/OrpheusGr/Discord-IRC-Bridge
https://github.com/milandamen/Discord-IRC-Python
