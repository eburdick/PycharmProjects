#
# This program scans a camera files directory and summarizes the starting and ending files for each camera download
# directory. The file names are in the format "yyyymmdd-hhmmss_xxxxnnnn.*", yyyymmdd-hhmmss is the timestamp and nnnn
# is the number of the file created by the camera. "xxx" depends on the camera, e.g. "dsc_" for Nikon d500, "dscn"
# for Nikon Coolpix b700, "img_" for Canon point and shoot cameras, and "dsc0" for Sony DSC-HX400V (actually the sony
# has a five digit camera file number we may need to deal with, but my camera files are all Nikons or Canons.
#
# In general, for a single camera, listing these files in the order of file name and looking for missing file names is
# a good first cut. Based on software processing that renames these files, the timestamp prefix in the file name
# should match the EXIF CreateDate. The files are stored in a series of directories named according the the date they
# copied from the camera "yyyy-mm-dd"
#

#
# Set base directory
#
base_dir = "V:\\Camera-buf\\nikon-d500\\renamed copies of flash memory"

#
# get list of subdirectories
#

#
# for each subdirectory, get a list of its files. For each file, parse its name into timestamp, camera file number, and
# file extension.
#

#
# go through each subdirectory in order examining file names to find gaps as follows:
# 1: Check if the camera file number is exactly one less than the following file.
# extension.
#