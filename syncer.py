#!/usr/local/bin/python3
#
# TODO Intro comments here.
#

# imports
# =======

import fcntl
from optparse import OptionParser
import os
import sys
import termios

# Internal names start with an underscore.


# globals
# =======

_verbose = False  # TODO Remove if unused.

# The string used in .syncer to denote name-path pairs.
_repos_header = 'name-path pairs'

# _repos = [[repoName, repoPath]]
_repos = []

# The string used in .syncer to denote file-file pairs.
_pairs_header = 'file-file pairs'

# _pairs = [[path1, path2]]
_pairs = []


# internal functions
# ==================

def _handleArgs(args):
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

def _loadConfig():
  pass  # TODO

# Save the current set of tracked files; while running, this
# data is kept in _repos and _pairs.
def _saveConfig():
  global _repos, _pairs
  # TEMP
  if True:
    _repos.append(['name1', 'path1'])
    _repos.append(['name2', 'path2'])
    _pairs.append(['path3', 'path4'])
    _pairs.append(['path5', 'path6'])
  configPath = os.path.expanduser('~/.syncer')
  with open(configPath, 'w') as f:
    if _repos:
      f.write('%s:\n' % _repos_header)
      for repo in _repos: f.write('  %s %s\n' % tuple(repo))
    if _pairs:
      f.write('%s:\n' % _pairs_header)
      for pair in _pairs: f.write('  %s %s\n' % tuple(pair))

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


# main
# ====

if __name__ ==  "__main__":
  try:
    _handleArgs(sys.argv)
  except KeyboardInterrupt:
    print("\nCheerio!")
    exit(1)
  _saveConfig()
