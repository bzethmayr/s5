import argparse
import sys

from s5 import tokenize, tokenize_files, Parser, Executor, TokenizerError, SyntaxError_, RuntimeError_


def main():
    arg_parser = argparse.ArgumentParser(
        prog="s5", description="S5 - The Set-Only Language"
    )
    arg_parser.add_argument("--repl", action="store_true", help="force REPL mode")
    arg_parser.add_argument(
        "--bufsize", "-b", type=int, default=None,
        help="set IO buffer size for all file descriptors"
    )
    arg_parser.add_argument(
        "--bufsize_0", "-b0", type=int, default=None,
        help="set IO buffer size for stdin (fd 0)"
    )
    arg_parser.add_argument(
        "--bufsize_1", "-b1", type=int, default=None,
        help="set IO buffer size for stdout (fd 1)"
    )
    arg_parser.add_argument(
        "--bufsize_2", "-b2", type=int, default=None,
        help="set IO buffer size for stderr (fd 2)"
    )
    arg_parser.add_argument(
        "files", nargs="*", metavar="FILE", help="S5 source files"
    )
    args = arg_parser.parse_args()

    if args.repl:
        mode = "repl"
    elif args.files:
        mode = "file"
    else:
        mode = "repl" if sys.stdin.isatty() else "piped"

    if mode == "repl":
        sys.stderr = sys.stdout

    buf_sizes = {}
    if args.bufsize is not None:
        buf_sizes = {0: args.bufsize, 1: args.bufsize, 2: args.bufsize}
    if args.bufsize_0 is not None:
        buf_sizes[0] = args.bufsize_0
    if args.bufsize_1 is not None:
        buf_sizes[1] = args.bufsize_1
    if args.bufsize_2 is not None:
        buf_sizes[2] = args.bufsize_2

    if args.files:
        token_stream = tokenize_files(args.files)
    else:
        try:
            token_stream = tokenize(sys.stdin.read())
        except TokenizerError as e:
            print(f"tokenizer error: {e}", file=sys.stderr)
            sys.exit(1)

    parser = Parser(token_stream)
    try:
        instructions = parser.parse_program()
    except SyntaxError_ as e:
        print(f"syntax error: {e}", file=sys.stderr)
        sys.exit(1)
    except TokenizerError as e:
        print(f"tokenizer error: {e}", file=sys.stderr)
        sys.exit(1)

    executor = Executor(buf_sizes=buf_sizes)
    try:
        status = executor.run(instructions)
        if mode == "repl":
            print(status)
    except RuntimeError_ as e:
        print(f"runtime error: {e}", file=sys.stderr)
        sys.exit(1)
