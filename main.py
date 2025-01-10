from ircc import IRC
from discordc import Discord
import timers

import json
import threading

# Get the settings for irc/discord bridge bots
f = open("settings.json", encoding="utf-8")
settings = json.loads(f.read())
f.close()

# Init with settings 
irc = IRC(settings)
discord = Discord(settings)
# & share "pointers" between IRC & Discord
irc.set_discord(discord)
discord.set_irc(irc)

# Shared mutex/thread lock for everyone who are error printing on the console log (?)
thread_lock = threading.Lock()
irc.set_thread_lock(thread_lock)
discord.set_thread_lock(thread_lock)
timers.set_thread_lock(thread_lock)

# Thread 1 : IRC
t1 = threading.Thread(target=irc.run)
t1.daemon = True # Thread dies when main thread (only non-daemon thread) exits.
t1.start()

# Thread 2 : Timers
t2 = threading.Thread(target=timers.run)
t2.daemon = True # Thread dies when main thread (only non-daemon thread) exits.
t2.start()

# Main thread : Discord
discord.run()
irc.stop_loop()
timers.shutdown_timers()
