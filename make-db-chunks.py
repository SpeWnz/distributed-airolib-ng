import ZHOR_Modules.nicePrints as np
import ZHOR_Modules.csvUtils as csvUtils
import ZHOR_Modules.logUtils as logUtils
import ZHOR_Modules.fileManager as fm
import sys
import os
import json

from common import WORDLIST_CHUNK_SIZE, AIROLIB_EXECUTABLE_PATH

# =========================================================
# GLOBAL VARIABLES

TEMP_WORDLIST = "__temp.txt"

OUTPUT_FOLDER = csvUtils.getTimeStamp()

# =========================================================

def splitWordlist(inputPath: str):
    com = "mkdir {}; split -l {} {} {}/wordlist-chunk-".format(
        OUTPUT_FOLDER,
        WORDLIST_CHUNK_SIZE,
        inputPath,
        OUTPUT_FOLDER
    )
    #print(com)
    os.system(com)

def filterWordlist(inputPath: str):
    # grep file -x '.\{A,B\}'
    com = "grep -a -x '.\\{8,63\\}' \"" + inputPath + "\" > \"" + TEMP_WORDLIST + "\""
    #print(com)
    os.system(com)


def generateDBChunks(wordlistChunksList: list,ssidListPath: str):

    dbIndex = 1
    total = len(wordlistChunksList)
    for item in wordlistChunksList:
        
        dbName = OUTPUT_FOLDER + "/DB-" + str(dbIndex) + ".db"
        
        msg = "Generating chunk " + dbName + " [{} / {}]".format(
            dbIndex,
            total
        )
        np.infoPrint(msg)
        

        #import passwords into db
        np.debugPrint("Importing passwords")
        com = "{} {} --import passwd {}".format(
            AIROLIB_EXECUTABLE_PATH,
            dbName,
            OUTPUT_FOLDER + "/" + item
        )
        os.system(com)

        #import ssids into db
        #import passwords into db
        np.debugPrint("Importing SSIDs")
        com = "{} {} --import essid {}".format(
            AIROLIB_EXECUTABLE_PATH,
            dbName,
            ssidListPath
        )
        os.system(com)

        dbIndex +=1


def deleteWordlistChunks(wordlistChunksList: list):

    for item in wordlistChunksList:
        #import passwords into db
        com = "rm {}".format(
            OUTPUT_FOLDER + "/" + item
        )
        os.system(com)

def generateInventoryJson(ssidFilePath: str):
    
    ssidCount = len(fm.fileToSimpleList(ssidFilePath))
    
    DBs = os.listdir(OUTPUT_FOLDER)
    dictObject = {
        'ssidCount': ssidCount,
        'chunks':{}
        }

    for item in DBs:
        dictObject['chunks'][item] = 'TODO'

    with open(OUTPUT_FOLDER + '/INVENTORY.json','w') as jsonFile:
        json.dump(dictObject,jsonFile)

# ========================================================

if (len(sys.argv) != 3):
    np.infoPrint("Usage: python3 script.py <wordlist path> <ssids path>")
    exit()

wordlistPath = str(sys.argv[1])
ssidPath = str(sys.argv[2])


print("Filtering out bad password candidates with grep. This might take a while...")
filterWordlist(wordlistPath)

print("Splitting wordlist  in chunks...")
splitWordlist(TEMP_WORDLIST)

print("Getting their names...")
chunkNames = os.listdir(OUTPUT_FOLDER)

#print(chunkNames)
print("Generating DB chunks...")
generateDBChunks(chunkNames,ssidPath)

print("Deleting temporary wordlist chunks...")
deleteWordlistChunks(chunkNames)

print("Creating json inventory file...")
generateInventoryJson(ssidPath)

print("Deleting temporary wordlist ...")
os.system("rm " + TEMP_WORDLIST)

print("Done.")