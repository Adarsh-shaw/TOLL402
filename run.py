import argparse
import os
import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TollRail402 FastAPI Server")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "3000")))
    parser.add_argument("--reload", action="store_true")
    args, _unknown = parser.parse_known_args()

    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
