set positional-arguments

python := "python3"
export PYTHONPATH := "src"

default:
    @just --list

[positional-arguments]
start *args:
    @{{python}} -m project_herdr --root . start "$@"

[positional-arguments]
doctor *args:
    @{{python}} -m project_herdr --root . doctor "$@"

[positional-arguments]
workspaces *args:
    @{{python}} -m project_herdr --root . workspaces "$@"

[positional-arguments]
status *args:
    @{{python}} -m project_herdr --root . status "$@"

[positional-arguments]
inbox *args:
    @{{python}} -m project_herdr --root . inbox "$@"

[positional-arguments]
notes *args:
    @{{python}} -m project_herdr --root . notes "$@"

[positional-arguments]
context *args:
    @{{python}} -m project_herdr --root . context "$@"

[positional-arguments]
sync *args:
    @{{python}} -m project_herdr --root . sync "$@"

[positional-arguments]
lesson *args:
    @{{python}} -m project_herdr --root . lesson "$@"

[positional-arguments]
dispatch *args:
    @{{python}} -m project_herdr --root . dispatch "$@"

[positional-arguments]
receipt *args:
    @{{python}} -m project_herdr --root . receipt "$@"

test:
    @PYTHONPATH=src {{python}} -m unittest discover -s tests -v

check:
    @{{python}} -m compileall -q src tests
    @just test
