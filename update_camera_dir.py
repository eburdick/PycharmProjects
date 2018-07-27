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
#     what name pattern to look for. If we find more than one camera card, we will deal with them one at a time, even
#     if they come from the same camera.
#
#     - Once a camera card is identified, go to the corresponding camera repository and check for a subdirectory
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
# name is dsc_0000. With the timestamp added to the beginning, this is generally OK, but if this rollover happens
# which shooting a burst, then the order can end up wrong if we use the camera file name to break the tie. Does this
# really matter? Maybe not. Is this an issue when looking for the newest file in the repository? We could end up 
# copying one or more of the files with the same timestamp to the new repository subdirectory, thus duplicating the 
# files. Maybe in this case, we do a special test to avoid this. Note this could also be an issue with in-camera
# edited files as described above.


import os
import win32api
import re
import exifread
from datetime import datetime

from string import ascii_uppercase

# utility function to reformat the EXIF time format to our file prefix format...
# YYYY:MM:DD HH:MM:SS --> YYMMDD-HHMMSS.
#
def exiftime_to_file_prefix (exif_time):
    return(exif_time[2:4]+exif_time[5:7]+exif_time[8:10]+'-'+exif_time[11:13]+exif_time[14:16]+exif_time[17:19])
#
# camera and memory care information for our cameras...
#
# This takes the form of a list of dictionaries, one list element for each camera. Each dictionary contains
#    'name' The name of the camera
#    'card_pattern' A regular expression pattern that matched the volume label of that camera's memory card(s)
#    'repository_base' The path to the top of that camera's directory tree on the computer
camera_info = [
    {'name': 'Nikon D500',
     'card_pattern': re.compile('.*d500', re.IGNORECASE),
     'repository_base': 'V:\\Camera-buf\\nikon-d500\\renamed copies of flash memory'},
    {'name': 'Nikon B700',
     'card_pattern': re.compile('.*b700', re.IGNORECASE),
     'repository_base': 'V:\\Camera-buf\\nikon-b700\\renamed copies of flash memory'}]

#
# list of file extensions for picture files. We use this to distinguish these from video files when we get
# exif information.
#
picture_extensions = ['.jpg', '.JPG', '.nef', '.NEF', '.nrw', '.NRW']
#
# Find, and set up data structures for all camera cards plugged into the computer and mounted as drives.
#

#
# Get a list of all mounted drives. This will include any mounted camera memory card(s). This is a list
# of two element dictionaries, each containing:
#    'label' The volume label of the drive. This is extracted using the win32api.GetVolumeInformation method
#    'path' The path to the volume
#
mounted_drives = []
for ltr in ascii_uppercase:
    drive_path = ltr + ':\\'
    if os.path.exists(drive_path):
        mounted_drives.append (
            {'label': win32api.GetVolumeInformation(drive_path)[0],
             'path':drive_path})

#
# scan all drive labels for matches to our camera cards. Where a match is found, add an element to the
# card_info list. Each element of this list is a dictionary identical to the camera_info dictionary
# corresponding to the camera memory card label with the addition of the path to the camera memory card.
# If there are more than one card from a camera, there will be an element in card_info for each. This covers
# the case where a professional camera has two cards
#
card_info = []
for drive in mounted_drives:
    for cam in camera_info:
        if cam ['card_pattern'].match(drive['label']):
            card_info.append(cam.copy())
            card_info[-1]['card_path'] = drive['path']
#
# card_info will be an empty list if there are no memory cards mounted.
#
# Temporary print calls here.
#
if len(card_info) == 0:
    print('no camera card found')
else:
    for card in card_info:
        print ('Camera: {}, Card Path: {}, Repository: {}'
               .format(card['name'], card['card_path'], card['repository_base']))

#
# At this point, we have path data for all memory cards present. For each memory card, we want to catalog
# each of its files with the following information:
#    file name
#    time digitized (the time of the actual shot in the camera)
#    camera memory card path to the file
# Each file will be in a directory on the card created by the camera. Besides knowing the path to the file, we
# do not care which of these directories it is in, and we will sort the files by time stamp.
#

#
# Get the picture files from the camera card.  These will be in the directory DCIM\subdir, where subdir is
# assigned by the camera.  We walk the entire card below the DCIM directory.  Note we are assuming all of our
# camera cards are organized with a DCIM top level directory with sub directories containing picture files below
# that.
#

for card in card_info:
    #
    # walk the entire card recursively to create a data structure. For each iteration, this loop will produce
    # a directory name which is the complete path to the directory containing the picture files, an empty
    # subdirectory list, and a list of file names.
    #
    card_file_time_list = []
    for dir_name, subdir_list, file_list in os.walk(card['card_path']+'DCIM\\'):
        #
        # for each file in file_list, combine it with dir_name\ to form the full file path, then get its time
        # stamp, either by getting the DateTimeOriginal EXIF value (picture files) or the file creation time
        # (video files). Put these into a tuple (file_full_path, timestamp) These are combined to create the
        # card_file_time_list.
        #
        for file in file_list:
            file_full_path = dir_name+'\\'+file
            file_extension = os.path.splitext(file)[1]

            if file_extension in picture_extensions:
                #
                # Picture file with EXIF metadata: Open the file and get the DateTimeOriginal metadata
                #
                f = open(file_full_path, 'rb')
                tags = exifread.process_file(f, details=False, stop_tag = 'DateTimeOriginal')
                #
                # create a tuple of full path file name and timestamp from the EXIF data, then add it to
                # the camera card file list
                #
                file_and_time_stamp = (
                    file_full_path,
                    exiftime_to_file_prefix(str(tags['EXIF DateTimeOriginal'])))
                card_file_time_list.append(file_and_time_stamp)
            else:
                #
                # File without EXIF metadata: get the file creation date from the directory and format it
                # to our timestamp prefix format. create a tuple of full path file name and this timestamp, then
                # add it to the camera card file list
                #
                file_and_time_stamp = (
                    file_full_path,
                    datetime.fromtimestamp(os.path.getctime(file_full_path)).strftime('%y%m%d-%H%M%S'))
                card_file_time_list.append(file_and_time_stamp)

#
# debug code: print card file time list
#
print('\nFile on memory card              Time stamp')
for file,time in card_file_time_list:
    print(file,time)


