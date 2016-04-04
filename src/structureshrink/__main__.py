from structureshrink import Shrinker, Volume
import os
from shutil import which
import shlex
import click
import subprocess


def validate_command(ctx, param, value):
    parts = shlex.split(value)
    command = parts[0]

    if os.path.exists(command):
        command = os.path.abspath(command)
    else:
        what = which(command)
        if what is None:
            raise click.BadParameter("%s: command not found" % (command,))
        command = os.path.abspath(what)
    return [command] + parts[1:]


@click.command(
    help="""
structureshrink takes a file and a test command and attempts to produce a
minimal example of every distinct status code it sees out of that command.
(Normally you're only interested in one, but sometimes there are other
interesting behaviours that occur while running it).

Usage is 'structureshrink filename test'. The file will be repeatedly
overwritten with a smaller version of it, with a backup placed in the backup
file. When the program exits the file will be replaced with the smallest
contents that produce the same exit code as was originally present.
""".strip()
)
@click.option("--debug", default=False, is_flag=True, help=(
    "Emit (extremely verbose) debug output while shrinking"
))
@click.option(
    "--quiet", default=False, is_flag=True, help=(
        "Emit no output at all while shrinking"))
@click.option(
    "--backup", default='', help=(
        "Name of the backup file to create. Defaults to adding .bak to the "
        "name of the source file"))
@click.option(
    '--shrinks', default="shrinks",
    type=click.Path(file_okay=False, resolve_path=True))
@click.argument('filename', type=click.Path(
    exists=True, resolve_path=True, dir_okay=False,
))
@click.argument('test', callback=validate_command)
def shrinker(debug, quiet, backup, filename, test, shrinks):
    if debug and quiet:
        raise click.UsageError("Cannot have both debug output and be quiet")

    if not backup:
        backup = filename + os.extsep + "bak"

    try:
        os.mkdir(shrinks)
    except OSError:
        pass

    try:
        os.remove(backup)
    except FileNotFoundError:
        pass

    def classify(string):
        try:
            os.rename(filename, backup)
            with open(filename, 'wb') as o:
                o.write(string)
            try:
                subprocess.check_output(test)
                return 0
            except subprocess.CalledProcessError as e:
                return e.returncode
        finally:
            try:
                os.remove(filename)
            except FileNotFoundError:
                pass
            os.rename(backup, filename)

    with open(filename, 'rb') as o:
        initial = o.read()

    if debug:
        volume = Volume.debug
    elif quiet:
        volume = Volume.quiet
    else:
        volume = Volume.normal

    def name_for_status(status):
        *base, ext = os.path.basename(filename).split(os.extsep, 1)
        base = os.extsep.join(base)
        if base:
            return os.path.extsep.join(((base + "-%r" % (status,), ext)))
        else:
            return ext + "-%r" % (status,)

    def shrink_callback(string, status):
        with open(os.path.join(shrinks, name_for_status(status)), 'wb') as o:
            o.write(string)

    shrinker = Shrinker(
        initial, classify, volume=volume,
        shrink_callback=shrink_callback, printer=click.echo
    )
    initial_label = shrinker.classify(initial)
    # Go through the old shrunk files. This both reintegrates them into our
    # current shrink state so we can resume and also lets us clear out old bad
    # examples.
    for f in os.listdir(shrinks):
        path = os.path.join(shrinks, f)
        if not os.path.isfile(path):
            continue
        with open(path, 'rb') as i:
            contents = i.read()
        if name_for_status(shrinker.classify(contents)) != f:
            shrinker.debug("Clearing out defunct %r file" % (f,))
            os.unlink(path)
    try:
        shrinker.shrink()
    finally:
        os.rename(filename, backup)
        with open(filename, 'wb') as o:
            o.write(shrinker.best[initial_label])


if __name__ == '__main__':
    shrinker()
