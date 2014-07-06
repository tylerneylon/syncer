# syncer

*A tool to help manage evolving code dependencies.*

## Motivation

I'm working simultaneously on a number of C repos that
depend on each other in nontrivial ways, and all of
which are evolving together. At first, I was manually
copying file changes between repos. I built
`syncer` as a way to help automate that process.

With `syncer`, you can edit files in either the main
repo, or in a secondary location that uses a copy of
the original file. These edits become easy to notice
and copy over, or merge by hand with the help of a diff.

## Use

The primary task of `syncer` is to track git repos that
depend on each other; that is, they both have copies of
the same file. If you edit one of the copies of
such a file, then you'll need to re-synchronize
the files.

Here's a brief summary of the available actions:
```
syncer track <repo-name>      # Track the current dir with the given repo name (e.g., a github url).
syncer track <file1> <file2>  # Track the given file pair.
syncer check                  # Check all known repo-name/dir and file/file pairs for differences.
syncer remind                 # Print all paths affected by last run of "syncer check".
```

Let's see an example.
We need a way to name repos. Many people use github,
so I'll use github URLs as the names. In reality, any
uniquely identifying space-free string is ok as a repo name.

### -- `track` action

Suppose you're github user `bob`, and
the file `my_png_reader.h` is shared between the
made-up repos `https://github.com/bob/pnglib.git` and
`https://github.com/bob/photoapp.git`. Begin by
telling `syncer` where these repos live in your
file system:

    cd /path/to/pnglib
    syncer track https://github.com/bob/pnglib.git
    cd /path/to/photoapp
    syncer track https://github.com/bob/photoapp.git

You also need to give `syncer` a way to know which files in a repo are
actually copies of originals from another. Do this by making the 3rd
line of the file end in the name of the home repo. For example, the
top of the file `my_png_reader.h` might look like this:

```
// my_png_reader.h
//
// Home repo: https://github.com/bob/pnglib.git
```

### -- `check` action

Let's say you edit `my_png_reader.h` in your local `photoapp` repo.
Once you're done with your current `photoapp` work, you can run
a check with `syncer` to identify any copied files that are no longer
identical, like so:

    syncer check

This begins an interactive process which will notice that the
copies of `my_png_reader.h` are not identical, and notice which one
is newer. It will show you the diff and give you the option of copying
over the file, or of saving the diff to a file in case you need to
manually make nuanced changes.

### -- `remind` action

Let's say you change many files at once, you run `syncer check` to
perform the appropriate copies, but now you've forgotten what testing
needs to be done to verify that the changes are good. You can run
the following command to remind you of every file that was changed
by the last run of `syncer`:

    syncer remind

### -- custom file pairs

Finally, `syncer` can track repo-agnostic file pairs. For example,
let's say you maintain a cross-platform library in which every platform's
code lives in its own directory. All the header files are thus duplicated,
but should always be identical.
This is a tricky case because both files are in the same repo, so the
above workflow doesn't apply.
Such file pairs can be tracked like so:

    syncer track /my/xpltfrm/win/audio.h /my/xpltfrm/lib/mac/audio.h

Now `syncer check` will notice differences between these two files in
addition to the above-mentioned repo-based checks. One subtle point here
is that file copies between such file/file pairs will preserve the 3rd
line of the copied-over file in order to make the two modes of operation
compatible. That is, file/file pairs may have different 3rd lines and
still be considered equivalent by `syncer`, and such differences are
kept.

## Notes

`syncer` is completely independent of `git` or `github`. It works
with subtrees of your directory structure that it calls "repos," but
they could be any subtree. This is partially a result of the design
goal being an ultra-lightweight, highly transparent tool.

All metadata is kept in the human-friendly `~/.syncer` file, which
you are free to hand edit.

## Installation

`syncer` is a Python 3 script. It assumes Python is
installed at `/usr/local/bin/python3`. If this isn't
true, edit the first line of `syncer.py`.

    $ git clone https://github.com/tylerneylon/syncer.git
    $ sudo ln -s $(cd fh; pwd)/syncer.py /usr/local/bin/syncer

## Alternatives

One alternative to this system is `git` submodules,
which is painful to use. Another alternative would
be a package manager like `npm`, but I have opted to
aim for a lighter-weight solution that I feel makes
life easier for potential users of the libraries I'm
building; C users may not be familiar with `npm`,
and `npm` is more focused on node.js use cases.

`syncer` is a choice that maximizes transparency.
It depends on a single comment line in the source
files you want to be tracked, but otherwise keeps all
of its metadata in a small, human-friendly text
file at `~/.syncer`, which you are free to hand edit.
