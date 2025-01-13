import irc.client
import logging
import time
import timers
import re
import requests               # 
from bs4 import BeautifulSoup # requests and bs4 are for http-page requests and the page Title + video Duration reporting to IRC

settings = None
irc_settings = None
bot_words = None

class IRC:
    """
        # IRC bot - Class (and all the utilities)
        - Data variables & details concerning the IRC-connection
        - Data caches about Channels & Users - both IRC & Discord -side
        - IRC event handlers 
        -- Keep bridged Discord-channels informed about linked IRC-channel
        -- Joins/parts/quits/kicks/topics
        - Respond to certain !commands, such as :
        -- !help for list of commands, or !topic for getting bridged 
           Discord-channel's topic, or !who to query whos online/around
           in Discord. etc..
        - Extra bridging/IRC-bot utilities/functionalities, such as:
        -- URL & Title & video duration parser : 
        --- inform URL-titles & youtube-video durations to 
            IRC-channel, when url-message found in Discord/IRC
    """

    def __init__(self, settings_):##nik, srv, prt):
        """ Save the bot-/bridge-settings and initialize logger and irc-bot """
        
        # Start Logger & File handler
        self.irc_logger = logging.getLogger('ircc')
        self.irc_logger.setLevel(logging.ERROR)

        irc_file_handler = logging.FileHandler('log_ircc_errors.log')  # Log to this file
        irc_file_handler.setLevel(logging.ERROR)

        irclogformatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        irc_file_handler.setFormatter(irclogformatter)
        self.irc_logger.addHandler(irc_file_handler)

        # Save global settings
        global settings
        global irc_settings
        global bot_words
        settings = settings_
        irc_settings = settings["irc"]
        # Save language & Used bot words
        used_language = settings["localization"]["used_language"]
        bot_words = settings["localization"][used_language]

        # init Reactor - the IRC-event -handler
        self.reactor = irc.client.Reactor()
        irc.client.ServerConnection.buffer_class.encoding = "utf-8"
        irc.client.ServerConnection.buffer_class.errors = "replace"        

        # set configurations from the settings
        self.is_running = 0
        self.irc_connection_successful = 0

        ## ! See the settings.json "comments" - for details concerning the settings !
        self.nick = irc_settings["bot_nickname"]
        self.server = irc_settings["server"]
        self.port = irc_settings["port"]
        self.bot_hostname = irc_settings["bot_hostname"]
        self.connection = self.reactor.server()
        self.connection.sent_quit = 0
        self.bot_realname = irc_settings["bot_realname"]
        self.callbacksAdded = 0

        self.nick_prefix_in_discord = irc_settings['ircNickPrefix']
        self.nick_postfix_in_discord = irc_settings['ircNickPostfix']
        ## ! See the settings.json "comments" - for details concerning the settings !
        self.network = ""                  # Cached IRC-server Network's name (IRCnet / Quakenet etc..)

        self.disconnectretries = 0         # Counter for disconnect retries
        self.maxConnectRetries = 10        # How many connecting-retries allowed before failing

        self.irc_channel_sets = {}         # The full irc-channel - discord -channel/webhooks -dictionary
        self.irc_channels_lists = {}       # Irc-channel <-> Irc-nicknames dictionary cache        
        self.irc_user_statuses = {}        # Dict / cache for irc user channel-statuses @todo : could/should combine channel lists & user status to one dict
        # @todo - in addition to caching just name + status ++ add also channel?
        self.known_discord_users = {}      # IRC-bot -side cache of Discord-users

        self.myprivmsg_line = ""           # Cache of received last private line
        self.last_used_channel = ""     # Cache of last used discord channel
        self.channel_spam_prots = {}
      
    #####################################
    #        CORE RUN / STOP            # 
    #####################################
    
    def run(self):
        """
        # Run IRC 
        - Start the IRC-bot loop
        - Connect to server
        - Keep processing IRC events
        - Keep connection and handle the events until shutdown -signal received
        """
        self.debug_print("[IRC] Starting irc-bot loop")

        self.is_running = 1
        self.start_time= int(time.time())

        # Initialize connection variables 
        # & Connect to IRC-server
        self.connect()
        # ... if the connection fails, we will receive fail/disconnect event,
        #     and the re-connecting is handled then from the event loop.

        # IRC-bots event handling -loop
        loop_process_time = 0.01 # 0.2 original -> 0.1, but fast messages not beying relayed still (?)
        while self.is_running:
            try:
                self.reactor.process_once(loop_process_time)
                time.sleep(loop_process_time)
            except Exception as e:
                self.on_error(f"Caught an error : {e}")

    def connect(self):
        """ 
        # Connect to the irc server 
        - Connect - and Retry connecting if it fails - to the IRC-server
        - Add IRC-event message handlers
        """
        self.debug_print("[IRC] Connecting to irc server ...")
        self.discord.set_status("Connecting to IRC...")        
        try:
            c = self.connection

            # Add event handlers / callbacks (but only once)
            if self.callbacksAdded == 0:
                c.add_global_handler("all_raw_messages", self.on_all_raw) # ! Should remove the RAW-messages after connection establishment to not spam !
                c.add_global_handler("pubmsg", self.on_pubmsg)
                c.add_global_handler("join", self.on_join)
                c.add_global_handler("part", self.on_part)
                c.add_global_handler("namreply", self.on_namreply)
                c.add_global_handler("action", self.on_pubmsg)
                c.add_global_handler("quit", self.on_quit)
                c.add_global_handler("welcome", self.on_connect)
                c.add_global_handler("nicknameinuse", self.on_nicknameinuse)
                c.add_global_handler("kick", self.on_kick)
                c.add_global_handler("featurelist", self.on_featurelist)
                c.add_global_handler("nick", self.on_nick)
                c.add_global_handler("disconnect", self.on_disconnect)
                c.add_global_handler("ping", self.on_ping)
                c.add_global_handler("error", self.on_error_event)
                c.add_global_handler("whoreply", self.on_whoreply)
                c.add_global_handler("privmsg", self.on_privmsg)
                c.add_global_handler("topic", self.on_topic)
                #c.add_global_handler("privnotice", self.on_privnotice)
                # Numeral hooks/handlers do not seem to work for some reason on IRCnet ?
                # -> Currently parsing these from Raw Events and calling these from the Raw Handler.. 
                ## c.add_global_handler("331", self.on_rpl_notopic)
                ## c.add_global_handler("332", self.on_rpl_topic)
                ## c.add_global_handler("333", self.on_rpl_topicwhotime)
                self.callbacksAdded = 1            
            
            c.connect(self.server, self.port, self.nick, None, self.bot_hostname, self.bot_realname)
            # With successfull connection - add all callbacks
            if self.connection:
                self.debug_print("[IRC] Connecting ...")

            # Retry if unsuccessfull conncetion
            else:
                self.debug_print(f"[IRC] Problem connecting to server ... retrying")
                self.connect() # retry
                return
            
        # Retry if exception while connecting
        except Exception as e:
            self.on_error(f"[IRC] Problem connecting to server : {e} - retrying")
            self.connect() # retry
            return
        
    def bridge_shutdown(self, message):
        """ 
        # Call function for shutting down the whole bot/bridge -process 
        - First notify the linked IRC & Discord channels about shutdown
        - Then shutdown the bots & connections properly
        """
        self.discord.set_status("Shutting down Bridge")

        # announce the shutdown
        uptime = self.get_uptime()
        reason = ""
        if len(message) > 1:
            reason = " ".join(message[1:])
        if reason == "":
            shutdownMessage = f'** `!! {self.get_word("shutdownmessage")} {uptime} !!` **'
        else:
            shutdownMessage = f'** `!! {self.get_word("shutdownmessage")} {uptime} *({reason})* !!` **'
        self.discord.send_to_all_discord_channels(shutdownMessage)
        self.send_to_all_irc_channels(shutdownMessage)

        # save current runtime settings AFTER Announcement - as we unload the discord channels before saving settings
        self.save_settings_to_json()
        
        # shutdown
        time.sleep(2)
        self.discord.shutdown(reason)

    def stop_loop(self):
        """ Stop the main irc-bot-loop """
        self.is_running = 0

    def sent_quit_on(self):
        """ Set quit/shutdown variable as reaction to event """
        self.connection.sent_quit = 1

    #####################################
    #        SEND MESSAGES              # 
    #####################################

    def send_message(self, channel, msg, action=False):
        """ Send a given message to a referred channel (as "action" if requested) """
        if not self.connection.is_connected():
            return
        
        # Split the message into suitable parts
        #self.debug_print(self.get_myprivmsg_line(channel))
        msg_parts = self.split_msg(msg, 479 - len(self.get_myprivmsg_line(channel))) # Need to split the messages to shorter pieces to ensure no missing words !

        # Check for split/multi message send
        if len(msg_parts) > 1:          
            # Send each part with a consistent delay
            send_delay = 0.1  
            for part in msg_parts:
                # time.sleep(0.5)  # Fixed delay between messages
                if action:
                    #self.connection.action(channel, f"{part}")
                    #self.debug_print(f"send part-action {channel} : {part}")
                    timers.add_timer("", send_delay, self.connection.action, channel, f"{part}")
                else:
                    #self.connection.privmsg(channel, f"{part}")
                    #self.debug_print(f"send part-msg {channel} : {part}")
                    timers.add_timer("", send_delay, self.connection.privmsg, channel, f"{part}")
                send_delay += 0.4                
        # Send a single message with no delay
        else: 
            for part in msg_parts:
                if action:
                    #self.debug_print(f"send action {channel} : {part}")
                    self.connection.action(channel, f"{part}")
                else:
                    #self.debug_print(f"send msg {channel} : {part}")
                    self.connection.privmsg(channel, f"{part}")


    def send_irc_message(self, irc_chan, message):
        """ The IRC-Bot sends a given message to the referred channel """
        self.send_message(irc_chan, message)

    def send_irc_and_discord(self, irc_chan, message): #self.debug_print("send_irc_and_discord-test")    
        """ Send message to both IRC-channel and to the connected discord """
        self.send_irc_message(irc_chan, message)
        self.discord.send_discord_message(self.irc_channel_sets[irc_chan]["real_chan"], message)

    def send_to_last_channel(self, message): #self.debug_print("sendtolastchan-test")   
        """ Sends message to last used channel - be it IRC/Discord """ 
        if type(self.last_used_channel) == str:
            self.send_irc_message(self.last_used_channel, message)
        else:
            self.discord.send_discord_message(self.last_used_channel, message)

    def send_to_all_irc_channels(self, message):
        """ Send message to all joined/known IRC-channels """
        for irc_chan in self.irc_channel_sets:
            self.send_irc_message(irc_chan, message)

    def send_to_matching_discord(self, nick, message):
        """ Sends message to a DISCORD channel where the matching nickname / user is found """
        for each_channel in self.irc_channels_lists:
            if nick in self.irc_channels_lists[each_channel]:
                if each_channel in self.irc_channel_sets:
                    self.discord.send_irc_msg_to_discord(self.irc_channel_sets[each_channel]["real_chan"], None, message) # self.discord.send_discord_message(self.irc_channel_sets[each_channel]["real_chan"], message)

    ############################################
    #            MISC UTILITIES                # 
    # - Debug printing / set & get vars / etc  #
    ############################################

    def debug_print(self, message):
        """ print on console with thread lock (= mutex ?) """
        if self.thread_lock.locked(): # Called from Discord setup - already locked
            print(message)
        else:
            with self.thread_lock:
                print(message)

    def change_language(self, new_language):
        """
        # Change IRC Bot Language
        - take in parameter of new 'language code'
        - Change bot's bot_word -dictioanry to refer to new language
        """
        global settings
        if new_language == "used_language" or new_language == "_c13" or new_language == settings["localization"]["used_language"]:
            return # these are not valid language -options, other can be added. (or we dont want to change to same language we already using)
        
        global bot_words
        if new_language in settings["localization"]:
            # if new language found, change IRC-bot language
            settings["localization"]["used_language"] = new_language
            bot_words = settings["localization"][new_language]
            # Announce new language on all channels
            self.send_to_all_irc_channels(f"{self.get_word('new_language_announce')}")
            self.discord.send_to_all_discord_channels(f"{self.get_word('new_language_announce')}")

    def extract_first_irc_channel(self, text):
        """ 
        # Extracts #irc-channel out of a text
        - split the string and go through words
        - if ' #word ' is found with only a single #
        - return the first match
        """
        # Split the text
        words = text.split()

        # Go through the words
        for word in words:
            # If the words "seems" like irc-channel / begins with #, return it
            if word.startswith("#") and word.count("#") == 1 and len(word) > 1:
                return word # Return found match
        return None # Return none as no matches found
    
    def get_matching_discord_channel(self, irc_channel):
        """
        # Get matching Discord channel by IRC-channel
        - Go through known channel sets
        - return the Discord-channel(ID) if match found
        """
        for item in self.irc_channel_sets:
            if item == irc_channel:
                return self.irc_channel_sets[item]["real_chan"]
        return None # Or return None if no match found
            
    def get_myprivmsg_line(self, channel):
        """ Return a private message lien froma given channel (?) """
        return f"{self.myprivmsg_line} {channel} :"

    def set_discord(self, disc):
        """ Sets the global discord -variable from given param """
        self.discord = disc

    def set_thread_lock(self, lock):
        """ Sets the global thread_lock -variable from given param """
        self.thread_lock = lock

    def get_start_time(self):
        """ Returns the IRC start-time -variable """
        return self.start_time

    def get_uptime(self, raw=False):
        """        
        # Returns the current runtime/uptime 
        - calculated from the start time at request
        """
        result = ""
        uptime = int(time.time()) - self.start_time
        if raw == True:
            return uptime
        day = uptime // (24 * 3600)
        uptime = uptime % (24 * 3600)
        hour = uptime // 3600
        uptime %= 3600
        minutes = uptime // 60
        uptime %= 60
        seconds = uptime
        if day > 0:
            result += f'{str(day)}{self.get_word("day_short")} '
        if hour > 0:
            result += f'{str(hour)}{self.get_word("hour_short")} '
        if minutes > 0:
            result += f'{str(minutes)}{self.get_word("minute_short")} '
        if seconds > 0:
            result += f'{str(seconds)}{self.get_word("second_short")} '
        return result

    def get_connection(self):
        """ Return the self's = IRC-CONNECTION """
        return self.connection

    ############################################
    #        CHANNEL / USER DATA CACHING       # 
    ############################################

    def set_irc_channel_sets(self, sets):
        """ Sets the self.irc_channel_sets -variable from given param (given from Discord bot at initialization) """
        
        self.irc_channel_sets = {}
        for item in sets:
            value = sets[item]
            self.irc_channel_sets[value["irc_chan"]] = {"discord_chan": item, "webhook": value["webhook"], "real_chan": value["real_chan"]}
            self.channel_spam_prots[value["irc_chan"]] = {"topic_asked":0, "topic_told": 0, "topic":"", "names_asked": 0, "names_told" : 0, "names":""}

        # If IRC-connection is already established when receiving the channels, join to them
        if self.irc_connection_successful == 1:
            self.slow_join_to_set_channels()
    
    def pop_from_channels(self, nick):
        """ Removes the given nickname/users from a channel cache """
        for each_channel in self.irc_channels_lists:
            if nick in self.irc_channels_lists[each_channel]:
                if each_channel in self.irc_channel_sets:
                    self.irc_channels_lists[each_channel].pop(nick)

    def is_on_channel(self, channel, nick):
        """ Returns true if a requested nickname is found from a given channel, false if not """
        if nick in self.irc_channels_lists[channel]:
            return True
        else:
            return False

    def query_irc_names_to_discord(self, channel):
        """ Function which flags / implicates that the irc users are requested to discord as information """
        # Check for channel specific spam prot
        if channel in self.channel_spam_prots:
            oldNamesTime = self.channel_spam_prots[channel]["names_asked"]
            curTime = int(time.time()) # self.debug_print(f"spamtest names_asked | oldTime {oldNamesTime} curtime {curTime}")
            if oldNamesTime == 0 or oldNamesTime + 5 < curTime:
                self.channel_spam_prots[channel]["names_asked"] = curTime     
            else: # self.debug_print("spamtest names_asked blocked")
                return
        self.connection.names(channel)

    def update_irc_users(self, channel, names):
        """ Known irc users & statuses per channel - caching  """
        splitNames = names.split()
        prefix = ""
        actual_name = ""

        for name in splitNames:
            if name.startswith(("@", "+")):
                prefix = name[0]
                actual_name = name[1:]
            else:
                prefix = ""
                actual_name = name
            # update statuses
            self.irc_user_statuses[actual_name] = prefix

            # update the channel lists
            if channel not in self.irc_channels_lists:
                self.irc_channels_lists[channel] = {}
            self.irc_channels_lists[channel][actual_name] = {"host": "?"}
            
        self.debug_print(f"[IRC] Users updated on channel :{str(channel)} {str(self.irc_user_statuses)}")

    def get_irc_user_statuses(self):
        """ Return the currently cachec IRC-users & their statuses """
        return self.irc_user_statuses
    
    def get_word(self, request_word):
        """ 
        # Get Word
        - Looks up the requested word from Bot localization / language dictionary
        - returns the correct word by currently used language
        - or fallback to english word (or return error if requesting invalid word)
        """
        # Get the word from currently used language
        for word in bot_words:
            if word == request_word:
                return bot_words[word]
        # Try to fallback and get the word from english
        for word in settings["localization"]["en"]:
            if word == request_word:
                return settings["localization"]["en"][word]        
        # return error
        return "<missingword>"
    
    def get_help(self, req_help):
        """ 
        # Get Help
        - Looks up the help text from Bot localization / language dictionary
        - returns the correct help text by currently used language
        - or fallback to english"
        """        
        # Get the word from currently used language
        for word in bot_words["help_dict"]:
            if word == req_help:
                return bot_words["help_dict"][word]
        # Try to fallback and get the word from english
        for word in settings["localization"]["en"]["help_dict"]:
            if word == req_help:
                return settings["localization"]["en"]["help_dict"][word]        
        # return error
        return "<missingword>"
        
    def get_help_dict(self):
        """ Returns the by current language used help-dictionary  """
        return bot_words["help_dict"]
    
    def change_bot_ircnick(self, new_botnick):
        """ Allows changeing of the bot's IRC name (in case of reconnects / auto-renames etc) - for bot operators only """        
        self.connection.nick(new_botnick)
        # Also change the bot nickname to (runtime) settings, to prevent auto nick name recovery
        global irc_settings
        irc_settings["bot_name"] = new_botnick

    def try_to_get_original_nickname(self):
        """ The bot tries to use the originally set nickname again (which might have been lost on reconnect etc..) """        
        cnick = self.connection.get_nickname()
        if cnick != irc_settings["bot_nickname"]:
            newnick = irc_settings["bot_nickname"]
            self.connection.nick(newnick)

    def keep_set_nick_loop(self):
        """ self-repeating loop that keeps checking the bot's irc nickname, and tries to change back to the original nick name if it has changed """   
        # Try to recover the original nickname
        self.try_to_get_original_nickname()   
        # Check again in 10 seconds  
        timers.add_timer("recover_botname", 10, self.keep_set_nick_loop)        
      
    def ignore_user_joinsquits(self, irc_channel, user_to_ignore):
        """ if there is a known IRC-user causing join/part/quit -spam on the channel, you can set the nicknames with this function to ignore 
            that spam for Discord """
        if user_to_ignore in irc_settings["ignore_parts_joins"]:
            self.send_irc_and_discord(irc_channel, f"User {user_to_ignore} was already on ignore list for JOINS/PARTS/QUITS.")
            return # user was already on ignore

        # Add ignore and announce
        irc_settings["ignore_parts_joins"].append(user_to_ignore)
        self.send_irc_and_discord(irc_channel, f"Ignoring IRC-user {user_to_ignore} for JOINS/PARTS/QUITS from now on.")

    def save_settings_to_json(self):
        """ # Save settings to JSON
        - Saves the current runtime-settings to the settings.json:
        -- Language, IgnoreQuits, ?
        - Allows saved settings to be loaded next time bot runs """
        import json

        # Remove / unload the Discord channels
        for channel in settings["channel_sets"]:
            settings["channel_sets"][channel].pop("real_chan")

        # Save settings to JSON
        with open("settings.json", "w", encoding="utf-8") as outfile:
            json.dump(settings, outfile, ensure_ascii=False, indent=4)

    ############################################
    #        TOPIC UTILITIES                   # 
    ############################################

    def query_irc_topic_to_discord(self, channel):
        """ Query topic for an irc channel"""
        # Check for channel specific spam prot
        if channel in self.channel_spam_prots:
            oldTopicTime = self.channel_spam_prots[channel]["topic_asked"]
            curTime = int(time.time()) # self.debug_print(f"spamtest topic_asked | oldTime {oldTopicTime} curtime {curTime}")
            if oldTopicTime == 0 or oldTopicTime + 5 < curTime:
                self.channel_spam_prots[channel]["topic_asked"] = curTime
            else: # self.debug_print("spamtest topic_asked blocked")
                return
        try:
            self.connection.topic(channel)
        except Exception as e:
            self.on_error(f"Error with topic querying : {e}")
    
    #####################################
    #                                   #
    #        MESSAGE PROCESSING         # 
    #      UTILITIES & HELPERS          #
    #                                   #
    #####################################

    def irc_to_disc_text(self, message):
        """         
        Processes and re-formats a given IRC message to be properly fit for sending to Discord.
        
        - Removes IRC color codes and formatting.
        - Escapes underscores in URLs.
        - Converts IRC-style formatting to Markdown-compatible Discord formatting.
        """
        bold_italic = 0
        # Use raw string for regex to avoid SyntaxWarning
        regexc = re.compile(r"\x03(\d{1,2}(,\d{1,2})?)?", re.UNICODE)
        
        # Replace specific IRC formatting characters
        message = message.replace("\x1d", "\\x1d")  # Temporarily escape underline
        msplit = message.split()
        
        # Replace underscores in URLs with placeholder
        for i in range(len(msplit)):
            mi = msplit[i]
            if mi.startswith("http") or mi.startswith("<http"):
                msplit[i] = mi.replace("_", "pholderunderdash95130")
        
        # Rejoin the split message
        message = " ".join(msplit)
        
        # Remove additional IRC formatting codes
        message = message.replace(r"\x31", "")
        message = message.replace("\x0f", "")
        message = message.replace(chr(2) + chr(29), "***")
        message = message.replace(chr(29) + chr(2), "***")
        message = message.replace(chr(2), "**")
        
        # Ensure underline formatting is even
        if message.count(chr(29)) % 2 != 0:
            message = f"{message} {chr(29)}"
        
        # Restore escaped underline and clean up IRC color codes
        message = message.replace("\\x1d", "_")
        message = regexc.sub("", message)  # Remove color codes
        
        # Ensure Markdown bold/italic formatting is even
        if message.count("***") % 2 != 0:
            message = message + "***"
            bold_italic = 1
        if message.count("**") % 2 != 0:
            if bold_italic == 0:
                message = message + "**"
        
        # Restore underscores in URLs
        message = message.replace("pholderunderdash95130", "_")
        
        return message
    
    def split_msg(self, msg, max_chars):
        """        
        # Split Message
        - Split by spaces while preserving IRC formatting codes
        - Processes a given string to an list/array of string with maximum character length
        - returns the processed string array/list
        """
        all_pieces = []
        current_piece = ""

        msgsplit = re.split(r'(\s+)', msg)  # Retain whitespace as part of tokens
        
        for part in msgsplit:
            if len(current_piece) + len(part) <= max_chars:
                current_piece += part  # Append to the current piece
            else:
                if current_piece:  # Add the full piece to the list
                    all_pieces.append(current_piece.strip())
                current_piece = part  # Start a new piece
                
        if current_piece:  # Add the remaining part
            all_pieces.append(current_piece.strip())
   
        return all_pieces

    def send_irc_topic_to_discord(self, topicString, irc_channel):
        """ 
        # Send the given IRC Topic string to Discord
        - Get matching Discord channel by IRC-channel
        - Send the Topic String
        - Handle topic spam protections
        """
        # Check for channel specific spam prot
        if irc_channel in self.channel_spam_prots:
            oldTopicTime = self.channel_spam_prots[irc_channel]["topic_told"]
            oldTopic = self.channel_spam_prots[irc_channel]["topic"]
            curTime = int(time.time())  # self.debug_print(f"spamtest topic_told | oldTime {oldTopicTime} curtime {curTime}")
            if oldTopicTime == 0 or oldTopicTime + 5 < curTime:
                self.channel_spam_prots[irc_channel]["topic_told"] = curTime
                self.channel_spam_prots[irc_channel]["topic"] = topicString
            elif oldTopic == "" or oldTopic != topicString:
                self.channel_spam_prots[irc_channel]["topic_told"] = curTime
                self.channel_spam_prots[irc_channel]["topic"] = topicString
            else: # self.debug_print("spamtest topic_told blocked")
                return

        # Matching discord-channel:
        discord_channel = self.get_matching_discord_channel(irc_channel)
        if discord_channel == None:
            discord_channel = self.last_used_channel

        # Send the topic
        timers.add_timer("", 1.0, self.discord.send_irc_msg_to_discord, discord_channel, None, topicString)
        #self.discord.send_irc_msg_to_discord(discord_channel, None, topicString) 

        # Debugs / Spam checks      
        self.debug_print(f"[IRC] Topic to [Discord] : {topicString}")

    def process_and_send_topic_string(self, topicArgs):
        """ 
        # Utility to extract topic and get the known IRC-channel 
        - then send the formatted channel-topic-info string
          to matching discord channel
        """

        topicstring = re.sub(r'^:[^:]*:', '', str(topicArgs))

        # Try to extract the irc-channel from the event reply itself
        irc_channel = self.extract_first_irc_channel(topicArgs)
        # ! Old way as backup: !
        if irc_channel is None:
            # @todo - better way to figure out the channel
            #  becouse this does not work at bot join
            irc_channel = "?"
            for item in self.irc_channel_sets:
                if self.irc_channel_sets[item]["real_chan"] == self.last_used_channel:
                    irc_channel = item
                    break
            # The actual problem / bug lies in the fact that the 331/332/333 topic event 
            # replies are a single plain string, from which there is no readily parsed
            # IRC-channel to target these queries to @todo : parse the irc-channel 
            # from the full event -sttring...

        # Format & fix the topic string to channel and to discord message
        fullTopicString = f'{self.get_word("topic_word")} @ {irc_channel} : **{topicstring}**'

        # Send to Matching discord-channel:
        self.send_irc_topic_to_discord(fullTopicString, irc_channel)

    def extract_urls(self, message):
        """ Find all URLs in the message / Check string for URLs and return the URLs, if found 
        - Return the found URLs """
        url_pattern = re.compile(r'(https?://[^\s]+)') # regex pattern for extracting URLs
        return url_pattern.findall(message)

    def get_page_soup(self, url):
        """ Returns the Beautiful Soup -parse of html-page from URL address 
        - Should call this by non-blocking means (timers) / from separate thread, to not block the event handlers """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        } # Present ourself as a web-browser when making the page-requests, as some sites do not otherwise care to respond.
        try:
            response = requests.get(url, headers=headers, timeout=10)  #  We need to get the response in 2 seconds for this to not block the bot too much. @todo async
            response.raise_for_status()                        # Raise an exception for HTTP errors
            response.encoding = response.apparent_encoding     # Try to correct the character enconding (to fix for example scandinavic letters 'äöå' etc)
            soup = BeautifulSoup(response.text, 'html.parser') # Parse the http-response
            return soup
        except Exception as e:
            self.on_error(f"Error fetching soup - {url} : {e}")
            return None

    def get_title_from_soup(self, soup):
        """ Return <title> webpage title </title> from soup parse of http-page """
        try:
            title = soup.title.string.strip() if soup.title else None
            return title
        except Exception as e:
            self.on_error(f"Error get_title_from_soup: {e}")
            return None
        
    def get_short_description_from_soup(self, soup):
        """ Look the http-soup for 'short description', 
        which we can print to IRC for information about URL """

        # Check for Open Graph description
        og_desc = soup.find('meta', attrs={'property':'og:description'})
        if og_desc and og_desc.get('content'):
            return og_desc['content'].strip()

        # Check for Twitter description
        twitter_desc = soup.find('meta', attrs={'name':'twitter:description'})
        if twitter_desc and twitter_desc.get('content'):
            return twitter_desc['content'].strip()

        # Check for standard meta description
        meta_desc = soup.find('meta', attrs={'name':'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content'].strip()

        # Fallback to the first paragraph
        first_paragraph = soup.find('p')
        if first_paragraph: # Use " " -separator to fix wikipedia-kind of http-syntax
            return first_paragraph.get_text(separator=" ", strip=True)

    def parse_iso8601_duration(self, iso_duration):
        """ Parses and returns video iso8601 duration from YouTube duration metadata content """
        import isodate
        try:
            duration = isodate.parse_duration(iso_duration)
            return int(duration.total_seconds())
        except Exception as e:
            self.on_error(f"Error parse_iso8601_duration: {e}")
            return None
    
    def format_seconds_to_hms(self, total_seconds):
        """ # Format seconds to hours / minutes / seconds
         - return string {hours}h {minutes}m {seconds}s (according to localization settings) """
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f'{hours}{self.get_word("hour_short")} {minutes}{self.get_word("minute_short")} {seconds}{self.get_word("second_short")}'
        else:
            return f'{minutes}{self.get_word("minute_short")} {seconds}{self.get_word("second_short")}'

    def get_video_dur_from_soup(self, soup):
        """ Return video duration from soup response, or None if no duration found """
        try:
            schemaDuration = soup.find("meta", itemprop="duration")
            if schemaDuration and 'content' in schemaDuration.attrs:
                seconds = self.parse_iso8601_duration(schemaDuration['content'])
                return self.format_seconds_to_hms(seconds)
            else:
                return None        
        except Exception as e:
            self.debug_print(f"Error with fetching video duration metadata")
            return None
        
    def report_btc_usd_valuation(self, irc_channel):
        """
        # Report BTC/USD valuation
        - fetch the current course from CoinMarketCap
        - report the current ratio to IRC-channel and the linked Discord -channel
        """
        url = "https://coinmarketcap.com/currencies/bitcoin/"
        soup = self.get_page_soup(url)

        # Get price element # price_element = soup.find("div", class_="priceValue") # sc-65e7f566-0 WXGwg base-text
        price_element = soup.find("div", class_="sc-65e7f566-0 czwNaM flexStart alignBaseline")
        if price_element:
            price = price_element.text.strip()
            priceString = f"BTC/USD : {price}"
        else:
            priceString = f"Problem connecting to {url}"
        
        self.send_irc_and_discord(irc_channel, priceString)

    def report_mstr_valuation(self, irc_channel):
        """ Report MSTR/USD valuation to given IRC-channel and the linked Discord -channel """
        self.get_and_report_stock_value(irc_channel, "MSTR")

    def get_and_report_stock_value(self, irc_channel, market_symbol):
        """
        # Report MSTR/USD valuation
        - fetch the current course from Yahoo Markets
        - report the current ratio to IRC-channel and the linked Discord -channel
        """
        url = f"https://finance.yahoo.com/quote/{market_symbol}/"
        soup = self.get_page_soup(url) # container yf-1tejb6
 
        # Get price element # price_element = soup.find("div", class_="priceValue") # sc-65e7f566-0 WXGwg base-text
        price_element = soup.find("div", class_="container yf-1tejb6")
        if price_element:
            price = price_element.text.strip()
            priceString = f"{market_symbol}/USD : {price}"
        else:
            priceString = f"Problem connecting to {url}"
        
        self.send_irc_and_discord(irc_channel, priceString)


    def process_message_urls(self, message, irc_channel):
        """ 
        # Process message for potential URLs 
        - If URLs found, report to IRC-channel the :
        - Webpage titles 
        - And/or video durations
        - Short descriptions
        """
        
        urls = self.extract_urls(message)
        for url in urls:
            soup = self.get_page_soup(url)                # Request the http-parse/soup from given URL
            title = self.get_title_from_soup(soup)        # Get the page-title from soup
            description = self.get_short_description_from_soup(soup) # Get the short description from soup
            duration = self.get_video_dur_from_soup(soup) # Get the youtube video duration from soup
            if (title):
                titleString = f"{title}"
                fullInfoString = titleString
            else: # could not get title
                return            
            
            # Combine title with Duration, if available
            if (duration):
                fullInfoString += f" | {duration}"
            
            # Contain the infostring in ( ) for clarity
            fullInfoString = f"({fullInfoString})"
            
            if (fullInfoString): # Send the title + duration info-string
                self.send_message(irc_channel, fullInfoString)
            if (description):    # Send the short-description info-string
                description_string = f"({description})"
                self.send_message(irc_channel, description_string)
   
    def try_to_process_message_urls(self, message, irc_channel):
        """ Wrapper for processing the message URLs with exception handling 
         - use this through timers/async to not block the threads while
           processing the URLs """
        try:
            self.process_message_urls(message, irc_channel)
        except Exception as e:
            self.on_error(f"Problem with URL processing : {e}")

    def print_discord_topic_to_irc(self, discord_chan, irc_chan):    
            """ Print discord channel topic on the IRC channel  """
            topic = self.discord.get_discord_channel_topic(discord_chan)
            discordTopicMessage = f'[Discord] #{discord_chan} - {self.get_word("topic_is")}: {topic}'
            self.send_message(irc_chan, discordTopicMessage)

    ################################################################
    #                                   
    #        IRC EVENT HANDLERS         
    # - Responses to various events that are sent from IRC server.      
    # - What needs to be done on connect/join/message/etc..
    #                                   
    ################################################################

    def on_ping(self, connection, event):
        """ Event handling for ping reactions """
        if connection == self.connection:
            return
        return

    def on_nicknameinuse(self, connection, event):
        """ Renames an irc-bot-client's nickname if given nickname was in use """
        cnick = connection.get_nickname()
        if cnick[-3:] == "[R]":
            newnick = f"{cnick[0:len(cnick)-3]}_[R]"
        else:
            newnick = f"{cnick}_"
        connection.nick(newnick)

    def on_all_raw(self, connection, event):
        """
        # Event handler for logging ALL raw data 
        - From the irc server (used while connecting/debugging)
        - Used to get the topic replies in IRCnet - as unable to catch them otherwise (?)
        """

        # This prints all traffic from irc-server if handled
        # self.debug_print(f"[IRC][RAW] {event.source} - {event.type} - {event.arguments}")

        splitArgs = str(event.arguments)#.split()

        # 020 = Connection initializing / handshaking with server
        if " 020 " in splitArgs:            
            self.debug_print(f"[IRC][RAW] {event.arguments}")
            return
        # 001 = Welcome message
        elif " 001 " in splitArgs: # Connection successful & finalized (?)
            self.irc_connection_successful = 1
            self.debug_print(f"[IRC][RAW] {event.arguments}")
            return
        # 331 - No topic -reply
        elif " 331 " in splitArgs:
            self.on_rpl_notopic(connection, event)
            return
        # 332 - Topic reply
        elif " 332 " in splitArgs:
            self.on_rpl_topic(connection, event)
            return
        # 333 - Topic Who / When -reply
        elif " 332 " in splitArgs:
            self.on_rpl_topicwhotime(connection, event)
            return
      
    def on_namreply(self, connection, event):
        """ Relay the returned names to Discord (per !who -request from Discord) 
        - Check for channel-specific spam-protection """

        if connection != self.connection: 
            return # self.debug_print("error?")
        
        channel = event.arguments[1]            
        names = event.arguments[2]
        # Check for channel specific spam prot
        if channel in self.channel_spam_prots:
            oldNamesTime = self.channel_spam_prots[channel]["names_told"]
            oldnames = self.channel_spam_prots[channel]["names"]
            curTime = int(time.time()) # self.debug_print(f"spamtest names_told | oldTime {oldNamesTime} curtime {curTime}")
            if oldNamesTime == 0 or oldNamesTime + 100 < curTime:
                self.channel_spam_prots[channel]["names_told"] = curTime
                self.channel_spam_prots[channel]["names"] = names
            elif oldnames != names:
                self.channel_spam_prots[channel]["names_told"] = curTime
                self.channel_spam_prots[channel]["names"] = names                
            else: # self.debug_print("spamtest names_told blocked")
                return
            
        finalReply = f'{self.get_word("on_the_channel")} @ {channel} : **{names}**'
        #self.debug_print(finalReply)

        # Update the users
        self.update_irc_users(channel, names)

        # If requested - Send queried irc names to discord with small delay / to make webhook slower than bot itself..
        discord_chan = self.irc_channel_sets[channel]["real_chan"]
        timers.add_timer("", 1.0, self.discord.send_irc_msg_to_discord, discord_chan, None, finalReply)
        #self.discord.send_irc_msg_to_discord(discord_chan, None, finalReply) # self.discord.send_discord_message(discord_chan, finalReply)

    def on_whoreply(self, connection, event):
        """ Event handler for /who -reply """

        host = event.arguments[2]
        nick = event.arguments[4]
        #realname = event.arguments[6].split()[1]
        channel = event.arguments[0]

        if channel not in self.irc_channels_lists:
            self.irc_channels_lists[channel] = {}

        self.irc_channels_lists[channel][nick] = {"host": host}
        #self.debug_print(self.irc_channels_lists)

    def on_join(self, connection, event):
        """ Event handler for IRC channel joins """

        connection_name = connection.get_nickname()
        if event.target not in self.irc_channel_sets:
            connection.part(event.target)
            return
        if connection != self.connection:
            return
        
        discord_chan = self.irc_channel_sets[event.target]["real_chan"]
        self.last_used_channel = discord_chan

        # check for ignored user event
        if event.source.nick in irc_settings["ignore_parts_joins"]:
            return # do not inform forwards
        
        # Someone joining IRC channel
        if connection_name != event.source.nick:
            if event.target not in self.irc_channels_lists:
                self.irc_channels_lists[event.target] = {}

            # Update the channel - nick -cache
            self.irc_channels_lists[event.target][event.source.nick] = {"host": event.source.host}
            
            # Update known irc users / statuses & also notify the linked discord channel of fresh people        
            self.query_irc_names_to_discord(event.target)
            self.discord.send_irc_msg_to_discord(discord_chan, None, f'**{event.source.nick} {self.get_word("joined")} {event.target}**')

        # The bot-connection itself joining
        else:
            connection.who(event.target)
            self.myprivmsg_line = f"{event.source} PRIVMSG"
            #self.debug_print(self.myprivmsg_line)

            time.sleep(2)
            self.debug_print(f"[IRC] Joined to channel {event.target}")
                
            joinmsg = f"** `!! {self.get_word('connected')} 'IRC {event.target}' - 'Discord #{discord_chan}' -{self.get_word('bridge')} == {self.get_word('msgs_on_channels_being_relayed')} !!` **"
            # On this occasion we actually want to send this message to discrd through the bot itself, instead of possible webhook
            # DO WE THOUGH ? -> Nope. -> Yep. More clear, maybe not more clean, in Discord.
            self.discord.send_discord_message(discord_chan, joinmsg)
            #self.discord.send_irc_msg_to_discord(discord_chan, None, joinmsg)
            self.send_message(event.target, joinmsg)

            # Also query the IRC topic and channel members and inform
            # to DISCORD as soon as we are connected to IRC-channel
            self.query_irc_topic_to_discord(event.target)
            self.query_irc_names_to_discord(event.target)
            # .. Actually should (?) happen automatically when joining a channel ? Also spam-protected (?)

            # Print discord channel topic on the IRC channel
            # And print the discord user statuses on IRC channel
            self.print_discord_topic_to_irc(discord_chan, event.target)        
            self.send_discord_users_to_irc(event.target)

    def on_part(self, connection, event):
        """ Event handler for irc-user parts from channels """

        if event.target not in self.irc_channel_sets:
            return
        if connection != self.connection:
            return

        # check for ignored user event
        if event.source.nick in irc_settings["ignore_parts_joins"]:
            return # do not inform forwards
        
        discord_chan = self.irc_channel_sets[event.target]["real_chan"]
        if connection.get_nickname() != event.source.nick:
            self.irc_channels_lists[event.target].pop(event.source.nick)
            
            if len(event.arguments) > 0:
                reason = f"({event.arguments[0]})"
            else:
                reason = "no reason"
            self.discord.send_irc_msg_to_discord(discord_chan, None, f'**{event.source.nick} {self.get_word("left_channel")} {event.target} ({self.get_word("reason")}: {reason})**') 
        else:
            connection.join(event.target)

    def on_quit(self, connection, event):
        """ Event handler for irc-user quits """
        if connection != self.connection:
            return
        if self.discord.is_running == 0:
            return
        if event.arguments[0]:
            reason = str(event.arguments[0])
        else:
            reason = "no reason"

        # check for ignored user event
        if event.source.nick in irc_settings["ignore_parts_joins"]:
            return # do not inform forwards

        self.send_to_matching_discord(event.source.nick, f'**{event.source.nick} {self.get_word("quit_irc")} / {self.network} ({self.get_word("reason")}: {reason})**')
        self.pop_from_channels(event.source.nick)

    def on_kick(self, connection, event):
        """ Event handler for IRC user kicks on channels """

        nick = event.source.nick
        knick = event.arguments[0]

        if event.target not in self.irc_channel_sets:
            return
        
        if connection == self.connection:            
            # Get matching discord channel
            discord_chan = self.irc_channel_sets[event.target]["real_chan"]

            # remove the nick from channel list
            self.irc_channels_lists[event.target].pop(knick)
            try:
                extras = f"({event.arguments[1]})"
            except IndexError:
                extras = ""
            # Inform Discord about the kick
            self.discord.send_irc_msg_to_discord(discord_chan, None, f'**{nick} {self.get_word("kicked_user")} {knick} {extras}**')
            if knick == connection.get_nickname():
                connection.join(event.target)             
        else:
            # I was kicked, try to rejoin the channel
            if knick == connection.get_nickname():
                connection.join(event.target)

    def on_featurelist(self, connection, event):
        """ # Event handler for IRC network features (?) 
        - Save the IRC Network name to local cache """
        if connection != self.connection:
            return
        
        featlen = len(event.arguments)

        for i in range(featlen):
            ce = event.arguments[i]
            spl = ce.split("=")
            if spl[0] == "NETWORK":
                self.network = spl[1]

    def on_nick(self, connection, event):
        """ Event handler for IRC-user nick changes """

        if connection != self.connection:
            return
        
        oldnick = event.source.nick # host = event.source.host
        newnick = event.target

        if connection.get_nickname() == event.source.nick:
            self.myprivmsg_line = f"{event.source} PRIVMSG"

        event_msg = f'**{oldnick}** *{self.get_word("new_nick_is")}* **{newnick}**'

        for each_channel in self.irc_channels_lists:
            x = self.irc_channels_lists[each_channel]
            if oldnick in x:
                prev = self.irc_channels_lists[each_channel][oldnick]
                self.irc_channels_lists[each_channel].pop(oldnick)
                self.irc_channels_lists[each_channel][newnick] = prev
                self.discord.send_irc_msg_to_discord(self.irc_channel_sets[each_channel]["real_chan"], None, event_msg) 
                
    def on_error(self, message):
        """ Event handler for irc-errors / print them to console/terminal """
        self.irc_logger.exception(message)
        self.debug_print(message)

    def on_error_event(self, connection, event):
        """ Event handler for irc-errors / print them to console/terminal """
        self.on_error(f"IRC-error {connection} - {event.source} : {event.arguments}")

    def on_privmsg(self, connection, event):
        """ Event handler for private irc-messages / pritn them to console / terminal
            - @todo (?) send to bot handler(s)? """
        self.debug_print(f"{event.source.nick} {event.arguments[0]}")

    #def on_privnotice(connection, event):
    #   self.debug_print(f"{event.source.nick} {event.arguments[0]}")

    #===========================
    # Handlers for topic replies

    def on_topic(self, connection, event):
        """ 
        # on_topic actually responds to TOPIC change
        - Not topic queries made by bot 
        """
        #self.debug_print("on_topic: ")
        irc_channel = event.target
        if connection == self.connection:
            # fix the topic format from raw argument
            fixTopicString = str(event.arguments)
            fixTopicString = fixTopicString[:-2] # strip ['
            fixTopicString = fixTopicString[2:]  #  and  '] from raw Arg
            
            # Format & fix the topic string to channel and to discord message
            fullTopicString = f'{irc_channel} - {self.get_word("topic_changed")}: **{fixTopicString}**'

            # Send to Matching discord-channel:
            self.send_irc_topic_to_discord(fullTopicString, irc_channel)
            
    # event.type 'TOPIC' -> function 'on_topic'
    # Does _not_ get called on IRCnet
    # So I have no idea of this function^^ 
    # IRCnet instead uses the below broken
    # numerical handlers through RAW events ..

    def on_rpl_notopic(self, connection, event):
        """ 331 - No topic (Called through the RAW Handler) """
        if connection == self.connection:
            self.process_and_send_topic_string(event.arguments[0])

    def on_rpl_topic(self, connection, event):
        """ 332 - Topic (Called through the RAW Handler) """
        if connection == self.connection:
            self.process_and_send_topic_string(event.arguments[0])

    def on_rpl_topicwhotime(self, connection, event):
        """ 333 - Who / Time (Called through the RAW Handler) """
        if connection == self.connection:
            self.process_and_send_topic_string(event.arguments[0])
        
    def send_discord_users_to_irc(self, irc_channel): 
        """         
        # Inform IRC-channel about discord users
        - @ todo - actually filter per discord channel (?)
        """  

        onlines = ""
        away = "" 
        offlines = "" 

        self.known_discord_users = self.discord.get_updated_known_users()
        for user in self.known_discord_users.values():
            if str(user.status) == "online":
                onlines += f"{user.user_nick}, "

            elif str(user.status) == "offline":
                offlines += f"{user.user_nick}, "

            else: # away/dnd/etc?
                away += f"{user.user_nick}, "

        # Strip the extra comma & spaces from final concatenated names
        onlines = onlines[:-2]
        offlines = offlines[:-2]
        away = away[:-2]

        # Send the known discord users & their statuses to IRC through self.connection-bot
        combinedMessage = f'[Discord] - {self.get_word("online")}: {onlines} | {self.get_word("away")} : {away} | {self.get_word("offline")}: {offlines}'
        self.send_message(irc_channel, combinedMessage)
        # @todo - maybe do not show the group & related label if its empty

    #####################################
    # IRC-message handling
    #####################################
    def on_pubmsg(self, connection, event):
        """ 
        # IRC-message handling
        - Verify message validity
        - Check for commands / responds to commands
        - Check for @mentions of known Discord users on IRC - and replace with functional Discord @mentions
        - Send message through Discord -handler class - priority with webhook if available
        -- Fallback to direct bot -message, if no webhook / errors with the webhook
        - REMOVE/replace @everyone and @here from IRC -messages to prevent pinging everyone from IRC
        - Check the message contents of URL's - if URL's found - fetch the web-page <title> and potential video duration and inform them to IRC-channel
        """

        # Update last used channels
        self.last_used_channel = event.target
        self.discord.last_used_channel = event.target

        #==================================
        # Verify that the message is on our watched channels
        if len(event.arguments[0].split()) == 0:
            return
        if event.target not in self.irc_channel_sets:
            return
        if connection != self.connection:
            return
        
        #==================================
        # Get the matching discord channel & author info
        discord_chan = self.irc_channel_sets[event.target]["real_chan"]
        sender = event.source.nick
        
        #==================================
        # Check, process and split the message
        messagenot = self.irc_to_disc_text(event.arguments[0])
        message = messagenot.split() #host = event.source.host

        if len(message) == 0:
            return
        
        # Get messages first 'word' as 'command' for processing
        cmd = message[0].lower()

        ###############################
        #  IRC bot ops commands block #
        ###############################

        # Allowed only if the sender is actually authorized as bot_owner in settings
        if sender in irc_settings["bot_owner"]:

            # Bridge Shutdown command -  Quits IRC, kills Discord bot, stops process.
            if cmd == "!sammu" or cmd == "!shutdown":
                self.bridge_shutdown(message)

            # Bot irc-nickname change
            if cmd == "!nick" and len(message) == 2:
                self.change_bot_ircnick(message[1])
            
            # Add given IRC-user to ignore join/part/quit -list
            elif cmd == "!ignorequits" and len(message) == 2:
                self.ignore_user_joinsquits(event.target, message[1])

        ###############################
        #   Public commands block     #
        ###############################

        # Help / commands
        if cmd == "!help" or cmd == "!apua" or cmd == "!apuva":
            #send_irc_and_discord(discord_chan, event.target, help["listcommands"])    
            if len(message) == 1:
                self.send_message(event.target, self.get_help("listcommands"))
            else:
                help_dict = self.get_help_dict() # settings["help_dict"]:
                if message[1] in help_dict:
                    # Clean the possible linebreaks etc. special-characters from Help -strings before sending to IRC !
                    cleanHelp = self.get_help(message[1]).replace("\n", "-")
                    self.send_message(event.target, cleanHelp) 
                else:
                    self.send_message(event.target, f'{self.get_word("invalid_command_param")}')

        # Status / Uptime (of bridge/bots)
        elif cmd == "!status" or cmd == "!tila":
            uptime = self.get_uptime()
            self.send_irc_and_discord(discord_chan, event.target, f'{self.get_word("bridge_uptime")} {uptime}')

        # Who are around in linked Discord-channel
        elif cmd == "!who" or cmd == "!ketä" or cmd == "!kuka":       
            self.send_discord_users_to_irc(event.target)
            
        # Get & print the linked Discord channel topic to IRC
        elif cmd == "!topic":
            self.print_discord_topic_to_irc(discord_chan, event.target)
            
        # Report the current BTC/USD value to both linked channels
        elif cmd == "!btc":
            self.report_btc_usd_valuation(event.target)

        # Report the current MSTR/USD value to both linked channels
        elif cmd == "!mstr":
            self.report_mstr_valuation(event.target)

        # Report the current market value for requested market symbol through yahoo finance
        elif cmd == "!stock" or cmd == "!value" or cmd == "!kurssi":
            if len(message) == 2:
                symbol_to_query = message[1]
                self.get_and_report_stock_value(event.target, symbol_to_query)

        # Change language
        elif cmd == "!speak" or cmd == "!viännä" or cmd == "!puhu":
            if len(message) == 2: # verify that there is the second word
                new_language = message[1] # take second word as the language param
                set_new_lang = ""
                avail_langs = ""

                if new_language == settings["localization"]["used_language"]:
                    self.send_irc_message(event.target, f"{self.get_word('lang_already_in_use')}")
                else:
                    for lang in settings["localization"]:
                        if str(lang) != "used_language" and str(lang) != "_c13":
                            avail_langs += f"'{lang}' "
                            if lang == new_language:
                                set_new_lang = new_language

                    if set_new_lang != "":
                        self.change_language(set_new_lang)
                    else:
                        self.send_irc_message(event.target, f'{self.get_word("lang_in_use")} {self.get_word("available_languages")} {avail_langs}')
            else:
                self.send_irc_message(event.target, f'{self.get_word("lang_in_use")} {self.get_help(cmd)}')
                    
        ###############################
        #  Regular message processing #
        ###############################

        #============================
        # Check for discord-mentions

        # !! Fix helpfully @everyones and @heres !! (remove them if someone tries to ping everyone...)
        ## (replace @everyone and @here -mentions with non-pinging varieties)
        for i in range(len(message)):
            msgi = message[i]
            msgii = msgi[:-1]
            if msgi == "@everyone" or msgii == "@everyone":
                message[i] = self.get_word("fix_everyone")
            elif msgi == "@here" or msgii == "@here":
                message[i] = self.get_word("fix_here")

        # Names from detailed and cached user dictionary
        # Discord display name-scraped dictionary
        for i in range(len(message)):
            # Get known discord users and compare each word of the message to users
            self.known_discord_users = self.discord.get_known_users()
            msgi = message[i]
            
            # Only look for matches if the word starts with explicit @ for mentioning
            if msgi.startswith("@"):
                msgi = msgi[1:]   # remove leading @
                msgii = msgi[:-1] # remove final char to try to match with nick, or nick: etc.
                ml = [msgi, msgii]
                check_dict = [msgi in self.known_discord_users, msgii in self.known_discord_users]
                if any(check_dict):
                    knownUser = self.known_discord_users[ml[check_dict.index(True)]]
                    message[i] = f"<@{str(knownUser.user_id)}>"

        #===============================================
        # Combine final message to Discord for sending
        finalmsg = ' '.join(message)

        # Cursive the message to Discord - if it was '/me' -action in IRC
        if event.type == "action":
            finalmsg = f"*{finalmsg}*"

        self.debug_print(f"[IRC] {event.target} > [Discord] #{discord_chan} - {sender} : {finalmsg}")

        #===============================================
        # SEND MESSAGE TO DISCORD (via webhook -wrapper, which will instead use direct bot -message, if no webhook available/problems with it)
        self.discord.send_irc_msg_to_discord(discord_chan, sender, finalmsg)

        #===============================================
        # Check if the message cointains URL's - and get the titles and report to IRC
        timers.add_timer("", 1, self.try_to_process_message_urls, finalmsg, event.target)

    def slow_join_to_set_channels(self):
        """ IRC-bot will join the IRC-channels in currently set channel_sets - given/fulfilled by the Discord
        - If IRC-connection is faster than Discord, this needs to be called when receiving the channels from Discord """

        # "Slow"-join to channels, with increasing delays
        channel_join_delay = 0.1
        for irc_channel in self.irc_channel_sets:
            self.debug_print(f"[IRC] Joining to {irc_channel} in {channel_join_delay} seconds")
            timers.add_timer(f"join-{irc_channel}", channel_join_delay, self.connection.join, irc_channel)
            channel_join_delay += 0.4

        self.discord.set_status() # start looping the statuses

    ########################################################
    # Handling of successfull IRC-server connection
    ########################################################
    def on_connect(self, connection, event):
        """        
        # Handling of successfull IRC-server connection
        - Join channels 
        - Get members & cache datas & etcc...
        """

        # Successfully connected
        self.debug_print(f"[IRC] Successful connection to {event.source}")
        # self.debug_print(str(self.irc_channel_sets))
        
        # Remove old reconnection timer if there for some reason is/was any
        if "self.connection-reconn" in timers.timers:
            timers.cancel_timer("self.connection-reconn")

        # "Slow"-join to channels, with increasing delays
        self.slow_join_to_set_channels()

        # Reset disconnect retries
        self.disconnectretries = 0
        # Start the Discord Status rotation -loop
        self.discord.set_status()

        # Start bot irc-nick keeping/guarding:
        timers.add_timer("keep-botnick", 10, self.keep_set_nick_loop)

        # Done with listening the connection - remove all raw message -handler
        ## connection.remove_global_handler("all_raw_messages", on_all_raw)
        # !! Except we actually need it for listening the wanted numeral events !!
        # becouse of the  numeral handlers for some reason do not seem to work ?!

        self.debug_print("[IRC] IRC CONNECTED & READY")

    #########################################################
    # Event handler for disconnecting / irc-connection lost #
    #########################################################
    def on_disconnect(self, connection, event):
        """            
        # Event handler for IRC-connection lost / disconnection
        - Try to reconnect back to the server (default max 10 times)
        """
        connection_name = connection.get_nickname()
        self.discord.set_status("Lost IRC-connection.")

        # retry connection self.maxConnectRetries times
        if connection == self.connection:  

            # Report the lost connection to Discord, for one time.
            if self.irc_connection_successful == 1:
                self.discord.send_to_all_discord_channels(f'[IRC] `Connection to server lost ... trying to re-connect ... Unable to relay the messages at this moment.`')

            self.irc_connection_successful = 0
            if connection.sent_quit == 1:
                connection.sent_quit = 0
                return
            
            # Verify that we are not trying to reconnect more than specified amount of times
            self.disconnectretries += 1
            if self.disconnectretries >= self.maxConnectRetries:
                # And print errors and message to discord if unsuccessfull with reconnecting to IRC
                self.debug_print(f"[IRC] Failed to connect {self.maxConnectRetries} times, aborting.")
                self.discord.send_to_all_discord_channels(f'`{self.get_word("retried")} {self.maxConnectRetries} {self.get_word("times_no_success")}: {event.source} {event.arguments[0]}`')
                time.sleep(1)
                # And then shut down the bot processes
                self.discord.shutdown()
                self.stop_loop()
                return
            
            # Remove old reconnection timer if there for some reason is/was any
            if "self.connection-reconn" in timers.timers:
                timers.cancel_timer("self.connection-reconn")

            # Add reconnecting timer to reconnect in 5 seconds
            timers.add_timer("self.connection_reconn", 5, connection.reconnect) # 10
            self.debug_print("[IRC] Failed to connect... reconnecting...")

        else:
            self.debug_print("[IRC] What connection did we exactly lose...?")
