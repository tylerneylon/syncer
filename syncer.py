#!/usr/local/bin/python3
#
# TODO Intro comments here.
#

# Future TODO Items:
#  * In _show_diffs_in_order, minimize the column widths based on string sizes.
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
import shutil
import sys


# globals
# =======

# Internal names start with an underscore.

_verbose = False  # TODO Remove if unused.

_config_path = os.path.expanduser('~/.syncer')

# The string used in .syncer to denote name-path pairs.
_repos_header = 'name-path pairs'

# _repos = [[repo_name, repo_path]]
_repos = []

# The string used in .syncer to denote file-file pairs.
_pairs_header = 'file-file pairs'

# _pairs = [[path1, path2]]
_pairs = []

# For accumulating differences.
# {home_path: set(copy_paths)}
_diffs_by_home_path = {}

# For displaying minimally identifying strings for files.
# {basename: set(home_paths)}
# File/file pairs read from this, but won't add to it.
# TODO Check accuracy of the above comment.
_paths_by_basename = {}

# The following are all designed to be the same length when printed.
# They'll be nicely aligned as long as the basename is <= 20 chars.

_basename_width = 20
#                                 1         2
#                1234567 12345678901234567890 1234567
_horiz_break =   '------------------------------------'
_diff_header = '\nvvvvvvv %20s vvvvvvv'
_diff_footer = '\n^^^^^^^ %20s ^^^^^^^\n'
#                1234567      1234567

_changed_paths_header = 'recently changed paths'
_changed_paths = []


# internal functions
# ==================

def _handle_args(args):
  global _verbose
  my_name = sys.argv[0].split('/')[-1]
  usage = """
             %s track <repo-name>      # Track the current dir with the given repo name (a name may be, e.g., a github url).
             %s track <file1> <file2>  # Track the given file pair.
             %s check                  # Check all known repo-name/dir and file/file pairs for differences."""
  usage = usage % (my_name, my_name, my_name)
  parser = OptionParser(usage=usage)
  (options, args) = parser.parse_args(args)
  if len(args) <= 1:
    parser.print_help()
    exit(2)
  action = args[1]
  if   action == 'track':
    _load_config()
    _track(args[2:])
  elif action == 'check':
    _load_config()
    _check(args[2:])
  else:
    print('Unrecognized action: %s.' % action)
    parser.print_help()
    exit(2)

def _track(action_args):
  global _repos, _pairs
  if len(action_args) < 1 or len(action_args) > 2:
    print('Expected one or two parameters as items to track.')
    exit(2)
  if len(action_args) == 1:  # Track a repo/path pair.
    _repos.append([action_args[0], os.getcwd()])
    print('Started tracking the repo and dir:\n%s\n%s' % tuple(_repos[-1]))
  if len(action_args) == 2:  # Track a file/file pair.
    # TODO Check that files exist and convert to absolute paths.
    _pairs.append(action_args)
    print('Started tracking the files:\n%s\n%s' % tuple(_pairs[-1]))

def _check(action_args):
  global _repos, _pairs, _changed_paths
  if len(action_args) > 0:
    print('Unexpected arguments after "check": %s' % ' '.join(action_args))
    exit(2)
  print('Checking for differences.')
  for name, root in _repos:
    for path, dirs, files in os.walk(root):
      for filename in files:
        filepath = os.path.join(path, filename)
        home_info = _check_for_home_info(filepath)
        if home_info is None:    continue
        if home_info[0] == name: continue
        home_file_path = _find_file_path(home_info, filepath)
        if home_file_path is None: continue  # An error is already printed by _find_file_path.
        _compare_full_paths(home_file_path, filepath)
  for path1, path2 in _pairs:
    _compare_full_paths(path1, path2, ignore_line_3=True)

  # Turn this on if useful for debugging.
  if False:
    print('Comparisons are done in _check.')
    print('_diffs_by_home_path:')
    pprint.pprint(_diffs_by_home_path)
    print('_paths_by_basename:')
    pprint.pprint(_paths_by_basename)

  home_paths = list(_diffs_by_home_path.keys())
  _show_diffs_in_order(home_paths)
  path_index = _ask_user_for_diff_index(home_paths)
  # If we get this far, then we're committed to the check and can reset _changed_paths.
  _changed_paths = []
  chosen_paths = [home_paths[path_index]] if path_index != -1 else home_paths
  for home_path in chosen_paths: _show_and_let_user_act_on_diff(home_path)
  _show_test_reminder_if_needed()

def _show_test_reminder_if_needed():
  global _changed_paths
  if _changed_paths:
    print('The following paths have been changed; testing is recommended!')
    for path in _changed_paths: print(path)

# Shows something like the following for each given home_path:
#   [1] <basename> [in repo name if not unique]
#         uniq_subpath:basename > uniq_subpath:basename
def _show_diffs_in_order(home_paths):
  if len(home_paths) == 0:
    print('No differences found.')
    exit(0)
  print('Differences found:')
  # Find column widths.
  uniq1_max, uniq2_max, base_max = 0, 0, 0
  for home_path in home_paths:
    base = os.path.basename(home_path)
    base_max = max(len(base), base_max)
    for diff_path in _diffs_by_home_path[home_path]:
      uniq1, uniq2 = _get_uniq_subpaths(home_path, diff_path)
      uniq1_max = max(len(uniq1), uniq1_max)
      uniq2_max = max(len(uniq2), uniq2_max)
  # fmt will end up as something like '         %20s: %10s %s %15s: %10s'.
  fmt = '%7s %%%ds: %%%ds %%s %%%ds: %%%ds' % ('', uniq1_max, base_max, uniq2_max, base_max)
  for i, home_path in enumerate(home_paths):
    prefix = '  [%d] ' % (i + 1) if i < 9 else '  [ ] '
    base = os.path.basename(home_path)
    suffix = '' if len(_paths_by_basename[base]) == 1 else (' in ' + home_path)
    print('\n' + prefix + base + suffix)
    for diff_path in _diffs_by_home_path[home_path]:
      uniq1, uniq2 = _get_uniq_subpaths(home_path, diff_path)
      cmp_str = _compare_paths_by_time(home_path, diff_path).center(13)
      print(fmt % (uniq1, base, cmp_str, uniq2, base))
  print('')  # End-of-section newline.

# Removes the common prefix and suffix from the given pair.
# Expects the paths to be unequal.
# In other words, given strings of the form ABC, ADC, this returns B, D.
def _get_uniq_subpaths(path1, path2):
  dirs1 = path1.split(os.sep)
  dirs2 = path2.split(os.sep)
  pre_idx = 0
  post_idx = -1
  while dirs1[pre_idx]  == dirs2[pre_idx] : pre_idx += 1
  while dirs1[post_idx] == dirs2[post_idx]: post_idx -= 1
  uniq1 = os.path.join(*dirs1[pre_idx:post_idx + 1])
  uniq2 = os.path.join(*dirs2[pre_idx:post_idx + 1])
  return uniq1, uniq2

# Returns a comparison result string based on the files' timestamps.
# Return values are '<-newer  ', '  newer->' or '!='.
def _compare_paths_by_time(path1, path2):
  t1 = os.path.getmtime(path1)
  t2 = os.path.getmtime(path2)
  if t1 < t2: return '  newer->'
  if t1 > t2: return '<-newer  '
  return '!='

# Present the user with an action prompt and receive their input.
def _ask_user_for_diff_index(home_paths):
  print(_horiz_break)
  num_paths = min(len(home_paths), 9)
  ok_chars = ['a'] + list(map(str, range(1, num_paths + 1)))
  one_file_choices = '1' if num_paths == 1 else '1-%d' % num_paths
  print('Actions: [%s] handle a file; handle [a]ll files.' % one_file_choices)
  print('What would you like to do?')
  c = _getch()
  while c not in ok_chars:
    print('Please press one of the keys [' + ''.join(ok_chars) + ']')
    c = _getch()
  # We return either a 0-based index of the path, or -1 for the 'all' choice.
  return ok_chars.index(c) - 1

# Present a specific diff and let the user respond to it.
def _show_and_let_user_act_on_diff(home_path):
  base = os.path.basename(home_path)
  print(_diff_header % ('start ' + base).center(_basename_width))
  for diff_path in _diffs_by_home_path[home_path]:
    home_is_older = (os.path.getmtime(home_path) < os.path.getmtime(diff_path))
    oldpath, newpath = (home_path, diff_path) if home_is_older else (diff_path, home_path)

    diff_strs = []
    def show_and_save(s, end='\n'):
      print(s, end=end)
      diff_strs.append(s + end)

    show_and_save('')
    show_and_save('Diff between:')
    show_and_save('older: ' + oldpath)
    show_and_save('newer: ' + newpath)
    show_and_save('')

    short1, short2 = _short_names(oldpath, newpath)
    diff = difflib.unified_diff(
        _file_lines(oldpath), _file_lines(newpath),
        fromfile=short1, tofile=short2)
    for line in diff: show_and_save(line, end='')
    _let_user_act_on_diff(newpath, oldpath, ''.join(diff_strs))
  print(_diff_footer % ('end ' + base).center(_basename_width))

def _let_user_act_on_diff(newpath, oldpath, diff):
  global _changed_paths
  print(_horiz_break)
  new_short, old_short = _short_names(newpath, oldpath)
  print('Actions: [c]opy %s to %s; [w]rite diff file and quit.' % (new_short, old_short))
  print('What would you like to do?')
  ok_chars = ['c', 'w']
  c = _getch()
  while c not in ok_chars:
    print('Please press one of the keys [' + ''.join(ok_chars) + ']')
    c = _getch()
  if c == 'c':
    shutil.copy2(newpath, oldpath)  # Copy newpath to oldpath; preserve metadata.
    _changed_paths.append(oldpath)
    print('Copied')
  if c == 'w':
    base = os.path.basename(newpath).replace('.', '_')
    fname = '%s_diff.txt' % base
    offset = 1
    while os.path.isfile(fname):
      offset += 1  # Purposefully have the next one called 'v2'.
      fname = '%s_diff_v%d.txt' % (base, offset)
    with open(fname, 'w') as f:
      f.write(diff)
    print('Diff saved in %s' % fname)
    if _changed_paths: print('')  # Visually distinguish the test reminder below.
    _show_test_reminder_if_needed()
    _save_config()
    exit(0)

def _file_lines(filename):
  with open(filename, 'r') as f:
    return f.readlines()

# Expects paths to be different but to have the same basename.
def _short_names(path1, path2):
  uniq1, uniq2 = _get_uniq_subpaths(path1, path2)
  base = os.path.basename(path1)
  return uniq1 + ':' + base, uniq2 + ':' + base

# Checks for a recognized repo name on line 3.
# Returns [home_dir, home_subdir] if found; home_subdir may be None;
# return None if no repo name is recognized.
def _check_for_home_info(filepath):
  global _repos
  with open(filepath, 'r') as f:
    try:
      file_start = f.read(4096)
    except:  # This can be caused by trying to read a binary file as if it were utf-8.
      return None
    start_lines = file_start.split('\n')
    if len(start_lines) < 3: return None
    line3 = start_lines[2]
    for name, root in _repos:
      regex = r'(%s)(?: in (\S+))?' % name
      m = re.search(regex, line3)
      if m is None: continue
      return [m.group(1), m.group(2)]

# Takes a [home_dir, home_subdir] pair as returned from _check_for_home_info,
# and resolves a file path for the home version. Emits a warning if
# multiple files match the given home_info.
def _find_file_path(home_info, filepath):
  global _repos
  for name, root in _repos:
    if home_info[0] == name: home_root = root
  base = os.path.basename(filepath)
  if home_info[1]:
    home_path = os.path.join(home_root, home_info[1], base)
    if not os.path.isfile(home_path):
      print('Error: %s pointed to home version %s, but it doesn\'t exist.' % (filepath, home_path))
      return None
    return home_path
  # Handle the case that no subdir was given; we must walk the dir to find it.
  candidate = None
  for path, dirs, files in os.walk(home_root):
    if base not in files: continue
    home_file_path = os.path.join(path, base)
    if candidate:
      fmt = 'Warning: found multiple possible home paths for %s. First two matches are:\n%s\n%s'
      print(fmt % (filepath, candidate, home_file_path))
    candidate = home_file_path
  return candidate

# Internally compares the given files.
# The results are stored in _diffs_by_home_path and _paths_by_basename.
# If one path is a home_path, this expects that as the first argument.
def _compare_full_paths(path1, path2, ignore_line_3=False):
  # Turn this on if useful for debugging.
  if False: print('_compare_full_paths(%s, %s)' % (path1, path2))
  if _files_are_same(path1, path2, ignore_line_3): return
  _diffs_by_home_path.setdefault(path1, set()).add(path2)
  base = os.path.basename(path1)
  _paths_by_basename.setdefault(base, set()).add(path1)

def _files_are_same(path1, path2, ignore_line_3=False):
  if not ignore_line_3: return filecmp.cmp(path1, path2)
  # We need to do more work to ignore line 3.
  lines = [None, None]
  paths = [path1, path2]
  for i in [0, 1]:
    lines[i] = _lines_of_file(paths[i])
    lines[i] = lines[i][:2] + lines[i][3:]  # Exclude line 3 (item [2] in a 0-indexed list).
  return lines[0] == lines[1]

def _lines_of_file(path):
  with open(path, 'r') as f:
    lines = f.readlines()
  return lines

def _load_config():
  global _repos, _pairs, _changed_paths
  if not os.path.isfile(_config_path): return  # First run; empty lists are ok.
  adding_to = None
  with open(_config_path, 'r') as f:
    for line in f:
      if len(line.strip()) == 0: continue
      if line.startswith(_repos_header):
        adding_to = _repos
      elif line.startswith(_pairs_header):
        adding_to = _pairs
      elif line.startswith(_changed_paths_header):
        adding_to = _changed_paths
      elif adding_to is not None:
        adding_to.append(line.strip().split(' '))
  # Undo the split(' ') in the case of _changed_paths.
  _changed_paths = [' '.join(path) for path in _changed_paths]

# Save the current set of tracked files; while running, this
# data is kept in _repos and _pairs.
def _save_config():
  global _repos, _pairs, _changed_paths
  with open(_config_path, 'w') as f:
    if _repos:
      f.write('%s:\n' % _repos_header)
      for repo in _repos: f.write('  %s %s\n' % tuple(repo))
    if _pairs:
      f.write('%s:\n' % _pairs_header)
      for pair in _pairs: f.write('  %s %s\n' % tuple(pair))
    if _changed_paths:
      f.write('%s:\n' % _changed_paths_header)
      for path in _changed_paths: f.write('  %s\n' % path)


# input functions
# ===============

# This implementation is from stackoverflow, here:
# http://stackoverflow.com/a/21659588

def _find_getch():
  try:
    import termios
  except ImportError:
    # Non-POSIX. Return msvcrt's (Windows') getch.
    import msvcrt
    return msvcrt.getch

  # POSIX system. Create and return a getch that manipulates the tty.
  import sys, tty
  def _getch():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
      tty.setraw(fd)
      ch = sys.stdin.read(1)
    finally:
      termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    if len(ch) == 1 and ord(ch) == 3: raise KeyboardInterrupt
    return ch

  return _getch

_getch = _find_getch()


# main
# ====

if __name__ ==  "__main__":
  try:
    _handle_args(sys.argv)
  except KeyboardInterrupt:
    print("\nCheerio!")
    exit(1)
  _save_config()
