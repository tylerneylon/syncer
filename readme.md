# syncer

*A tool to help manage evolving code dependencies.*

This tool is under construction and not yet functional.

## Motivation

I'm working simultaneously on a number of C repos that
depend on each other in nontrivial ways, and all of
which are evolving together. At first, I was manually
copying file changes between repos. I'm building
`syncer` as a way to partially automate that process.

With `syncer`, you can edit files in either the main
repo, or in a secondary location that uses a copy of
the original file. These edits become easy to notice,
copy over, and test.

One alternative to this system is `git` submodules,
which is painful to use. Another alternative would
be a package manager like `npm`, but I have opted to
stick with lighter-weight solutions that I feel make
life easier for potential users of the libraries I'm
building; C users may not be familiar with `npm`,
and `npm` is more focused on node.js use cases.
