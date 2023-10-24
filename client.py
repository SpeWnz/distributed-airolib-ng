import re
import requests
import argparse
import sys
import threading
import os
import subprocess
import time
import termios
import tty

import ZHOR_Modules.nicePrints as np
import ZHOR_Modules.randUtils as ru
from common import _VERSION, WORDLIST_CHUNK_SIZE


parser = argparse.ArgumentParser(description="Distributed Airolib-ng - Client - Version " + _VERSION)
REQUIRED_ARGUMENTS = parser.add_argument_group("Required arguments")
OPTIONAL_ARGUMENTS = parser.add_argument_group("Optional arguments")

# Argomenti necessari
REQUIRED_ARGUMENTS.add_argument('-i',metavar='"IP"',type=str,required=True,help='Server IP')
REQUIRED_ARGUMENTS.add_argument('-p',metavar='"PORT"',type=str,required=True,help='Server port')
REQUIRED_ARGUMENTS.add_argument('-t',metavar='"PORT"',type=int,required=True,help='Threads (parallel airolib-ng instances the client can execute)')

# Argomenti opzionali
OPTIONAL_ARGUMENTS.add_argument('--limit',metavar='"LIMIT CHUNKS"',type=str,required=False,help='Max number of chunks to batch, after which the client will quit. Cannot be less than the value specified in -t')
OPTIONAL_ARGUMENTS.add_argument('--debug',action="store_true",help="Debug mode")

args = parser.parse_args()

np.DEBUG = ("--debug" in sys.argv)

# =========================================================================================================================================================
# global vars

SERVER_ADDRESS = 'http://{}:{}/'.format(args.i,args.p)
CUSTOM_EXECUTABLE_PATH = "/usr/bin/airolib-ng"          # default executable location - change this if necessary

STDOUT_LOCK = threading.Lock()                          # lock used specifically for managing the stdout (printing messages and such)

PERFORMANCE_DICTIONARY = {}                             # used to keep track of the performance
PERFORMANCE_STATUS_UPDATE_INTERVAL = 3                  # frequency (in seconds) at which the current performance is calculated and sent over to the server

MAX_CHUNKS_TO_BATCH = 0                                 # how many chunks should the client batch at most
MAX_CHUNKS_SET = False                                  # global flag used to check wether the user specified a limit or not
MAX_CHUNKS_COUNTER = 0                                  # global variable used to count how many chunks have been batched (if a limit is set)
MAX_CHUNKS_COUNTER_LOCK = threading.Lock()              # lock used specifically for managing the max amount of chunks to batch

ALL_THREADS_JOINED = False                              # global flag used to keep the keypress detector alive or not
CLIENT_ID = ru.randomString(30,specialChars=False)      # global variable used to uniquely identify a client instance

HEADERS = {
    'clientID':CLIENT_ID
}

# =========================================================================================================================================================

# tests if the server is reachable or not
def heartbeat():
    np.infoPrint("Testing connectivity...")
    try:
        r = requests.get(url=SERVER_ADDRESS + "/heartbeat",headers=HEADERS)
        np.infoPrint("The server is reachable.")
        return True
    except Exception as e:
        np.errorPrint("The server is not reachable.")
        np.debugPrint("Server is not reachable due to exception: " + str(e))
        return False

# verifies the thread count is valid.
# the count must not be > core count
# the count must not be < 1
def checkThreadCount(threadCount: int):
    
    np.debugPrint("Determining max CPU cores...")
    maxCpuCores = os.cpu_count()
    np.debugPrint("Max CPU cores: " + str(maxCpuCores))

    # no negative or 0
    if (threadCount < 1):
        np.errorPrint("Can't have a negative amount of threads. Defaulting to 1")
        return 1

    # in the rare occasion that it returns None, return "threadCount", hoping that the user knows what he/she is doing
    if maxCpuCores == None:
        np.errorPrint("It was not possible to determine the max cores count. The script will use the user-defined count: " + str(threadCount))
        return threadCount

    
    
    # no more than maxCpuCores
    if (threadCount > maxCpuCores):
        np.errorPrint("Cannot select an amount of threads larger than the CPU cores count. Defaulting to " + str(maxCpuCores))
        return maxCpuCores

    
    return threadCount

# verifies the chunks limit (if set) is valid
# the count must not be < 1
# the count must be >= threadCount
def checkChunkLimitCount(threadCount: int):
    global MAX_CHUNKS_TO_BATCH

    # can't be less than threadCount
    if(MAX_CHUNKS_TO_BATCH < threadCount):
        np.infoPrint("Cannot limit chunk count to a value that's less than the specified thread count. Defaulting to " + str(threadCount))
        MAX_CHUNKS_TO_BATCH = threadCount
        return

    # can't be less than 1
    if (MAX_CHUNKS_TO_BATCH < 1):
        np.infoPrint("Cannot limit chunk count to a value that's less than 1. Defaulting to " + str(threadCount))
        MAX_CHUNKS_TO_BATCH = threadCount
        return




# auto locking information message
def thread_infoMessage(threadID: int,message: str):
    msg = "[Thread #{}] {}".format(
        str(threadID),
        message
        )

    STDOUT_LOCK.acquire()
    np.infoPrint(msg)
    STDOUT_LOCK.release()

# auto locking debug message
def thread_debugMessage(threadID: int,message: str):
    msg = "[Thread #{}] {}".format(str(threadID),message)

    STDOUT_LOCK.acquire()
    np.debugPrint(msg)
    STDOUT_LOCK.release()

# auto locking error message
def thread_errorMessage(threadID: int,message: str):
    msg = "[Thread #{}] {}".format(
        str(threadID),
        message
        )

    STDOUT_LOCK.acquire()
    np.errorPrint(msg)
    STDOUT_LOCK.release()

# requests and downloads (if possible) a chunk to batch
def downloadChunk(threadID: int):
    # get a todo chunk from the server
    thread_infoMessage(threadID, "Obtaining todo chunk from server...")

    thread_debugMessage(threadID, "requesting chunk ...")
    r = requests.get(url=SERVER_ADDRESS + "/getTodoChunk",headers=HEADERS)

    # if there are no chunks, return None
    if (r.status_code == 404):
        thread_debugMessage(threadID, "Server returned 404. There are no more chunks to batch")
        return None

    thread_debugMessage(threadID, "chunk downloaded")

    thread_debugMessage(threadID, "writing chunk on disk...")
    fileName = r.headers['Content-Disposition'].split('=')[-1]

    with open(fileName,'wb') as f:
        f.write(r.content)

    thread_debugMessage(threadID, "wrote chunk " + fileName + " on disk")

    return fileName

# parses information from the process output string of airolib-ng
# Computed 25000 PMK in 48 seconds (520 PMK/s, 225000 in buffer)
def parseProcessOutputString(processOutputString: str):
     
    # Regular expression pattern to extract values from parentheses
    pattern = r'\((.*?)\)'

    # Use re.findall() to find all matches of the pattern in the input string
    matches = re.findall(pattern, processOutputString)
    return matches

def batchChunk(threadID: int,chunk: str):
    global PERFORMANCE_DICTIONARY

    # Command to be executed
    #command = "{} {} --batch".format(CUSTOM_EXECUTABLE_PATH,chunk)

    # debugging / testing - COMMENT OUT THE FOLLOWING 2 LINES WHEN YOU'RE DONE
    command = "echo [FAKE] Computed 25000 PMK in 48 seconds (520 PMK/s, 225000 in buffer)".format(CUSTOM_EXECUTABLE_PATH,chunk)
    time.sleep(ru.extractRandomNumber(1, 10))

    thread_infoMessage(threadID, "Batch started for chunk " + chunk)

    # execute the command and capture the output in real time
    process = subprocess.Popen(command.split(' '), shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Read and print the output line by line in real-time
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            
            # info-print the interesting stuff, debug-print the rest
            if('PMK/s' in output):
                thread_infoMessage(threadID, output.strip())

                stats = parseProcessOutputString(output.strip())

                pmk_per_second = stats[0].split(' ')[0]
                PERFORMANCE_DICTIONARY[threadID] = pmk_per_second


            else:
                thread_debugMessage(threadID, output.strip())
            

    # Wait for the process to complete and get the return code
    return_code = process.poll()

    # Print the return code
    #print("Return Code:", return_code)

    thread_infoMessage(threadID, "Batch finished for chunk " + chunk)


def uploadChunk(threadID: int, chunk: str):
    
    thread_infoMessage(threadID, "Submitting chunk to server ...")

    # Open the file in binary mode and send it to the server
    thread_debugMessage(threadID, "Opening file ...")
    
    try:

        with open(chunk, 'rb') as file:
            files = {'file': (chunk, file)}

            thread_debugMessage(threadID, "Uploading file with post request ...")
            r = requests.post(url=SERVER_ADDRESS + "/submitChunk", files=files,headers=HEADERS)
            thread_debugMessage(threadID, "Upload completed")

        thread_debugMessage(threadID, "Server response: " + r.text)

    except Exception as e:
        thread_errorMessage(threadID, "Error while trying to submit the file: " + str(e))

# main function used by the threads
def threadFunction(threadID: int):
    global MAX_CHUNKS_COUNTER
    global MAX_CHUNKS_COUNTER_LOCK
    global MAX_CHUNKS_TO_BATCH
    global MAX_CHUNKS_SET
    
    while True:


        chunk = downloadChunk(threadID)

        if (chunk != None and chunk != 'null'):
            batchChunk(threadID, chunk)
            uploadChunk(threadID, chunk)

            # cleanup
            os.system("rm " + chunk)


            # if a limit has been set, check if you can continue
            if(MAX_CHUNKS_SET == True):
                MAX_CHUNKS_COUNTER_LOCK.acquire()
                MAX_CHUNKS_COUNTER += 1
                MAX_CHUNKS_COUNTER_LOCK.release()

                thread_debugMessage(threadID, "MAX_CHUNKS_COUNTER increased by 1: " + str(MAX_CHUNKS_COUNTER))

                if(MAX_CHUNKS_COUNTER >= MAX_CHUNKS_TO_BATCH):
                    thread_infoMessage(threadID, "Chunk limit reached. Thread job done.")
                    return

        else:
            thread_infoMessage(threadID, "No chunks left to batch. Thread job done.")
            return

    
# prints the current status on screen
# sends the current total performance to the server
def performanceStatus():
    global ALL_THREADS_JOINED
    global PERFORMANCE_DICTIONARY
    global PERFORMANCE_STATUS_UPDATE_INTERVAL
    global CLIENT_ID
    global SERVER_ADDRESS

    while ALL_THREADS_JOINED == False:

        totalPerf = 0
        for key in PERFORMANCE_DICTIONARY:
            totalPerf += int(PERFORMANCE_DICTIONARY[key])

        msg = "[STATUS] [Total performance: {} PMK/s]".format(
            totalPerf
        )

        # print on screen
        STDOUT_LOCK.acquire()
        #print(PERFORMANCE_DICTIONARY)
        np.infoPrint(msg)
        STDOUT_LOCK.release()

        # send info to server
        jsonData = {
            'clientID':CLIENT_ID,
            'performance':totalPerf
        }

        r = requests.post(url=SERVER_ADDRESS + "/sendPerformanceInfo",json=jsonData,headers=HEADERS)
        
        if np.DEBUG:
            STDOUT_LOCK.acquire()
            np.debugPrint(r.text)
            STDOUT_LOCK.release()

        time.sleep(PERFORMANCE_STATUS_UPDATE_INTERVAL)

# communicate the end of work to the server
def jobDone():
    
    jsonData = {
        'clientID':CLIENT_ID
    }

    r = requests.post(url=SERVER_ADDRESS + "/clientJobDone",json=jsonData,headers=HEADERS)
    np.debugPrint(r.text)


if __name__ == '__main__':

    if not heartbeat():
        exit()

    threadList = []

    
    threadCount = checkThreadCount(args.t)
    
    
    if("--limit") in sys.argv:
        MAX_CHUNKS_TO_BATCH = int(args.limit)
        MAX_CHUNKS_SET = True
        checkChunkLimitCount(threadCount)

    # initialize threads
    for i in range(threadCount):
        t = threading.Thread(target=threadFunction,args=(i+1,))
        threadList.append(t)

    # start threads
    for t in threadList:
        t.start()

    # start performance status thread
    threadPerformanceStatus = threading.Thread(target=performanceStatus)
    threadPerformanceStatus.start()


    # wait for threads to finish
    for t in threadList:
        t.join()

    ALL_THREADS_JOINED = True
    threadPerformanceStatus.join()


    jobDone()
    np.infoPrint("Client job done. ")