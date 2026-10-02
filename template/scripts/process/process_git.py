"""Environment for git readers: judge the objects the push actually carries."""
import os


def git_environment(extra=None):
    return {**(os.environ if extra is None else extra), "GIT_NO_REPLACE_OBJECTS": "1"}
