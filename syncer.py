#!/usr/local/bin/python3
#
# TODO Intro comments here.
#

# imports
# =======

import fcntl
from optparse import OptionParser
import sys
import termios

# globals
# =======

# Globals start with an underscore.

_verbose = False  # TODO Remove if unused.

# public functions
# ================

def handleArgs(args):
  global _verbose
  myName = sys.argv[0].split('/')[-1]
  usage = """
             %s track <url>            # Track the current directory paired with the given url (for a home repo).
             %s track <file1> <file2>  # Track the given file pair.
             %s check                  # Check all known url/dir and file/file pairs for differences."""
  usage = usage % (myName, myName, myName)
  parser = OptionParser(usage=usage)
  (options, args) = parser.parse_args(args)
  if False and len(args) <= 1:  # TODO Probably just show help in this case.
    #runInteractive(parser)
    pass

# input functions
# ===============

def _getch():
  fd = sys.stdin.fileno()

  oldterm = termios.tcgetattr(fd)
  newattr = termios.tcgetattr(fd)
  newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
  termios.tcsetattr(fd, termios.TCSANOW, newattr)

  oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)
  fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)

  try:        
    while 1:            
      try:
        c = sys.stdin.read(1)
        break
      except IOError: pass
  finally:
    termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
    fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)
  return c

# Main
# ====

if __name__ ==  "__main__":
  try:
    handleArgs(sys.argv)
  except KeyboardInterrupt:
    print("\nCheerio!")
    exit(1)
  #_saveConfig()  # TODO
