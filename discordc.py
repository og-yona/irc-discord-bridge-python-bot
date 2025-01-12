# Imports
import discord
from discord.ext import commands
from discord_webhook import DiscordWebhook
import asyncio
import atexit
from datetime import timedelta
from dataclasses import dataclass, field
import logging
import time
import timers
import re

settings = None
discord_settings = None
discordc = None
irc = None

# How many hours to shift from Discord Server (UTC) to get to the IRC/local time
localTimeShiftToUTC = timedelta(hours=2)
# .. for discord message timestamp -fixing to local-IRC-time ..

@dataclass
class DiscordUserInfo:
    """ Utility data struct class for caching discord user specs """
    user_id: str
    user_name: str
    user_nick: str
    status: str
    guilds: set = field(default_factory=set)

class Discord:
    """ 
        # Discord -bot Utility Handler/Wrapper Class
        - Data variables & details concerning the Discord-Bot/APP-connection
        - Data caches about Channels & Users - both IRC & Discord -side
        - Discord event handlers 
        -- Keep bridged IRC-channels informed about linked Discord-channel
        --- Post messages / reacts / edits to IRC
        - Respond to certain !commands, as :
        -- !help for list of commands, or !topic for getting bridged 
           IRC-channel's topic, or !who to query whos online/around
           in IRC. etc..
        - Most of the "extras" and "bridging" utilities are implemented on IRC -bot side
        - Webhook -wrapper to provide IRC-bot ability for sending messages also through webhook
        # the actual discord bot and event handlers with async -functions are defined on the global scope after Discord utility -class.
    """

    def __init__(self, settings_):
        """ Save & set settings, initialize the discord-bot/bridge and set logger """

        # Save settings
        global settings
        global discord_settings
        settings = settings_
        discord_settings = settings["discord"]

        # Set this as global discord ref for async / etc
        global discordc
        discordc = self

        # Discord - variables / caches
        self.known_users: dict[str, DiscordUserInfo] = {} # Dictionary for the discord - users
        self.statusindex = 0     # Index for Discord status run-through
        self.timesleep = 0
        self.sendmymsg_lastcall = 0
        self.sendmymsg_delay = 0
        self.last_used_channel = ""
        self.connected_to_discord = 0
        self.temp_status_message = ""

        # Init logger & Create a FileHandler for logging to a file
        self.discord_logger = logging.getLogger('discordc')
        self.discord_logger.setLevel(logging.ERROR)

        self.discord_file_handler = logging.FileHandler('log_discordc_errors.log')  # Log to this file
        self.discord_file_handler.setLevel(logging.ERROR)

        irclogformatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.discord_file_handler.setFormatter(irclogformatter)
        self.discord_logger.addHandler(self.discord_file_handler)
        
        # Register async -message for/when terminal interrupt/shutdown
        atexit.register(self.shutdown, "Killed from terminal", True)

    #####################################
    #        CORE RUN / STOP            # 
    #####################################

    def run(self):
        """ Start the discord bot on this thread """
        global discord_settings
        self.is_running = 1
        discord_bot.run(discord_settings["token"], log_handler=self.discord_file_handler, log_level=logging.ERROR)

    def shutdown(self, reason="", exiting=False):
        """ Signal funtion to start shutting down the whole IRC-Discord-Bridge -bot/framework """
        if exiting == False:
            atexit.unregister(self.shutdown)
        self.is_running = 0
        self.quit_all(reason, exiting)

    def die(self):
        """ Util(?) func to start async -killing effect(?) """
        asyncio.run_coroutine_threadsafe(shutdown_async(), discord_bot.loop)
        irc.stop_loop()

    def quit_all(self, reason, exiting):
        """
        # Quit All
        - The actual implementation for shutting down the connections and bots
        """
        uptime = irc.get_uptime()
        debug_print(f"Exit : {reason} / IRC-cord bridges falling down - falling down - falling down...")
            
        self.timesleep = 0
        irc.sent_quit_on()
        if exiting == False:
            timers.add_timer("", self.timesleep+1, irc.connection.disconnect, f'!! {irc.get_word("quitmessage")} {uptime} *({reason})* !!')
            asyncio.run_coroutine_threadsafe(do_async_stuff(self.die, self.timesleep + 3), discord_bot.loop)
        else:        
            irc.connection.disconnect(f'!! {irc.get_word("quitmessage")} {uptime} *({reason})* !!')

    #####################################
    #        SEND MESSAGES              # 
    #####################################

    def send_irc_msg_to_discord(self, discord_chan, sender, message):
        """ 
        # Send IRC message to Discord (wrapper/utilities)
        - !! USE THIS AS MAIN MESSAGE SENDING FUNCTION AT IRC - CLASS !!
        - By default IRC-nicks are set as Webhook user, and messages are sent through that
        - If relaying BOT MESSAGE through WebHook, uses '[IRC]' as Webhook User Name
        - If relaying IRC USER message through BOT - add '[IRC] ' as prefix to the message to separate it from bot name in Discord
        - If no webhook is set for the channel_set - relay the message through bot instead
        - If webhook is invalid/errors with sending - will relay warning & the message through bot itself
        """
        #debug_print(f"[Discord] debug ircmsg: disc_chan:{discord_chan} sender: {sender} msg: {message}")

        if sender:
            ircUserStatuses = irc.get_irc_user_statuses()
            if sender in ircUserStatuses:
                statusPrefix = ircUserStatuses[sender]
            else:
                statusPrefix = ""
            ircDisplayname = f"{settings['irc']['ircNickPrefix']}{statusPrefix}{sender}{settings['irc']['ircNickPostfix']}"
        else:
            ircDisplayname = "[IRC]" # Bot messages through webhook
        webhooklink = settings["channel_sets"][str(discord_chan.id)]["webhook"]
        if webhooklink:
            try:
                response = self.send_through_webhook(webhooklink, message, ircDisplayname)
            except Exception as e:
                debug_print(f"[Discord] Webhook error: {e}")
                self.discord_logger.exception(f"[Discord] Webhook error: {e}")
                self.send_discord_message(discord_chan, f'```{irc.get_word("webhook_problem_message")}```\n**[IRC]** {ircDisplayname} {message}')
        # Or simply relay the message through the bot itself
        else:
            if sender: # Sent by actual IRC -user
                self.send_discord_message(discord_chan, f"**[IRC]** {ircDisplayname} {message}")
            else:      # Sent by the Bot / Bridge
                self.send_discord_message(discord_chan, f"**[IRC]** {message}")

    def send_through_webhook(self, webhooklink, finalmsg, renderedUsername):
        """ Utility / wrapper for creating / sending messages through webhooks (so we dont have to do it on IRC-class' side..) """
        webhook = DiscordWebhook(url=webhooklink, content=finalmsg, username=renderedUsername)
        response = webhook.execute()
        return response
    
    def send_discord_message(self, discord_chan, message):
        """
        # Send Discord Message
        - Send messages to the discord through slowed/timed/filtered util
        """
        if self.sendmymsg_lastcall == 0:
            self.sendmymsg_lastcall = time.time()
        ctime = time.time()
        diff = ctime - self.sendmymsg_lastcall
        if diff < 2:
            self.sendmymsg_delay += 2
            timers.add_timer("", self.sendmymsg_delay, self.send_discord_message_b, *(discord_chan, message))
        else:
            self.sendmymsg_delay = 0
            self.send_discord_message_b(discord_chan, message)
        self.sendmymsg_lastcall = ctime

    def send_discord_message_b(self, discord_chan, message):
        """ Wrapper for async Discord message send """
        global discord_bot
        asyncio.run_coroutine_threadsafe(send_discord_message_async(discord_chan, message), discord_bot.loop)

    def send_to_all_discord_channels(self, message):
        """ Send message to All configured DISCORD channels"""
        for item in settings["channel_sets"]:
            self.send_discord_message(settings["channel_sets"][item]["real_chan"], message)

    def send_uptime(self, discord_chan, irc_chan):
        """ Sends the current uptime to both refered - IRC and Discord channels """
        time = irc.get_uptime()
        irc.send_irc_and_discord(discord_chan, irc_chan, f'{irc.get_word("bridge_uptime")} {time}') 

    #####################################
    #    CHANNEL / USER DATA CACHE      # 
    #####################################

    def get_known_users(self):
        """ Returns the currently cached and known discord users with their details """
        return self.known_users

    def get_updated_known_users(self):
        """ Returns 'force refreshed' known Discord users """
        self.update_known_users()
        return self.known_users

    def update_known_users(self):
        """
        # Fetches all user-data from connected Discord servers/channels
        - and saves them to global/local "self.known_users" -dictionary cache
        """

        findServer = [x for x in discord_bot.guilds if str(x.id) == discord_settings["server"]]
        server = findServer[0]

        # Loop through channels (todo : get param channel & check only one)
        for item in settings["channel_sets"]:
            findChannel = [x for x in server.channels if str(x.id) == item and x.type == discord.ChannelType.text]
            if not len(findChannel):
                return
            settings["channel_sets"][item]["real_chan"] = findChannel[0]    
            currentChannel = settings["channel_sets"][item]["real_chan"]
            channell = discord_bot.get_channel(currentChannel.id)
            if channell is None:
                return

            # List channel members to known -users -dictionary
            all_members_in_channel = currentChannel.members

            # Save the users to bots discord-user-dictionary
            for member in all_members_in_channel:
                new_user_info = DiscordUserInfo(
                    user_id = member.id,
                    user_name = member.name,
                    user_nick = member.display_name,
                    status = member.status,
                    guilds = {currentChannel}
                )
                self.known_users[member.display_name] = new_user_info
        debug_print("[Discord] Known users / details updated") # Debug print all member infos

    #####################################
    #    SET & GET GLOBALS / VARIABLES  # 
    #####################################

    def set_irc(self, irc_bot_connection):
        """ Util function for setting the global IRC-Bot-Connection object"""
        global irc
        irc = irc_bot_connection

    def set_thread_lock(self, lock):
        """ Util function for setting the global thread lock object """
        global thread_lock
        thread_lock = lock

    def set_status(self, statusmsg=""):
        """ A self -advancing and repeating loop/routine to change between given bot-settings["status_messages"] in Discord 
        - If custom status message is given, displays that in Discord AND STOPS LOOPING the default statuses """
        
        # If discord is not yet connected, save the temp-status message
        if self.connected_to_discord == 0:
            self.temp_status_message = statusmsg
            return

        if statusmsg != "": # Set Custom status
            asyncio.run_coroutine_threadsafe(set_status_async(statusmsg, 5), discord_bot.loop)
            # Stop looping statuses if manual status is set
            if "set_status" in timers.timers:
                timers.cancel_timer("set_status")
            return

        # Or loop through settings.json -statuses with "Listening to..."
        c_status = settings["status_messages"][self.statusindex]
        asyncio.run_coroutine_threadsafe(set_status_async(c_status), discord_bot.loop)
        if self.statusindex < len(settings["status_messages"])-1:
            self.statusindex += 1
        else:
            self.statusindex = 0
        timers.add_timer("set_status", 300, self.set_status)

    def is_member(self, id):
        """ Returns a discord user/member by the ID - if known """
        guild = discord_bot.get_guild(int(discord_settings["server"]))
        member = guild.get_member(int(id))
        return member

    def get_discord_channel_topic(self, channel):
        """ Returns Discord channel topic """
        if channel.topic: # Check that it exists
            return channel.topic
        else:
            return "No topic set."

    #####################################
    #               DISCORD CLASS END ] # 
    ##################################### 
 
#####################################
#          MISC. UTILITIES          # 
##################################### 

def debug_print(message):
    """ debug print - with thread lock to the console """
    global thread_lock
    with thread_lock:
        print(message)

def fix_nick(nick):
    """ Util to regex scrape invalid characters out of a nick """
    new_nick = re.sub(r'[^A-Za-z0-9 ^\[\]\\{}`_-]+', '', nick)
    if new_nick == "":
        return False
    else:
        return new_nick

def get_urls_from_attachments(attach):
    """ Looks the discord attachment and returns the text/string URL from the attachment """
    urls = ""
    add = ""
    for i in range(len(attach)):
        urls += add + attach[i].url
        if add == "":
            add = " | "
    return urls

def dressup_replace(m, substr, replacement):
    """ Util function for replacing substrings with another substrings within a string (?) """
    if m.count(substr) == 1:
        return m
    m = m.replace(substr, replacement)
    return m

def irc_dressup(m):
    """ Helper function which will process a string to make it IRC-compatible
    - returns the IRC compatible string
    """
    msplit = m.split()
    for i in range(len(msplit)):
        if msplit[i].startswith("http") or msplit[i].startswith("<http"):
            msplit[i] = msplit[i].replace("_", "underdashreplacementplaceholderdiscordbotregexsucks")
    m = " ".join(msplit)
    m = dressup_replace(m, "***", "\x1d" + "\x02")
    m = dressup_replace(m, "**", "\x02")
    m = dressup_replace(m, "*", "\x1d")
    m = dressup_replace(m, "```", "")
    m = dressup_replace(m, "_", "\x1d")
    m = m.replace("underdashreplacementplaceholderdiscordbotregexsucks", "_")
    return m

def get_reference(reference_message, pin, new_msg_author, webhookid):
    """ 
    # Get Referenced message
    - Create a "reference" / "reply" -message from a referenced message
    - Combine the original author & content (or pinning information) of new message
    - return the combined string of what the reference is / was
    """
    rauthor = reference_message.author.display_name
    
    if rauthor == "" and str(reference_message.webhook_id) == webhookid:
        rauthor = rauthor[0:len(rauthor)-6]
    rurl = ""
    if len(reference_message.attachments) > 0:
        rurl = get_urls_from_attachments(reference_message.attachments)
        
    rcont = irc_dressup(reference_message.clean_content.replace("\n", " ").strip())
    if rcont == "":
        rcont = rurl
    if pin == False:
        rfull = f'{discord_settings["relayNickPrefix"]}{rauthor}{discord_settings["relayNickPostfix"]} {rcont} <<<'
    else:
        rfull = f'{new_msg_author} {irc.get_word("pinned_message")}: {discord_settings["relayNickPrefix"]}{rauthor}{discord_settings["relayNickPostfix"]} {rcont} <<<'
        
    return rfull

def replace_emojis(content):
    """Replace Discord custom emoji references with textual representations.
    
    Custom Discord emojis have the format `<:emoji_name:emoji_id>`. 
    This function replaces them with `:emoji_name:`.
    """
    regexc = re.compile(r'<:\w*:\d*>', re.UNICODE)  # Use raw string
    findmoji = re.findall(regexc, content)
    for moji in findmoji:
        namemoji = ":" + moji.split(":")[1] + ":"  # Extract emoji_name
        content = content.replace(moji, namemoji)
    return content

def do_extra_tag_cleanups(message):
    """ 
    # Do Extra Tag Cleanups
    - Fix some of the "known" formatting problems with current formats/syntaxes
    - like double << into single <, or <[ into just [ 
    - ie. fixes lazy syntaxing problems
    """
    # fix some of the "known" formatting problems with current formats/syntaxes
    message = message.replace("<<", "<")
    message = message.replace(">>", ">")
    message = message.replace("<[", "[")
    message = message.replace("]>", "]")
    return message

def give_local_timestamp_string(message_created_at):
    """
    # Give Local timestamp String
    - takes in a discord message.created_at
    - returns %H:%M formatted and local time fixed string
    """    
    timestampLocal = message_created_at + localTimeShiftToUTC
    timeFormatted = timestampLocal.strftime("%H:%M")
    return timeFormatted

def give_short_version_of_message(content, length):
    """
    # Give Short version of Message
    - takes in a message string & how many max chars we wanty
    - checks the length, and if needed, shortens the message
      and adds "..." prefix to indicate that message has been "cut short"
    -returns the shortened message
    """
    ## .. combine the reaction to snippet of original message
    if len(content) > length:
        shortMessage = content[:length]
        shortMessage += "..."
    else: # We want to refer max <length> character of original message to IRC
        shortMessage = content
    return shortMessage

################################
#        Async utils           #
################################

async def send_discord_message_async(discord_chan, message):
    """ Async Send message to Discord """
    await discord_chan.send(message.strip())

async def edit_my_message_async(msg_object, edit):
    """ Async Edit message at Discord """
    await msg_object.edit(content=edit)

async def del_my_message_async(msg_object):
    """ Async Delete my message from discord """
    await msg_object.delete()

async def set_status_async(status, activityType=2):
    """ Async Set the discord bot status
    - activityType = 0 = playing
    - activityType = 1 = streaming
    - activityType = 2 = listening
    - activityType = 3 = watching
    - activityType = 4 = custom
    - activityType = 5 = competing
    - !NOTE! Bots are not allowed to use the '4'-Custom type !
    """
    activity_type = discord.ActivityType.listening
    if activityType != 2:
        if activityType == 0:
            activity_type = discord.ActivityType.playing
        if activityType == 1:
            activity_type = discord.ActivityType.streaming
        if activityType == 3:
            activity_type = discord.ActivityType.watching
        if activityType == 4:
            activity_type = discord.ActivityType.custom
        if activityType == 5:
            activity_type = discord.ActivityType.competing
    await discord_bot.change_presence(activity=discord.Activity(type=activity_type, name=status))

async def shutdown_async():
    """ Async shutdown discord bot """
    await asyncio.sleep(2)
    await discord_bot.close()

async def do_async_stuff(target, delay, *arguments):
    """ Async Run the target function with given arguments after the delay time
    - @param : target Function
    - @param : delay Time 
    - @param : (function) arguments """
    await asyncio.sleep(delay)
    target(*arguments)

#####################################
#                                   #
#      Discord Bot functions        #
#        and event handlers         #
#                                   #
#####################################

# Set intents & Create discord bot
Intents = discord.Intents.all()
Intents.members = True
Intents.messages = True
Intents.presences = True
Intents.reactions = True
discord_bot = commands.Bot(command_prefix="!", intents=Intents)

#####################################
#  Discord -status update handling  #
#####################################
@discord_bot.event
async def on_presence_update(before, after):
    """ 
    # Discord Presence Update Event Handler / Hook
    - Async Update discord presence/status 
    """
    dname = after.display_name
    if dname in discordc.known_users:
        user_in_dict = discordc.known_users[dname]
        user_in_dict.status = str(after.status)

#####################################
#  Discord -edit handling           #
#####################################
@discord_bot.event
async def on_message_edit(before, after):
    """ 
    # Discord Edit Message Event Handler / Hook
    - Async Edit messages 
    - Check if the content actually differs
    - Fix timestamp to IRC -time 
    - Send before/after messages to IRC
    """
    # Certain conditions on which we don't want the bot to act
    if before.author == discord_bot.user:
        return
    if str(before.channel.id) not in settings["channel_sets"]:
        return
    if discordc.is_running == 0:
        return

    # Get & clean the before & after content
    beforecontent = replace_emojis(before.clean_content.replace("\n", " ").strip())    
    aftercontent = replace_emojis(after.clean_content.replace("\n", " ").strip())

    # If contents differ - carry on processing with the message
    if beforecontent != aftercontent:
    
        # Get channel & message details
        irc_chan = settings["channel_sets"][str(before.channel.id)]["irc_chan"]
        author = str(before.author.display_name)

        # fix timestamp & Format as HH-MM 
        timeFormatted = give_local_timestamp_string(before.created_at)

        # Update last used channels
        irc.last_used_channel = after.channel
        discordc.last_used_channel = after.channel

        cleanedBefore = irc_dressup(beforecontent)
        cleanedAfter = irc_dressup(aftercontent)

        editMessage = f'{discord_settings["relayTagUsed"]}{discord_settings["relayNickPrefix"]}{author}{discord_settings["relayNickPostfix"]} [EDIT] @\"{timeFormatted} {cleanedBefore}\" -> \"{cleanedAfter}\"'

        # and Relay to IRC
        irc.send_irc_message(irc_chan, editMessage)

        # debug print on console log
        debug_print("[Discord] " + editMessage)

#####################################
#  Discord -reaction handling       #
#####################################
@discord_bot.event
async def on_reaction_add(reaction, user):
    """ 
    # Discord Reaction Added Event Handler / Hook
    - Async React on discord-message
    - Create a "reaction" -string message for sending to IRC
    - Combine the emoji and timestamp/original message that it is reaction to
    - And then send as a irc message, for example; 
    - <discordNickname> :thumbsup: (@ 13:37 <ircUser> cool stuff at http://....)
    """
    if user == discord_bot.user:
        return  # skip bot's own reactions

    # ID if its on a channel we're actually monitoring
    channel_id = reaction.message.channel.id
    if str(channel_id) in settings["channel_sets"]:
        
        # Get the original message & details
        msg = reaction.message
        content = msg.clean_content
        author = msg.author

        # Update last used channels
        irc.last_used_channel = reaction.message.channel
        discordc.last_used_channel = reaction.message.channel

        irc_chan = settings["channel_sets"][str(channel_id)]["irc_chan"]

        # fix timestamp & Format as HH-MM 
        timeFormatted = give_local_timestamp_string(msg.created_at)

        # Build the description string about reaction
        reactionString = replace_emojis(str(reaction.emoji))
        ## .. combine the reaction to snippet of original message
        shortMessage = give_short_version_of_message(content, 70)

        # Format to our IRC-message relaying format 
        fixedMessage = f'{discord_settings["relayTagUsed"]}{discord_settings["relayNickPrefix"]}{user.display_name}{discord_settings["relayNickPostfix"]} {reactionString} (@ {timeFormatted} <{author.display_name}> {shortMessage})'
        
        # fix some of the "known" formatting problems with current formats/syntaxes
        fixedMessage = do_extra_tag_cleanups(fixedMessage)

        # Relay to IRC
        irc.send_irc_message(irc_chan, fixedMessage)

        # debug print on console log
        debug_print("[Discord] " + fixedMessage)

#####################################
#   Discord -message handling       #
#####################################
@discord_bot.event
async def on_message(message):
    """ 
    # Discord MESSAGE Added Event Handler / Hook
    - Async Discord Message
    - Verify the legitimity of the message according to our settings
    - Check if its a reply / has other sorts of attachments
    - Fetch the attachment URLS
    - Check matching IRC-channel & Send the message
    - Check for and handle known commands
    - HANDLE REPLYS:    
    - Create a "replied to" -string message for sending to IRC
    - Combine the reply and timestamp with original message that it is reply to
    - And then send as a irc message, for example; 
    - '<discordNickname> reply message (Re: 13:37 <ircUser> cool stuff at http://....)'
    """
    global thread_lock

    uptime = irc.get_uptime(True)

    if uptime <= 20:
        return

    #==================================
    # Update last used channels
    irc.last_used_channel = message.channel
    discordc.last_used_channel = message.channel

    ref = ""
    msgrefpin = False
    channel_id = str(message.channel.id)
    whid = None

    #==================================
    # Certain conditions on which we don't want the bot to act
    if message.author == discord_bot.user:
        return
    if channel_id not in settings["channel_sets"]:
        return
    if settings["channel_sets"][channel_id]["webhook"]:
        whid = settings["channel_sets"][channel_id]["webhook"].split("/")[5]
        if str(message.webhook_id) == whid:
            return
    if discordc.is_running == 0:
        return
    
    #==================================
    # Get matching irc-channel
    irc_chan = settings["channel_sets"][channel_id]["irc_chan"]

    #==================================
    # Detect if a message was pinned
    if message.type == discord.MessageType.pins_add:
        msgrefpin = True

    authorid = str(message.author.id)
    content = replace_emojis(message.clean_content.replace("\n", " ").strip())

    #==================================
    # Fix message attachments to URLs
    if len(message.attachments) > 0:
        urls = get_urls_from_attachments(message.attachments)
        if content == "":
            content = urls
        else:
            content = content + " " + urls
    if content == "" and msgrefpin == False:
        debug_print("Stickers/embed are not seen by discord.py")
        return    
    
    #==================================
    # Detect if the message is a reply to another message
    if message.reference:
        # Get the referenced message content
        refid = message.reference.message_id
        refinfo = await message.channel.fetch_message(refid)
        ref = get_reference(refinfo, msgrefpin, message.author.name, whid)

        # fix timestamp & Format as HH-MM 
        timeFormatted = give_local_timestamp_string(refinfo.created_at)

        # Build the description string the reply
        repliedToMessage = replace_emojis(str(ref))

        ## .. combine the reaction to snippet of original message
        shortMessage = give_short_version_of_message(repliedToMessage, 70)

        # fix some of the "known" formatting problems with current formats/syntaxes
        shortMessage = do_extra_tag_cleanups(shortMessage)

        # Add our reference message to after the reply
        content = f"{content} (Re: {timeFormatted}  {shortMessage})"

    # Debug print on terminal
    debug_print(f"[Discord] {message.channel.name} > [IRC] {irc_chan} {message.author.name}: {content}")
   
    ###################################
    # SEND the discord message to IRC #
    ###################################

    # Fix the discord message to include author & send to IRC
    fixedMessage = f'{discord_settings["relayTagUsed"]}{discord_settings["relayNickPrefix"]}{message.author.display_name}{discord_settings["relayNickPostfix"]} {content}'
    # Send the fixed discord-message to IRC:
    irc.send_irc_message(irc_chan, irc_dressup(fixedMessage))

    # Scrape URL's from discord messages and relay the titles to IRC
    timers.add_timer("", 1, irc.try_to_process_message_urls, content, irc_chan)

    ###################################
    #  USER & BOT OPERATOR COMMANDS   #
    ###################################

    # Take first word as "command" for later processing
    contentsplit = content.split()
    cmd = contentsplit[0].lower()

    # NOTE: add DM command !config to edit the config here

    #==================================
    # Bot-ops commands block    
    
    if authorid in discord_settings["bot_owner"]:

        # Bridge Shutdown command -  Quits IRC, kills Discord bot, stops process.
        if cmd == "!sammu" or cmd == "!shutdown":
            irc.bridge_shutdown(contentsplit)

        # Bot irc nickname change
        if cmd == "!nick" and len(contentsplit) == 2:
            irc.change_bot_ircnick(contentsplit[1])
            
        # Add given IRC-user to ignore join/part/quit -list
        elif cmd == "!ignorequits" and len(contentsplit) == 2:
            irc.ignore_user_joinsquits(irc_chan, contentsplit[1])

    #==================================
    # Public commands block
    
    # Help / apua - list commands
    if cmd == "!help" or cmd == "!apua" or cmd == "!apuva":
        if len(contentsplit) == 1:
            discordc.send_discord_message(message.channel, irc.get_help("listcommands"))
        else:
            help_dict = irc.get_help_dict()
            if contentsplit[1] in help_dict: # settings["help_dict"]:
                discordc.send_discord_message(message.channel, irc.get_help(contentsplit[1]))
    if cmd == "!info":
        discordc.send_discord_message(message.channel, irc.get_help("!info"))
    
    # Bridge uptime commmand - Simply sends the bot's uptime to Discord and IRC.
    elif cmd == "!status" or cmd == "!tila":
        discordc.send_uptime(message.channel, irc_chan)
    
    # Who are around in linked IRC-channel
    elif cmd == "!who" or cmd == "!ketä" or cmd == "!kuka":
        irc.query_irc_names_to_discord(irc_chan)
    
    # Topic of the linked IRC-channel
    elif cmd == "!topic" or cmd == "!otsikko":
        irc.query_irc_topic_to_discord(irc_chan)
            
    # Report the current BTC/USD value to both linked channels
    elif cmd == "!btc":
        irc.report_btc_usd_valuation(irc_chan)
            
    # Report the current MSTR/USD value to both linked channels
    elif cmd == "!mstr":
        irc.report_mstr_valuation(irc_chan)

    # Report the current market value for requested market symbol through yahoo finance
    elif cmd == "!stock" or cmd == "!value" or cmd == "!kurssi":
        if len(contentsplit) == 2:
            symbol_to_query = contentsplit[1]
            irc.get_and_report_stock_value(irc_chan, symbol_to_query)

    # Change language
    elif cmd == "!speak" or cmd == "!viännä" or cmd == "!puhu":
        if len(contentsplit) == 2: # verify that there is the second word
            new_language = contentsplit[1] # take second word as the language param
            set_new_lang = ""
            avail_langs = ""

            if new_language == settings["localization"]["used_language"]:
                discordc.send_discord_message(message.channel, f"{irc.get_word('lang_already_in_use')}")
            else:
                for lang in settings["localization"]:
                    if str(lang) != "used_language" and str(lang) != "_c13":
                        avail_langs += f"'{lang}' "
                        if lang == new_language:
                            set_new_lang = new_language

                if set_new_lang != "":
                    irc.change_language(set_new_lang)
                else:               
                    discordc.send_discord_message(message.channel, f'{irc.get_word("lang_in_use")} {irc.get_word("available_languages")} {avail_langs}')
        else:
            discordc.send_discord_message(message.channel, f'{irc.get_word("lang_in_use")} {irc.get_help(cmd)}')

#####################################
# Bot Connection Established-Event  #
#####################################
@discord_bot.event
async def on_ready():
    """ 
    # Discord Bot Ready & Connected Event Handler / Hook
    - Handling of successfull discord bot connection
    - Verify that the settings have been correctly fullfilled on Discord & Channels -part
    - Save connected/known Discord user details to local cache
    - Send the set channels to IRC - bot class for its local processing
    """
    global settings
    global discord_settings
    global thread_lock

    with thread_lock:
        # Print Discord bot / connection details
        print(f"[Discord] Logged in as: {discord_bot.user.name} ({str(discord_bot.user.id)})") 

        # Discord bot has not joined any discord server
        if len(discord_bot.guilds) == 0:
            print(f"[Discord] Bot is not yet in any server.")
            await discord_bot.close()
            return

        # Bot settings are missing a discord server - print available server ID's
        if discord_settings["server"] == "":
            print(f"[Discord] You have not configured a server to use in the config, please check: settings.json")
            print(f"[Discord] Input one of the ID's below when you are asked for the Discord Server ID")
            for server in discord_bot.guilds:
                print(f"[Discord] {server.name} {server.id}")
            await discord_bot.close()
            return

        # Verify that the bot is on the server that is in discord server setting
        findServer = [x for x in discord_bot.guilds if str(x.id) == discord_settings["server"]]
        if not len(findServer):
            print(f'[Discord] No server could be found with the specified id: {discord_settings["server"]}')
            print(f"[Discord] Available servers:")
            for server in discord_bot.guilds:
                print(f"[Discord] {server.name} {server.id}")
            await discord_bot.close()
            return
        server = findServer[0]

        # Channels missing from the settings
        if settings["channel_sets"] == {}:
            print(f"[Discord] You have not configured any channels sets. Please run check settings.json")
            print(f"[Discord] Input one of the channel IDs listed below when asked for channel ID")
            for channel in server.channels:
                if channel.type == discord.ChannelType.text:
                    print(f"[Discord] {channel.name} {channel.id}")
            await discord_bot.close()
            return

        # Loop through set channels & verify they match bot's/server's available channels
        for item in settings["channel_sets"]:
            findChannel = [x for x in server.channels if str(x.id) == item and x.type == discord.ChannelType.text]
            if not len(findChannel):
                print(f"[Discord] No channel could be found with the specified id: {item}")
                print(f"[Discord] Note that you can only use text channels.")
                print(f"[Discord] Available channels:")

                for channel in server.channels:
                    if channel.type == discord.ChannelType.text:
                        print(f"[Discord] {channel.name} {channel.id}")

                print("You can edit channel settings from settings.json")
                await discord_bot.close()
                return
            
            # Save the channel id's / caches & final verifications
            settings["channel_sets"][item]["real_chan"] = findChannel[0]
            currentChannel = settings["channel_sets"][item]["real_chan"]
            print(f"[Discord] Channel: {currentChannel.name} {currentChannel.id}")

            channell = discord_bot.get_channel(currentChannel.id)
            if channell is None:
                print(f"[Discord] Problem with channel")
                return

            #============================================================
            # Save all channel members to known discord-users -dictionary
            all_members_in_channel = currentChannel.members
            print(f"[Discord] Members in {currentChannel.name} :")
            for member in all_members_in_channel:
                print(f"[Discord]  - name:{member.name} / nick: {member.nick} / display: {member.display_name} (id:{member.id} (status: {member.status}))")
                # Save the users to bot-dictionary
                new_user_info = DiscordUserInfo(
                    user_id = member.id,
                    user_name = member.name,
                    user_nick = member.display_name,
                    status = member.status,
                    guilds = {currentChannel}
                )
                discordc.known_users[member.display_name] = new_user_info       

        # Give channels to irc
        irc.set_irc_channel_sets(settings["channel_sets"])

        # Discord initialization ok
        print("[Discord] DISCORD READY")
        discordc.connected_to_discord = 1
        if discordc.temp_status_message != "":
            discordc.set_status(discordc.temp_status_message)

