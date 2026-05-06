"""KAZI CLI — command-line interface for the KAZI platform."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="kazi",
        description="KAZI — AI-powered professional services platform",
    )
    subparsers = parser.add_subparsers(dest="command")

    # kazi init <domain-name>
    init_parser = subparsers.add_parser("init", help="Create a new domain plugin")
    init_parser.add_argument("domain_name", help="Name of the domain to create")

    # kazi serve
    serve_parser = subparsers.add_parser("serve", help="Start the KAZI platform server")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")

    # kazi run <job-type> [--payload JSON]
    run_parser = subparsers.add_parser("run", help="Run a pipeline manually")
    run_parser.add_argument("pipeline", help="Pipeline name to execute")
    run_parser.add_argument("--payload", default="{}", help="JSON payload")

    # kazi domains
    subparsers.add_parser("domains", help="List loaded domain plugins")

    args = parser.parse_args()

    if args.command == "init":
        from cli.init import init_domain
        init_domain(args.domain_name)
    elif args.command == "serve":
        from cli.serve import serve
        serve(host=args.host, port=args.port)
    elif args.command == "run":
        from cli.run import run_pipeline
        run_pipeline(args.pipeline, args.payload)
    elif args.command == "domains":
        from cli.serve import list_domains
        list_domains()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
