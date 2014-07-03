#!/usr/local/bin/python3
#
# TODO Intro comments here.
#

# imports
# =======

import difflib
import fcntl
import filecmp
from optparse import OptionParser
import os
import os.path
import pprint
import re
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

# For accumulating differences.
# {homePath: set(copyPaths)}
_diffsByHomePath = {}

# For displaying minimally identifying strings for files.
# {basename: set(homePaths)}
# File/file pairs read from this, but won't add to it.
_pathsByBasename = {}


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
    exit(2)
  action = args[1]
  if   action == 'track':
    _loadConfig()
    _track(args[2:])
  elif action == 'check':
    _loadConfig()
    _check(args[2:])
  else:
    print('Unrecognized action: %s.' % action)
    parser.print_help()
    exit(2)

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
  global _repos, _pairs, _testReminder
  if len(actionArgs) > 0:
    print('Unexpected arguments after "check": %s' % ' '.join(actionArgs))
    exit(2)
  for name, root in _repos:
    for path, dirs, files in os.walk(root):
      for filename in files:
        filePath = os.path.join(path, filename)
        homeInfo = _check_for_home_info(filePath)
        if homeInfo is None:    continue
        if homeInfo[0] == name: continue
        homeFilePath = _findFilePath(homeInfo, filePath)
        if homeFilePath is None: continue  # An error is already printed by _findFilePath.
        _compareFullPaths(homeFilePath, filePath)
  for path1, path2 in _pairs:
    _compareFullPaths(path1, path2, ignoreLine3=True)

  # Turn this on if useful for debugging.
  if False:
    print('Comparisons are done in _check.')
    print('_diffsByHomePath:')
    pprint.pprint(_diffsByHomePath)
    print('_pathsByBasename:')
    pprint.pprint(_pathsByBasename)

  homePaths = list(_diffsByHomePath.keys())
  _showDiffsInOrder(homePaths)
  pathIndex = _askUserForDiffIndex()
  chosenPaths = [homePaths[pathIndex]] if pathIndex != -1 else homePaths
  for homePath in chosenPaths: _letUserHandleDiff(homePath)
  _testReminder = _getTestReminder()

# Shows something like the following for each given homePath:
#   [1] <basename> [in repo name if not unique]
#         uniq_subpath:basename > uniq_subpath:basename
def _showDiffsInOrder(homePaths):
  if len(homePaths) == 0:
    print('No differences found.')
    exit(0)
  print('Differences found:')
  for i, homePath in enumerate(homePaths):
    prefix = '  [%d] ' % (i + 1) if i < 9 else '  [ ] '
    base = os.path.basename(homePath)
    suffix = '' if len(_pathsByBasename[base]) == 1 else (' in ' + homePath)
    print('\n' + prefix + base + suffix)
    for diffPath in _diffsByHomePath[homePath]:
      uniq1, uniq2 = _getUniqSubpaths(homePath, diffPath)
      cmpStr = _comparePathsByTime(homePath, diffPath)
      print('        %8s:%10s%s%8s:%10s' % (uniq1, base, cmpStr, uniq2, base))
  print('')  # End-of-section newline.

# Removes the common prefix and suffix from the given pair.
# In other words, given strings of the form ABC, ADC, this returns B, D.
def _getUniqSubpaths(path1, path2):
  return '<uniq1>', '<uniq2>'  # TODO

# Returns a comparison result string based on the files' timestamps.
# Return values are '<-newer', 'newer->' or '  !=   ' (all 7 chars long).
def _comparePathsByTime(path1, path2):
  return '  !=   '  # TODO

# Present the user with an action prompt and receive their input.
def _askUserForDiffIndex():
  return -1  # TODO

# Present a specific diff and let the user respond to it.
def _letUserHandleDiff(homePath):
  pass  # TODO

# Return a string to remind the user what they need to test based
# on their latest check action.
def _getTestReminder():
  return ''  # TODO

# Checks for a recognized repo name on line 3.
# Returns [homeDir, homeSubdir] if found; homeSubdir may be None;
# return None if no repo name is recognized.
def _check_for_home_info(filePath):
  global _repos
  with open(filePath, 'r') as f:
    try:
      fileStart = f.read(4096)
    except:  # This can be caused by trying to read a binary file as if it were utf-8.
      return None
    startLines = fileStart.split('\n')
    if len(startLines) < 3: return None
    line3 = startLines[2]
    for name, root in _repos:
      regex = r'(%s)(?: in (\S+))?' % name
      m = re.search(regex, line3)
      if m is None: continue
      return [m.group(1), m.group(2)]

# Takes a [homeDir, homeSubdir] pair as returned from _check_for_home_info,
# and resolves a file path for the home version. Emits a warning if
# multiple files match the given homeInfo.
def _findFilePath(homeInfo, filePath):
  global _repos
  for name, root in _repos:
    if homeInfo[0] == name: homeRoot = root
  base = os.path.basename(filePath)
  if homeInfo[1]:
    homePath = os.path.join(homeRoot, homeInfo[1], base)
    if not os.path.isfile(homePath):
      print('Error: %s pointed to home version %s, but it doesn\'t exist.' % (filePath, homePath))
      return None
    return homePath
  # Handle the case that no subdir was given; we must walk the dir to find it.
  candidate = None
  for path, dirs, files in os.walk(homeRoot):
    if base not in files: continue
    homeFilePath = os.path.join(path, base)
    if candidate:
      fmt = 'Warning: found multiple possible home paths for %s. First two matches are:\n%s\n%s'
      print(fmt % (filePath, candidate, homeFilePath))
    candidate = homeFilePath
  return candidate

# Internally compares the given files.
# The results are stored in _diffsByHomePath and _pathsByBasename.
# If one path is a homePath, this expects that as the first argument.
def _compareFullPaths(path1, path2, ignoreLine3=False):
  # Turn this on if useful for debugging.
  if False: print('_compareFullPaths(%s, %s)' % (path1, path2))
  if _filesAreSame(path1, path2, ignoreLine3): return
  _diffsByHomePath.setdefault(path1, set()).add(path2)
  base = os.path.basename(path1)
  _pathsByBasename.setdefault(base, set()).add(path1)

def _filesAreSame(path1, path2, ignoreLine3=False):
  if not ignoreLine3: return filecmp.cmp(path1, path2)
  # We need to do more work to ignore line 3.
  lines = [None, None]
  paths = [path1, path2]
  for i in [0, 1]:
    lines[i] = _linesOfFile(paths[i])
    lines[i] = lines[i][:2] + lines[i][3:]  # Exclude line 3 (item [2] in a 0-indexed list).
  return lines[0] == lines[1]

def _linesOfFile(path):
  with open(path, 'r') as f:
    lines = f.readlines()
  return lines

def _loadConfig():
  # TODO Load _testReminder
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
  # TODO Save _testReminder
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
