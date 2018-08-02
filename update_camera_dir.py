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
import re
import exifread
from datetime import datetime, date
from string import ascii_uppercase


# utility function to reformat the EXIF time format to our file prefix format...
# YYYY:MM:DD HH:MM:SS --> YYYYMMDD-HHMMSS.
#
def exiftime_to_file_prefix(exif_time):
    return exif_time[0:4]+exif_time[5:7]+exif_time[8:10]+'-'+exif_time[11:13]+exif_time[14:16]+exif_time[17:19]


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
picture_extensions = ['.jpg', '.JPG', '.nef', '.NEF', '.nrw', '.NRW']
#
# get today's date.  This will be used to create directories in the repositories for new files on the camera cards
#
today = str(date.today())

#
# Find, and set up data structures for all camera cards plugged into the computer and mounted as drives.
#

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
            {'label': win32api.GetVolumeInformation(drive_path)[0],
             'path': drive_path})

#
# scan all drive labels for matches to our camera cards. Where a match is found, add an element to the
# cam_cards_info list. Each element of this list is a dictionary identical to the camera_info dictionary
# corresponding to the camera memory card label with the addition of the path to the camera memory card.
# If there are more than one card from a camera, there will be an element in cam_cards_info for each. This covers
# the case where a professional camera has two cards
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
# Create a list of the picture files from the camera card.  These will be in the directory DCIM\subdir, where subdir is
# assigned by the camera.  We walk the entire card below the DCIM directory.  Note we are assuming all of our
# camera cards are organized with a DCIM top level directory with sub directories containing picture files below
# that.
#
for cam in camera_info:
    if 'card_path_list' in cam:
        for path in cam['card_path_list']:
            for dir_name, subdir_list, file_list in os.walk(path+'DCIM\\'):
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
                        tags = exifread.process_file(f, details=False, stop_tag='DateTimeOriginal')
                        #
                        # create a tuple of full path file name and timestamp from the EXIF data, then add it to
                        # the camera card file list
                        #
                        cam['files_with_times'].append(
                                                (file_full_path,
                                                exiftime_to_file_prefix(str(tags['EXIF DateTimeOriginal']))))
                    else:
                        #
                        # File without EXIF metadata: get the file creation date from the directory and format it
                        # to our timestamp prefix format. create a tuple of full path file name and this timestamp, then
                        # add it to the camera card file list
                        #
                        # Technical note: strftime format %Y means 4 digit year including century (vs %y for 2 digit
                        # year), %H means hours on 24 hour clock (vs %I for 12 hour clock with %p for am/pm)
                        #
                        cam['files_with_times'].append(
                            (file_full_path,
                            datetime.fromtimestamp(os.path.getctime(file_full_path)).strftime('%Y%m%d-%H%M%S')))
        #
        # Sort the file list on the timestamp element. This is to handle files edited in the camera that will have
        # camera assigned file numbers that appear to be out of sequence with their time stamp, or cases where the
        # camera has started naming files again at 0001 or another out-of-sequence file name. We want to process these
        # files in time stamp order. We reverse the order because we want to scan in reverse later.
        #
        # technical note: we set the sort key to be a function (lambda) that returns the item we want to sort on, which
        # in this case is the second item of tuple that makes up an element of the list. The function
        # lambda element: element[1], when passed a tuple, will return the second element of the tuple, which, in our
        # case, is the file's timestamp.
        #
        cam['files_with_times'].sort(reverse=True, key=lambda element: element[1])
#
# test prints
#
for cam in camera_info:
    if 'card_path_list' in cam:
        print(cam['name'], cam['card_pattern'], cam['new_repository_dir'], cam['card_path_list'], sep='\n')
        for file_and_time in cam['files_with_times']:
            print(file_and_time)

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
        #
        # Traverse the repositories backward to find the last files. This may start with the empty directory just
        # created and keep going until it finds a directory that has files. It could also start with a directory
        # that was already created today from a different memory card from the same camera.
        #
        # technical note: we sort the lists returned by os.listdir() because the order of the list it returns is
        # not in the spec.
        #
        dirlist = list(sorted(os.listdir(cam['repository_base']), reverse=True))
        for directory in dirlist:
            filelist = os.listdir(cam['repository_base']+directory)
            print(directory)
            cam['repository_last_dir'] = directory + '\\'
            if len(filelist) == 0:
                continue
            else:
                cam['repository_last_file'] = sorted(filelist)[-1]
                break

#
# test prints
#
for cam in camera_info:
    if 'repository_last_dir' in cam:
        print(cam['name'], 'last file = ',
              "{0}{1}{2}".format(cam['repository_base'], cam['repository_last_dir'], cam['repository_last_file']))

#
# For each camera, iterate though its files_with_times list, copying each file from the memory card to the
# camera's new_repository_dir. The file_with_times list is in reverse order, so the newest files will be copied
# first. Before each copy, we check see if the file is newer than the last repository file, and when this fails to be
# the case, we break out of the loop.
#
for cam in camera_info:
    for file_and_time in cam['files_with_times']:
        last_file_timestamp = cam['repository_last_file'][0:15]
        if file_and_time[1] > last_file_timestamp:
            print(file_and_time,last_file_timestamp)
            #get base filename
            sourcepath,base_filename = os.path.split(file_and_time[0])
            new_filename = (file_and_time[1] + '_' + base_filename).lower()
            shutil.copy2(file_and_time[0],os.path.join(cam['new_repository_dir'],new_filename))

        else:
            break


#
# to do...
#
# Provide a mechanism for filling in the gaps in case a second card is being used to update a camera. real world case:
# SD card from d500 has been loaded, but there are files on the XQD card that fill in a gap. This card does not load
# because the latest file now in the d500 repository is later than any files on this card.  There needs to be a search
# for the gap to take care of this situation.