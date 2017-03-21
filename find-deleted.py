#!/usr/bin/env python3

import collections
import os
import re
import stat
import sys

from typing import Dict, Iterator, List, Set, Tuple

Pid = int

MAP_REGEX = re.compile(r'^[\da-f]+-[\da-f]+ [r-][w-][x-][sp-] '
                       r'[\da-f]+ [\da-f]{2}:[\da-f]{2} '
                       r'(\d+) *(.+)( \(deleted\))?\n$')


def warn(msg: str):
    sys.stderr.write('warning: {}\n'.format(msg))


def is_magic(path: str) -> bool:
    return (path.startswith('[')
            or path.startswith('/[')
            or path.startswith('/anon_hugepage')
            or path.startswith('/dev/')
            or path.startswith('/drm')
            or path.startswith('/memfd')
            or path.startswith('/proc/')
            or path.startswith('/SYSV'))


def is_tmp(path: str) -> bool:
    return (path.startswith('/dev/shm/')
            or path.startswith('/tmp')
            or path.startswith('/run')
            or path.startswith('/var/run'))


class Deleted:
    def __init__(self):
        self.permission_errors = 0  # type: int
        self.pre_filter = lambda path: not is_magic(path) and not is_tmp(path)

    def load_maps(self) -> Iterator[Tuple[Pid, List[str]]]:
        # scandir is not closeable in 3.5
        for entry in os.scandir('/proc'):
            if not entry.is_dir() or not entry.name.isdigit():
                continue
            try:
                with open('/proc/{}/maps'.format(entry.name)) as f:
                    yield (int(entry.name), f.readlines())
            except IOError as e:
                if e is PermissionError:
                    self.permission_errors += 1
                warn("reading details of pid {}: {}".format(entry.name, e))

    def pids_using_files(self) -> Dict[str, Set[Pid]]:
        users = collections.defaultdict(set)  # type: Dict[str, Set[Pid]]
        for (pid, lines) in self.load_maps():
            for line in lines:
                ma = MAP_REGEX.match(line)
                if not ma:
                    warn('parse error for /proc/{}/maps: {}'.format(pid, repr(line)))

                inode = ma.group(1)
                if 0 == inode:
                    continue

                path = ma.group(2)
                if path.endswith(' (deleted)'):
                    path = path[0:-10]

                if not self.pre_filter(path):
                    continue

                try:
                    if os.stat(path)[stat.ST_INO] != inode:
                        users[path].add(pid)
                except FileNotFoundError:
                    users[path].add(pid)
                except IOError as e:
                    if e is PermissionError:
                        self.permission_errors += 1
                    warn("failed to stat {} for {}: {}".format(path, pid, e))

        return users


def main():
    for path in sorted(Deleted().pids_using_files().keys()):
        print(path)


if '__main__' == __name__:
    main()