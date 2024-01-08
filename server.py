from flask import Flask, jsonify, send_file, request, make_response,render_template
import requests
import sys
import os
import json
import threading
import time
import re
from datetime import timedelta, datetime
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

CLIENTS_LOD = []                                # lod structure used to keep track of connected clients and their data

np.DEBUG = True

#======================================================================================================
# class used to manage the connected clients and their data
class _ClientManager():

    # example of how a lod should look like
    _sample_lod = [
        {
            'clientID':'abc123',
            'ip':'11.22.33.44',
            'chunks':['DB-1.db','DB-2.db'],
            'performance':999,
            'lastSeen':'13-10-21 15:30:45'
        },
        {
            'clientID':'def456',
            'ip':'10.20.30.40',
            'chunks':['DB-7.db','DB-20.db'],
            'performance':999,
            'lastSeen':'13-10-21 16:30:45'
        }
    ]

    INACTIVE_CLIENT_SECONDS = 60            # seconds after which a client is declared inactive
    INACTIVE_CLIENT_CHECK_FREQUENCY = 20    # every X seconds, check for inactive clients

    CLIENTS_LOD = []                        # lod structure for clients and their data
    CLIENTS_LOD_LOCK = threading.Lock()     # lock used specifically for the client lod

    # init
    def __init__(self):
        pass

    
    # returns the amount of total connected clients
    def getTotalConnectedClients(self):

        self.CLIENTS_LOD_LOCK.acquire()
        l = len(self.CLIENTS_LOD)
        self.CLIENTS_LOD_LOCK.release()

        return l

    # returns a a value corresponding to the total performance of all clients combined
    def getTotalPerformance(self):
        totalPerf = 0

        self.CLIENTS_LOD_LOCK.acquire()
        for c in self.CLIENTS_LOD:
            totalPerf += int(c['performance'])

        self.CLIENTS_LOD_LOCK.release()

        return totalPerf

    # returns true if a client with that clientID exists in the LOD
    # returns false otherwise
    def clientExists(self,clientID: str):
        self.CLIENTS_LOD_LOCK.acquire()
        
        for c in self.CLIENTS_LOD:
            if c['clientID'] == clientID:

                # exists
                self.CLIENTS_LOD_LOCK.release()
                return True

        
        # does not exist
        self.CLIENTS_LOD_LOCK.release()
        return False

    # adds a client to the client lod
    def addClient(self,clientID: str, clientIP: str):
        if self.clientExists(clientID):
            log_clientActivity(clientID,clientIP,"Tried to add a client that already exists.")
            return

        newClient = {
            'clientID':clientID,
            'ip':clientIP,
            'chunks':[],
            'performance':0,
            'lastSeen':str(getCurrentTimestamp())
        }

        self.CLIENTS_LOD_LOCK.acquire()
        self.CLIENTS_LOD.append(newClient)
        self.CLIENTS_LOD_LOCK.release()

        log_clientActivity(clientID,clientIP,"New client connected and has been added to the lod.")


    # assigns a performance value to a client by clientID
    def setClientPerformance(self,clientID: str,performance: int):
        self.CLIENTS_LOD_LOCK.acquire()

        for c in self.CLIENTS_LOD:
            if c['clientID'] == clientID:
                c['performance'] = performance
                break


        self.CLIENTS_LOD_LOCK.release()

    # given a clientID, deletes the client from the client lod
    def deleteClient(self, clientID: str):
        log_clientActivity(clientID,"N/A","The client has been deleted from the lod.")

        self.CLIENTS_LOD_LOCK.acquire()
        self.CLIENTS_LOD = [d for d in self.CLIENTS_LOD if d.get('clientID') != clientID]
        self.CLIENTS_LOD_LOCK.release()

    # given a clientID, all its chunks will be removed and put back 
    # into the chunks dictionary as TODO chunks
    def revokeAllChunks(self,clientID: str):
        log_clientActivity(clientID,"N/A","Chunks have been revoked from the client.")
        
        self.CLIENTS_LOD_LOCK.acquire()

        for c in self.CLIENTS_LOD:
            if c['clientID'] == clientID:
                
                setChunkState(c['chunks'],'TODO')
                break

        self.CLIENTS_LOD_LOCK.release()


    # given a clientID, a specific chunk will be removed from its list
    # (used when a cliend completed its job on that chunk)
    def removeChunk(self,clientID: str, chunk: str):
        log_clientActivity(clientID,"N/A","Chunk {} has been removed from the client list.".format(chunk))
        
        self.CLIENTS_LOD_LOCK.acquire()

        for c in self.CLIENTS_LOD:
            if c['clientID'] == clientID:
                c['chunks'].remove(chunk)
                break

        self.CLIENTS_LOD_LOCK.release()


    # given a clientID, a chunk will be assigned to it and added to its list
    def assignChunk(self,clientID: str, chunk: str):
        log_clientActivity(clientID,"N/A","A new chunk has been assigned to the client: " + chunk)
        
        self.CLIENTS_LOD_LOCK.acquire()

        for c in self.CLIENTS_LOD:
            if c['clientID'] == clientID:
                
                c['chunks'].append(chunk)
                
                break

        self.CLIENTS_LOD_LOCK.release()

    # refreshes the last seen timestamp of a client by its id
    # i.e., that client gets the current timestamp
    def refreshLastSeen(self,clientID: str):
        log_clientActivity(clientID,"N/A","The client's last seen has been refreshed.")
        self.CLIENTS_LOD_LOCK.acquire()

        for c in self.CLIENTS_LOD:
            if c['clientID'] == clientID:
                c['lastSeen'] = getCurrentTimestamp()
                break

        self.CLIENTS_LOD_LOCK.release()

    # returns None if there is no client with that ID
    def getLastSeen(self, clientID: str):
        result = None
        
        self.CLIENTS_LOD_LOCK.acquire()

        for c in self.CLIENTS_LOD:
            if c['clientID'] == clientID:
                result = c['lastSeen']
                break

        self.CLIENTS_LOD_LOCK.release()

        return result

    # returns a list clientIDs belonging to inactive clients
    # returns an empty list if all of the clients are still alive
    def getInactiveClients(self):

        # curried function for managing time difference
        def isInactive(timestamp1, timestamp2):            
            
            format_str = '%d-%m-%y %H:%M:%S'
            try:
                datetime1 = datetime.strptime(timestamp1, format_str)
                datetime2 = datetime.strptime(timestamp2, format_str)
            except ValueError:
                # Handle invalid timestamp format
                raise ValueError("Invalid timestamp format. Please provide timestamps in dd-mm-yy HH:MM:SS format.")
            
            # Calculate the time difference in seconds
            time_difference = abs((datetime2 - datetime1).total_seconds())
            
            # Check if the time difference is less than X seconds
            if time_difference < self.INACTIVE_CLIENT_SECONDS:
                return False    # still active
            else:
                return True     # not active anymore

        result = []
        now = getCurrentTimestamp()

        self.CLIENTS_LOD_LOCK.acquire()

        # cycle through all clients
        for c in self.CLIENTS_LOD:
            lastSeen = c['lastSeen']
            
            if isInactive(lastSeen,now):
                result.append(c['clientID'])

        self.CLIENTS_LOD_LOCK.release()

        return result

    # handles inactive clients (used by the thread "inactiveClientsThread")
    def inactiveClientsHandler(self):
        global CHUNKS_DIRECTORY
        log_generic("inactiveClientsThread started. Will look for inactive clients every {} seconds.".format(self.INACTIVE_CLIENT_CHECK_FREQUENCY))

        while True:

            # if no clients are online, no need to check 
            if self.getTotalConnectedClients() > 0:

                inactiveClients = self.getInactiveClients()
                
                for clientID in inactiveClients:
                    log_clientActivity(clientID,"N/A","Client is inactive. All chunks have been revoked.")
                    self.revokeAllChunks(clientID)
                    self.deleteClient(clientID)

                saveInventoryFile(CHUNKS_DIRECTORY)

            time.sleep(self.INACTIVE_CLIENT_CHECK_FREQUENCY)


    
ClientManager = _ClientManager()

# =====================================================================================================
# airolib-ng server

# returns current timestamp in DD-MM-YY HH:MM:SS
def getCurrentTimestamp():
    # Get the current date and time
    current_datetime = datetime.now()
    
    # Format the date and time as dd-mm-yy HH:MM:SS
    formatted_timestamp = current_datetime.strftime('%d-%m-%y %H:%M:%S')
    
    return formatted_timestamp

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
def setChunkState(chunkName, state: str):
    global CHUNKS_INVENTORY_DICT

    removeNullChunks()

    # specified only 1 chunk
    if (type(chunkName) == str):
        CHUNK_LOCK.acquire()
        CHUNKS_INVENTORY_DICT['chunks'][chunkName] = state
        CHUNK_LOCK.release()
        return

    # specified multple chunks in a list
    if (type(chunkName) == list):
        CHUNK_LOCK.acquire()
        for c in chunkName:
            CHUNKS_INVENTORY_DICT['chunks'][c] = state
        CHUNK_LOCK.release()
        return

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

    #print(CHUNKS_INVENTORY_DICT)
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

    # step 1 - get a snapshot of the current performance
    totalPerf = ClientManager.getTotalPerformance()

    # step 2 - check chunks status. How many have and haven't been batched?
    countDone = lambda d: len(list(filter(lambda key: d[key] == 'DONE',d)))
    countWIP = lambda d: len(list(filter(lambda key: d[key] == 'WIP',d)))
    done = countDone(CHUNKS_INVENTORY_DICT['chunks'])
    wip = countWIP(CHUNKS_INVENTORY_DICT['chunks'])
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
        'clientStatusDictionary':ClientManager.CLIENTS_LOD,
        'eta':eta,
        'totalPerformance':totalPerf,
        'batchedChunks':done,
        'todoChunks':todo,
        'wipChunks':wip,
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


# method used by the client to determine if there actually is work to do or not
@app.route('/workAvailable', methods=['GET'])
def workAvailable():
    log_clientActivity(request.headers['clientID'], request.remote_addr,  "The client has requested the path /workAvailable")

    CLIENT_CHUNK_REQUEST_LOCK.acquire()
    result = getTODOChunk()
    CLIENT_CHUNK_REQUEST_LOCK.release()

    if result == None:
        return jsonify({'response': False}),404
    else:
        return jsonify({'response': True}),200

# method used by the client to comunicate that it officially began to work
@app.route('/connect', methods=['GET'])
def clientConnected():
    log_clientActivity(request.headers['clientID'], request.remote_addr,  "The client has begun its work.")

    ClientManager.addClient(request.headers['clientID'],request.remote_addr)

    return jsonify({'response': 'client connected'}),200

# method used by the server web UI to display the current status
@app.route('/getClientsLOD', methods=['GET'])
def getClientsLOD():

    amount = ClientManager.getTotalConnectedClients()

    if amount == 0:
        return jsonify({'error': 'no clients connected'}),404

    return ClientManager.CLIENTS_LOD

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

    # refresh the last seen and add that chunk to the client's chunk list
    ClientManager.refreshLastSeen(request.headers['clientID'])
    ClientManager.assignChunk(request.headers['clientID'],todoChunk)
    
    log_clientActivity(request.headers['clientID'], request.remote_addr,  "The client has requested a chunk. Sent the following: " + todoChunk)
    return send_file(file_path, as_attachment=True)


# method used by clients to submit batched chunks.
# when a chunk is submitted, its filename will be used by the server to mark it as "done"
@app.route('/submitChunk', methods=['POST'])
def submitChunk():
    

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

    # refresh last seen and remove the chunk from that client's list
    ClientManager.refreshLastSeen(request.headers['clientID'])
    ClientManager.removeChunk(request.headers['clientID'],file.filename)

    log_clientActivity(request.headers['clientID'], request.remote_addr, "The client has submitted a chunk: " + file.filename)
    return jsonify({'message': 'File uploaded successfully', 'file_path': file_path})


# method used by clients to submit their performance
@app.route('/sendPerformanceInfo', methods=['POST'])
def sendPerformanceInfo():
    log_clientActivity(request.headers['clientID'], request.remote_addr, "The client has submitted its performance info")

    # Get the JSON data from the POST request
    data = request.get_json()

    try:
        ClientManager.setClientPerformance(data['clientID'],data['performance'])
        ClientManager.refreshLastSeen(data['clientID'])

        return jsonify({'status': 'Message received successfully'})
    except:
        return jsonify({'error': 'Invalid JSON data'}), 400


# method used by clients to comunicate they're done. This lets the server delete their id from the
# global status dictionary
# TODO
@app.route('/clientJobDone', methods=['POST'])
def clientJobDone():

    removeNullChunks()

    global CHUNKS_DIRECTORY

    # Get the JSON data from the POST request
    data = request.get_json()

    # is it a valid json object? does it contain clientID?
    if 'clientID' in data:
        
        try:

            # delete that specific client id
            ClientManager.deleteClient(request.headers['clientID'])
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
    
    inactiveClientsThread = threading.Thread(target=ClientManager.inactiveClientsHandler)
    inactiveClientsThread.start()

    #resetWIPchunks()
    resetALLchunks()

    
    app.run(host="0.0.0.0",debug=True,port=PORT)

    inactiveClientsThread.join()