import re
#
# starting camera and memory card information for our cameras...
#
# This takes the form of a list of dictionaries, one list element for each camera. Each dictionary contains
#    'name' The name of the camera
#    'card_pattern' A regular expression pattern that matches the volume label of that camera's memory card(s)
#    'repository_base' The path to the top of that camera's directory tree on the computer
#
# note this is the starting form of these dictionaries.  More will be added if we find memory cards associated
# with these cameras as follows:
#    'processed': Initialized to False and set to True when this dictionary is processed in any way
#    'files_with_times': Initialized as an empty list. Records the media files on the memory cards for this cameraa
#                        and their creation timestamps
#    'card_path_list': a list of paths to memory cards for this camera eg ['H:\','J:\']
#    'new_repository_dir': path to directory for new files named from today's date, eg
#                    'V:\Camera-buf\nikon-d500\renamed copies of flash memory\2018-07-27'
camera_info = [
    {'name': 'Nikon D500',                                 # D500 camera
     'card_pattern': re.compile('.*d500', re.IGNORECASE),  # pattern: any characters followed by "d500"
     'repository_base': 'V:\\Camera-buf\\nikon-d500\\renamed copies of flash memory\\',
     'digital_camera_image_path': 'DCIM'},  # camera card directory containing media files
    {'name': 'Nikon Coolpix B700',                         # B700 camera
     'card_pattern': re.compile('.*b700', re.IGNORECASE),  # pattern: any characters followed by "b700"
     'repository_base': 'V:\\Camera-buf\\nikon-coolpix-b700\\renamed copies of flash memory\\',
     'digital_camera_image_path': 'DCIM'}]
#
# starting backup drive info.  This is for drives that camera information is backed up to while traveling.
# The assumption is that the drive will have a label like "travel_drive" and a directory for each camera at the
# top level, so if the drive mounted, for example, as T:, then the data for two cameras might be in
# T:\d500\dcim\directories... and T:\b700\dcim\directories...
#
# This structure is a dictionary with keys 'card_pattern' and 'cameras'
# 'card_pattern' is a compiled regular expression to match the volume label of the backup drive
# 'cameras' is a list of tuples, each with a camera name that matches one of the camera_info names above and a
# compiled regular expression to match a directory for the corrsponding camera. It is assumed that there will be a
# DCIM directory below each of these.
#
backup_drive_info = {'drive_pattern': re.compile('.*travel', re.IGNORECASE),
     'cameras': [['Nikon D500', re.compile('.*d500', re.IGNORECASE)],
                ['Nikon Coolpix B700', re.compile('.*b700', re.IGNORECASE)]]}
#
# Data structure to enable accessing files to import as a convenience, say for
# pictures and videos from a friend's camera or a smart phone.
# The overall program is for reading and managing files from a known set of cameras with an existing set of
# repositories. Importing once or twice from a different device does not follow this paradigm unless we have a
# mechanism for creating repositories on the fly. In my camera_buf directory I have a subdirectory called other-pictures
# where I put pictures from guest cameras and other devices like phones. Most of the time, with conventional digital
# cameras, I have been doing the same kind of file renaming I do with my own cameras, but not all picture files in
# there have exif time data, and smart phone pictures have a variety of file formats, most of which have timestamp
# components already. To make this feature useful, we want...
#   - A GUI component to select the source. This might be a phone plugged into the computer, a camera card, a camera
#     plugged into the computer, a directory containing downloaded pictures, etc. For camera cards, we want to be able
#     to extract from directories under dcim, but we also want to just pick a directory full of picture files.
#   - I we want to pick and choose media files from an incoming source, there is functionality in the OS file manager
#     for this, so the method of choice will be to copy the desired file to a temporary directory and use that as a
#     source.
#   - A GUI component to specify a new destination directory under a base like my current V:\camera-buf\other pictures\
#   - Some renaming options to make sure the timestamp ends up at the beginning of the file name to match the standard
#     set by our standard repositories.  The simplest thing is to just append it no matter what the picture files look
#     like, even if the time stamp is duplicated.
#     - Many times, guests have their camera clocks set wrong, so a way to correct this on the fly would be useful
#     - If the files do not have exif data, having an alternate way to get timestamp data would be good, if possible.
#
misc_source_info = {'input_start': '', 'input_path': '', 'output_path': '',
                    'repository_base': 'V:\\Camera-buf\\Other Pictures'}

#
# list of file extensions for files used by these cameras.
#
PICTURE_EXTENSIONS = ['.jpg', '.JPG', '.nef', '.NEF', '.nrw', '.NRW', '.tif', '.TIF']
RAW_EXTENSIONS = ['.NEF', '.nef', '.nrw', '.NRW']
VIDEO_EXTENSIONS = ['.MP4', '.mp4', '.MOV', '.mov']