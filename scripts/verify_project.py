import argparse
import compileall
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify TollRail402 Python & Frontend project integrity")
    parser.add_argument("--compile-only", action="store_true")
    args = parser.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    backend_dir = root / "backend"
    contracts_dir = root / "contracts"

    ok = compileall.compile_dir(str(backend_dir), quiet=1)
    ok = compileall.compile_dir(str(contracts_dir), quiet=1) and ok
    ok = compileall.compile_file(str(root / "run.py"), quiet=1) and ok
    api_index = root / "api" / "index.py"
    if api_index.is_file():
        ok = compileall.compile_file(str(api_index), quiet=1) and ok

    if not ok:
        print("Python compilation failed.", file=sys.stderr)
        return 1

    required_frontend = [
        root / "frontend" / "index.html",
        root / "frontend" / "css" / "styles.css",
        root / "frontend" / "js" / "api.js",
        root / "frontend" / "js" / "charts.js",
        root / "frontend" / "js" / "app.js",
    ]
    for path in required_frontend:
        if not path.is_file():
            print(f"Missing required frontend file: {path}", file=sys.stderr)
            return 1

    if not args.compile_only:
        # Verify FastAPI app imports cleanly
        sys.path.insert(0, str(root))
        from backend.app.main import app  # noqa: F401
        print("TollRail402 verification passed: Python modules, FastAPI app, and frontend assets valid.")
    else:
        print("TollRail402 build compilation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
