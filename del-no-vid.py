#!/usr/bin/python3
#
# Prototype code for portable file operations, just to have code to cut and
# paste for other programs.
#
#
# Import library modules
#
import os
#from pathlib import Path
#from glob import glob
from send2trash import send2trash

#import shutil          # high level file operations like copy, rename, etc
#startingDir = "C:\\test"
startingDir = "."
targetFileTypes = [".mp4", ".avi", ".mov", ".wmv", ".flv"]


#
# Examine all directories below startingDir, and delete the ones that do not contain any files with extensions matching
# members of the list targetFileTypes
#

#
# Walk the directory tree, but stop at the top level. We are looking for the qualifying files to be at the top level.
#
for root, dirs, files in os.walk(startingDir):
     break
#
# Iterate through the directories in the top level
#
for dir in dirs:
    #
    # Get a list of the files in this directory and preset at flag indicating deletion.  If we find a qualifying file
    # will will clear this flag
    #
    filenames = os.listdir(startingDir+"\\"+dir)
    delDir = True
    #
    # Iterate through the files in this directory.  If we find a file with one of the qualifying extensions, we
    # clear the delDir flag.
    #
    for filename in filenames:
        name,ext = os.path.splitext(filename)
        if ext.lower() in targetFileTypes:
            delDir = False
    #
    # If the delete flag is still set after looking at all of the files in the directory, send the directory to the
    # trash repository.  We can empty the trash later to clean things up.
    #
    if delDir:
        send2trash(startingDir+"\\"+dir)







#filenames = os.listdir(startingDir)
#print(filenames)
#
#result = []
#for filename in filenames:
#    print(filename)
#    filepath = Path(os.path.join(os.path.abspath("."), filename))
#    print(filepath, type(filepath))
#    print(filepath.is_dir())
#    if filepath.is_dir():
#        result.append(filename)
#        print(result)



#result.sort()
#print(result)



