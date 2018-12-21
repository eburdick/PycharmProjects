#!/usr/bin/python3

#
# The motivation for this program is to find gaps in a group of camera file names found in a group of directories,
# with the goal of catching missing files, normally missing because they didn't get copied from the camera. This
# program is assumed to run in the context of my storage strategy as defined in the camera file copy program
# update_camera_dir_gui.py, which imports the module my_camera_data.py, where the camera file repositories are defined.
# This program will import that same module.
#
# The file names are in the format "yyyymmdd-hhmmss_xxxxnnnn.*", yyyymmdd-hhmmss is the timestamp and nnnn
# is the number of the file created by the camera. "xxxx" depends on the camera, e.g. "dsc_" for Nikon d500, "dscn"
# for Nikon Coolpix b700, "img_" for Canon point and shoot cameras, and "dsc0" for Sony DSC-HX400V (actually the sony
# has a five digit camera file number, of which the "0" in "dsc0" is the first digit. We should deal with this even
# though we don't own any cameras in that category.
#
# In general, for a single camera, listing these files in the order of file name and looking for missing file names is
# a good first cut. Based on software processing that renames these files, the timestamp prefix in the file name
# should match the EXIF CreateDate. The files are stored in a series of directories named according the the date they
# copied from the camera "yyyy-mm-dd"
#
# GUI features we would like:
#
#   - Select a sequence of directories to check from a given camera's repository.
#   - Display the highest and lowest file number in each of these directories, along with the last number in the
#     previous directory and the first number in the next directory, if any.
#   - Note files that are out of time sequence, and allow moving of these to the appropriate directory.  This can
#     happen when a file is edited and saved in the camera some time after file was created.
#   - Have a way of searching the repository directories for missing files
#   - List files in order of timestamp or in the order of file number with our of sequence files highlighted
#   - Do the same analysis on camera cards, including the ability to do multiple camera cards from the same camera,
#     showing the card volume with the rest of the information.
#   - File preview so we can look at the picture or frame shot of a file to help identify it.
#
# Note pretty much all of these features have analogs in update_camera_dir_gui.py.
#
# Implementation notes:
#
# The basic approach is to create a dictionary with the keys being the file numbers and the values being tuples of
# tuples of path names, one name for each file type found, typically only JPG files, raw files, or both.  If a file
# group (path\foo.jpg, path\foo.nef) is found in only one directory, the top tuple will only have one member.
# {...'2263': {{'path\20160927_dsc_2263.jpg', 'path\20160927_dsc_2263.nef'))...} If duplicates are found, there will be
# more, {...'2263': (('path1\20160927_dsc_2263.jpg', 'path1\20160927_dsc_2263.nef'),('path2\20160927_dsc_2263.jpg'))...}
# For display, we will copy this dictionary to a list of tuples:
# [...('2263', (('path1\20160927_dsc_2263.jpg', 'path1\20160927_dsc_2263.nef'),('path2\20160927_dsc_2263.jpg')))...],
# which we can sort to the order we want to display it.
#
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
#
# import site specific camera information
#
import my_camera_data

print(my_camera_data.camera_info)


