#!/usr/bin/python3

#
# 
# The overall goal is to copy files from camera memory cards to the file respository on the computer that corresponds
# to the camera each memory card came from. File names in the repository are formated as a time code: YYYYMMDD-HHMMSS_
# followed by the original file name, for example "20170417-130751_dsc_2930.nef" This started out as a camera file
# without the time code: "DSC_2930.NEF". The time code is appended by a script that copies the "time digitized" metadata
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
#     After copying the files to the repository directory, we rename them,
#     appending the time code as described above from the datetimeoriginal EXIF metadata.
# 
# Program flow:
#     - Scan storage devices plugged into the computer for known camera cards from our cameras. This assumes we know
#     what name pattern to look for. If there are more than one cards from the same camera, we are going to combine
#     them into one data structure, so there will be one data structure (dictionary) for each camera. See camera_info
#     below for details.
#
#     - For each camera card detected, add its path to the corresponding camera_info dictionary by added it to
#       the list at key card_path_list. Then add an empty list for paths to the files on the card and a path to the
#       a new repository directory for new files on these cards that corresponds to today.  If there is none, then
#       create one.
#
#     - Scan and sort the entire camera repository and identify the newest file(s). There may be two with the same
#     time stamp, one jpg and one raw. We will assume there are only two at most.
#
#     - Scan and sort the entire memory card to find the first file(s) newer than the newest file(s) found in the
#     repository.
#
#     - Copy the files to the new repository sub directory, renaming on the fly. Clock corrections can  be done
#     after doing this copy/rename.
#
# Things we are not handling:
#
#     - Major clock corrections of more than a few hours, and specifically clock corrections that make files in
#     the repository newer than the files on a memory card.
#
#     - Gaps in the repository due to previous manual copies with mistakes or deletions.


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

#
# Import library modules
#
import os
import shutil          # high level file operations like copy, rename, etc
import win32api        # windows specific operations (pip install pywin32)
import win32file       # windows specific file stuff
import pywintypes      # supports common windows types like times
import win32con        # windows constants
import re              # the regular expression module
import exifread        # media file metadata stuff we use it for getting timestamps (pip install exifread)
import subprocess      # subprocess utilities for spawning applications like exiftool
from subprocess import Popen
from datetime import datetime, date  # date and time related utilities
from string import ascii_uppercase   # pretty self explanitory
from tkinter import *                # GUI stuff
from tkinter import ttk              # more widgets
from tkinter.scrolledtext import ScrolledText  # not sure why we need to import a module for scrolled text
from tkinter import filedialog
import tkinter.font                  # GUI font stuff
from PIL import Image, ImageTk       # (pip install Pillow)
from PIL.ExifTags import TAGS


from resizeimage import resizeimage  # (pip install python-resize-image)
import numpy as np                   # (pip install numpy)
import cv2                           # (pip install opencv-python)
import rawpy                         # (pip install rawpy)

# import piexif


#
# import site specific camera information
#
import my_camera_data


def exiftime_to_file_prefix(exif_time):
    #
    # utility function to reformat the EXIF time format to our file prefix format...
    # YYYY:MM:DD HH:MM:SS --> YYYYMMDD-HHMMSS.
    #
    return exif_time[0:4]+exif_time[5:7]+exif_time[8:10]+'-'+exif_time[11:13]+exif_time[14:16]+exif_time[17:19]


def change_file_times(fname, timestamp):
    #
    # Function to change all three timestamps of a file...creation time, modify time and access time. We will use
    # this for matching these timestamps in picture files to the EXIF metadata in the file. This helps with the
    # problem of burst photos taken several a second having file timestamps that are off by a couple of seconds because
    # they are written to the memory card from the camera buffer in an unpredictable order.  The EXIF original time tag
    # records when the picture was captured, not when it was written to the memory card.
    #
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
    # We must close the file because it is a platform specific object created by the OS
    #
    winfile.close()
    return


#
# add and initialize working keys and values to the camera dictionaries
#
#   'processed': False to inicate no processing has yet been done to this camera info
#   'files_with_times': Initially an empty list...
#                 a list of the files and original creation dates of the files on the camera card(s) for this camera
#                 in the form of a list of 2-tuples (fully expanded file name,time stamp in the form YYMMDD-HHMMSS)
#                     eg [('H:\\DCIM\110NIKON\DSC_1234.NEF', '171224-173053')
#                         ('H:\\DCIM\110NIKON\DSC_1234.JPG', '171224-173053')
#                         ('J:\\DCIM\110NIKON\DSC_1235.NEF', '171224-173503')...]
#

for cam_dict in my_camera_data.camera_info:
    cam_dict['processed'] = False
    cam_dict['files_with_times'] = []


def get_camera_info():
    #
    # function for getting the camera_info structure. This is a little cleaner than just using the structure
    # as a global variable. This should probably be a CameraInfo class.
    #
    return my_camera_data.camera_info


def get_backup_drive_info():
    return my_camera_data.backup_drive_info


def get_temp_source_info():
    return my_camera_data.temp_source_info


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


def is_picture_file(file_name):
    #
    # check if a file name has a picture file extension
    #
    file_extension = os.path.splitext(file_name)[EXTENSION]
    if file_extension in my_camera_data.PICTURE_EXTENSIONS:
        return True
    else:
        return False


def is_raw_file(file_name):
    #
    # check if a file name has a raw file extension
    #
    file_extension = os.path.splitext(file_name)[EXTENSION]
    if file_extension in my_camera_data.RAW_EXTENSIONS:
        return True
    else:
        return False


def is_video_file(file_name):
    #
    # check if a file name has a video file extension
    #
    file_extension = os.path.splitext(file_name)[EXTENSION]
    if file_extension in my_camera_data.VIDEO_EXTENSIONS:
        return True
    else:
        return False


def get_cam_cards_info():
    #
    # Function get_cam_cards_info() finds the camera cards that are mounted as drives on this computer and adds the
    # following information to each of the corresponding camera card dictionaries:
    #    - A list of the drive paths to this camera's cards
    #    - A list of the files on all of the cards and the date and time the corresponing images were captured
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
            mounted_drives.append(
                {'label': win32api.GetVolumeInformation(drive_path)[VOLUME_NAME],
                 'path': drive_path})
    print(mounted_drives)
    #
    # scan all drive labels for matches to our camera cards. Where a match is found:
    #     Increment cam_cards_count
    #     Add the card's path to 'card_path_list' in the camera's camera_info dictionary
    #     Add a 'new_repository_dir' to each camera data structure that has a corresponging mounted memory card.
    #         This is the name of the directory that we will create when with copy files from the card(s).
    #
    cam_cards_count = 0
    for drive in mounted_drives:        # iterate over all mounted drives
        for cam in get_camera_info():   # for each mounted drive, iterate over our camera definition
            cam['processed'] = True     # marked this camera as processed
            if cam['card_pattern'].match(drive['label']):  # if the current drive label matches the known camera label
                cam_cards_count += 1
                if 'card_path_list' not in cam:
                    #
                    # The data structure for this camera has not had card data added yet. Here, we add those entries...
                    # - card_path_list with a path to the first card
                    # - path to a new directory where we will copy the new files.
                    #
                    cam['card_path_list'] = [drive['path']]
                    cam['today_dir'] = str(date.today())
                    cam['new_repository_dir'] = cam['repository_base']+cam['today_dir']
                else:
                    #
                    # The dictionary for this camera already has entries for a memory card, which means we have
                    # found an additional memory card for this camera. We just need to add the path to this card to
                    # the card path list for the camera
                    #
                    cam['card_path_list'].append(drive['path'])
    # scan all drive labels for matches to our backup drives. We assume a backup drive has a structure like this...
    # drive:\camera1\DCIM\directory1\media files...
    #                    \directory2\media files...
    #                    ...
    #       \camera2\DCIM\directory1\media files...
    #                    \...
    # backup drive labels will match backup_drive_info['drive_pattern']
    # camera2, camera2, etc come from the camera info dictionaries, cam['card_pattern']
    #
    for drive in mounted_drives:
        drivepath = drive['path']
        if get_backup_drive_info()['drive_pattern'].match(drive['label']):
            #
            # we have identified a backup drive.  Now we scan its top level directories for matches to our
            # cameras.
            #
            level_1_dirs = [d for d in os.listdir(drivepath) if os.path.isdir(os.path.join(drivepath, d))]
            #
            # loop through level 1 directories on this backup drive
            #
            for dir in level_1_dirs:
                #
                # loop through cameras
                #
                for cam in get_camera_info():
                    #
                    # check whether the camera card_pattern matches the directory name
                    #
                    if cam['card_pattern'].match(dir):
                        cam_cards_count += 1
                        #
                        # add the path to this directory to the camera dictionary
                        #
                        if 'card_path_list' not in cam:
                            #
                            # The data structure for this camera has not had card data added yet. Here, we add those
                            # entries...
                            # - card_path_list with a path to the first card
                            # - path to a new directory where we will copy the new files.
                            #
                            cam['card_path_list'] = [drive['path']+dir+'\\']
                            cam['today_dir'] = str(date.today())
                            cam['new_repository_dir'] = cam['repository_base'] + cam['today_dir']
                        else:
                            #
                            # The dictionary for this camera already has entries for a file source, which means we have
                            # found an additional file source for this camera. We just need to add the path to this
                            # card to the card path list for the camera
                            #
                            cam['card_path_list'].append(drive['path']+dir+'\\')
    #
    # check if there is a temp_source directory. This is a temporary location on the computer for importing files
    # that are not from our regular cameras or backup drives. We require that it have the same structure as our
    # backup drives:
    # temp_source_root\camera1\DCIM\directory1\media files...
    #                              \directory2\media files...
    #                              ...
    #                 \camera2\DCIM\directory1\media files...
    #                              \...
    #
    # temp_source_root is the root of the directory tree chosen by the user
    # camera2, camera2, etc come from the camera info dictionaries, cam['card_pattern']
    #
    # test if the user has specifed a temp_source_root.  If so, traverse the directories under it and add the files
    # to the camera_info dictionaries as we did above.
    #
    # !!!Note this code is close to identical to the backup drive code, so we should probably put it into a function
    tmpsrc = TempSource()
    tmpsrcroot = tmpsrc.temp_source_root
    if tmpsrc.temp_source_root:
        #
        # we have identified the temp source directory.  Now we scan its top level directories for matches to our
        # cameras.
        #
        level_1_dirs = [d for d in os.listdir(tmpsrcroot) if os.path.isdir(os.path.join(tmpsrcroot, d))]
        #
        # loop through level 1 directories
        #
        for dir in level_1_dirs:
            #
            # loop through cameras
            #
            for cam in get_camera_info():
                #
                # check whether the camera card_pattern matches the directory name
                #
                if cam['card_pattern'].match(dir):
                    cam_cards_count += 1
                    #
                    # add the path to this directory to the camera dictionary
                    #
                    if 'card_path_list' not in cam:
                        #
                        # The data structure for this camera has not had card data added yet. Here, we add those
                        # entries...
                        # - card_path_list with a path to the first card
                        # - path to a new directory where we will copy the new files.
                        #
                        cam['card_path_list'] = [tmpsrcroot + dir + '\\']
                        cam['today_dir'] = str(date.today())
                        cam['new_repository_dir'] = cam['repository_base'] + cam['today_dir']
                    else:
                        #
                        # The dictionary for this camera already has entries for a file source, which means we have
                        # found an additional file source for this camera. We just need to add the path to this
                        # card to the card path list for the camera
                        #
                        cam['card_path_list'].append(tmpsrc.temp_source_root + dir + '\\')

    #
    #
    #
    # At this point, we have found all of the camera data paths in all backup drives and added them to the
    # appropriate camera data dictionaries.
    #

    # At this point, we have path data for all memory cards and backup drives present. For each source, we want to
    # catalog each of its files with the following information:
    #    file name
    #    time created (the time of the actual shot in the camera)
    #    path to the file
    # Each file will be in a directory on the card created by the camera. Besides knowing the path to the file, we
    # do not care which of these directories it is in, and we will sort the files by time stamp.
    #
    # Create a list of the media files from the source drives we found.  These will be in the directory DCIM\subdir,
    # where subdir is assigned by the camera.  We walk the entire card below the DCIM directory.  Note we are assuming
    # all of our camera cards and backup drives are organized with a DCIM directory with one layer of sub directories
    # containing only media files below that. Any other directories we find below the DCIM directory will be skipped.
    # We get the DCIM path from the camera profile (cam['digital_camera_image_path']) just in case we end up with a
    # camera that does things differently (not likely. smart phones even have a dcim directory for thier cameras)
    #
    for cam in get_camera_info():
        if 'card_path_list' in cam:
            for path in cam['card_path_list']:
                for dir_name, subdir_list, file_list in os.walk(path+cam['digital_camera_image_path']):
                    #
                    # for each file in file_list, combine it with dir_name\ to form the full file path, then get its
                    # time stamp, either by getting the DateTimeOriginal EXIF value (picture files) or the file
                    # creation time (video files). Put these into a tuple (file_full_path, timestamp) These are
                    # combined to create the card_file_time_list.
                    #
                    for file in file_list:
                        file_full_path = dir_name+'\\'+file
                        #
                        # skip files in directories more than one deep below DCIM, like thumbnail directories
                        # eg H:\DCIM\100NIKON\.Thumbs.
                        #
                        # 1: dir_name is the full path from the drive. Parse it using the \ as a separator.
                        # 2: get the position in the path of the DCIM directory.
                        # 3: if DCIM is in the second last position, then the last position is a valid camera directory
                        # and we will process the files in file_list. Otherwise, we will skip this directory because
                        # it is not a camera generated image directory.
                        #
                        parsed_dir = dir_name.split('\\')
                        dcim_pos=parsed_dir.index(cam['digital_camera_image_path'])
                        #
                        # We want the dcim directory to be in the second last position, so we compare list length
                        # to dcim position. Since position counts from 0, the second last position is the one
                        # that matches 2 less than the length.  E.G. list length is 4, and dcim position is 2 (third
                        # item)  If this test fails, we skip the rest of the loop.
                        #
                        if dcim_pos != len(parsed_dir)-2:
                            log_text.insert(END, 'Skipping {}\n'.format(file_full_path))
                            continue
                        #
                        # GUI...Update status label and add the file to the log
                        #
                        status_text.set('Found {}'.format(file_full_path))
                        status_label.update()
                        log_text.insert(END, 'Found {}\n'.format(file_full_path))
                        file_extension = os.path.splitext(file)[EXTENSION]
                        #
                        # determine that time stamp and add the file to the camera files_with_times list
                        #
                        if file_extension in my_camera_data.PICTURE_EXTENSIONS:
                            #
                            # This is a picture file with EXIF metadata: Open the file for binary read and get the
                            # DateTimeOriginal metadata
                            #
                            f = open(file_full_path, 'rb')
                            tags = exifread.process_file(f, details=False, stop_tag='DateTimeOriginal')
                            #
                            # create a tuple of full path file name and timestamp from the EXIF data, then add it to
                            # the camera card file list
                            #
                            if 'EXIF DateTimeOriginal' in tags:
                                cam['files_with_times'].append(
                                                               (file_full_path,
                                                                exiftime_to_file_prefix(
                                                                    str(tags['EXIF DateTimeOriginal']))))
                            else:
                                print('no exif? {}'.format(file_full_path))
                        else:
                            #
                            # File either does not have EXIF metadata, or exifread cannot process it. Get the file
                            # creation date from the containing memory card directory and format it
                            # to our timestamp prefix format. create a tuple of full path file name and this
                            # timestamp, then add it to the camera card file list
                            #
                            # Technical note: strftime format %Y means 4 digit year including century (vs %y for 2
                            # digit year), %H means hours on 24 hour clock (vs %I for 12 hour clock with %p for am/pm)
                            #
                            cam['files_with_times'].append(
                                (file_full_path, datetime.fromtimestamp
                                 (os.path.getctime(file_full_path)).strftime('%Y%m%d-%H%M%S')))
            #
            # Sort the files_with_times list on the timestamp element followed by file name, which are the two
            # fields that will make up the filename as renamed in the repository. We reverse the order because we
            # want to scan in reverse order (latest file first) later.
            #
            # technical note: we set the sort key to be a function (lambda) that returns the item we want to sort on,
            # which in this case is the timestamp followed by the file name. The key function
            # lambda element: element[TIMESTAMP]+element[FILENAME].split(sep='\\')[3]) returns a string
            # (timestamp + filename) that is used for doing the comparisons during the sort. "element" here is one of
            # tuples making up the list we are sorting...(full path file name, timestamp) and the function parses out
            # the base file name and adds it to the end of the timestamp string.
            #
            cam['files_with_times'].sort(reverse=True,
                                         key=lambda element: element[TIMESTAMP]+element[FILENAME].split(sep='\\')[3])
            #
            # GUI...update status label with total (for all cameras) number of camera card files found
            #
            status_text.set('{} Camera Card Files Found. See Log tab for list'.format(len(cam['files_with_times'])))
            status_label.update()

    return cam_cards_count


def make_today_dir():
    #
    # use new_repository_dir from each camera card dictionary to create a target directory for upcoming file copies
    #
    for cam in get_camera_info():
        if 'new_repository_dir' in cam:
            if os.path.exists(cam['new_repository_dir']):
                log_text.insert(END,
                                '\n{} repository dir\n{}\nalready exists\n'
                                .format(cam['name'], cam['new_repository_dir']))
            else:
                os.mkdir(cam['new_repository_dir'])
                log_text.insert(END,
                                '{} making repository dir {}\n'.format(cam['name'], cam['new_repository_dir']))
            log_text.yview_pickplace('end')  # Scroll log text to the bottom
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
    for cam in get_camera_info():
        if 'new_repository_dir' in cam:
            dirlist = list(sorted(os.listdir(cam['repository_base']), reverse=True))
            skip_dir = os.path.exists(cam['new_repository_dir'])
            for directory in dirlist:
                if skip_dir:
                    skip_dir = False
                    log_text.insert(END, 'Find last files: Skipping existing today directory {}\n'.format(directory))
                    continue
                filelist = os.listdir(cam['repository_base']+directory)
                cam['repository_last_dir'] = directory + '\\'
                # skip directory if it is empty
                if len(filelist) == 0:
                    log_text.insert(END, 'Find last files: Skipping empty dir {}\n'.format(directory))
                    continue
                else:
                    #
                    # newest file is the last file in the last populated directory. This assumes all of the file names
                    # start with a timestamp string, which is our naming standard.
                    #
                    cam['repository_last_file'] = sorted(filelist)[-1]
                    break
    return


def copy_and_rename():
    #
    # Copy the new files on the camera cards to the new repository directories...
    #
    # For each camera, iterate though its files_with_times list, copying each file from the memory card to the
    # camera's new_repository_dir, changing the file name to add the timestamp to the beginning of the file with '_'
    # as a separator and lower casing. EG "20180523-112822_dscn0111.jpg". The file_with_times list is in reverse order,
    # so the newest files will be copied first. To make sure the file's timestamps match the timestamp prefix, we also
    # modify the file's create, modify and access metadata to match it. Before each copy, we check see if the file is
    # newer than the last repository file, and when this fails to be the case, we break out of the loop.
    #
    notebook.select(log_page)       # open the notebook to the log page
    notebook.update()
    for cam in get_camera_info():
        #
        # If this camera is contributing files, post its name, repository base, and target directory to the log
        #
        if len(cam['files_with_times']):
            log_text.insert(END,
                            '\nCopy files for camera {}\nRepository Base:\n   {}\nNew Repository Directory: {}\n\n'
                            .format(cam['name'], cam['repository_base'], cam['today_dir']))
        #
        # Iterate over all of the files and copy the new ones to the repository, renaming along the way by
        # prepending the timestamp. Also, change the filesystem timestamps for the file to match its EXIF
        # timestamp.
        #
        copied_count = 0                                                 # initialize counter for the log
        for file_and_time in cam['files_with_times']:
            last_file_timestamp = cam['repository_last_file'][0:15]
            #
            # check if the file is newer than the last file in the existing repository. If not, we are done.
            #
            if file_and_time[TIMESTAMP] > last_file_timestamp:
                sourcepath, base_filename = os.path.split(file_and_time[FILENAME])  # get base filename
                #
                # create new target name with timestamp_
                #
                new_filename = (file_and_time[TIMESTAMP] + '_' + base_filename).lower()
                dest_path = os.path.join(cam['new_repository_dir'], new_filename)
                #
                # check if the target file in the repository already exists.  If so, skip the copy.
                #
                if os.path.exists(dest_path):
                    #
                    # Destination file already exists. Just post to the log that we are skipping the copy
                    #
                    log_text.insert(END, '{} exists - skipping\n'.format(new_filename))
                    log_text.yview_pickplace('end')  # Scroll log text to the bottom
                    log_text.update()
                    continue
                else:
                    #
                    # Destination file does not exist. Copy the file with the new name created above
                    #
                    shutil.copy2(file_and_time[FILENAME], dest_path)        # copy to repository with name update
                    change_file_times(dest_path, file_and_time[TIMESTAMP])  # update file timestamps
                    #
                    # post a line to the log. Note \u279C is the "heavy round-tipped rightwards arrow"
                    # unicode character (➜)
                    #
                    log_text.insert(END, '{} \u279C {}\n'.format(file_and_time[FILENAME], new_filename))
                    log_text.yview_pickplace('end')  # Scroll log text to the bottom
                    log_text.update()

                    copied_count += 1

        log_text.insert(END, '{} files copied for {}\n'.format(str(copied_count), cam['name']))
        log_text.yview_pickplace('end')  # Scroll log text to the bottom
        log_text.update()
    return


#
# Graphical User Interface code
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

    for cam in get_camera_info():
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
                last_file = new_file        # save old file value for use as last_file.
                #
                # Iterate through files_with_times
                #
                #
                # Parse the list element
                #
                path_tokens = full_path.split(sep='\\')
                timestamp_tokens = timestamp.split(sep='-')
                #
                # The path tokens list looks like one of these:
                #    backup drive files --> [drive, camera pattern, dcim, camera directory, file name]
                #    camera card files  --> [drive, dcim, camera directory, file name]
                #
                # new_path is the path up to and including the dcim directory
                # new_dir is the directory under the dcim directory
                #
                path_token_count = len(path_tokens)
                if path_token_count == 4:
                    new_path = path_tokens[0]+'\\'+path_tokens[1]+'\\'
                    new_dir = path_tokens[2]
                    new_file = path_tokens[3]
                elif path_token_count == 5:
                    new_path = path_tokens[0]+'\\'+path_tokens[1]+'\\'+path_tokens[2]+'\\'
                    new_dir = path_tokens[3]
                    new_file = path_tokens[4]
                else:
                    new_path = 'path error'
                    new_dir = 'dir error'
                #
                # The timestamp tokens list is just the date and the time.  We care only about the date here
                #
                new_date = timestamp_tokens[0]

                #
                # If the path, the directory and the date are the same as the previous iteration, we skip to the
                # end of the loop, creating no new summary information
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
                # the next time this test is made, then skip to the end of the loop.
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
            # finally, copy the reference to the path list into the camera's summary_info slot.
            #
            cam['summary_info'] = path_list

    return

#
# Widget Callbacks
#


def exit_button_clicked():
    #
    # exit the program
    #
    sys.exit(1)


def getcard_clicked():
    #
    # Populate the camera data structures with information about the correesponding mounted camera cards, including
    # directories and files on the cards and timestamps.
    #
    cam = get_camera_info()
    #
    # If we have not touched the camera dictionaries yet, we need to get the information from the camera memory
    # cards and populate the camera dictionaries.  Otherwise, we have already done it.  Count is the number of
    # camera cards found.  If we don't call get_cam_cards_info(), then we get the count by looking at the
    # camera dictionaries.
    #
    if not cam[0]['processed']:
        count = get_cam_cards_info()
    else:
        count = 0
        for cam in get_camera_info():
            if 'card_path_list' in cam:
                count += len(cam['card_path_list'])
    #
    # Populate the camera data structures with information about the correponding existing repository directories. A
    # side effect of this operation is identifying the latest file in each camera repository, and creating a new
    # subdirectory in the repository for today's new files.
    #
    find_repository_last_files()
    #
    # disable the button to avoid scanning the camera cards again.
    #
    get_card_info_button.config(state=DISABLED)
    #
    # enable the file copy button
    #
    copy_files_button.config(state=NORMAL)
    #
    # create the camera memory card summary
    #
    add_camcards_summary()
    #
    # put file camera card summaries on the summary list box. Format:
    #
    # Camera name 1
    #    card path 1
    #       directory1
    #          date1: first file - last file
    #          ...
    #          dateN: first file - last file
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
        for cam in get_camera_info():
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


class TempSource:
    #
    # Temp source is a directory tree with the same structure as a backup drive that can serve as an intermediate
    # location for holding media files for import from sources like smart phones, thumb drives, etc.  This class
    # maintains the state for this mechanism.
    #
    temp_source_root = None

    def set(self, root):
        self.temp_source_root = root


def setsource_clicked():
    #
    # This button raises a file selection box to allow the user to select an area on the computer to use
    # as a source for media files.
    #
    tempsource = TempSource()
    tempsource.temp_source_root=filedialog.askdirectory(title='Pick Temp Source Directory',
                                                        initialdir=get_temp_source_info()['initial_path'])
    print(tempsource.temp_source_root)


def copyfiles_clicked():
    #
    # To copy the files from the camera memory files, we create the destination directories, then copy and
    # rename the files to those directories.  When we are done, we disable the button.
    #
    make_today_dir()
    copy_and_rename()
    copy_files_button.config(state=DISABLED)
    return


def card_info_filter_changed(*args):
    #
    # Callback for option menu change. The main reason we have this is to provide a callback with the right
    # arguments, even though we don't actually use the arguments.  Otherwise, we could just call the getcard button
    # callback.
    #
    # Clear the list box
    #
    cardfiles_list_box.delete(0, END)
    #
    # run the callback for the getcard button.  That code will check the value of this menu while re-populating the
    # list box
    #
    getcard_clicked()


def make_pic_for_canvas(filename, height, width):
    #
    # This function takes a file name and a canvas height and width and creates an image
    # properly scaled and rotated to fit on a Tk canvas of those dimentions. The assumption
    # is that this file come from a camera containing the EXIF flag Image Orientation tag, but
    # if this tag is absent, the orientation part is skipped. It is assumed that this function
    # will only be passed Tk recognized image files.
    #
    if is_raw_file(filename):
        #
        # create a rawpy image object from the file
        #
        raw_image = rawpy.imread(filename)
        #
        # postprocess does processing on the raw image and puts the pixels into an array. We specify options
        # to use the while balance value specified by the camera and to not "flip" the image.  Without this,
        # the image will be rotated based on the camera orientation when the picture was shot. Because we do
        # that rotation below for both raw and jpg files, we disable this function. Half size merges each 4x4
        # pixel block into a single pixel, resulting is a lower resolution, but a smaller array good enough for
        # our preview.
        #
        raw_array = raw_image.postprocess(use_camera_wb=True, user_flip=0, half_size=True)
        #
        # create an image from the array
        #
        pic = Image.fromarray(raw_array)
    else:
        pic = Image.open(filename)

    #
    # at this point we have an openCV image either from reading a jpg file or from reading and processing
    # a raw file. We resize the image to fit a preview canvas, then we open the file an extract the EXIF tags
    # to find the camera orientation at the time of the shot. If we find it, we rotate the image to turn it
    # right side up.
    #
    pic = resizeimage.resize_contain(pic, [width, height])
    f = open(filename, 'rb')
    tags = exifread.process_file(f, details=False, stop_tag='Image Orientation')
    if 'Image Orientation' in tags:
        if 'Rotated 90 CW' in str(tags['Image Orientation']):
            pic = pic.rotate(-90)
        elif 'Rotated 180 CW' in str(tags['Image Orientation']):
            pic = pic.rotate(180)
        elif 'Rotated 270 CW' in str(tags['Image Orientation']):
            pic = pic.rotate(-270)
    #
    # Convert the image to a TK image object and return it.
    #
    return ImageTk.PhotoImage(pic)


def get_first_frame(vidfile, height, width):
    #
    # This function opens a video file, gets a frame from it, resizes the frame to fit our canvase,
    # and creates a Tk image from the result.
    #
    vidcap = cv2.VideoCapture(vidfile)
    #
    # Read a frame from the video capture object
    #
    ret, frame = vidcap.read()
    #
    # convert frame color space from the BGR coding used by OpenCV to RGB used by Tk. If we don't
    # do this, the red and blue channels will be reversed in the image
    #
    cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
    #
    # OpenCV stores the image in an array managed by python's array support module, numpy. Here we convert that array
    # to a PIL (python imaging library) image, then we resize the image to fit the canvas, then convert it to a Tk
    # image and put it on the canvas
    #
    pic = Image.fromarray(cv2image)
    #
    # resize the image to fit the canvas
    #
    pic = resizeimage.resize_contain(pic, [height, width])
    #
    # convert the image to a Tk image object and return it
    #
    return ImageTk.PhotoImage(pic)


def on_summary_select(evt):
    #
    # This is the callback function for a selection change in the memory card summary list. If the user clicks
    # on a line with file names (first and last for a given date) then this code will display a preview of each
    # file. This code parses out the file names and their extensions, searches the camera file lists for matching
    # names with full paths, then calls the appropriate function to make a still image (make_pic_for_canvas()) or
    # capture a video frame (get_first_frame()), and finally puts the results on the canvases (canvas_list[0] and [1])
    #
    # Get the widget that called this function and then get the index and value string of the selection
    #
    w = evt.widget
    index = int(w.curselection()[0])
    value = w.get(index)
    #
    # If the selected line is one with file names, parse out the file names.  We determine such lines based on
    # the format chosen (date=string: first_file - last_file), which are the only lines containing both : and -
    # Changing this format will break this code.
    #
    if ':' in value and '-' in value:
        filenames = value.split(sep=':')[1]
        first_file = filenames.split(sep='-')[0].strip()
        last_file = filenames.split(sep='-')[1].strip()
    else:
        #
        # selected line does not have file information
        #
        return
    #
    # create and initialize working list for the file paths
    #
    file_path = [None, None]
    #
    # Find the file names in the camera file lists.  We search all cameras here because the likelihood of
    # finding the file in the wrong camera is very slight.  Probably should change the code to get the correct
    # camera name, but this should rarely be a bug.
    #
    found_paths = False
    for cam in get_camera_info():
        if cam['files_with_times']:
            for file, time in cam['files_with_times']:
                if last_file in file:
                    # set path to last file
                    file_path[1] = file
                if first_file in file:
                    # set path to first file
                    file_path[0] = file
                    #
                    # because the file list we are searching is in reverse order, we know we have already
                    # found the last file and the first file when we get here, so we can break out of the
                    # both the inner and outer loops
                    #
                    found_paths = True
                    break
        if found_paths:
            break

    #
    # create instances of PreviewImages() and ImageCanvases. This is where we are going to store our preview images
    # and the canvases we are going to display them on. The PreviewImages class __init__ method clears the old value.
    # Note when this function returns, the instance will be garbage collected, but because the attribute we are using
    # is a class variable, not an instance variable, it retains its value so the canvases will have something to
    # display. Similarly, the canvases are also class variables, and are only created when the GUI is initialized,
    # so these values will never change.
    #
    previews = PreviewImages()
    can = ImageCanvases()
    #
    # We have two file paths and two canvases arranged in lists. Display first path file on first canvas and
    # second path file on second canvas. Note that the images we display on the canvas need to remain in memory
    # after this function returns, or they will disappear from the canvas. To make this happen, we store these
    # images in a class attribute, PreviewImages.img, which is a list of two images.
    #
    for i in range(0, 2):
        #
        # Get canvas width and height
        #
        width = int(can.canvases[i].cget('width'))
        height = int(can.canvases[i].cget('height'))
        #
        # make tkimage from the file and put in on the canvas
        #
        if is_picture_file(file_path[i]):
            previews.set_img(i, make_pic_for_canvas(file_path[i], height, width))
        elif is_video_file(file_path[i]):
            previews.set_img(i, get_first_frame(file_path[i], height, width))

        #
        # put the image onto the canvas. We test to make sure there is an image first. This test could fail if
        # the file is not recognized as a photo or video file.
        #
        if previews.img[i]:

            can.canvases[i].delete('all')
            can.canvases[i].create_image(width // 2, height // 2, image=previews.img[i], anchor=CENTER)

    return


class PreviewImages:
    #
    # This class holds the state of the preview images we display on image canvases. img is a class variable,
    # so it survives the garbage collection of its instances.
    #
    img = [None, None]
    #
    # clear img when and new instance is created. We want img to hold any value it is set to by and instance,
    # but we never expect more than one instance at a time, and we test the values before trying to use
    # them, so initializing to None meets those needs
    #
    def __init__(self):
        self.img[0] = None
        self.img[1] = None

    def set_img(self, idx, img):
        self.img[idx] = img

    def set_canvas(self, idx, can):
        self.canvases[idx] = can


class ImageCanvases:
    #
    # This class holds the state of the canvases on which we display preview images. canvases is a class variable,
    # so it survives the garbage collection of its instances.
    #
    canvases = [None, None]
    #
    # initialize canvases when a new instance is created. We want camvases to hold any value it is set to by an
    # instance,
    # but we never expect more than one instance at a time, and we test the values before trying to use
    # them, so initializing to None meets those needs
    #

    def set_canvas(self, idx, can):
        self.canvases[idx] = can
#
# Create the main window and set style and size
#
window = Tk()
s = ttk.Style()
s.theme_use('xpnative')
s.configure('window.TFrame', font=('Helvetica', 20))
#
# create and size the main window
#
window.title('Camera Memory Card Tool')
window.geometry("1400x600")
#
# Create a notebook to contain our information pages
#
notebook = ttk.Notebook(window)
#
# create canvases for displaying preview images. We keep these canvases in a class variable in ImageCanvases
# so we can reference it in callbacks
#
canvas_height = 500
canvas_width = 500
image_canvas = ImageCanvases()
image_canvas.set_canvas(0, Canvas(window, width=canvas_width, height=canvas_height, bg="gray"))
image_canvas.set_canvas(1, Canvas(window, width=canvas_width, height=canvas_height, bg="gray"))
#
# add the summary page frame with a listbox and scrollbar to the notebook
#
summary_page = ttk.Frame(notebook)
cardfiles_list_box = Listbox(summary_page, height=30, width=60, border=0, selectmode=SINGLE)
list_scrollbar = Scrollbar(summary_page, orient="vertical")
notebook.add(summary_page, text='Cards Summary')
#
# Set scrollbar to call the list box yview method. This method scrolls the list to a given position.
# Set the and set the yscrollcommand function of the list box to be the set command of the scrollbar. This tells
# the scrollbar where to put the top and bottom edges of the slider for accurate visual feedback.
#
list_scrollbar.config(command=cardfiles_list_box.yview)
cardfiles_list_box.config(yscrollcommand=list_scrollbar.set)
#
# Set up callback for selecting a line in the list box. We bind ListboxSelect and pass the event
# to the callback.
#
cardfiles_list_box.bind('<<ListboxSelect>>', on_summary_select)
#
# add the log page frame with a scrolled text widget to the notebook
#
log_page = ttk.Frame(notebook)
log_text = ScrolledText(log_page, width=60, font='Helvetica 8')
notebook.add(log_page, text='Log')
#
# Create a button to populate the summary page
#
get_card_info_button = Button(window, text='Get Cam Cards', command=getcard_clicked)
#
# Create a button to set a media file source on the computer
#
set_source_button = Button(window, text='Set Temp Source', command=setsource_clicked)
#
# create a menu to select summary filter mode
#
card_info_filter_var = StringVar(window)
card_info_filter_var.set("Memory Card(s): Show All Files")
card_info_filter_menu = OptionMenu(window,
                                   card_info_filter_var,
                                   'Memory Card(s): Show All Files',
                                   'Memory Card(s): Show New Files')
card_info_filter_var.trace('w', card_info_filter_changed)
#
# create a label for reporting status
#
status_text = StringVar()
status_label = Label(window, textvariable=status_text, relief=SUNKEN)
status_text.set('Status')
#
# Create a button for copying files from the camera card(s) to the repositories and
# initially disable it (will be enabled when memory card data has been analysed
#
copy_files_button = Button(window, text='Copy Files', command=copyfiles_clicked)
copy_files_button.config(state=DISABLED)
#
# Create the exit button
#
exit_button = Button(window, text='Exit', command=exit_button_clicked)
#
# Place Window widgets using grid layout
#
get_card_info_button.grid(row=0, column=0)
set_source_button.grid(row=0, column=1)
copy_files_button.grid(row=0, column=2)
notebook.grid(row=1, column=0, columnspan=3)
card_info_filter_menu.grid(row=3, column=0, columnspan=2, sticky=W)
exit_button.grid(row=3, column=2, sticky=E)
status_label.grid(row=2, column=0, columnspan=3, sticky=E+W)
#
# Place the card summary list box and its scrollbar in its frame using grid layout
#
cardfiles_list_box.grid(column=0, row=0)
list_scrollbar.grid(column=1, row=0, sticky=N+S)
#
# Place the log text box to fill its notebook page
#
log_text.grid(column=0, row=0, sticky=E+W+N+S)
#
# place canvases
#
image_canvas.canvases[0].grid(column=3, row=1)
image_canvas.canvases[1].grid(column=4, row=1)
#
# start gui main loop
#
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
