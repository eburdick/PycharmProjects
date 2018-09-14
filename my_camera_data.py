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
     'digital_camera_image_path': 'DCIM\\'},  # camera card directory containing media files
    {'name': 'Nikon Coolpix B700',                         # B700 camera
     'card_pattern': re.compile('.*b700', re.IGNORECASE),  # pattern: any characters followed by "b700"
     'repository_base': 'V:\\Camera-buf\\nikon-coolpix-b700\\renamed copies of flash memory\\',
     'digital_camera_image_path': 'DCIM\\'}]

#
# list of file extensions for files used by these cameras.
#
PICTURE_EXTENSIONS = ['.jpg', '.JPG', '.nef', '.NEF', '.nrw', '.NRW', '.tif', '.TIF']
RAW_EXTENSIONS = ['.NEF', '.nef', '.nrw', '.NRW']
VIDEO_EXTENSIONS = ['.MP4', '.mp4', '.MOV', '.mov']