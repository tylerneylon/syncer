#!/usr/local/bin/python3
#
# syncer helps manage evolving code dependencies.
#
"""
  syncer track <repo-name>      # Track the current dir with the given repo name (a name may be, e.g., a github url).
  syncer track <file1> <file2>  # Track the given file pair.
  syncer check                  # Check current repo for any incoming out outgoing file changes.
  syncer check --all            # Check all known repo-name/dir and file/file pairs for differences.
  syncer remind                 # Print all paths affected by last run of "syncer check"; useful for testing.
  syncer list                   # Print all file pairs checked for equality.
"""
#
# Metadata is stored in the human-friendly file ~/.syncer
# More details are in readme.md.
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
# Some globals are defined inline close to where they're used.

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
# {home_path: set((copy_path, ignore_line3))}
_diffs_by_home_path = {}

# For collecting the full file-connection graph.
# {full_path: set((home_path, copy_path, ignore_line3))}
_conns_by_path = {}

# For displaying minimally identifying strings for files.
# {basename: set(home_paths)}
_paths_by_basename = {}

# The following are all designed to be the same length when printed.
# They'll be nicely aligned as long as the basename is <= 20 chars.

_basename_width = 20
#                                  1         2
#                 1234567 12345678901234567890 1234567
_horiz_break =   '------------------------------------'
_diff_header = '\nvvvvvvv %20s vvvvvvv'
_diff_footer = '\n^^^^^^^ %20s ^^^^^^^'
#                 1234567      1234567

# The string used in .syncer to denote recently changed paths (_changed_paths).
_changed_paths_header = 'recently changed paths'

# This is a list of recently changed paths, where key 0 is from the most recent syncer check.
# _changed_paths[0-9] = [changed_path]
_changed_paths = {}

# Header and dictionary to track cached info.
# _cached_info_by_path[path] = {home_info: [home_repo, home_subdir], times: (mtime, ctime)}
_cached_info_header = 'cached info (home_repo, home_subdir, file times)'
_cached_info_by_path = {}

# This is used by the 'syncer check' command to indicate when we're filtering to a local repo, and
# to indicate the path of that local repo.
_do_use_local_repo = False
_local_repo_path   = None

# _copy_dirs_by_home[home_name][home_subpath][copy_path] = <copy_info>
#     <copy_info> = {tracking: <bool>, home_path: <str>, excluded: <set>}
# The excluded set contains subpaths s so that copy_path/s is an excluded dir or file.
_copy_dirs_by_home = {}
# _copy_info_by_copy_path[copy_path] = <copy_info>
_copy_info_by_copy_path = {}


# top-level functions
# ===================

def _init():
  global _horiz_break, _diff_header, _diff_footer
  rows, columns = os.popen('stty size', 'r').read().split()
  pad_len = min(int(columns) - len(_horiz_break) - 2, 100)  # 100 is the max separator width.
  if pad_len <= 0: return
  _horiz_break += '-' * pad_len
  _diff_header += 'v' * pad_len
  _diff_footer += '^' * pad_len

def _handle_args(args):
  my_name = sys.argv[0].split('/')[-1]
  parser = OptionParser(usage=__doc__)
  parser.add_option('--all', action='store_true', dest='do_check_all', default=False,
                    help='for check action, globally checks all tracked files')
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
    _check(args[2:], options)
  elif action == 'remind':
    _load_config()
    _remind(args[2:])
  elif action == 'list':
    _load_config()
    _list(args[2:])
  else:
    print('Unrecognized action: %s.' % action)
    parser.print_help()
    exit(2)


# primary action functions
# ========================

def _track(action_args):
  global _repos, _pairs
  if len(action_args) < 1 or len(action_args) > 2:
    print('Expected one or two parameters as items to track.')
    exit(2)
  if len(action_args) == 1:  # Track a repo/path pair.
    # Make sure the repo name is new.
    repo_name = action_args[0]
    repo_map  = dict(_repos)
    if repo_name in repo_map:
      print('Error: repo %s is already tracked at %s' % (repo_name, repo_map[repo_name]))
      exit(1)
    _repos.append([action_args[0], os.getcwd()])
    print('Started tracking the repo and dir:\n%s\n%s' % tuple(_repos[-1]))
  if len(action_args) == 2:  # Track a file/file pair.
    for path in action_args:
      if not os.path.isfile(path):
        print('Error: %s is not a file.' % path)
        exit(1)
    # Make sure we have absolute paths saved.
    paths = [os.path.abspath(path) for path in action_args]
    if os.path.basename(paths[0]) != os.path.basename(paths[1]):
      print('Error: file names must match to track them together.')
      exit(1)
    _pairs.append(paths)
    print('Started tracking the files:\n%s\n%s' % tuple(_pairs[-1]))

def _check(action_args, options):
  global _repos, _pairs, _changed_paths, _do_use_local_repo
  if len(action_args) > 0:
    print('Unexpected arguments after "check": %s' % ' '.join(action_args))
    exit(2)
  _setup_local_repo_globals(options)
  print('Checking for differences.')
  repo_file_pairs = _find_repo_file_pairs()
  for home_file_path, copy_path in repo_file_pairs:
    _compare_full_paths(home_file_path, copy_path)
  for path1, path2 in _pairs:
    _compare_full_paths(path1, path2, ignore_line3=True)
  if False: _debug_show_known_diffs()  # Turn this on if useful for debugging.
  home_paths = list(_diffs_by_home_path.keys())
  _show_diffs_in_order(home_paths)
  path_index = _ask_user_for_diff_index(home_paths)
  # If we get this far, then we're committed to the check and set up a new changed paths list.
  _add_new_changed_paths_list()
  chosen_paths = [home_paths[path_index]] if path_index != -1 else home_paths
  # Filter out diffs the user has chosen to ignore for now.
  # Transitive closure may add more home paths, so we don't consult chosen_paths after this.
  for home_path in list(_diffs_by_home_path):
    if home_path not in chosen_paths: del _diffs_by_home_path[home_path]
  _show_and_let_user_act_on_diffs()
  if _there_are_changed_paths(): _show_test_reminder()

def _remind(action_args):
  global _changed_paths
  if len(action_args) > 0:
    print('Warning: ignoring the extra arguments %s' % ' '.join(action_args))
  _show_test_reminder()

def _list(action_args):
  global _pairs
  if len(action_args) > 0:
    print('Warning: ignoring the extra arguments %s' % ' '.join(action_args))
  repo_file_pairs = _find_repo_file_pairs()
  for path1, path2 in repo_file_pairs: print(path1, path2)
  for path1, path2 in _pairs:          print(path1, path2)


# internal functions
# ==================

def _setup_local_repo_globals(options):
  global _do_use_local_repo, _local_repo_path
  if options.do_check_all: return  # _do_use_local_repo is False by default.
  # Find the current local repo.
  cwd = os.getcwd()
  for _, repo_path in _repos:
    if cwd.startswith(repo_path):
      _do_use_local_repo = True
      _local_repo_path   = repo_path
      return
  # If we get here, then we aren't in any repo.
  print('Error: not in a known repo; use "syncer check --all" to check all possible connections.')
  exit(1)

def _find_repo_file_pairs():
  global _repos
  repo_file_pairs = []
  for name, root in _repos:
    for path, dirs, files in os.walk(root):
      dirs[:] = [d for d in dirs if not _should_skip_dir(d)]
      for filename in files:
        filepath = os.path.join(path, filename)
        home_info = _check_for_home_info(filepath)
        if home_info is None:    continue
        if home_info[0] == name: continue
        home_path, home_subpath = _find_home_path(home_info, filepath)
        if home_path is None: continue  # An error is already printed by _find_home_path.
        repo_file_pairs.append([home_path, filepath])

        # Update directory-tracking data.
        copy_paths_by_home_subpath = _copy_dirs_by_home.setdefault(home_info[0], {})
        copy_info_by_copy_path = copy_paths_by_home_subpath.setdefault(home_subpath, {})
        filedir = os.path.dirname(filepath)
        home_dir_path = os.path.dirname(home_path)
        default_copy_info = {'tracking': True, 'home_path': home_dir_path}
        # It's important that same dict is used twice here; if we edit it later from either source,
        # the data changes in both structures - that indexed by home, and that indexed by copy.
        copy_info_by_copy_path.setdefault(filedir, default_copy_info)
        _copy_info_by_copy_path.setdefault(filedir, default_copy_info)
  return repo_file_pairs

def _debug_show_known_diffs():
  print('Comparisons are done in _check.')
  print('_diffs_by_home_path:')
  pprint.pprint(_diffs_by_home_path)
  print('_paths_by_basename:')
  pprint.pprint(_paths_by_basename)

def _add_new_changed_paths_list():
  global _changed_paths
  for i in range(9, 0, -1):
    if i - 1 in _changed_paths: _changed_paths[i] = _changed_paths[i - 1]
  _changed_paths[0] = []

# Returns True iff union(_changed_paths[how_recent]) is nonempty;
# by default this focuses on just the single most recent changed paths list.
def _there_are_changed_paths(how_recent=[0]):
  global _changed_paths
  return any([_changed_paths[i] for i in how_recent if i in _changed_paths])

# Prints out recent changed paths based on the how_recent list;
# prints out a message saying there are no changed paths if there are none.
def _show_test_reminder(how_recent=[0]):
  global _changed_paths
  if _there_are_changed_paths(how_recent):
    print('The following paths have been changed; testing is recommended!')
    for i in how_recent:
      for path in _changed_paths[i]:
        print(path)
  else:
    num_runs = len(how_recent)
    quantity_strs = ('', '') if num_runs == 1 else (str(num_runs) + ' ', 's')
    print('No files changed during last %srun%s of syncer check.' % quantity_strs)

# Shows something like the following for each given home_path:
#   [1] <basename> [in repo name if not unique]
#         uniq_subpath:basename > uniq_subpath:basename
def _show_diffs_in_order(home_paths):
  if len(home_paths) == 0:
    print('No differences found.')
    print('All good!')
    _save_config()
    exit(0)
  print('Differences found:')
  # Find column widths.
  uniq1_max, uniq2_max, base_max = 0, 0, 0
  for home_path in home_paths:
    base = os.path.basename(home_path)
    base_max = max(len(base), base_max)
    for diff_path, ignore_line3 in _diffs_by_home_path[home_path]:
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
    for diff_path, ignore_line3 in _diffs_by_home_path[home_path]:
      uniq1, uniq2 = _get_uniq_subpaths(home_path, diff_path)
      cmp_str = _compare_paths_by_time(home_path, diff_path).center(13)
      print(fmt % (uniq1, base, cmp_str, uniq2, base))
  print('')  # End-of-section newline.

# Removes the common prefix and suffix from the given pair.
# Expects the paths to be unequal, but the file names to match.
# In other words, given strings of the form ABC, ADC, this returns B, D.
def _get_uniq_subpaths(path1, path2):
  dirs = [path1.split(os.sep), path2.split(os.sep)]
  pre_idx, post_idx = 0, -1
  while dirs[0][pre_idx]  == dirs[1][pre_idx] : pre_idx  += 1
  while dirs[0][post_idx] == dirs[1][post_idx]: post_idx -= 1
  uniqs = [d[pre_idx:post_idx + 1] for d in dirs]
  for i in range(len(uniqs)):
    # Handle the special case that paths are of the form [ABC, AC].
    if len(uniqs[i]) == 0: uniqs[i] = dirs[i][pre_idx:post_idx + 2]
    uniqs[i] = os.path.join(*uniqs[i])
  return tuple(uniqs)

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
  fmt = 'Actions: [%s] handle a file; handle [a]ll files; [q]uit.'
  print(fmt % one_file_choices)
  print('What would you like to do?')
  c = _wait_for_key_in_list(ok_chars)
  # We return either a 0-based index of the path, or -1 for the 'all' choice.
  return ok_chars.index(c) - 1

def _show_and_let_user_act_on_diffs():
  global _do_use_local_repo
  # Turn off local filtering to allow _compare_full_paths to follow transitive diffs.
  _do_use_local_repo = False
  while len(_diffs_by_home_path) > 0:
    home_paths = sorted(_diffs_by_home_path.keys())
    home_path = home_paths[0]
    copy_path, ignore_line3 = _diffs_by_home_path[home_path].pop()
    _show_and_let_user_act_on_diff(home_path, copy_path, ignore_line3)
    if len(_diffs_by_home_path[home_path]) == 0:
      del _diffs_by_home_path[home_path]

# These globals are only used by the next function, so they make more sense here.
# They're used to determine when we should display a header/footer for groupings based on filename.
_last_home_path = None
_last_base      = None

def _show_and_let_user_act_on_diff(home_path, copy_path, ignore_line3):
  global _last_home_path, _last_base

  # Print a footer and/or header as appropriate.
  base = os.path.basename(home_path)
  if _last_home_path != home_path:
    if _last_home_path is not None:
      print(_diff_footer % ('end ' + _last_base).center(_basename_width))
      print('')  # Print a blank line.
    print(_diff_header % ('start ' + base).center(_basename_width))

  # Determine which file version is older.
  home_is_older = (os.path.getmtime(home_path) < os.path.getmtime(copy_path))
  oldpath, newpath = (home_path, copy_path) if home_is_older else (copy_path, home_path)

  # Build and print diff strings.
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
  no_newline_str = ' ^^^^^^^ (no ending newline)'
  for line in diff:
    end = '' if line.endswith('\n') else ('\n' + no_newline_str + '\n')
    show_and_save(line, end=end)

  # Accept user action and cleanup.
  _let_user_act_on_diff(newpath, oldpath, ''.join(diff_strs), ignore_line3)
  _last_home_path = home_path
  _last_base      = base

def _let_user_act_on_diff(newpath, oldpath, diff, ignore_line3):
  global _changed_paths
  print(_horiz_break)
  new_short, old_short = _short_names(newpath, oldpath)
  fmt  = 'Actions:\n'
  fmt += '  [c]opy %s to %s;\n'
  fmt += '  [r]everse copy %s to %s;\n'
  fmt += '  [s]kip this file; [w]rite diff file and quit; [q]uit.'
  print(fmt % (new_short, old_short, old_short, new_short))
  print('What would you like to do?')
  c = _wait_for_key_in_list(list('crws'))
  if c == 'c':
    _copy_src_to_dst_and_update_metadata(newpath, oldpath, preserve_line3=ignore_line3)
    print('Copied')
  if c == 'r':
    _copy_src_to_dst_and_update_metadata(oldpath, newpath, preserve_line3=ignore_line3)
    print('Reverse copied')
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
    if _there_are_changed_paths():
      print('')  # Visually distinguish the test reminder below.
      _show_test_reminder()
    _save_config()
    exit(0)
  if c == 's':
    print('Skipped!')

# Wait for a key in the given set.
# 'q' is added if not present, and acted on immmediately as a quit option.
# Otherwise the selected key is returned.
def _wait_for_key_in_list(ok_chars):
  if 'q' not in ok_chars: ok_chars.append('q')
  c = _getch()
  while c not in ok_chars:
    print('Please press one of the keys [' + ''.join(ok_chars) + ']')
    c = _getch()
  if c == 'q':
    _save_config()
    exit(0)
  return c

def _copy_src_to_dst(src, dst, preserve_line3=False):
  global _changed_paths
  if not preserve_line3:
    shutil.copy2(src, dst)
    return
  # Preserve line 3.
  src_lines = _file_lines(src)
  dst_lines = _file_lines(dst)
  src_lines[2] = dst_lines[2]
  with open(dst, 'w') as f:
    f.write(''.join(src_lines))

def _copy_src_to_dst_and_update_metadata(src, dst, preserve_line3=False):
  _copy_src_to_dst(src, dst, preserve_line3)
  _changed_paths[0].append(dst)
  # Check for other files affected by this change.
  for home_path, copy_path, ignore_line3 in _conns_by_path[dst]:
    _compare_full_paths(home_path, copy_path, ignore_line3)

def _file_lines(filename):
  with open(filename, 'r') as f:
    return f.readlines()

# Expects paths to be different but to have the same basename.
def _short_names(path1, path2):
  uniq1, uniq2 = _get_uniq_subpaths(path1, path2)
  base = os.path.basename(path1)
  return uniq1 + ':' + base, uniq2 + ':' + base

# A regex that matches line 3 and extracts the home info.
# This is lazily setup from _get_homeinfo_regex.
_homeinfo_regex = None

def _get_homeinfo_regex():
  global _homeinfo_regex
  if _homeinfo_regex is None:
    or_list = '|'.join([name for name, root in _repos])
    regex_str = r'(%s)(?: in (\S+))?$' % or_list
    _homeinfo_regex = re.compile(regex_str)
  return _homeinfo_regex

# Checks for a recognized repo name on line 3.
# Returns [home_repo, home_subdir] if found; home_subdir may be None;
# return None if no repo name is recognized.
def _check_for_home_info(filepath):
  global _cached_info_by_path, _repos
  st = os.stat(filepath)
  st_times = (st.st_ctime, st.st_mtime)
  if filepath in _cached_info_by_path:
    info = _cached_info_by_path[filepath]
    if st_times == info['times']:
      home_info = info['home_info']
      return home_info if home_info[0] else None
  # If we get here, then the cache didn't have the info; need to populate it.
  info = {'home_info': [None, None], 'times': st_times}
  _cached_info_by_path[filepath] = info
  with open(filepath, 'r') as f:
    try:
      file_start = f.read(4096)
    except:  # This can be caused by trying to read a binary file as if it were utf-8.
      return None
    start_lines = file_start.split('\n')
    if len(start_lines) < 3: return None
    line3 = start_lines[2]
    regex = _get_homeinfo_regex()
    m = regex.search(line3)
    if m is None: return None
    home_info = [m.group(1), m.group(2)]
    info['home_info'] = home_info
    return home_info

# A cache to avoid redundant os.walk calls.
# _subpaths_of_root[root][base] = [(path, subpath)]
# This is used in _get_all_subpaths.
_subpaths_of_root = {}

def _should_skip_dir(dirname):
  return dirname == '.git'

def _get_all_subpaths(root):
  global _subpaths_of_root
  if root in _subpaths_of_root: return _subpaths_of_root[root]
  subpaths = {}
  for path, dirs, files in os.walk(root):
    dirs = [d for d in dirs if not _should_skip_dir(d)]
    subpath = path[len(root) + 1:]
    for f in files: subpaths.setdefault(f, []).append((path + os.sep + f, subpath))
  _subpaths_of_root[root] = subpaths
  return subpaths

# _known_home_paths[(home_repo, home_subdir, base)] = home_path
# This is used in _find_home_path.
_known_home_paths = {}

# Takes a [home_repo, home_subdir] pair as returned from _check_for_home_info,
# and resolves a file path for the home version. Emits a warning if
# multiple files match the given home_info.
def _find_home_path(home_info, filepath):
  global _repos, _known_home_paths
  for name, root in _repos:
    if home_info[0] == name:
      home_root = root
      break
  base = os.path.basename(filepath)
  key = (home_info[0], home_info[1], base)
  if key in _known_home_paths: return _known_home_paths[key]
  if home_info[1]:
    home_path = os.path.join(home_root, home_info[1], base)
    if not os.path.isfile(home_path):
      print('Error: %s pointed to home version %s, but it doesn\'t exist.' % (filepath, home_path))
      return None
    val = (home_path, home_info[1])
    _known_home_paths[key] = val
    return val
  # Handle the case that no subdir was given; we must walk the dir to find it.
  subpaths = _get_all_subpaths(home_root)
  if base not in subpaths:
    print('Error: no home path found for %s' % filepath)
    return None
  basepaths = subpaths[base]
  if len(basepaths) > 1:
    print('Warning: found multiple home paths for %s, listed below:' % filepath)
    for path in basepaths: print('    %s' % path)
  _known_home_paths[key] = basepaths[0]
  return basepaths[0]  # This is a (path, subpath) tuple.

# Internally compares the given files; "internally" means we don't show the user yet.
# The results are stored in _diffs_by_home_path and _paths_by_basename.
# If one path is a home_path, this expects that as the first argument.
def _compare_full_paths(path1, path2, ignore_line3=False):
  # Turn this on if useful for debugging.
  if False: print('_compare_full_paths(%s, %s)' % (path0, path2))
  _conns_by_path.setdefault(path1, set()).add((path1, path2, ignore_line3))
  _conns_by_path.setdefault(path2, set()).add((path1, path2, ignore_line3))
  if _do_use_local_repo:
    # Since we're focused on the local repo, skip over pairs that don't affect it.
    if (not path1.startswith(_local_repo_path) and
        not path2.startswith(_local_repo_path)):
      return
  if _files_are_same(path1, path2, ignore_line3): return
  _diffs_by_home_path.setdefault(path1, set()).add((path2, ignore_line3))
  base = os.path.basename(path1)
  _paths_by_basename.setdefault(base, set()).add(path1)

def _files_are_same(path1, path2, ignore_line3=False):
  if not ignore_line3: return filecmp.cmp(path1, path2)
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


# config file functions
# =====================

def _load_file_connections():
  global _repos, _pairs
  file_path = os.path.join(_config_path, 'file_connections')
  if not os.path.isfile(file_path): return
  with open(file_path, 'r') as f:
    for line in f:
      if len(line.strip()) == 0: continue
      if line.startswith(_repos_header):
        adding_to = _repos
      elif line.startswith(_pairs_header):
        adding_to = _pairs
      elif adding_to is not None:
        adding_to.append(line.strip().split(' '))

def _load_changed_paths():
  global _changed_paths
  file_path = os.path.join(_config_path, 'changed_paths')
  if not os.path.isfile(file_path): return
  with open(file_path, 'r') as f:
    for line in f:
      if len(line.strip()) == 0: continue
      if line.startswith(_changed_paths_header):
        adding_to = _changed_paths
      elif adding_to == _changed_paths:
        m = re.match(r'  (\d):', line)
        if m: changed_paths_key = int(m.group(1))
        else: _changed_paths.setdefault(changed_paths_key, []).append(line.strip())

def _load_cached_info():
  global _cached_info_by_path
  file_path = os.path.join(_config_path, 'cached_info')
  if not os.path.isfile(file_path): return
  with open(file_path, 'r') as f:
    adding_to = None
    for line in f:
      if len(line.strip()) == 0: continue
      if line.startswith(_cached_info_header):
        adding_to = _cached_info_by_path
      elif adding_to == _cached_info_by_path:
        m = re.match(r'  \S.*', line)  # All non-paths start with a space.
        line = line.strip()
        if m:
          path = m.group(0).lstrip()
          key = 'home_info'
        else:
          info = _cached_info_by_path.setdefault(path, {})
          if key == 'home_info':
            # The [1:] here ignores the initial : character on non-None string values.
            info.setdefault(key, []).append(line[1:] if line != 'None' else None)
            if len(info[key]) == 2: key = 'times'
          else:
            info[key] = tuple([int(t) for t in line.split(' ')])

def _load_config():
  if not os.path.isdir(_config_path): return  # First run; empty lists are ok.
  adding_to = None
  changed_paths_key = 0
  _load_file_connections()
  _load_changed_paths()
  _load_cached_info()

def _save_file_connections():
  file_path = os.path.join(_config_path, 'file_connections')
  with open(file_path, 'w') as f:
    if _repos:
      f.write('%s:\n' % _repos_header)
      for repo in _repos: f.write('  %s %s\n' % tuple(repo))
    if _pairs:
      f.write('%s:\n' % _pairs_header)
      for pair in _pairs: f.write('  %s %s\n' % tuple(pair))

def _save_changed_paths():
  file_path = os.path.join(_config_path, 'changed_paths')
  with open(file_path, 'w') as f:
    if _changed_paths:
      f.write('%s:\n' % _changed_paths_header)
      for key in _changed_paths.keys():
        f.write('  %d:\n' % key)
        for path in _changed_paths[key]:
          f.write('    %s\n' % path)

def _save_cached_info():
  global _cached_info_by_path
  file_path = os.path.join(_config_path, 'cached_info')
  with open(file_path, 'w') as f:
    f.write(_cached_info_header + '\n')
    for path, info in _cached_info_by_path.items():
      f.write('  %s\n' % path)
      for i in range(2):
        item = info['home_info'][i]
        f.write('    %s\n' % ((':' + item) if item else 'None'))
      f.write('    %d %d\n' % info['times'])

# Save the current config data. This is the data kept in
# _repos, _pairs, and _changed_paths.
def _save_config():
  if not os.path.isdir(_config_path): os.mkdir(_config_path)
  _save_file_connections()
  _save_changed_paths()
  _save_cached_info()


# input functions
# ===============

# This implementation is a modification of one from stackoverflow, here:
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
    print(ch)
    return ch

  return _getch

_getch = _find_getch()


# main
# ====

if __name__ ==  "__main__":
  _init()
  try:
    _handle_args(sys.argv)
  except KeyboardInterrupt:
    print("\nCheerio!")
    exit(1)
  _save_config()
