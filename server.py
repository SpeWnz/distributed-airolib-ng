from flask import Flask, jsonify, send_file, request, make_response,render_template
import requests
import sys
import os
import json
import threading
import time
import re
from datetime import timedelta
import termios
import tty

import ZHOR_Modules.nicePrints as np
import ZHOR_Modules.terminalUtils as tu
import ZHOR_Modules.csvUtils as csvUtils
import ZHOR_Modules.logUtils as logUtils
from common import _VERSION, WORDLIST_CHUNK_SIZE



# =====================================================================================================
# Global vars 
PORT = None
CHUNKS_DIRECTORY = None


INVENTORY_FILE_NAME = 'INVENTORY.json'
LOG_PATH = "server-log.txt"

LOCK = threading.Lock()
CHUNK_LOCK = threading.Lock()                   # lock used specifically for chunks operations that must not be overlapped (for example, a client requesting a todo chunk)
STDOUT_LOCK = threading.Lock()                  # lock used specifically for managing the stdout (printing messages and such)
LOG_LOCK = threading.Lock()                     # lock used specifically for the log
CLIENT_CHUNK_REQUEST_LOCK = threading.Lock()    # lock used specifically for managing clients requesting chunks

CHUNKS_INVENTORY_DICT = {}

STATUS_DICTIONARY = {}
STATUS_DICTIONARY_LOCK = threading.Lock()       # lock used specifically for reading and writing to the status dictionary

np.DEBUG = True

# =====================================================================================================
# airolib-ng server

# log function dedicated to clients activity
def log_clientActivity(clientID: str, clientIP: str, message: str):
    
    if clientID == None:
        clientID == "N/A"
    
    line = "[{}] [{}] {}".format(clientID,clientIP,message)
    log_generic(line)

# base log function - AUTO LOCKING
def log_generic(message: str):
    
    line = "[{}] {}".format(
        csvUtils.getTimeStamp(),
        message
    )
    
    LOG_LOCK.acquire()

    with open(LOG_PATH,'a') as f:
        f.write(line + "\n")

    LOG_LOCK.release()

# make sure to remove any "null" keys (which for some reason i can't explain they get created)
def removeNullChunks():
    global CHUNKS_INVENTORY_DICT
    log_generic("removeNullChunks() has been invoked. Current status of the dictionary: " + str(CHUNKS_INVENTORY_DICT))


    CHUNK_LOCK.acquire()
    
    if "null" in CHUNKS_INVENTORY_DICT['chunks']:
        log_generic("found 'null' chunk in dict, deleting")
        del CHUNKS_INVENTORY_DICT['chunks']['null']

    if "None" in CHUNKS_INVENTORY_DICT['chunks']:
        log_generic("found 'null' chunk in dict, deleting")
        del CHUNKS_INVENTORY_DICT['chunks']['None']

    if None in CHUNKS_INVENTORY_DICT['chunks']:
        log_generic("found 'null' chunk in dict, deleting")
        del CHUNKS_INVENTORY_DICT['chunks'][None]
    
    CHUNK_LOCK.release()

# sets a state to a chunk:
# Possible states: TODO, WIP, DONE
def setChunkState(chunkName: str, state: str):
    global CHUNKS_INVENTORY_DICT

    removeNullChunks()

    CHUNK_LOCK.acquire()
    CHUNKS_INVENTORY_DICT['chunks'][chunkName] = state
    CHUNK_LOCK.release()

# returns a chunk name that needs to be batched
# returns "None" if there are no chunks to batch
def getTODOChunk():
    global CHUNKS_INVENTORY_DICT

    CHUNK_LOCK.acquire()
    for item in CHUNKS_INVENTORY_DICT['chunks']:
        #thread_debugMessage(999, item)
        if CHUNKS_INVENTORY_DICT['chunks'][item] == 'TODO':

            CHUNK_LOCK.release()
            return item

    #thread_debugMessage(999, "No TODO, returning None")
    CHUNK_LOCK.release()
    return None

# loads json inventory file into the global variable
def loadInventoryFile(folderPath: str):
    global CHUNKS_INVENTORY_DICT

    path = "{}/{}".format(
        folderPath,
        INVENTORY_FILE_NAME
    )

    CHUNKS_INVENTORY_DICT = json.load(open(path,'r'))
    

# saves onto the inventory file
def saveInventoryFile(folderPath: str):
    path = "{}/{}".format(
        folderPath,
        INVENTORY_FILE_NAME
    )

    CHUNK_LOCK.acquire()
    with open(path,'w') as jsonFile:
        json.dump(CHUNKS_INVENTORY_DICT,jsonFile)
    CHUNK_LOCK.release()


# it is assumed there are no WIP chunks. Therefore, they are treated as TODO, which delivers the same
# results
# NO LOCKS, because it gets executed before any thread
def resetWIPchunks():
    global CHUNKS_INVENTORY_DICT

    removeNullChunks()

    for key in CHUNKS_INVENTORY_DICT['chunks']:
        if CHUNKS_INVENTORY_DICT['chunks'][key] == 'WIP':
            setChunkState(key, 'TODO')

    log_generic("WIP chunks have been reset")

# sets all chunks as TODO. For debug purposes
def resetALLchunks():
    global CHUNKS_INVENTORY_DICT

    removeNullChunks()

    for key in CHUNKS_INVENTORY_DICT['chunks']:
            setChunkState(key, 'TODO')

    log_generic("All chunks have been reset")





# =====================================================================================================
# FLASK SERVER
app = Flask(__name__)


# example root url
@app.route('/')
def index():
    log_clientActivity(None, request.remote_addr, "The client has requested the path /")

    return render_template('index.html')

# status
@app.route('/status')
def status():
    removeNullChunks()

    log_clientActivity(None, request.remote_addr,  "The client has requested the path /status")

    return render_template('status.html')

# used by the server ui to get performance stats
@app.route('/performanceStats', methods=['GET'])
def performanceStats():
    removeNullChunks()
    log_clientActivity(None, request.remote_addr, "The client has requested the path /performanceStats")

    global STATUS_DICTIONARY
    totalPerf = 0

    # step 1 - are there actually clients connected? (prevent division by zero)
    if len(STATUS_DICTIONARY) >= 1:
        
        # step 1.1 if yes, what is the total performance?
        for key in STATUS_DICTIONARY:
            totalPerf += int(STATUS_DICTIONARY[key]['performance'])
    


    # step 2 - check chunks status. How many have and haven't been batched?
    countDone = lambda d: len(list(filter(lambda key: d[key] == 'DONE',d)))
    done = countDone(CHUNKS_INVENTORY_DICT['chunks'])
    todo = len(CHUNKS_INVENTORY_DICT['chunks']) - done
    
    # step 3 - how many passwords remain? (approximately)
    remainingPasswords = todo * WORDLIST_CHUNK_SIZE * CHUNKS_INVENTORY_DICT['ssidCount']

    # step 4 - calculate eta (considering cases where there are no currently connected clients too)
    if(totalPerf != 0):
        totalSeconds = int(remainingPasswords / totalPerf)
        eta = str(timedelta(seconds=totalSeconds))
    else:
        totalSeconds = "N/A"
        eta = "N/A"

    # step 5 - build returning json Object
    # add specific client data
    jsonObject = {
        'clientData':STATUS_DICTIONARY,
        'eta':eta,
        'totalPerformance':totalPerf,
        'batchedChunks':done,
        'todoChunks':todo,
        'totalChunks':len(CHUNKS_INVENTORY_DICT['chunks'])
    }

    return jsonify(jsonObject)

# test api method used by the client to verify wether the server is reachable or not
@app.route('/heartbeat', methods=['GET'])
def heartbeat():
    log_clientActivity(request.headers['clientID'], request.remote_addr,  "The client has requested the path /heartbeat")

    data = {
        'response': 'The server is reachable!'
    }
    
    return jsonify(data)

# Sends a "todo" chunk to a client that requests it.
# the lock is there to prevent other clients from requesting the same chunk
@app.route('/getTodoChunk', methods=['GET'])
def getTodoChunk():
        
    # makes sure no two clients get the same chunk
    CLIENT_CHUNK_REQUEST_LOCK.acquire()
    todoChunk = getTODOChunk()
    setChunkState(todoChunk, 'WIP')
    CLIENT_CHUNK_REQUEST_LOCK.release()

    if todoChunk == None:
        log_clientActivity(request.headers['clientID'], request.remote_addr,  "The client has requested a chunk, but there are none left.")
        response = jsonify({'error': 'No TODO chunks left to batch'})
        return make_response(response, 404)

    file_path = CHUNKS_DIRECTORY + '/' + todoChunk
    
    log_clientActivity(request.headers['clientID'], request.remote_addr,  "The client has requested a chunk. Sent the following: " + todoChunk)
    return send_file(file_path, as_attachment=True)


# method used by clients to submit batched chunks.
# when a chunk is submitted, its filename will be used by the server to mark it as "done"
@app.route('/submitChunk', methods=['POST'])
def submitChunk():
    
    #global CHUNKS_DIRECTORY

    # Check if the POST request has a file part
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'})

    file = request.files['file']

    # If the user does not select a file, the browser submits an empty file without a filename
    if file.filename == '':
        return jsonify({'error': 'No selected file'})

    # Specify the folder where you want to save the uploaded files
    upload_folder = CHUNKS_DIRECTORY + '/uploads'
    os.makedirs(upload_folder, exist_ok=True)

    # Save the file to the specified folder
    file_path = os.path.join(upload_folder, file.filename)
    file.save(file_path)

    # set the chunk as done and save the progress
    setChunkState(file.filename, "DONE")
    removeNullChunks()
    saveInventoryFile(CHUNKS_DIRECTORY)

    log_clientActivity(request.headers['clientID'], request.remote_addr, "The client has submitted a chunk: " + file.filename)
    return jsonify({'message': 'File uploaded successfully', 'file_path': file_path})


# method used by clients to submit their performance
@app.route('/sendPerformanceInfo', methods=['POST'])
def sendPerformanceInfo():
    log_clientActivity(request.headers['clientID'], request.remote_addr, "The client has submitted its performance info")
    global STATUS_DICTIONARY

    # Get the JSON data from the POST request
    data = request.get_json()

    try:
        clientIP = request.remote_addr
        clientID = data['clientID']
        perf = int(data['performance'])

        STATUS_DICTIONARY_LOCK.acquire()

        STATUS_DICTIONARY[clientID] = {
            'ip':clientIP,
            'performance':perf
            }
        
        STATUS_DICTIONARY_LOCK.release()

        return jsonify({'status': 'Message received successfully'})
    except:
        return jsonify({'error': 'Invalid JSON data'}), 400


# method used by clients to comunicate they're done. This lets the server delete their id from the
# global status dictionary
# TODO
@app.route('/clientJobDone', methods=['POST'])
def clientJobDone():

    removeNullChunks()

    global STATUS_DICTIONARY
    global CHUNKS_DIRECTORY

    # Get the JSON data from the POST request
    data = request.get_json()

    # is it a valid json object? does it contain clientID?
    if 'clientID' in data:
        
        try:

            # delete that specific client id
            del STATUS_DICTIONARY[data['clientID']]
            log_clientActivity(request.headers['clientID'], request.remote_addr, "The client has completed its work.")
            
            #save the progress
            removeNullChunks()
            saveInventoryFile(CHUNKS_DIRECTORY)

            return jsonify({'status': 'Message received successfully.'})

        except Exception as e:
            log_clientActivity(request.headers['clientID'], request.remote_addr, "The client submitted an invalid clientID: " + str(data))
            return jsonify({'error': 'Could not delete the specified key. Exception: ' + str(e)}), 404


    
    # If 'message' key is not in the JSON data, return an error response
    else:        

        log_clientActivity(request.headers['clientID'], request.remote_addr, "The client submitted an invalid json object: " + data)
        return jsonify({'error': 'Invalid JSON data'}), 400

# =====================================================================================================

if __name__ == '__main__':

    np.infoPrint("Distributed Airolib-ng - Server - Version " + _VERSION)

    if len(sys.argv) != 3:
        np.errorPrint("Usage: python3 server.py <port> <chunks directory>")
        exit()

    PORT = int(sys.argv[1])
    CHUNKS_DIRECTORY = str(sys.argv[2])

    try:
        loadInventoryFile(CHUNKS_DIRECTORY)
    except:
        np.errorPrint("Couldn't load the inventory file. Make sure you specified a folder containing properly generated chunks.")
        exit()
    
    
    resetWIPchunks()
    #resetALLchunks()

    
    app.run(host="0.0.0.0",debug=True,port=PORT)