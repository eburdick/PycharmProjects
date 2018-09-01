#!/usr/bin/python3

#
# 
# The overall goal is to copy files from a camera memory card to the file respository on the computer that corresponds
# to the camera the memory card came from. File names in the repository are of the form of a time code: YYYYMMDD-HHMMSS_
# followed by the original file name, for example "20170417-130751_dsc_2930.nef" This started out as a camera file
# without the time code: "dsc_2930.nef". The time code is appended by a script that copies the "time digitized" metadata
# from the file and formats it into the chosen format. This pretty much guarantees that every file will have a unique
# name over a very long time.
#
#     
# Camera repository directory:
#     The repository directory tree for each camera is just a set of directories named after the date the files are
#     copied from the camera. It looks like this:
#         base_directory
#             2018-05-14
#             2018-05-18
#             More subdirectories in the format YYYY-MM-DD
#     
# File renaming:
#     Before copying the files to the repository directory, we copy them to a temporary directory and rename them, 
#     appending the time code as described above from the datetimeoriginal EXIF metadata. At that time, we may apply
#     a correction if the camera clock was set wrong.
# 
# Program flow:
#     - Scan storage devices plugged into the computer for known camera cards from our cameras. This assumes we know
#     what name pattern to look for. If there are more than one cards from the same camera, we are going to combine
#     them into one data structure, so there will be one data structure (dictionary) for each camera. See camera_info
#     below for details.
#
#     - For each camera card detected, add its path to the corresponding camera_info dictionary by added it to
#       the list at key card_path_list. Then add an empty list for paths to the files on the card and a path to the
#       a new repository directory for new files on these cards.
#
#
#     that corresponds to today.  If there is none, then create one.
#
#     - Scan and sort the entire camera repository and identify the newest file(s). There may be two with the same
#     time stamp, one jpg and one raw. We will assume there are only two at most. (issue: we will need an algorithm
#     to resolve that fact that the timestamps have only a one second resolution, and burst shots will create several
#     files within a second. This can probably be resolved by looking at the camera assigned sequence number, but 
#     there are special cases that can mess this up.)
#
#     - Scan and sort the entire memory card to find the first file(s) newer than the newest file(s) found in the
#     repository.
#
#     - Copy the first newer file(s) and all later ones to the temporary rename directory.
#
#     - Scan the camera card and the repository to find any stragglers -- older files that did not get copied
#     in the past. Put these where they belong in the repository and report to the user. This step could be done
#     later if it makes sense...
#
#     - Run the rename and copy the renamed files to the new repository sub directory. Clock corrections should be
#     done here, probably via a GUI designed for this purpose. Alternatively, this could be done later. There could
#     be code added here to detect timestamps that do not make sense, like pictures taken in the middle of the night,
#     and alert the user.
#


# Notes:
#
# Special case with d500: You can edit a raw file in camera and save it as a jpg file. The file name will be the next
# one available and the datetime exif flag will be set to the time that new file was created.  The datetimeoriginal
# exif flag is copied from the original file. The result of this is that a camera file with a larger file number than
# another will not necessarily contain a newer image, but its timestamp prefix will reflect the original time, thus
# listing files in order of name after renaming will result in a different order than the original un-named files. In
# addition, it is possible that files edited in the camera may be copied to the computer on a later date. The policy
# here will be to put such out of order files with the files from which they were derived, which means we must detect
# this situation and deal with it as a special case.
#    possible way of dealing with this: every repository directory contains all files generated during an interval of
#    full days. This means that all new files get put into the corresponding directories even if they were generated
#    inside of the camera at a much later date. This implies a two stage sorting process, first sorting new files by
#    camera file number and renaming, then moving files to the repository based on timestamp (datetimeoriginal, which
#    will be preppended to the file name by the renaming procedure.)  For this scheme, how do we decide which files
#    on the camera card to process? The brute force way would be to process (copy and rename)all of the files on the
#    card and copy to the corresponding repository directory, skipping duplicates, but this will be slow. Another way
#    is to do it all based on file number and then detect which files are out of time sequence and move them as
#    required as a post process.
#
# Special case for camera sequence number rollover: When a Nikon camera file name reaches dsc_9999, then next file
# name is dsc_0001. With the timestamp added to the beginning, this is generally OK, but if this rollover happens
# while shooting a burst, then the order can end up wrong if we use the camera file name to break the tie. Does this
# really matter? Maybe not. Is this an issue when looking for the newest file in the repository? We could end up 
# copying one or more of the files with the same timestamp to the new repository subdirectory, thus duplicating the 
# files. Maybe in this case, we do a special test to avoid this. Note this could also be an issue with in-camera
# edited files as described above.


import os
import shutil
import win32api
import win32file
import pywintypes
import win32con
import re
import exifread
import subprocess
from datetime import datetime, date
from string import ascii_uppercase
from tkinter import *
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
import tkinter.font
from datetime import datetime


#
# utility function to reformat the EXIF time format to our file prefix format...
# YYYY:MM:DD HH:MM:SS --> YYYYMMDD-HHMMSS.
#


def exiftime_to_file_prefix(exif_time):
    return exif_time[0:4]+exif_time[5:7]+exif_time[8:10]+'-'+exif_time[11:13]+exif_time[14:16]+exif_time[17:19]

#
# Function to change all three timestamps of a file...creation time, modify time and access time. We will use
# this for matching these timestamps in picture files to the EXIF metadata in the file. This helps with the
# problem of burst photos taken several a second having file timestamps that are off by a couple of seconds because
# they are written to the memory card from the camera buffer in an unpredictable order.  The EXIF original time tag
# records when the picture was captured, not when it was written to the memory card.
#


def change_file_times(fname, timestamp):
    newtime = datetime.strptime(timestamp, '%Y%m%d-%H%M%S')  # format matches our renamed file timestamp prefix
    wintime = pywintypes.Time(newtime)
    #
    # create a windows file object from the specified existing file
    #
    winfile = win32file.CreateFile(
        fname, win32con.GENERIC_WRITE,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
        None, win32con.OPEN_EXISTING,
        win32con.FILE_ATTRIBUTE_NORMAL, None)
    #
    # Set the file                  create, modify & access times
    #
    win32file.SetFileTime(winfile, wintime, wintime, wintime)
    #
    # We must close the file because it was opened by the OS
    #
    winfile.close()
    return


#
# starting camera and memory card information for our cameras...
#
# This takes the form of a list of dictionaries, one list element for each camera. Each dictionary contains
#    'name' The name of the camera
#    'card_pattern' A regular expression pattern that matched the volume label of that camera's memory card(s)
#    'repository_base' The path to the top of that camera's directory tree on the computer
#    'files_with_times': Initially and empty list...
#                 a list of 2-tuples (fully expanded file name,time stamp in the form YYMMDD-HHMMSS)
#                     eg [('H:\\DCIM\110NIKON\DSC_1234.NEF', '171224-173053')
#                         ('H:\\DCIM\110NIKON\DSC_1234.JPG', '171224-173053')
#                         ('J:\\DCIM\110NIKON\DSC_1235.NEF', '171224-173503')...]
#
# note this is the starting form of these dictionaries.  More will be added if we find memory cards associated
# with these cameras as follows:
#    'card_path_list': a list of paths to memory cards for this camera eg ['H:\','J:\']
#    'new_repository_dir': path to directory for new files named after today's date, eg
#                    'V:\Camera-buf\nikon-d500\renamed copies of flash memory\2018-07-27'
#
#
camera_info = [
    {'name': 'Nikon D500',
     'card_pattern': re.compile('.*d500', re.IGNORECASE),  # pattern: any characters followed by "d500"
     'repository_base': 'V:\\Camera-buf\\nikon-d500\\renamed copies of flash memory\\',
     'files_with_times': []},
    {'name': 'Nikon Coolpix B700',
     'card_pattern': re.compile('.*b700', re.IGNORECASE),  # pattern: any characters followed by "b700"
     'repository_base': 'V:\\Camera-buf\\nikon-coolpix-b700\\renamed copies of flash memory\\',
     'files_with_times': []}]


#
# list of file extensions for picture files. We use this to distinguish these from video files when we get
# exif information.
#
PICTURE_EXTENSIONS = ['.jpg', '.JPG', '.nef', '.NEF', '.nrw', '.NRW']
#
# index constants for files_with_times tuple
#
FILENAME = 0
TIMESTAMP = 1
#
# index constants for os.path.splittext
#
EXTENSION = 1
#
# index constants for win32api.GetVolumeInformation
#
VOLUME_NAME = 0
#
# index constants for the summary_info lists
#
CARDINFOPATH = 0
CARDINFODIRLIST = 1
DIRINFODIR = 0
DIRINFODATELIST = 1
DATEINFODATE = 0
DATEINFOFIRSTFILE = 1
DATEINFOLASTFILE = 2
#
# get today's date.  This will be used to create directories in the repositories for new files on the camera cards
#
today = str(date.today())
# today_no_dashes = today[0:4]+today[5:7]+today[8:10]
today_no_dashes = '20180620'
print(today, today_no_dashes)
#
# Find, and set up data structures for all camera cards plugged into the computer and mounted as drives.
#

# Function get_cam_cards_info() finds and camera cards that are mounted as drives on this computer and adds the
# following information to each of the corresponding camera card dictionaries:
#    - A list of the drive paths to this camera's cards
#    - A list of the files on all of the cards and the date and time the corresponing images were captured
#


def get_cam_cards_info():
    #
    # Get a list of all mounted drives. This will include any mounted camera memory card(s). This is a list
    # of two element dictionaries, each containing:
    #    'label' The volume label of the drive. This is extracted using the win32api.GetVolumeInformation method
    #    'path' The path to the volume
    mounted_drives = []
    for ltr in ascii_uppercase:
        drive_path = ltr + ':\\'
        if os.path.exists(drive_path):
            mounted_drives.append(
                {'label': win32api.GetVolumeInformation(drive_path)[VOLUME_NAME],
                 'path': drive_path})

    #
    # scan all drive labels for matches to our camera cards. Where a match is found:
    #     Increment cam_cards_count
    #     Add the card's path to 'card_path_list' in the camera's camera_info dictionary
    #     Add a 'new_repository_dir' to each camera data structure that has a corresponging mounted memory card.
    #         This is the name of the directory that we will create when with copy files from the card(s).
    #
    cam_cards_count = 0
    for drive in mounted_drives:  # iterate over mounted drives
        for cam in camera_info:   # for each mounted drive, iterate over our camera definition
            if cam['card_pattern'].match(drive['label']):  # if the current drive label matches the known camera label
                cam_cards_count += 1
                if 'card_path_list' not in cam:
                    #
                    # The data structure for this camera has not had card data added yet. Here, we add those entries...
                    # - card_path_list with a path to the first card
                    # - empty files_with_times list. We will fill this list later.
                    # - path to a new directory where we will copy the new files.
                    #
                    cam['card_path_list'] = [drive['path']]
                    cam['new_repository_dir'] = cam['repository_base']+today
                else:
                    #
                    # The dictionary for this camera already have entries for a memory card, which means we have
                    # found an additional memory card for this camera. We just need to add the path to this card to
                    # the card path list for the camera
                    #
                    cam['card_path_list'].append(drive['path'])
    #
    # test prints
    #
    if cam_cards_count == 0:
        print('no camera card found')
    else:
        for cam in camera_info:
            print(cam)
    #
    # At this point, we have path data for all memory cards present. For each memory card, we want to catalog
    # each of its files with the following information:
    #    file name
    #    time created (the time of the actual shot in the camera)
    #    camera memory card path to the file
    # Each file will be in a directory on the card created by the camera. Besides knowing the path to the file, we
    # do not care which of these directories it is in, and we will sort the files by time stamp.
    #

    #
    # Create a list of the media files from the camera cards we found.  These will be in the directory DCIM\subdir,
    # where subdir is assigned by the camera.  We walk the entire card below the DCIM directory.  Note we are assuming
    # all of our camera cards are organized with a DCIM top level directory with one layer of sub directories
    # containing only media files below that.
    #
    for cam in camera_info:
        if 'card_path_list' in cam:
            for path in cam['card_path_list']:
                for dir_name, subdir_list, file_list in os.walk(path+'DCIM\\'):
                    #
                    # for each file in file_list, combine it with dir_name\ to form the full file path, then get its
                    # time stamp, either by getting the DateTimeOriginal EXIF value (picture files) or the file
                    # creation time (video files). Put these into a tuple (file_full_path, timestamp) These are
                    # combined to create the card_file_time_list.
                    #
                    for file in file_list:
                        file_full_path = dir_name+'\\'+file
                        file_extension = os.path.splitext(file)[EXTENSION]

                        # Update status label
                        status_text.set('Processing '+file_full_path)
                        status_label.update()

                        if file_extension in PICTURE_EXTENSIONS:
                            #
                            # Picture file with EXIF metadata: Open the file and get the DateTimeOriginal metadata
                            #
                            f = open(file_full_path, 'rb')
                            tags = exifread.process_file(f, details=False, stop_tag='DateTimeOriginal')
                            #
                            # create a tuple of full path file name and timestamp from the EXIF data, then add it to
                            # the camera card file list
                            #
                            cam['files_with_times'].append(
                                                           (file_full_path,
                                                            exiftime_to_file_prefix(
                                                                str(tags['EXIF DateTimeOriginal']))))
                        else:
                            #
                            # File without EXIF metadata: get the file creation date from the directory and format it
                            # to our timestamp prefix format. create a tuple of full path file name and this
                            # timestamp, then add it to the camera card file list
                            #
                            # Technical note: strftime format %Y means 4 digit year including century (vs %y for 2
                            # digit year), %H means hours on 24 hour clock (vs %I for 12 hour clock with %p for am/pm)
                            #
                            cam['files_with_times'].append(
                                (file_full_path, datetime.fromtimestamp
                                 (os.path.getctime(file_full_path)).strftime('%Y%m%d-%H%M%S')))

                        status_text.set('Camera Card Files Analyzed')
                        status_label.update()

            #
            # Sort the file list on the timestamp element followed by file name, which are the two fields that will
            # make up the filename as renamed in the repository. We reverse the order because we want to scan in
            # reverse order later.
            #
            # technical note: we set the sort key to be a function (lambda) that returns the item we want to sort on,
            # which in this case is the timestamp followed by the file name. The key function
            # lambda element: element[TIMESTAMP]+element[FILENAME].split(sep='\\')[3]) returns a string
            # (timestamp + filename) that is used for doing the comparisons durring the sort. "element" here is one of
            # tuples making up the list we are sorting...(full path file name, timestamp) and the function parses out
            # the base file name and adds it to the end of the timestamp string.
            #
            # cam['files_with_times'].sort(reverse=True, key=lambda element: element[TIMESTAMP])
            cam['files_with_times'].sort(reverse=True,
                                         key=lambda element: element[TIMESTAMP]+element[FILENAME].split(sep='\\')[3])

    #
    # test prints
    #
    for cam in camera_info:
        if 'card_path_list' in cam:
            print(cam['name'], cam['card_pattern'], cam['new_repository_dir'], cam['card_path_list'], sep='\n')
            # for file_and_time in cam['files_with_times']:
            #     print(file_and_time)
    return cam_cards_count


def make_today_dir():
    #
    # use new_repository_dir from each camera card dictionary to create a directory
    #
    for cam in camera_info:
        if 'new_repository_dir' in cam:
            if os.path.exists(cam['new_repository_dir']):
                print('repository today directory exists')
            else:
                os.mkdir(cam['new_repository_dir'])
                print('repository today directory created')
    return

def find_repository_last_files():
            #
            # Traverse the repositories backward to find the last files, but if a directory for today has already been
            # created, we skip it, because it may already have files from a different memory card for the same camera,
            # and they may be newer than the files we want to copy.
            #
            # technical note: we sort the lists returned by os.listdir() because the order of the list it returns is
            # not in the spec.
            #
    for cam in camera_info:
        if 'new_repository_dir' in cam:
            dirlist = list(sorted(os.listdir(cam['repository_base']), reverse=True))
            skip_dir = os.path.exists(cam['new_repository_dir'])
            for directory in dirlist:
                if skip_dir:
                    skip_dir = False
                    print('skipping existing today directory')
                    continue
                filelist = os.listdir(cam['repository_base']+directory)
                print(directory)
                cam['repository_last_dir'] = directory + '\\'
                # skip directory if it is empty
                if len(filelist) == 0:
                    continue
                else:
                    # newest file is the last file in the last populated directory. This assumes all of the file names
                    # start with a timestamp string, which is our naming standard.
                    cam['repository_last_file'] = sorted(filelist)[-1]
                    break
    #
    # test prints
    #
    for cam in camera_info:
        if 'repository_last_dir' in cam:
            print(cam['name'], 'last file = ',
                  "{0}{1}{2}".format(cam['repository_base'], cam['repository_last_dir'], cam['repository_last_file']))
    return

#
# For each camera, iterate though its files_with_times list, copying each file from the memory card to the
# camera's new_repository_dir, changing the file name to add the timestamp to the beginning of the file with '_' as a
# separator and lower casing. EG "20180523-112822_dscn0111.jpg". The file_with_times list is in reverse order, so the
# newest files will be copied first. To make sure the file's timestamps match the timestamp prefix, we also modify
# the file's create, modify and access metadata to match it. Before each copy, we check see if the file is newer than
# the last repository file, and when this fails to be the case, we break out of the loop.
#


def copy_and_rename():
    for cam in camera_info:
        for file_and_time in cam['files_with_times']:
            last_file_timestamp = cam['repository_last_file'][0:15]
            # check if the file is newer than the last file in the existing repository. If not, we are done.
            if file_and_time[TIMESTAMP] > last_file_timestamp:
                sourcepath, base_filename = os.path.split(file_and_time[FILENAME])  # get base filename
                # create new target name with timestamp_
                new_filename = (file_and_time[TIMESTAMP] + '_' + base_filename).lower()
                dest_path = os.path.join(cam['new_repository_dir'], new_filename)
                # check if the target file in the repository already exists.  If so, skip the copy.
                if os.path.exists(dest_path):
                    print('Skipping copy to {}. File already exists.'.format(dest_path))
                    continue
                else:
                    shutil.copy2(file_and_time[FILENAME], dest_path)  # copy to repository
                    change_file_times(dest_path, file_and_time[TIMESTAMP])
                    print('copied {} to {}'.format(file_and_time[FILENAME], dest_path))
            else:
                # we have already copied the files newer than the newest repository entry
                break
    return


#
# Graphical User Interface
#

#
# Utility routines
#
def add_camcards_summary():
    #
    # This function goes through the camera card file data and create summary information for the GUI.
    #
    # The summary information is a series of nested lists...
    #
    # date_file_entry --> ['YYMMDD', firstfile, lastfile]          Block of files from a specific date
    # date_file_list  --> [date_file_entry...]                     List of date file entries
    # dir_entry       --> [dir, date_entry_list]                   directory with a list of date file entries
    # dir_list        --> [dir_entry...]                           list of dir entries
    # path_entry      --> [path, dir_list]                         path with a dir list
    # path_list       --> [path_entry...]                          list of path entries
    #
    # path_list gets copied to camera_data[n] as camera_data[n]['summary-info']
    #
    #
    # We get this information by parsing the camera's files_and_names list. Example:
    # H:\DCIM\103ND500\DSC_1516.JPG 20180729-151337
    # path = H:\DCIM\
    # directory = 103ND500
    # date = 20180729
    # file = DSC_1516.JPG
    #
    # Technical note: the file_with_times list is sorted by timestamp, so if we do a one-pass
    # scan, we could end up with more than one listing for a card_path or a directory depending on camera settings,
    # cards removed and added, etc This will not happen
    # very often and if it does, this imparts useful information, so we will let it happen.
    #

    for cam in camera_info:
        #
        # Test to see if one or more memory cards for this camera were found.  If so, create the summary
        # information for the cards
        #
        if 'card_path_list' in cam:

            #
            # make a copy of the camera's file_with_times list and reverse it so we have it in forward chronological
            # order.
            #
            files_with_times = cam['files_with_times'][:]
            files_with_times.reverse()
            #
            # initialize running values. We add new summary data each time we get a new value
            #
            old_path = ''
            old_dir = ''
            old_date = ''
            new_file = ''
            date_file_entry = None
            #
            # create empty path_list.  This will be built on the create our summary data.
            #
            path_list = []
            date_file_list = []  # initialize to prevent Pycharm warning. This value is never used.
            dir_list = []        # initialize to prevent Pycharm warning. This value is never used.

            for full_path, timestamp in files_with_times:
                #
                # Iterate through files_with_times
                #
                #
                # Parse the list element
                #
                path_tokens = full_path.split(sep='\\')
                timestamp_tokens = timestamp.split(sep='-')
                new_path = path_tokens[0]+'\\'+path_tokens[1]+'\\'
                new_dir = path_tokens[2]
                new_date = timestamp_tokens[0]
                last_file = new_file        # save old file value for use as last_file.
                new_file = path_tokens[3]
                #
                # If the path, the directory and the date are the same as the previous iteration, we create
                # no new summary information
                #
                if new_path == old_path and new_dir == old_dir and new_date == old_date:
                    continue
                #
                # if we get here, something has changed, so we will be starting a new list. First, we finish up
                # the current date_file_entry by adding the last file, which is new_file from the previous iteration.
                # The date_file_list that contains this entry is already in the datastructure, so we are adding it
                # in place. This operation is only done if this not the first iteration, so we test to see that
                # date_file_entry is not in its initial state.
                #
                if date_file_entry:
                    date_file_entry.append(last_file)
                #
                # no matter what has changed, we will need a new date_file_entry, so we create it here
                #
                date_file_entry = [new_date, new_file]
                #
                # if only the date has changed, we just add the new date_file_entry to the current date_file_list.
                # We also update old_date to this new date for the next time this test is made
                #
                if new_path == old_path and new_dir == old_dir and new_date != old_date:
                    date_file_list.append(date_file_entry)
                    old_date = new_date
                    continue
                #
                # if the directory has changed but the path is the same, then we need to add a directory entry
                # to the current dir_list, but first, we create a new date_file_list with the date_file_entry
                # we just created and use it to create the dir_entry. We also copy the new dir to old_dir for
                # the next time this test is made
                #
                if new_path == old_path and new_dir != old_dir:
                    date_file_list = [date_file_entry]
                    dir_entry = [new_dir, date_file_list]
                    dir_list.append(dir_entry)
                    old_dir = new_dir
                    old_date = new_date
                    continue
                #
                # if the path has changed, we need to add a new path element and all of the nested lists
                # under it. We also set old_path to this new path for the next time this test is made
                #
                if new_path != old_path:
                    date_file_list = [date_file_entry]
                    dir_entry = [new_dir, date_file_list]
                    dir_list = [dir_entry]
                    path_entry = [new_path, dir_list]
                    path_list.append(path_entry)
                    old_path = new_path
                    old_dir = new_dir
                    old_date = new_date

            #
            # At this point, all of the files have been processed, but the last file has not been added to the
            # date_file_entry, because there was no change in path, directory or date detected. The last file is
            # actually the current new_file, because that is the last one we picked up from the date_file_list. We
            # append this to the last date_file_entry in the for loop else clause, which is the end of loop cleanup
            # clause. Note that because there is no break in the loop, the else part is not strictly needed, but
            # this makes it more clear.
            #
            else:
                if date_file_entry:
                    date_file_entry.append(new_file)

            #
            # copy the reference to the path list into the camera's summary_info slot.
            #
            cam['summary_info'] = path_list

    return

#
# Widget Callbacks
#


def exit_button_clicked():
    exit()
    return


def getcard_clicked():
    #
    # Populate the camera data structures with information about the correesponding mounted camera cards, including
    # directories and files on the cards and timestamps.
    #
    count = get_cam_cards_info()
    #
    # Populate the camera data structures with information about the correponding existing repository directories. A
    # side effect of this operation is identifying the latest file in each camera repository, and creating a new
    # subdirectory in the repository for today's new files.
    #
    # make_today_dir()
    find_repository_last_files()

    # disable the button to avoid loading the camera card a second time.
    get_card_info_button.config(state=DISABLED)
    # enable the file copy button
    copy_files_button.config(state=NORMAL)
    # set_repos_button.config(state=NORMAL)

    #
    # create the camera memory card summary
    #
    add_camcards_summary()

    #
    # put file camera card summaries on the list box. Format:
    #
    # Camera name 1
    #    card path 1
    #       directory1
    #          date1, first file, last file
    #          ...
    #          dateN
    #       ...
    #          ...
    #       directoryN
    #          ...
    #    ...
    #    card path N
    #       ...
    #          ...
    # ...
    # Camera name N
    #
    if count == 0:
        status_text.set('No Camera Card Found')
        status_label.config(fg='Red', font='Helvetica 12 bold')
        status_label.update()
    else:
        for cam in camera_info:
            #
            # Check if the camera has summary info.  If so, then there is a camera card for that camera present and
            # we proceed to display the information for its card(s). Otherwise, we do nothing
            #
            if 'summary_info' in cam:
                #
                # Display the camera name and grab the date from its last repository file.
                #
                cardfiles_list_box.insert(END, cam['name'])
                cam_last_file_date = cam['repository_last_file'][0:8]
                for card_info in cam['summary_info']:
                    #
                    # There is one or more memory cards for this camera. Iterate through them, starting by listing
                    # the path of the card in the file system.
                    #
                    cardfiles_list_box.insert(END, '   {}'.format(card_info[CARDINFOPATH]))
                    for dir_info in card_info[CARDINFODIRLIST]:
                        #
                        # Iterate through the directories on the card, starting by listing the name of the directory
                        #
                        cardfiles_list_box.insert(END, '      {}'.format(dir_info[DIRINFODIR]))
                        for date_info in dir_info[DIRINFODATELIST]:
                            #
                            # Iterate through the file dates in the directory, displaying the date, and the names
                            # of the first and last files captured on that date.
                            #
                            # Check the options menu to see if the user wants to see a summary for all files on the
                            # memory cards or just ones that have not been put into the repository yet. If the
                            # menu does not indicate all files, then skip files that are already in the repository.
                            #
                            if date_info[DATEINFODATE] > cam_last_file_date or 'All' in card_info_filter_var.get():
                                cardfiles_list_box.insert(
                                    END, '         {}: {} - {}'.format(
                                        date_info[DATEINFODATE],
                                        date_info[DATEINFOFIRSTFILE],
                                        date_info[DATEINFOLASTFILE]))
    return


# def setrepos_clicked():
#    make_today_dir()
#    set_repos_button.config(state=DISABLED)
#    copy_files_button.config(state=NORMAL)
#    return


def copyfiles_clicked():
    make_today_dir()
    copy_and_rename()
    copy_files_button.config(state=DISABLED)
    return


def card_info_filter_changed(*args):
    #
    # Clear the list box
    #
    cardfiles_list_box.delete(0, END)
    #
    # run the callback for the getcard button.  That code will check the value of this menu while re-populating the
    # list box
    #
    getcard_clicked()

#
# Create the main window
#
window = Tk()
s = ttk.Style()
s.theme_use('xpnative')
s.configure('window.TFrame', font=('Helvetica', 20))
print(s.theme_names())
# print(s.element_options('Button.label'))

window.title('Camera Memory Card Tool')
window.geometry("800x600")
#
# Create a notebook to contain our information pages
#
notebook = ttk.Notebook(window)
page1 = ttk.Frame(notebook)
page2 = ttk.Frame(notebook)
text2 = ScrolledText(page2, width=40)
text2.insert(INSERT, 'Page reserved for later')
notebook.add(page1, text='cards summary')
notebook.add(page2, text='page two')


# Create the card file list box, its scrollbar, and the button that populates it

cardfiles_list_box = Listbox(page1, height=30, width=50, border=0, selectmode=SINGLE)
list_scrollbar = Scrollbar(page1, orient="vertical")
get_card_info_button = Button(window, text='Get Cam Cards', command=getcard_clicked)
card_info_filter_var = StringVar(window)
card_info_filter_var.set("Memory Card(s): Show All Files")
# create a label for reporting status
status_text = StringVar()
status_label = Label(window, textvariable=status_text, relief=SUNKEN)
status_text.set('Status')


# set_repos_button = Button(window, text='Set Repository', command=setrepos_clicked)
# set_repos_button.config(state=DISABLED)

copy_files_button = Button(window, text='Copy Files', command=copyfiles_clicked)
copy_files_button.config(state=DISABLED)
card_info_filter_menu = OptionMenu(window,
                                   card_info_filter_var,
                                   'Memory Card(s): Show All Files',
                                   'Memory Card(s): Show New Files')
card_info_filter_var.trace('w', card_info_filter_changed)

# Set scrollbar to call the list box yview method. This method scrolls the list to a given position.
# Set the and set the yscrollcommand function of the list box to be the set command of the scrollbar. This tells
# the scrollbar where to put the top and bottom edges of the slider for accurate visual feedback.
list_scrollbar.config(command=cardfiles_list_box.yview)
cardfiles_list_box.config(yscrollcommand=list_scrollbar.set)

# Create the exit button
exit_button = Button(window, text='Exit', command=exit_button_clicked)

# Place Window widgets using grid layout

get_card_info_button.grid(row=0, column=0)
# set_repos_button.grid(row=0, column=1)
copy_files_button.grid(row=0, column=2)
notebook.grid(row=1, column=0, columnspan=3)
card_info_filter_menu.grid(row=3, column=0, columnspan=2, sticky=W)
exit_button.grid(row=3, column=2, sticky=E)
status_label.grid(row=2, column=0, columnspan=3, sticky=E+W)
# Place the card summary list box and its scrollbar using pack layout

# cardfiles_list_box.pack(side=LEFT)
# list_scrollbar.pack(side=RIGHT, fill=Y)
cardfiles_list_box.grid(column=0, row=0)
list_scrollbar.grid(column=1, row=0, sticky=N+S)

# place the text2 text widget using pack
# text2.pack(expand=1, fill='both')
text2.grid(column=0, row=0, sticky=E+W+N+S)

window.mainloop()

#
# code for running exiftool in a subprocess so we can write exif values.  This example uses the exiftool -execute
# command to pack multiple commands onto one line.
#
# subprocess.check_output spawns a subprocess and sends a command line to it, then returns any output from the command
# line as a byte string.  Note we are not really sending a shell command, but starting a program in the process without
# running the shell. exiftool is in the path, so it will start and run, then the process shuts down. The try: block is
# to catch errors.  Need to learn how to catch the actual text of a traceback in the except: block so we can display
# it in the gui.
#
# import subprocess
# try:
#     output = subprocess.check_output(
#              "exiftool -make -model 20170922-152750_dsc07951.jpg -execute -modifydate 20170922-152716_dsc07951.jpg",
#               stderr=subprocess.STDOUT)
# except:
#     print('error')
# else:
#     do stuff
