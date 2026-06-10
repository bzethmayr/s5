import argparse
import os
import sys

from s5 import (
    tokenize,
    Parser,
    Executor,
    TokenizerError,
    SyntaxError_,
    RuntimeError_,
    WORD_MAP,
    sniff,
    encode_tokens,
    decode_tokens,
)


def _resolve_source(path):
    if os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    if ext not in (".s5", ".s5b"):
        alt = path + ".s5"
        if os.path.exists(alt):
            return alt
    return None


def _compile_target_path(source_path):
    base, ext = os.path.splitext(source_path)
    if ext in (".s5", ".s5b"):
        return base + ".s5b"
    return source_path + ".s5b"


def _do_compile(source_path):
    src = _resolve_source(source_path)
    if src is None:
        print(f"s5: source not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    with open(src, "rb") as f:
        first = f.read(1)
        if first and sniff(first[0]):
            print(f"s5: source is already binary: {source_path}", file=sys.stderr)
            sys.exit(1)

    with open(src, encoding="utf-8-sig") as f:
        source = f.read()
    try:
        tokens = list(tokenize(source))
    except TokenizerError as e:
        print(f"tokenizer error: {e}", file=sys.stderr)
        sys.exit(1)

    target = _compile_target_path(src)
    try:
        with open(target, "wb") as f:
            f.write(encode_tokens(tokens))
    except OSError as e:
        print(f"s5: cannot write {target}: {e}", file=sys.stderr)
        sys.exit(1)


def _tokenize_files_auto(paths):
    for path in paths:
        with open(path, "rb") as f:
            data = f.read()
        if data and sniff(data[0]):
            yield from decode_tokens(data)
        else:
            text = data.decode("utf-8-sig")
            for word in text.split():
                token = WORD_MAP.get(word)
                if token is None:
                    raise TokenizerError(f"unknown token: {word!r}")
                yield token


def main():
    arg_parser = argparse.ArgumentParser(
        prog="s5", description="S5 - The Set-Only Language"
    )
    arg_parser.add_argument("--repl", action="store_true", help="force REPL mode")
    arg_parser.add_argument(
        "-c", "--compile", type=str, default=None, metavar="FILE",
        help="compile source to .s5b binary",
    )
    arg_parser.add_argument(
        "--pretty", "-p", action="store_true",
        help="pretty-print parsed source to stdout",
    )
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

    if args.compile is not None:
        _do_compile(args.compile)
        return

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
        token_stream = _tokenize_files_auto(args.files)
    else:
        raw = sys.stdin.buffer.read()
        if raw and sniff(raw[0]):
            try:
                token_stream = list(decode_tokens(raw))
            except TokenizerError as e:
                print(f"tokenizer error: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            try:
                token_stream = tokenize(raw.decode("utf-8-sig"))
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

    if args.pretty:
        from s5.pretty import pretty_print
        print(pretty_print(instructions), end="")
        return

    executor = Executor(buf_sizes=buf_sizes)
    try:
        status = executor.run(instructions)
        if mode == "repl":
            print(status)
    except RuntimeError_ as e:
        print(f"runtime error: {e}", file=sys.stderr)
        sys.exit(1)
