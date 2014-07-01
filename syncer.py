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

_configPath = os.path.expanduser('~/.syncer')

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
             %s track <repo-name>      # Track the current dir with the given repo name (a name may be, e.g., a github url).
             %s track <file1> <file2>  # Track the given file pair.
             %s check                  # Check all known repo-name/dir and file/file pairs for differences."""
  usage = usage % (myName, myName, myName)
  parser = OptionParser(usage=usage)
  (options, args) = parser.parse_args(args)
  if len(args) <= 1:
    parser.print_help()
    return
  action = args[1]
  okActions = ['track', 'check']
  if action in okActions: _loadConfig()
  if   action == 'track':
    _track(args[2:])
  elif action == 'check':
    _check(args[2:])
  else:
    print('Unrecognized action: %s.' % action)
    parser.print_help()

def _track(actionArgs):
  global _repos, _pairs
  if len(actionArgs) < 1 or len(actionArgs) > 2:
    print('Expected one or two parameters as items to track.')
    exit(2)
  if len(actionArgs) == 1:  # Track a repo/path pair.
    _repos.append([actionArgs[0], os.getcwd()])
    print('Started tracking the repo and dir:\n%s\n%s' % tuple(_repos[-1]))
  if len(actionArgs) == 2:  # Track a file/file pair.
    # TODO Check that files exist and convert to absolute paths.
    _pairs.append(actionArgs)
    print('Started tracking the files:\n%s\n%s' % tuple(_pairs[-1]))

def _check(actionArgs):
  global _repos, _pairs
  if len(actionArgs) > 0:
    print('Unexpected arguments after "check": %s' % ' '.join(actionArgs))
    exit(2)
  # TODO Compare files.

def _loadConfig():
  global _repos, _pairs
  if not os.path.isfile(_configPath): return  # First run; empty lists are ok.
  addingTo = None
  with open(_configPath, 'r') as f:
    for line in f:
      if len(line.strip()) == 0: continue
      if line.startswith(_repos_header):
        addingTo = _repos
      elif line.startswith(_pairs_header):
        addingTo = _pairs
      elif addingTo is not None:
        addingTo.append(line.strip().split(' '))

# Save the current set of tracked files; while running, this
# data is kept in _repos and _pairs.
def _saveConfig():
  global _repos, _pairs
  with open(_configPath, 'w') as f:
    if _repos:
      f.write('%s:\n' % _repos_header)
      for repo in _repos: f.write('  %s %s\n' % tuple(repo))
    if _pairs:
      f.write('%s:\n' % _pairs_header)
      for pair in _pairs: f.write('  %s %s\n' % tuple(pair))


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


# main
# ====

if __name__ ==  "__main__":
  try:
    _handleArgs(sys.argv)
  except KeyboardInterrupt:
    print("\nCheerio!")
    exit(1)
  _saveConfig()
