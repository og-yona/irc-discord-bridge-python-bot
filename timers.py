import time

is_running = 0
timers = {}
unnamed_index = 0

def set_thread_lock(lock):
    """ Sets the global thread_lock -variable from given param """
    global thread_lock
    thread_lock = lock

def run():
    """ 
    # Run Timers
    - Timers should run / loop in separate thread loop
    - Advance the timers 
    - Process the finished timers' target functions & args
    """
    global is_running
    is_running = 1
    global thread_lock

    with thread_lock:
        print(f"[TIMERS] : Starting timer loop")

    while is_running:
        try:
            check_timers()
            time.sleep(0.1)
        except Exception as e:
            with thread_lock:
                print(f"Timer caught an error: {e}")

def shutdown_timers():
    """ 
    # Shutdown Timers
    - Stop running the timer loop 
    """
    global is_running
    is_running = 0

def check_timers():
    """ 
    # Check Timers
    - Advance the timers 
    - Run their function with args, if Finished 
    """
    global timers
    for i in timers.copy():
        timer = timers[i]
        timertime = timer["time"]
        currtime = time.time()

        if currtime >= timertime:
            target = timer["target"]
            arguments = timer["arguments"]
            timers.pop(i)

            if arguments != None:
                target(*arguments)
            else:
                target()

def add_timer(name, delay, target, *arguments):
    """ 
    # Add Timer
    - @param name for the timer
    - @param delay time for timer
    - @param target function to run once finished
    - @param args / params to run the target function with
    """
    global timers
    
    currtime = time.time()
    if name == "":
        global unnamed_index
        name = f"ID#{str(unnamed_index)}"
        unnamed_index += 1
        #name = str(currtime)

    if name in timers:
        with thread_lock:
            print(f"[TIMERS] a timer with this name already exists")
        raise Exception(f"[TIMERS] a timer with this name already exists")
    
    if type(delay) != int and type(delay) != float:
        with thread_lock:
            print(f"[TIMERS] delay argument is expected to be int or float")
        raise TypeError(f"[TIMERS] delay argument is expected to be int or float")
    
    timetodo = currtime + float(delay)
    timers[name] = {"time": timetodo, "target": target, "arguments": arguments}

def cancel_timer(name):
    """ 
    # Cancel Timer
    - Remove the timer object
    - so it does not run its target function & args
    """
    global timers
    if name in timers:
        timers.pop(name)
    else:
        with thread_lock:
            print(f"[TIMERS] No timer with name {name} found.")
        raise Exception(f"[TIMERS] No timer with name {name} found.")
